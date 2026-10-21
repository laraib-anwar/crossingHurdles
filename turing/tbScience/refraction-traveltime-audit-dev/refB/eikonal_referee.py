#!/usr/bin/env python
"""Finite-difference eikonal referee for the refraction-traveltime-audit task.

Solves |grad T| = 1/v(z) on a uniform (x, z) grid for a point source at the
surface corner (x, z) = (0, 0) of a flat layered model (TRAVELTIME_SPEC.md,
section 1), by Gauss-Seidel fast sweeping vectorised along grid
anti-diagonals.  First a first-order Godunov solution is converged, then a
second-order (one-sided three-point) solution is iterated from it.

Interfaces are aligned with grid rows.  An interface row carries three
slownesses: the upper-side limit (used when the z-upwind neighbour is above),
the lower-side limit (z-upwind neighbour below) and their minimum (pure
horizontal update along the interface, which carries head waves and waves
creeping along an interface).  Second-order z stencils never straddle an
interface.  Nodes within a fixed physical radius R of the source are frozen
at the exact layer-0 traveltime (arccosh formula), which removes the
point-source singularity.

The surface row T(x, 0) is the eikonal first arrival T_1(X).  Each model is
solved on 3 or 4 nested grids (h, h/2, h/4[, h/8]); Richardson extrapolation
gives the extrapolated values and error estimates.  Kinks of T_1 (crossovers,
slope drops) and C1 transitions (curvature changes with continuous slope,
e.g. a curved arrival passing into a straight head or creeping wave) are
located by fitting polynomial pieces on each side and intersecting them.

Usage:
  python eikonal_referee.py --model dev_01.json --outdir out/dev_01 [--budget 6e6]
"""
import argparse
import json
import math
import os
import time

import numpy as np

INF = np.inf


# ----------------------------------------------------------------------------
# model
# ----------------------------------------------------------------------------

def load_model(path):
    with open(path) as f:
        m = json.load(f)
    layers = m["layers"]
    n = len(layers)
    tops = [0.0]
    for k in range(n - 1):
        tops.append(tops[-1] + float(layers[k]["thickness_km"]))
    a = np.array([float(L["v_top_km_s"]) for L in layers])
    b = np.array([float(L["gradient_per_s"]) for L in layers])
    return {
        "id": m["model_id"], "n": n, "tops": np.array(tops), "a": a, "b": b,
        "thick": [L["thickness_km"] for L in layers],
        "xmax": float(m["x_max_km"]), "offsets": [float(x) for x in m["offsets_km"]],
    }


def velocity(model, z, side):
    """v at depth z; side='below' (z+) or 'above' (z-)."""
    tops = model["tops"]
    if side == "below":
        k = int(np.searchsorted(tops, z + 1e-12, side="right") - 1)
    else:
        k = int(np.searchsorted(tops, z - 1e-12, side="right") - 1)
        k = max(k, 0)
    return model["a"][k] + model["b"][k] * (z - tops[k])


def exact_layer0(model, x, z):
    """Exact traveltime in the (extended) linear layer 0 from (0,0)."""
    a0, b0 = model["a"][0], model["b"][0]
    r2 = x * x + z * z
    if b0 == 0.0:
        return np.sqrt(r2) / a0
    v = a0 + b0 * z
    return np.arccosh(1.0 + b0 * b0 * r2 / (2.0 * a0 * v)) / abs(b0)


def tau_vertical(model, z):
    """Vertical one-way time from the surface to depth z inside layer 0."""
    a0, b0 = model["a"][0], model["b"][0]
    if b0 == 0.0:
        return z / a0
    return np.log((a0 + b0 * z) / a0) / b0


def exact_region(model, X, Z):
    """Nodes of layer 0 (z < h0) where the exact layer-0 time is provably the
    first arrival:
      (1) the minimum-time arc of the linear medium from (0,0) to (x,z) stays
          inside layer 0 (for b0 > 0 its deepest point is above h0);
      (2) T_direct <= tau_v(0,h0) + tau_v(z,h0), a strict lower bound for every
          path that touches depth h0 (a path must cross each depth between 0
          and h0 on the way down and between z and h0 on the way back, paying
          at least the vertical slowness integral)."""
    a0, b0 = model["a"][0], model["b"][0]
    h0 = model["tops"][1]
    inside = Z < h0 - 1e-12
    T = exact_layer0(model, X, Z)
    bound = tau_vertical(model, h0) + (tau_vertical(model, h0) - tau_vertical(model, np.minimum(Z, h0)))
    ok = inside & (T <= bound * (1 - 1e-12))
    if b0 > 0:
        c = a0 / b0                     # centre of ray circles at height c above surface
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (X * X + (Z + c) ** 2 - c * c) / (2 * X)
        rho = np.sqrt(xc * xc + c * c)
        zdeep = np.where((xc > 0) & (xc < X), rho - c, Z)    # deepest point of the arc
        zdeep = np.where(X == 0, Z, zdeep)
        ok &= zdeep < h0 - 1e-12
    return ok


# ----------------------------------------------------------------------------
# grid set-up
# ----------------------------------------------------------------------------

def gcd_km(values, unit=1e-6):
    g = 0
    for v in values:
        iv = int(round(v / unit))
        if abs(iv * unit - v) > 1e-9:
            raise ValueError("value %r not representable on %g km lattice" % (v, unit))
        g = math.gcd(g, iv)
    return g * unit


class Grid:
    def __init__(self, model, h, zmax, xmax_grid, R):
        self.h = h
        self.nx = int(round(xmax_grid / h)) + 1
        self.nz = int(round(zmax / h)) + 1
        nx, nz = self.nx, self.nz
        self.NX, self.NZ = nx + 4, nz + 4
        zs = np.arange(nz) * h
        tops = model["tops"]
        iface = np.zeros(nz, bool)
        for zt in tops[1:]:
            i = int(round(zt / h))
            if abs(i * h - zt) > 1e-9 * max(1.0, zt):
                raise ValueError("interface %.6f not on grid h=%g" % (zt, h))
            if i < nz:
                iface[i] = True
        s_up = np.empty(nz)
        s_dn = np.empty(nz)
        for i, z in enumerate(zs):
            vd = velocity(model, z, "below")
            vu = velocity(model, z, "above") if i > 0 else vd
            s_dn[i] = 1.0 / vd
            s_up[i] = 1.0 / vu
        s_x = np.minimum(s_up, s_dn)
        # padded row arrays (2 ghost rows each side)
        def pad(arr, fill):
            out = np.full(nz + 4, fill, dtype=arr.dtype)
            out[2:nz + 2] = arr
            return out
        self.s_up = pad(s_up, 1.0)
        self.s_dn = pad(s_dn, 1.0)
        self.s_x = pad(s_x, 1.0)
        # second order allowed from above at row i iff row i-1 is not an
        # interface (row i-2 then lies in the closure of row i's layer)
        a2up = np.zeros(nz, bool)
        a2dn = np.zeros(nz, bool)
        for i in range(nz):
            a2up[i] = (i >= 2) and (not iface[i - 1])
            a2dn[i] = (i + 2 <= nz - 1) and (not iface[i + 1])
        self.a2up = pad(a2up, False)
        self.a2dn = pad(a2dn, False)
        self.iface = iface
        # source disk
        T = np.full((self.NZ, self.NX), INF)
        X, Z = np.meshgrid(np.arange(nx) * h, zs)
        if R == "exact-region":
            disk = exact_region(model, X, Z)
        else:
            disk = (X * X + Z * Z) <= R * R * (1 + 1e-12)
        T[2:nz + 2, 2:nx + 2][disk] = exact_layer0(model, X[disk], Z[disk])
        frozen = np.zeros((self.NZ, self.NX), bool)
        frozen[2:nz + 2, 2:nx + 2] = disk
        self.T = T
        self.frozen = frozen
        self.ndisk = int(disk.sum())


# ----------------------------------------------------------------------------
# sweeping kernel
# ----------------------------------------------------------------------------

def _update(T0, L1, L2, R1, R2, U1, U2, D1, D2, s_up, s_dn, s_x, a2up, a2dn, h, order2):
    with np.errstate(invalid="ignore"):
        return _update_core(L1, L2, R1, R2, U1, U2, D1, D2, s_up, s_dn, s_x, a2up, a2dn, h, order2)


def _update_core(L1, L2, R1, R2, U1, U2, D1, D2, s_up, s_dn, s_x, a2up, a2dn, h, order2):
    ih = 1.0 / h
    useL = L1 <= R1
    X1 = np.where(useL, L1, R1)
    if order2:
        X2 = np.where(useL, L2, R2)
        okx = np.isfinite(X2) & (X2 <= X1)
        ax = np.where(okx, (4.0 * X1 - X2) / 3.0, X1)
        alx = np.where(okx, 1.5 * ih, ih)
    else:
        ax = X1
        alx = np.full_like(X1, ih)
    best = ax + s_x / alx                      # 1-D horizontal update
    wx = alx * alx
    for Z1, Z2, a2, s in ((U1, U2, a2up, s_up), (D1, D2, a2dn, s_dn)):
        if order2:
            okz = a2 & np.isfinite(Z2) & (Z2 <= Z1)
            az = np.where(okz, (4.0 * Z1 - Z2) / 3.0, Z1)
            alz = np.where(okz, 1.5 * ih, ih)
        else:
            az = Z1
            alz = np.full_like(Z1, ih)
        np.minimum(best, az + s / alz, out=best)   # 1-D vertical update
        wz = alz * alz
        wsum = wx + wz
        disc = wsum * s * s - wx * wz * (ax - az) ** 2
        t2 = (wx * ax + wz * az + np.sqrt(np.maximum(disc, 0.0))) / wsum
        ok = (disc >= 0.0) & (t2 >= ax) & (t2 >= az)
        np.minimum(best, np.where(ok, t2, INF), out=best)
    return best


def sweep(G, sx, sz, order2):
    """One Gauss-Seidel sweep in direction (sx, sz); returns max |change|."""
    T = G.T.ravel()
    FR = G.frozen.ravel()
    NX = G.NX
    nx, nz, h = G.nx, G.nz, G.h
    maxd = 0.0
    if sx == sz:
        step = NX - 1
        ds = range(4, nz + nx + 3)
        if sx < 0:
            ds = reversed(ds)
        for d in ds:
            i0 = max(2, d - (nx + 1))
            i1 = min(nz + 1, d - 2)
            if i1 < i0:
                continue
            st = i0 * NX + (d - i0)
            maxd = max(maxd, _diag(G, T, FR, st, step, i0, i1, h, order2))
    else:
        step = NX + 1
        cs = range(2 - (nz + 1), (nx + 1) - 2 + 1)
        if sx < 0:      # (x-, z+): descending c
            cs = reversed(cs)
        for c in cs:
            i0 = max(2, 2 - c)
            i1 = min(nz + 1, nx + 1 - c)
            if i1 < i0:
                continue
            st = i0 * (NX + 1) + c
            maxd = max(maxd, _diag(G, T, FR, st, step, i0, i1, h, order2))
    return maxd


def _diag(G, T, FR, st, step, i0, i1, h, order2):
    n = i1 - i0 + 1
    en = st + (n - 1) * step + 1
    NX = G.NX

    def v(off):
        return T[st + off:en + off:step]
    cur = v(0)
    new = _update(cur, v(-1), v(-2), v(1), v(2), v(-NX), v(-2 * NX), v(NX), v(2 * NX),
                  G.s_up[i0:i1 + 1], G.s_dn[i0:i1 + 1], G.s_x[i0:i1 + 1],
                  G.a2up[i0:i1 + 1], G.a2dn[i0:i1 + 1], h, order2)
    fr = FR[st:en:step]
    if order2:
        new = np.where(np.isfinite(new), new, cur)
    else:
        new = np.minimum(new, cur)
    new = np.where(fr, cur, new)
    with np.errstate(invalid="ignore"):
        dd = np.abs(new - cur)
    dd = dd[np.isfinite(dd)]
    m = float(dd.max()) if dd.size else (0.0 if np.all(np.isfinite(cur)) else INF)
    if not np.all(np.isfinite(cur)) and np.any(np.isfinite(new) & ~np.isfinite(cur)):
        m = INF
    T[st:en:step] = new
    return m


def solve(G, tol=1e-12, max_iter=80, log=None):
    """Converge the first-order pass, then the second-order pass.  Iterations use
    the two x+ sweeps (T is non-decreasing in x); at apparent convergence a full
    four-direction iteration must also change nothing above tol."""
    t0 = time.time()
    hist = []
    for order2 in (False, True):
        it = 0
        while it < max_iter:
            it += 1
            m = max(sweep(G, 1, 1, order2), sweep(G, 1, -1, order2))
            full = False
            if m <= tol:
                m = max(sweep(G, sx, sz, order2) for sx, sz in ((1, 1), (1, -1), (-1, 1), (-1, -1)))
                full = True
            hist.append((2 if order2 else 1, it, m))
            if log:
                log("    order%d iter %d max change %.3e%s (%.1fs)" % (2 if order2 else 1, it, m,
                    " [4-dir check]" if full else "", time.time() - t0))
            if full and m <= tol:
                break
    return time.time() - t0, hist


def surface(G):
    return G.T[2, 2:G.nx + 2].copy()


# ----------------------------------------------------------------------------
# post-processing of T_1(X)
# ----------------------------------------------------------------------------

def value_at(xs, Ts, X, h):
    j = X / h
    jr = int(round(j))
    if abs(j - jr) < 1e-9:
        return float(Ts[jr])
    # cubic through 4 surrounding nodes
    j0 = int(math.floor(j)) - 1
    j0 = max(0, min(j0, len(Ts) - 4))
    c = np.polyfit(xs[j0:j0 + 4] - X, Ts[j0:j0 + 4], 3)
    return float(c[-1])


def slope_at(xs, Ts, X, h, half=4):
    """p = dT/dX by a local quadratic fit over +-half nodes."""
    j = int(round(X / h))
    lo, hi = max(0, j - half), min(len(Ts), j + half + 1)
    c = np.polyfit(xs[lo:hi] - X, Ts[lo:hi], 2)
    return float(c[-2])


def find_kinks(xs, Ts, h, xmin, thr=2e-4, merge=12, bgw=30):
    """Candidate node indices of slope drops (concave kinks).

    k_j = -(T_{j+1} - 2 T_j + T_{j-1}) / h is ~ the slope drop at a kink node
    and ~ -h T'' on a smooth arrival.  A candidate must stand out from the
    local background (median of k over nodes 5..bgw away on both sides):
    k_j - bg > thr and k_j > 4 |bg|."""
    c = (Ts[2:] - 2 * Ts[1:-1] + Ts[:-2]) / h
    k = -c
    n = len(k)
    idx = np.arange(1, len(Ts) - 1)
    bg = np.zeros(n)
    for j in range(n):
        w = np.concatenate([k[max(0, j - bgw):max(0, j - 5)], k[min(n, j + 5):min(n, j + bgw)]])
        bg[j] = np.median(w) if w.size else 0.0
    above = ((k - bg) > thr) & (k > 4 * np.abs(bg)) & (xs[1:-1] > xmin)
    cand = []
    j = 0
    while j < n:
        if above[j]:
            j2 = j
            while j2 + 1 < n and above[j2 + 1]:
                j2 += 1
            jj = idx[j + int(np.argmax(k[j:j2 + 1]))]
            if cand and jj - cand[-1] <= merge:
                if k[jj - 1] > k[cand[-1] - 1]:
                    cand[-1] = jj
            else:
                cand.append(jj)
            j = j2 + 1
        else:
            j += 1
    return cand


def fit_side(xs, Ts, lo, hi, x0, deg):
    sl = slice(max(lo, 0), min(hi, len(Ts)))
    xx = xs[sl] - x0
    if len(xx) < deg + 2:
        return None
    c = np.polyfit(xx, Ts[sl], deg)
    res = float(np.max(np.abs(np.polyval(c, xx) - Ts[sl])))
    return c, res


def refine_kink(xs, Ts, h, jk, jprev, jnext, w=12, Lkm=1.5, deg=2):
    nL = max(6, int(round(Lkm / h)))
    lo_l = max(jprev + w, jk - w - nL)
    hi_l = jk - w + 1
    lo_r = jk + w
    hi_r = min(jnext - w + 1, jk + w + nL + 1)
    x0 = xs[jk]
    fl = fit_side(xs, Ts, lo_l, hi_l, x0, deg)
    fr = fit_side(xs, Ts, lo_r, hi_r, x0, deg)
    if fl is None or fr is None:
        return None
    d = np.polysub(fl[0], fr[0])
    roots = np.roots(d) if np.any(d[:-1] != 0) else np.array([])
    roots = roots[np.isreal(roots)].real if roots.size else roots
    if roots.size == 0:
        return None
    r = roots[np.argmin(np.abs(roots))]
    if abs(r) > (w + 2) * h:
        return None
    pl = np.polyval(np.polyder(fl[0]), r)
    pr = np.polyval(np.polyder(fr[0]), r)
    return {"x": float(x0 + r), "t": float(np.polyval(fl[0], r)), "p_left": float(pl),
            "p_right": float(pr), "dp": float(pl - pr), "fit_res": max(fl[1], fr[1])}


def local_curvature(xs, Ts, lo, hi, W):
    """Quadratic-fit curvature T'' on sliding windows of width W inside [lo, hi)."""
    n = max(5, int(round(W / (xs[1] - xs[0]))))
    out_x, out_k, out_p = [], [], []
    step = max(1, n // 4)
    for j in range(lo, hi - n, step):
        sl = slice(j, j + n)
        xc = xs[j + n // 2]
        c = np.polyfit(xs[sl] - xc, Ts[sl], 2)
        out_x.append(xc)
        out_k.append(2 * c[0])
        out_p.append(c[1])
    return np.array(out_x), np.array(out_k), np.array(out_p)


def find_c1(xs, Ts, h, lo, hi, W=2.0, ktol=5e-6):
    """C1 transitions inside a kink-free node range [lo, hi): switches between
    straight (|T''| < ktol on 2-km quadratic windows) and curved parts.

    Location: the straight-side slope p0 is a line fit from 1 to 5 km into the
    straight side (the window-based estimate xb0 lies inside it).  With the
    node slopes p_j (centred differences), the transition is the root of a
    quadratic fitted to p - p0 on the curved side, over the 2 km next to the
    last node where |p - p0| is still below max(20x straight-side noise,
    5e-4 s/km)."""
    X, K, P = local_curvature(xs, Ts, lo, hi, W)
    if len(X) < 4:
        return [], X, K, P
    straight = np.abs(K) < ktol
    pj = np.full(len(Ts), np.nan)
    pj[1:-1] = (Ts[2:] - Ts[:-2]) / (2 * h)
    jj = np.arange(len(Ts))
    inrng = (jj >= lo + 1) & (jj < hi - 1)
    out = []
    for q in range(3, len(X) - 2):
        if straight[q] == straight[q - 1]:
            continue
        if not (np.all(straight[q:q + 3] == straight[q]) and np.all(straight[q - 3:q] == straight[q - 1])):
            continue
        xb0 = 0.5 * (X[q] + X[q - 1])
        left_straight = bool(straight[q - 1])
        g = -1.0 if left_straight else 1.0      # +1: straight side lies at larger X
        dd = (xs - xb0) * g                     # >0 on the straight side
        js = np.where(inrng & (dd >= 1.0) & (dd <= 5.0))[0]
        if len(js) < 10:
            continue
        line = np.polyfit(xs[js], Ts[js], 1)
        p0 = line[0]
        noise = max(float(np.std(pj[js] - p0)), 1e-9)
        thr = max(20 * noise, 5e-4)
        # walk from the straight side towards the curved side
        order = np.where(inrng & (dd <= 1.0) & (dd >= -4.0))[0]
        order = order[np.argsort(-dd[order])]
        xq = None
        for j in order:
            if abs(pj[j] - p0) > thr:
                xq = xs[j]
                break
        if xq is None:
            continue
        dq = (xs - xq) * g                      # <=0 on the curved side of xq
        jc = np.where(inrng & (dq <= 0.0) & (dq >= -2.0))[0]
        jc = jc[np.abs(pj[jc] - p0) > thr]
        if len(jc) < 8:
            continue
        cfit = np.polyfit(xs[jc] - xq, pj[jc] - p0, 2)
        roots = np.roots(cfit)
        roots = roots[np.isreal(roots)].real
        if roots.size == 0:
            continue
        r = roots[np.argmin(np.abs(roots))]
        if abs(r) > 1.0:
            continue
        out.append({"x": float(xq + r), "p": float(p0),
                    "from": "straight" if left_straight else "curved",
                    "to": "curved" if left_straight else "straight",
                    "curv_left": float(K[q - 1]), "curv_right": float(K[q]),
                    "curv_at_transition": float(cfit[1]),
                    "slope_noise": noise})
    return out, X, K, P


def analyse_surface(xs, Ts, h, xmin):
    cands = find_kinks(xs, Ts, h, xmin)
    kinks = []
    for q, jk in enumerate(cands):
        jprev = cands[q - 1] if q > 0 else int(math.ceil(xmin / h))
        jnext = cands[q + 1] if q + 1 < len(cands) else len(Ts) - 1
        r = refine_kink(xs, Ts, h, jk, jprev, jnext)
        if r is not None and r["dp"] > 2e-4:
            r["node"] = jk
            kinks.append(r)
    # segments between kinks
    bounds = [int(math.ceil(xmin / h))] + [k["node"] for k in kinks] + [len(Ts)]
    segs = []
    c1s = []
    for q in range(len(bounds) - 1):
        lo = bounds[q] + (14 if q > 0 else 0)
        hi = bounds[q + 1] - (13 if q + 1 < len(bounds) - 1 else 0)
        if hi - lo < 6:
            continue
        pA = slope_at(xs, Ts, xs[lo + 3], h)
        pB = slope_at(xs, Ts, xs[hi - 4], h)
        c1, X, K, P = find_c1(xs, Ts, h, lo, hi)
        c1s.extend(c1)
        segs.append({"x_from": float(xs[lo]), "x_to": float(xs[hi - 1]), "p_start": pA, "p_end": pB,
                     "curv_min": float(K.min()) if len(K) else None,
                     "curv_max": float(K.max()) if len(K) else None})
    return kinks, segs, c1s


# ----------------------------------------------------------------------------
# Richardson
# ----------------------------------------------------------------------------

def _fit(hs, vals, orders):
    A = np.column_stack([np.ones(len(hs))] + [np.asarray(hs) ** p for p in orders])
    return float(np.linalg.solve(A, np.asarray(vals))[0])


def _pobs_extrap(v):
    d1, d2 = v[-3] - v[-2], v[-2] - v[-1]
    if d2 != 0.0 and 2 ** 1.2 < d1 / d2 < 2 ** 3.5:
        r = d1 / d2
        return v[-1] - d2 / (r - 1.0), math.log2(r)
    return None, None


def richardson(vals, hs):
    """vals on spacings hs (coarse to fine, ratio 2).

    primary : observed-order Richardson on the three finest levels when the
              observed order p lies in (1.2, 3.5) (p ~ 2 in smooth regions,
              ~1.5 where a field is emitted tangentially from an interface);
              otherwise the fit Q* + C h^2 + D h^3 to the three finest levels
    bar     : 2 x max |primary - alternative| over the alternatives
              {h^2+h^3 fit, two-level h^2 value, observed-order value} and,
              with four levels, |primary - same estimator on the three coarser
              levels| (exposes pre-asymptotic levels)."""
    v = np.array(vals, float)
    h = np.array(hs, float)
    out = {"values": [float(x) for x in v]}
    fit23 = _fit(h[-3:], v[-3:], (2, 3))
    two = _fit(h[-2:], v[-2:], (2,))
    pe, p_obs = _pobs_extrap(v)
    prim = pe if pe is not None else fit23
    alts = [fit23, two] + ([pe] if pe is not None else [])
    d1, d2 = v[-3] - v[-2], v[-2] - v[-1]
    if pe is None and (d1 != 0.0 or d2 != 0.0):
        alts.append(v[-1] + max(abs(d1), abs(d2)))      # non-asymptotic: raw differences
    err = 2.0 * max(abs(prim - x) for x in alts)
    out["extrapolated"] = float(prim)
    out["p_obs"] = p_obs
    out["fit23"] = fit23
    if len(v) >= 4:
        pc, pco = _pobs_extrap(v[:-1])
        coarse = pc if pc is not None else _fit(h[-4:-1], v[-4:-1], (2, 3))
        out["extrapolated_coarser_triple"] = float(coarse)
        out["p_obs_coarser_triple"] = pco
        err = max(err, abs(prim - coarse))
    # floor: the extrapolation is credited with at most halving the finest-level error
    err = max(err, 0.5 * abs(v[-1] - prim))
    out["err"] = float(max(err, 1e-12 * abs(prim)))
    out["finest_minus_extrap"] = float(v[-1] - prim)
    return out


# ----------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------

def choose_levels(model, zmax, budget):
    """Finest h = G/m (G = lattice of interfaces, offsets, X_max), coarsest of
    three levels 4h; a fourth coarser level 8h is added when it stays aligned
    and resolves layer 0 with at least 6 cells."""
    G = gcd_km(list(model["tops"][1:]) + model["offsets"] + [model["xmax"]])
    xm = model["xmax"]
    nodes = lambda hf: (xm / hf + 1) * (zmax / hf + 1)
    m = 4
    while nodes(G / (m + 4)) <= budget:
        m += 4
    if m % 8 and nodes(G / (m + 4)) <= 1.5 * budget:
        m += 4
    hf = G / m
    hs = [hf * 4, hf * 2, hf]
    if m % 8 == 0 and 8 * hf <= model["tops"][1] / 6:
        hs = [hf * 8] + hs
    return hs


def run(model_path, outdir, budget, log=print):
    model = load_model(model_path)
    os.makedirs(outdir, exist_ok=True)
    xm = model["xmax"]
    tops = model["tops"]
    zlast = tops[-1]
    h0 = tops[1]
    R = "exact-region"
    timings = {}
    t_all = time.time()

    # --- depth of the domain: grow until the surface times stop changing (coarse grid)
    G = gcd_km(list(tops[1:]) + model["offsets"] + [xm])
    mm = 1
    while (xm / (G / mm) + 1) * ((zlast + 2) / (G / mm) + 1) > 6e5 or G / mm > h0 / 4:
        mm += 1
    hd = G / mm
    margin = max(1.0, 4 * hd)
    prev = None
    depth_log = []
    t0 = time.time()
    while True:
        zmax = zlast + margin
        zmax = math.ceil(zmax / hd - 1e-9) * hd
        Gd = Grid(model, hd, zmax, xm, R)
        solve(Gd, tol=1e-10)
        Ts = surface(Gd)
        if prev is not None:
            dmax = float(np.max(np.abs(Ts - prev)))
            depth_log.append((zmax, dmax))
            if dmax < 1e-7:
                break
        else:
            depth_log.append((zmax, None))
        prev = Ts
        margin *= 2
        if margin > 400:
            break
    # the shallower of the two depths that agreed, plus 25 % of its margin
    zmax_final = zlast + (margin / 2) * 1.25
    timings["depth_search_s"] = time.time() - t0
    log("  depth search: %s -> zmax %.3f km (%.1fs)" % (depth_log, zmax_final, timings["depth_search_s"]))

    hs = choose_levels(model, zmax_final, budget)
    hc = hs[0]
    zmax_final = math.ceil(zmax_final / hc - 1e-9) * hc
    log("  levels h = %s, zmax = %.3f" % (hs, zmax_final))
    surf = []
    level_info = []
    for h in hs:
        G_ = Grid(model, h, zmax_final, xm, R)
        log("  h=%.5f grid %d x %d = %.2fM nodes, disk %d nodes" % (h, G_.nx, G_.nz, G_.nx * G_.nz / 1e6, G_.ndisk))
        el, hist = solve(G_, log=log)
        Ts = surface(G_)
        xs = np.arange(G_.nx) * h
        surf.append((h, xs, Ts))
        level_info.append({"h_km": h, "nx": G_.nx, "nz": G_.nz, "nodes": G_.nx * G_.nz,
                           "disk_nodes": G_.ndisk, "solve_s": round(el, 2),
                           "iterations_order1": sum(1 for o, _, _ in hist if o == 1),
                           "iterations_order2": sum(1 for o, _, _ in hist if o == 2),
                           "final_change": hist[-1][2]})
        del G_
    timings["levels"] = level_info
    timings["solve_total_s"] = round(time.time() - t_all, 1)
    meta = {"depth_search": depth_log, "zmax_km": zmax_final, "timings": timings}
    np.savez(os.path.join(outdir, "surface_levels.npz"), hs=np.array(hs),
             **{"T%d" % l: surf[l][2] for l in range(len(hs))}, meta=json.dumps(meta))
    return analyse(model, outdir)


def analyse(model, outdir):
    """Post-processing of the saved surface rows (no re-solve)."""
    d = np.load(os.path.join(outdir, "surface_levels.npz"))
    hs = [float(x) for x in d["hs"]]
    meta = json.loads(str(d["meta"]))
    surf = [(h, np.arange(len(d["T%d" % l])) * h, d["T%d" % l]) for l, h in enumerate(hs)]
    depth_log, zmax_final, timings = meta["depth_search"], meta["zmax_km"], meta["timings"]
    xm = model["xmax"]
    t_all = time.time()

    # --- queried offsets
    queried = []
    for X in model["offsets"]:
        tv = [value_at(xs, Ts, X, h) for (h, xs, Ts) in surf]
        pv = [slope_at(xs, Ts, X, h) for (h, xs, Ts) in surf]
        rt = richardson(tv, hs)
        rp = richardson(pv, hs)
        queried.append({"x_km": X, "t_s": rt["extrapolated"], "t_err_s": rt["err"],
                        "t_levels": rt["values"], "t_p_obs": rt["p_obs"],
                        "p_s_km": rp["extrapolated"], "p_err": rp["err"], "p_levels": rp["values"],
                        "v_app_km_s": 1.0 / rp["extrapolated"]})

    # --- kinks and C1 transitions per level
    xmin = 0.5
    per_level = []
    for (h, xs, Ts) in surf:
        k, s, c1 = analyse_surface(xs, Ts, h, xmin)
        per_level.append((k, s, c1))
    # match kinks across levels by position (relative to finest)
    kf, sf, c1f = per_level[-1]
    crossovers = []
    for kk in kf:
        found = []
        for (k, s_, c1) in per_level:
            near = min(k, key=lambda e: abs(e["x"] - kk["x"])) if k else None
            if near is not None and abs(near["x"] - kk["x"]) > max(0.5, 0.02 * kk["x"]):
                near = None
            found.append(near)
        run_ = []
        for e in reversed(found):          # trailing run of levels where it was found
            if e is None:
                break
            run_.insert(0, e)
        entry = {"x_finest_km": kk["x"], "t_finest_s": kk["t"], "p_left": kk["p_left"], "p_right": kk["p_right"],
                 "slope_drop": kk["dp"], "v_app_left": 1 / kk["p_left"], "v_app_right": 1 / kk["p_right"],
                 "levels_found": len(run_)}
        if len(run_) >= 3:
            rx = richardson([e["x"] for e in run_], hs[-len(run_):])
            rt = richardson([e["t"] for e in run_], hs[-len(run_):])
            rl = richardson([e["p_left"] for e in run_], hs[-len(run_):])
            rr = richardson([e["p_right"] for e in run_], hs[-len(run_):])
            entry.update({"x_km": rx["extrapolated"], "x_err_km": rx["err"], "x_levels": rx["values"],
                          "x_p_obs": rx["p_obs"], "t_s": rt["extrapolated"], "t_err_s": rt["err"],
                          "p_left_extrap": rl["extrapolated"], "p_left_err": rl["err"],
                          "p_right_extrap": rr["extrapolated"], "p_right_err": rr["err"]})
        else:
            entry.update({"x_km": kk["x"], "x_err_km": None, "note": "found on fewer than 3 levels"})
        crossovers.append(entry)
    c1_out = []
    for cc in c1f:
        xs_l = []
        for (k, s, c1) in per_level:
            near = [e for e in c1 if abs(e["x"] - cc["x"]) < max(1.0, 0.05 * cc["x"]) and e["from"] == cc["from"]]
            if near:
                xs_l.append(min(near, key=lambda e: abs(e["x"] - cc["x"]))["x"])
        e = dict(cc)
        e["v_app_straight"] = 1 / cc["p"]
        e["x_levels"] = xs_l
        e["x_km"] = cc["x"]
        if len(xs_l) >= 2:
            e["x_spread_km"] = float(max(xs_l) - min(xs_l))
        c1_out.append(e)
    feats = [c["x_km"] for c in crossovers]
    for q in queried:
        d = min([abs(q["x_km"] - f) for f in feats] or [INF])
        q["dist_to_nearest_kink_km"] = d
        q["near_kink"] = bool(d < 20 * hs[-1] * 2)
    segments = []
    for s in sf:
        s = dict(s)
        s["v_app_start"] = 1 / s["p_start"]
        s["v_app_end"] = 1 / s["p_end"]
        straight = s["curv_max"] is not None and max(abs(s["curv_min"]), abs(s["curv_max"])) < 5e-6
        s["shape"] = "straight (constant apparent slowness)" if straight else "curved or mixed"
        segments.append(s)

    # --- fine X grid output (common nodes of all levels = coarsest grid nodes)
    hcst, xsc, _ = surf[0]
    rows = []
    fine_ratio = [int(round(hcst / h)) for (h, _, _) in surf]
    for jc in range(len(xsc)):
        vals = [surf[l][2][jc * fine_ratio[l]] for l in range(len(surf))]
        r = richardson(vals, hs)
        rows.append((xsc[jc], *vals, r["extrapolated"], r["err"]))
    # crossover bar: add the branch-time error propagated through the slope drop,
    # |dX| = (err_T_left + err_T_right) / (p_left - p_right), using the time error
    # bars at coarse nodes 15 coarse spacings either side of the kink
    errs = np.array([r[-1] for r in rows])
    for c in crossovers:
        jc = int(round(c["x_km"] / hcst))
        jl, jr = max(0, jc - 15), min(len(errs) - 1, jc + 15)
        prop = (errs[jl] + errs[jr]) / max(c["slope_drop"], 1e-12)
        c["x_err_from_time_bars_km"] = float(prop)
        if c.get("x_err_km") is not None:
            c["x_err_km"] = float(max(c["x_err_km"], prop))
    # C1 bar: information limit sqrt(2 eps / |T''|) of locating where a curve
    # leaves its tangent line with time accuracy eps, and a third of the change
    # between the two finest levels (order >= 2 assumed)
    for c in c1_out:
        jc = int(round(c["x_km"] / hcst))
        eps = float(errs[max(0, min(len(errs) - 1, jc))])
        kap = abs(c.get("curv_at_transition") or 0.0) or 1e-12
        lim = math.sqrt(2 * eps / kap)
        lv = c["x_levels"]
        dl = abs(lv[-1] - lv[-2]) / 3.0 if len(lv) >= 2 else INF
        c["x_err_km"] = float(max(lim, dl)) if math.isfinite(dl) else None
        c["x_err_information_limit_km"] = lim
    hf, xsf, Tsf = surf[-1]
    pf = np.gradient(Tsf, hf)
    with open(os.path.join(outdir, "T1_levels.csv"), "w") as f:
        f.write("x_km," + ",".join("T_h%.5g" % h for (h, _, _) in surf) + ",T_extrap,err_s\n")
        for r in rows:
            f.write(",".join("%.12g" % v for v in r) + "\n")
    with open(os.path.join(outdir, "T1_finest.csv"), "w") as f:
        f.write("x_km,T_s,dTdX_s_km\n")
        for x, t, p in zip(xsf, Tsf, pf):
            f.write("%.6f,%.12g,%.10g\n" % (x, t, p))

    timings["analysis_s"] = round(time.time() - t_all, 1)
    summary = {"model_id": model["id"], "zmax_km": zmax_final, "source_treatment": "exact layer-0 region",
               "depth_search": depth_log, "levels_h_km": hs,
               "queried": queried, "crossovers": crossovers, "c1_transitions": c1_out,
               "segments_finest": segments, "timings": timings}
    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--budget", type=float, default=4e6, help="max nodes on the finest grid")
    ap.add_argument("--reanalyse", action="store_true", help="re-run post-processing from surface_levels.npz")
    a = ap.parse_args()
    print("model", a.model)
    if a.reanalyse:
        s = analyse(load_model(a.model), a.outdir)
    else:
        s = run(a.model, a.outdir, a.budget)
    for q in s["queried"]:
        print("  X=%8.3f  T=%.7f +- %.1e  p=%.7f +- %.1e" % (q["x_km"], q["t_s"], q["t_err_s"], q["p_s_km"], q["p_err"]))
    for c in s["crossovers"]:
        print("  kink X=%s +- %s  p %.6f -> %.6f" % (c["x_km"], c["x_err_km"], c["p_left"], c["p_right"]))
    for c in s["c1_transitions"]:
        print("  C1   X=%.4f +- %s %s->%s p=%.6f levels %s" % (c["x"], c["x_err_km"], c["from"], c["to"], c["p"], c["x_levels"]))


if __name__ == "__main__":
    main()
