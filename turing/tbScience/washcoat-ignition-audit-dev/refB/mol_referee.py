#!/usr/bin/env python
"""
mol_referee.py -- transient (method-of-lines) referee for the washcoat ignition problem of
WASHCOAT_SPEC.md section 1:

    Le theta_t = theta_xx + beta phi^2 c R(theta)
       c_t     = c_xx     -      phi^2 c R(theta),      R = exp(gamma theta / (1 + theta))
    x = 0 : theta_x = c_x = 0          x = 1 : -c_x = Bi_m (c - 1),  -theta_x = Bi_h theta

Space: cell-centred finite volumes on N cells, optionally clustered towards x = 1 by
x(s) = 1 - sinh(a (1 - s)) / sinh(a).  Interior face fluxes are centred differences; the Robin
face flux comes from the quadratic through the two last cell centres and the face value, with the
face value eliminated through the Robin condition (second order, flux form).  theta_c is the
zero-slope quadratic extrapolation of the first two cells to x = 0; eta = c_x(1) / phi^2 is the
Robin face flux of c divided by phi^2.

Time: solve_ivp, BDF (default) or Radau with the analytic Jacobian, which is banded (unknowns
interleaved theta_0, c_0, theta_1, c_1, ...; half bandwidth 2) and is handed over as a sparse
CSC matrix; LSODA receives it in LAPACK packed band form (lband = uband = 2).

Nothing in this file solves the steady equations directly: every state it reports is the end
of a time integration.

Commands (all print a summary; --out FILE writes JSON)
  relax  --recipe R --phi P [--theta0 T --c0 C | --state NPZ --branch up|down] [--cells N --tmax T]
  sweep  --recipe R [--cells N --per-decade K --resolution r --save-states NPZ]
  probe  --recipe R --phi P [P ...] [--cells N --ntheta 7 --nc 5 --extra NPZ]
  summary --recipe R --outdir DIR [--cells N]      (sweep + probe at every phi_query)
  kick   --recipe R --base-recipe B --state NPZ --phi P   (departure from a steady state of a
         companion recipe with another Le: growth rate / frequency of the leading mode)
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import scipy.sparse as sp
from scipy.integrate import solve_ivp

# ----------------------------------------------------------------------------- recipe / grid


def load_recipe(path):
    with open(path) as fh:
        r = json.load(fh)
    for k in ("beta", "gamma", "Bi_m", "Bi_h", "Le", "phi_min", "phi_max", "phi_query"):
        if k not in r:
            raise SystemExit("recipe lacks key %s" % k)
    r.setdefault("recipe_id", os.path.splitext(os.path.basename(path))[0])
    return r


def auto_cluster(r, N):
    """Clustering parameter a so that the face cell is ~1/20 of the thinnest reaction zone
    expected anywhere in the window, delta = 1/(phi_max sqrt(R(theta_ad))), never coarser than
    uniform and capped at a = 7."""
    t_ad = r["beta"] * r["Bi_m"] / r["Bi_h"]
    delta = 1.0 / (r["phi_max"] * math.sqrt(math.exp(r["gamma"] * t_ad / (1.0 + t_ad))))
    target = delta / 20.0
    if 1.0 / N <= target:
        return 0.0
    lo, hi = 1e-6, 7.0
    g = lambda a: a / math.sinh(a) / N - target
    if g(hi) > 0:
        return hi
    for _ in range(80):
        m = 0.5 * (lo + hi)
        if g(m) > 0:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


class Grid:
    def __init__(self, N, a):
        s = np.linspace(0.0, 1.0, N + 1)
        if a > 1e-9:
            xf = 1.0 - np.sinh(a * (1.0 - s)) / math.sinh(a)
        else:
            xf = s.copy()
        xf[0], xf[-1] = 0.0, 1.0
        self.N, self.a = N, a
        self.xf = xf
        self.h = np.diff(xf)
        self.xc = 0.5 * (xf[:-1] + xf[1:])
        self.dxc = np.diff(self.xc)                     # distances between centres (N-1)
        x0, x1, x2 = self.xc[-2], self.xc[-1], 1.0
        # derivative at x = 1 of the quadratic through (x0,u0), (x1,u1), (1,ub)
        self.w0 = (x2 - x1) / ((x0 - x1) * (x0 - x2))
        self.w1 = (x2 - x0) / ((x1 - x0) * (x1 - x2))
        self.w2 = (2 * x2 - x0 - x1) / ((x2 - x0) * (x2 - x1))
        # theta_c extrapolation (zero slope at 0): u(0) = e0 u_0 + e1 u_1
        q0, q1 = self.xc[0] ** 2, self.xc[1] ** 2
        self.e0 = 1.0 + q0 / (q1 - q0)
        self.e1 = -q0 / (q1 - q0)

    def robin(self, Bi):
        """face flux u_x(1) = k0 u_{N-2} + k1 u_{N-1} + kb u_inf"""
        f = Bi / (self.w2 + Bi)
        return f * self.w0, f * self.w1, f * self.w2


class Problem:
    def __init__(self, r, N=200, cluster=None):
        self.r = r
        self.beta, self.gamma, self.Le = float(r["beta"]), float(r["gamma"]), float(r["Le"])
        self.Bi_m, self.Bi_h = float(r["Bi_m"]), float(r["Bi_h"])
        a = auto_cluster(r, N) if cluster is None else float(cluster)
        self.g = Grid(int(N), a)
        self.N = int(N)
        self.kh = self.g.robin(self.Bi_h)
        self.km = self.g.robin(self.Bi_m)
        self.theta_ad = self.beta * self.Bi_m / self.Bi_h
        self._pattern()

    # -- operators -----------------------------------------------------------------
    def _diffusion(self, u, k, uinf):
        g = self.g
        F = np.empty(self.N + 1)
        F[0] = 0.0
        F[1:-1] = np.diff(u) / g.dxc
        F[-1] = k[0] * u[-2] + k[1] * u[-1] + k[2] * uinf
        return np.diff(F) / g.h

    def _lap_bands(self, k):
        """tridiagonal Laplacian: (lower, diag, upper) with lower[i] = d(row i+1)/d(u_i)"""
        g, N = self.g, self.N
        inv = 1.0 / g.dxc
        diag = np.zeros(N)
        up = np.zeros(N - 1)
        lo = np.zeros(N - 1)
        # face i+1/2 between i and i+1 contributes to rows i (+F) and i+1 (-F)
        diag[:-1] -= inv / g.h[:-1]
        up += inv / g.h[:-1]
        diag[1:] -= inv / g.h[1:]
        lo += inv / g.h[1:]
        diag[-1] += k[1] / g.h[-1]
        lo[-1] += k[0] / g.h[-1]
        return lo, diag, up

    def _pattern(self):
        N = self.N
        ar = np.arange(N)
        self.Lh = self._lap_bands(self.kh)
        self.Lm = self._lap_bands(self.km)
        rows, cols = [], []
        for off, (r_, c_) in (("th", (2 * ar, 2 * ar)), ("thc", (2 * ar, 2 * ar + 1)),
                              ("cth", (2 * ar + 1, 2 * ar)), ("cc", (2 * ar + 1, 2 * ar + 1))):
            rows.append(r_)
            cols.append(c_)
        a1 = np.arange(N - 1)
        rows += [2 * a1, 2 * (a1 + 1), 2 * a1 + 1, 2 * (a1 + 1) + 1]   # upper/lower of theta and c
        cols += [2 * (a1 + 1), 2 * a1, 2 * (a1 + 1) + 1, 2 * a1 + 1]
        self.jr = np.concatenate(rows)
        self.jc = np.concatenate(cols)
        self.n = 2 * N

    def rhs(self, t, y, phi):
        th, c = y[0::2], y[1::2]
        src = (phi * phi) * c * np.exp(self.gamma * th / (1.0 + th))
        out = np.empty_like(y)
        out[0::2] = (self._diffusion(th, self.kh, 0.0) + self.beta * src) / self.Le
        out[1::2] = self._diffusion(c, self.km, 1.0) - src
        return out

    def _jvals(self, y, phi):
        th, c = y[0::2], y[1::2]
        p2 = phi * phi
        R = np.exp(self.gamma * th / (1.0 + th))
        dR = R * self.gamma / (1.0 + th) ** 2
        iL = 1.0 / self.Le
        d_tt = (self.Lh[1] + self.beta * p2 * c * dR) * iL
        d_tc = self.beta * p2 * R * iL
        d_ct = -p2 * c * dR
        d_cc = self.Lm[1] - p2 * R
        return np.concatenate([d_tt, d_tc, d_ct, d_cc,
                               self.Lh[2] * iL, self.Lh[0] * iL, self.Lm[2], self.Lm[0]])

    def jac(self, t, y, phi):
        return sp.csc_matrix((self._jvals(y, phi), (self.jr, self.jc)), shape=(self.n, self.n))

    def jac_banded(self, t, y, phi):
        """LAPACK packed band form, lband = uband = 2: B[2 + i - j, j] = J[i, j]; LSODA wants
        2 lband + uband + 1 = 7 rows (the last lband rows are LU fill space)"""
        B = np.zeros((7, self.n))
        B[2 + self.jr - self.jc, self.jc] = self._jvals(y, phi)
        return B

    # -- observables -----------------------------------------------------------------
    def theta_c(self, y):
        y = np.asarray(y)
        return self.g.e0 * y[0, ...] + self.g.e1 * y[2, ...]

    def eta(self, y, phi):
        y = np.asarray(y)
        k = self.km
        return (k[0] * y[2 * self.N - 3, ...] + k[1] * y[2 * self.N - 1, ...] + k[2]) / (phi * phi)

    def uniform(self, th0, c0):
        y = np.empty(self.n)
        y[0::2], y[1::2] = th0, c0
        return y

    def resid(self, y, phi):
        """max |dy/dt| (theta rows multiplied back by Le, i.e. the steady-equation residual),
        scaled by max(1, phi^2) so that the test is uniform across the window"""
        f = self.rhs(0.0, y, phi)
        f[0::2] *= self.Le
        return float(np.max(np.abs(f))) / max(1.0, phi * phi)


# ----------------------------------------------------------------------------- relaxation


def _extrema(t, s, eps=1e-9):
    """local maxima / minima of a sampled series, zigzag-filtered: a swing smaller than eps
    (round-off wiggles of a settled state) does not create an extremum"""
    i = np.arange(1, len(s) - 1)
    raw = i[((s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:])) | ((s[1:-1] < s[:-2]) & (s[1:-1] <= s[2:]))]
    if raw.size == 0:
        return raw, raw
    ismax = s[raw] > s[raw - 1]
    keep, kmax = [], []
    for j, m in zip(raw.tolist(), ismax.tolist()):
        if not keep:
            keep.append(j)
            kmax.append(m)
        elif m == kmax[-1]:
            if (s[j] > s[keep[-1]]) == m and s[j] != s[keep[-1]]:
                keep[-1] = j
        elif abs(s[j] - s[keep[-1]]) >= eps:
            keep.append(j)
            kmax.append(m)
    keep, kmax = np.array(keep, int), np.array(kmax, bool)
    if keep.size >= 2 and abs(s[keep[0]] - s[keep[1]]) < eps:
        keep, kmax = keep[1:], kmax[1:]
    return keep[kmax], keep[~kmax]


def _parab(t, s, i):
    y0, y1, y2 = s[i - 1], s[i], s[i + 1]
    t0, t1, t2 = t[i - 1], t[i], t[i + 1]
    # quadratic through three (possibly uneven) points
    A = np.array([[t0 * t0, t0, 1.0], [t1 * t1, t1, 1.0], [t2 * t2, t2, 1.0]])
    try:
        a, b, c = np.linalg.solve(A - np.array([[0, 0, 0]]), [y0, y1, y2])
    except np.linalg.LinAlgError:
        return t1, y1
    if a == 0:
        return t1, y1
    tm = -b / (2 * a)
    if not (t0 <= tm <= t2):
        return t1, y1
    return tm, a * tm * tm + b * tm + c


def _refine(prob, sol, t, s, i, sign):
    t0, t1 = t[max(i - 1, 0)], t[min(i + 1, len(t) - 1)]
    if t0 < sol.t[0] or t1 > sol.t[-1] or t1 <= t0:
        return _parab(t, s, i)
    tf = np.linspace(t0, t1, 201)
    sf = prob.theta_c(sol.sol(tf))
    k = int(np.argmax(sign * sf))
    k = min(max(k, 1), 199)
    return _parab(tf, sf, k)


def _osc_trend(t, s, mx, mn):
    """amplitude (peak minus following trough) of the last oscillations and its log-slope"""
    if mx.size < 4 or mn.size < 3:
        return None
    amps, tim = [], []
    for i in mx[-8:]:
        j = mn[mn > i]
        if j.size:
            amps.append(s[i] - s[j[0]])
            tim.append(t[i])
    amps, tim = np.array(amps), np.array(tim)
    if amps.size < 3 or np.any(amps <= 1e-12):
        return None
    rate = float(np.polyfit(tim, np.log(amps), 1)[0])
    per = float(np.mean(np.diff(t[mx[-4:]])))
    if t[-1] - max(t[mx[-1]], t[mn[-1]]) > 3.0 * per:
        return None          # no extremum for three periods: the oscillation has died out
    return {"amplitude": float(amps[-1]), "amp_growth_rate": rate, "period_est": per}


def relax(prob, phi, y0, tmax=None, ss_tol=1e-9, rtol=1e-8, atol=1e-11, method="BDF",
          sub=8, w0=None, wmax=None, osc_tmax=None, verbose=False):
    """Integrate from y0 until (a) steady: resid < ss_tol, or (b) a settled limit cycle, or
    (c) t = tmax, or (d) oscillations of theta_c (amplitude > 1e-6) are still unsettled at
    t = osc_tmax (default 300 max(1, Le)).  In cases (c), (d) the result carries 'osc', the
    current peak-to-trough amplitude and its exponential growth rate.  'y' is the final state."""
    Le = prob.Le
    tscale = max(1.0, Le)
    if tmax is None:
        tmax = 3000.0 * tscale
    W = w0 if w0 else 1.0 * tscale
    Wmax = wmax if wmax else 40.0 * tscale
    t, y = 0.0, np.array(y0, float)
    kw = dict(method=method, rtol=rtol, atol=atol, args=(phi,), dense_output=True)
    if method == "LSODA":
        kw.update(jac=prob.jac_banded, lband=2, uband=2)
    else:
        kw.update(jac=prob.jac)
    status, nst, cyc, osc = "unresolved", 0, None, None
    if osc_tmax is None:
        osc_tmax = 300.0 * tscale
    hist_t, hist_s = np.empty(0), np.empty(0)
    t_wall = time.time()
    while t < tmax - 1e-12:
        W = min(W, tmax - t)
        sol = solve_ivp(prob.rhs, (t, t + W), y, **kw)
        if not sol.success:
            status = "integrator_failed"
            break
        nst += len(sol.t) - 1
        # sample theta_c: every integrator step subdivided `sub` times
        ts = sol.t
        # (fewer sub-samples when the steps are already dense; extrema are refined on the
        # dense output anyway)
        fr = np.linspace(0.0, 1.0, sub if len(ts) < 2000 else 2, endpoint=False)
        tt = np.concatenate([(ts[:-1, None] + np.diff(ts)[:, None] * fr[None, :]).ravel(), ts[-1:]])
        Y = sol.sol(tt)
        s = prob.theta_c(Y)
        dy = float(np.max(np.abs(sol.y[:, -1] - y)))
        y = sol.y[:, -1].copy()
        t = t + W
        r = prob.resid(y, phi)
        if verbose:
            print("   t=%9.3f W=%.3g res=%.2e dy=%.2e thc=%.6f steps=%d" % (t, W, r, dy, s[-1], nst), file=sys.stderr)
        # steady: residual below tolerance, or (residual at its round-off floor) the state did not
        # move by more than 1e-11 over a window of at least 10 thermal/mass time constants
        if r < ss_tol or (r < 1e3 * ss_tol and W >= 10.0 * tscale and dy < 1e-11):
            status = "steady"
            break
        # limit-cycle test on this window (concatenate with the previous one)
        hist_t = np.concatenate([hist_t, tt[1:] if hist_t.size else tt])
        hist_s = np.concatenate([hist_s, s[1:] if hist_s.size else s])
        if hist_t.size > 1000000:
            hist_t, hist_s = hist_t[-500000:], hist_s[-500000:]
        mx, mn = _extrema(hist_t, hist_s)
        osc = _osc_trend(hist_t, hist_s, mx, mn)
        if mx.size >= 8 and mn.size >= 7:
            # refine each extremum on the dense output of this window when it lies inside it
            # (sharp ignition spikes are under-resolved by the step samples)
            pk = np.array([_refine(prob, sol, hist_t, hist_s, i, +1) for i in mx[-7:]])
            tr = np.array([_refine(prob, sol, hist_t, hist_s, i, -1) for i in mn[-6:]])
            per = np.diff(pk[:, 0])
            amp = pk[1:, 1] - tr[-per.size:, 1] if tr.shape[0] >= per.size else None
            if amp is not None and amp.size and np.all(amp > 1e-7):
                pspread = (per.max() - per.min()) / per.mean()
                aspread = (amp.max() - amp.min()) / amp.mean()
                if verbose:
                    print("     cycle test: period spread %.2e amplitude spread %.2e" % (pspread, aspread), file=sys.stderr)
                if pspread < 2e-3 and aspread < 2e-3:
                    status = "cycle"
                    cyc = (sol, pk, per)
                    break
        if osc is not None and osc["amplitude"] > 1e-6 and t >= osc_tmax:
            status = "unresolved_oscillating"
            break
        W = min(2.0 * W, Wmax)
        # if a few periods are already visible, keep windows at ~30 periods
        if osc is not None and osc["amplitude"] > 1e-7:
            W = min(W, max(30.0 * osc["period_est"], 1e-3))
    out = {"phi": float(phi), "status": status, "t_end": float(t), "resid": prob.resid(y, phi),
           "theta_c": float(prob.theta_c(y)), "eta": float(prob.eta(y, phi)), "n_steps": int(nst),
           "wall_s": time.time() - t_wall}
    if status.startswith("unresolved") and osc is not None:
        out["osc"] = osc
    if status == "cycle":
        # one more integration over 3 periods, densely sampled, for period/mean/extremes
        P = float(np.mean(cyc[2][-4:]))
        sol2 = solve_ivp(prob.rhs, (t, t + 3.0 * P), y, t_eval=np.linspace(t, t + 3.0 * P, 6001), **kw)
        s2 = prob.theta_c(sol2.y)
        e2 = prob.eta(sol2.y, phi)
        mx2, mn2 = _extrema(sol2.t, s2)
        pk2 = np.array([_parab(sol2.t, s2, i) for i in mx2]) if mx2.size else np.empty((0, 2))
        if pk2.shape[0] >= 2:
            P = float(np.mean(np.diff(pk2[:, 0])))
        m = sol2.t <= t + 2.0 * P + 1e-12
        n_one = max(2, int(np.searchsorted(sol2.t, t + P)))
        out["cycle"] = {"period": P, "omega": 2 * math.pi / P,
                        "theta_c_mean": float(np.trapz(s2[:n_one], sol2.t[:n_one]) / (sol2.t[n_one - 1] - sol2.t[0])),
                        "theta_c_min": float(s2[m].min()), "theta_c_max": float(s2[m].max()),
                        "amplitude_pp": float(s2[m].max() - s2[m].min()),
                        "eta_mean": float(np.trapz(e2[:n_one], sol2.t[:n_one]) / (sol2.t[n_one - 1] - sol2.t[0])),
                        "eta_min": float(e2[m].min()), "eta_max": float(e2[m].max()),
                        "period_spread_last_windows": float((cyc[2].max() - cyc[2].min()) / cyc[2].mean())}
        out["y_mean"] = sol2.y[:, :n_one].mean(axis=1)
        y = sol2.y[:, -1]
        out["t_end"] = float(sol2.t[-1])
    out["y"] = y
    return out


def attractor_type(res):
    """steady / cycle; an unsettled oscillation counts as cycle when growing, steady when decaying"""
    st = res["status"]
    if st.startswith("unresolved") and res.get("osc") and res["osc"]["amplitude"] > 1e-9:
        return "cycle" if res["osc"]["amp_growth_rate"] > 0 else "steady"
    return st


def attractor_key(res):
    if res["status"] == "cycle":
        return res["cycle"]["theta_c_mean"]
    return res["theta_c"]


# ----------------------------------------------------------------------------- sweep


def _pass(prob, phis, y, kw, label, verbose, store):
    rows = []
    for phi in phis:
        res = relax(prob, phi, y, **kw)
        y = res["y"]
        row = {k: res[k] for k in ("phi", "status", "theta_c", "eta", "t_end", "resid", "wall_s")}
        if "cycle" in res:
            row["cycle"] = res["cycle"]
        row["key"] = attractor_key(res)
        row["type"] = attractor_type(res)
        if "osc" in res:
            row["osc"] = res["osc"]
        rows.append(row)
        store.append(y.copy())
        if verbose:
            extra = (" cycle P=%.5g pp=%.4g" % (res["cycle"]["period"], res["cycle"]["amplitude_pp"])) if "cycle" in res else ""
            print("  %s phi=%-10.6g %-10s thc=%-10.6f eta=%-10.6f t=%-8.4g %.2fs%s" % (
                label, phi, res["status"], res["theta_c"], res["eta"], res["t_end"], res["wall_s"], extra), file=sys.stderr)
    return rows, y


def _bisect(prob, row_a, y_a, row_b, kw, resolution, verbose):
    """Event between consecutive sweep steps a (old attractor still followed) and b.  Bisect in
    ln phi, always restarting from the last state on the old attractor.  A step is 'jumped'
    when its attractor key is nearer the post-event key than the pre-event key, or when the
    attractor type changes (steady <-> cycle) to the post-event type."""
    a, b = row_a["phi"], row_b["phi"]
    ka, kb = row_a["key"], row_b["key"]
    sa, sb = row_a["type"], row_b["type"]
    hist = []
    if sa != sb and abs(row_a["key"] - row_b["key"]) < 0.01 * prob.theta_ad:
        # steady <-> cycle without a jump (Hopf point): the transients near it are slow;
        # bracket only to 1e-3 and with a shorter time budget per trial
        resolution = max(resolution, 1e-3)
        kw = dict(kw, tmax=400.0 * max(1.0, prob.Le))
    while abs(math.log(b / a)) > resolution:
        m = math.sqrt(a * b)
        res = relax(prob, m, y_a, **kw)
        km = attractor_key(res)
        if sa != sb:
            st = attractor_type(res)     # unsettled near a Hopf point: growing = cycle side
            jumped = (st == sb) if st in (sa, sb) else abs(km - kb) < abs(km - ka)
        else:
            jumped = abs(km - kb) < abs(km - ka)
        hist.append({"phi": m, "status": res["status"], "key": km, "jumped": bool(jumped), "t_end": res["t_end"],
                     "osc": res.get("osc")})
        if verbose:
            print("    bisect phi=%.8g -> %s key=%.6f %s (t=%.4g)%s" % (m, res["status"], km,
                  "JUMP" if jumped else "stay", res["t_end"],
                  (" osc amp %.2e rate %.3g" % (res["osc"]["amplitude"], res["osc"]["amp_growth_rate"])) if "osc" in res else ""),
                  file=sys.stderr)
        if jumped:
            b, kb = m, km
        else:
            a, ka, y_a = m, km, res["y"]
    return {"phi_old_side": a, "phi_new_side": b, "phi_estimate": math.sqrt(a * b),
            "rel_width": abs(b - a) / math.sqrt(a * b),
            "key_old_side": ka, "key_new_side": kb, "gap": kb - ka, "bisection": hist}


def run_sweep(prob, per_decade=None, resolution=5e-5, gap_min=None, kw=None, verbose=False):
    r = prob.r
    kw = kw or {}
    t0 = time.time()
    if not per_decade:      # at least 60 steps per decade and 150 steps per pass
        per_decade = max(60, int(math.ceil(150.0 / math.log10(r["phi_max"] / r["phi_min"]))))
    n = max(8, int(math.ceil(per_decade * math.log10(r["phi_max"] / r["phi_min"]))) + 1)
    grid = np.geomspace(r["phi_min"], r["phi_max"], n)
    phis = np.unique(np.concatenate([grid, np.asarray(r["phi_query"], float)]))
    store_up, store_dn = [], []
    y0 = prob.uniform(0.0, 1.0)            # cold start: bulk-gas state in the layer
    up, y_end = _pass(prob, phis, y0, kw, "up", verbose, store_up)
    dn, _ = _pass(prob, phis[::-1], y_end, kw, "down", verbose, store_dn)   # hot start
    if gap_min is None:
        gap_min = 0.01 * prob.theta_ad
    events = []
    for label, rows, store in (("up", up, store_up), ("down", dn, store_dn)):
        dk = np.abs(np.diff([w["key"] for w in rows]))
        typ = [w["type"] for w in rows]
        smooth = np.median(dk) if dk.size else 0.0
        for i in range(1, len(rows)):
            cand = (dk[i - 1] > gap_min and dk[i - 1] > 4.0 * max(dk[max(0, i - 3):i - 1].max(initial=0.0),
                                                                    dk[i:i + 2].max(initial=0.0), smooth)) \
                or (typ[i] != typ[i - 1])
            if not cand:
                continue
            ev = _bisect(prob, rows[i - 1], store[i - 1], rows[i], kw, resolution, verbose)
            ev["direction"] = label
            ev["from"] = rows[i - 1]["type"]
            ev["to"] = rows[i]["type"]
            ev["coarse_bracket"] = [rows[i - 1]["phi"], rows[i]["phi"]]
            ev["is_jump"] = bool(abs(ev["gap"]) > gap_min)
            if ev["from"] != ev["to"]:
                kind = "onset_of_oscillation" if ev["to"] == "cycle" else (
                    "end_of_oscillation" if ev["from"] == "cycle" else "status_change")
            else:
                kind = None
            if ev["is_jump"]:
                kind = ("ignition" if ev["gap"] > 0 else "extinction") + ("" if kind is None else "+" + kind)
            ev["kind"] = kind or "steep_continuous"
            events.append(ev)
    queries = []
    for q in r["phi_query"]:
        iu = int(np.argmin(np.abs(np.array([w["phi"] for w in up]) - q)))
        idn = int(np.argmin(np.abs(np.array([w["phi"] for w in dn]) - q)))
        queries.append({"phi": q, "up": up[iu], "down": dn[idn],
                        "same_attractor": bool(abs(up[iu]["key"] - dn[idn]["key"]) < 1e-4 * max(1.0, abs(up[iu]["key"]))
                                               and up[iu]["status"] == dn[idn]["status"])})
    out = {"recipe_id": r["recipe_id"], "cells": prob.N, "cluster_a": prob.g.a, "h_min": float(prob.g.h.min()),
           "h_max": float(prob.g.h.max()), "steps_per_pass": int(len(phis)),
           "step_ratio": float(grid[1] / grid[0]), "bisection_resolution_ln_phi": resolution,
           "gap_min_theta_c": gap_min, "events": events, "queries": queries, "up": up, "down": dn,
           "n_unresolved_steps": int(sum(w["status"] not in ("steady", "cycle") for w in up + dn)),
           "n_cycle_steps": int(sum(w["status"] == "cycle" for w in up + dn)),
           "wall_s": time.time() - t0}
    states = {"phi_up": np.array([w["phi"] for w in up]), "Y_up": np.array(store_up),
              "phi_down": np.array([w["phi"] for w in dn]), "Y_down": np.array(store_dn),
              "cells": prob.N, "cluster_a": prob.g.a}
    return out, states


def print_sweep(out):
    print("sweep %s N=%d a=%.3f (h %.2e..%.2e) steps/pass=%d ratio=%.4f  %.1fs" % (
        out["recipe_id"], out["cells"], out["cluster_a"], out["h_min"], out["h_max"], out["steps_per_pass"],
        out["step_ratio"], out["wall_s"]))
    for e in out["events"]:
        print("  %-5s %-34s phi in [%.7g, %.7g] (rel %.1e)  key %.5f -> %.5f  [%s -> %s]" % (
            e["direction"], e["kind"], min(e["phi_old_side"], e["phi_new_side"]), max(e["phi_old_side"], e["phi_new_side"]),
            e["rel_width"], e["key_old_side"], e["key_new_side"], e["from"], e["to"]))
    for q in out["queries"]:
        u, d = q["up"], q["down"]
        def f(w):
            if w["status"] == "cycle":
                return "cycle mean %.6f pp %.5f P %.5f" % (w["cycle"]["theta_c_mean"], w["cycle"]["amplitude_pp"], w["cycle"]["period"])
            return "%s thc=%.7f eta=%.7f" % (w["status"], w["theta_c"], w["eta"])
        print("  q=%-8g up: %-44s | down: %s" % (q["phi"], f(u), f(d)))
    print("  unresolved steps %d, cycle steps %d" % (out["n_unresolved_steps"], out["n_cycle_steps"]))


# ----------------------------------------------------------------------------- probe


def same(a, b):
    if a["type"] != b["type"]:
        return False
    if a["type"] == "steady":
        return abs(a["theta_c"] - b["theta_c"]) < 1e-4 * max(1.0, abs(a["theta_c"])) and \
            abs(a["eta"] - b["eta"]) < 1e-4 * max(1.0, abs(a["eta"]))
    return abs(a["theta_c_mean"] - b["theta_c_mean"]) < 2e-3 * max(1.0, abs(a["theta_c_mean"])) and \
        abs(a["period"] - b["period"]) < 1e-2 * a["period"]


def run_probe(prob, phi, ntheta=7, nc=5, extra=None, kw=None, verbose=False):
    kw = kw or {}
    t0 = time.time()
    inits = [("uniform", float(th), float(c), prob.uniform(th, c))
             for th in np.linspace(0.0, prob.theta_ad, ntheta) for c in np.linspace(0.0, 1.0, nc)]
    for lab, y in (extra or []):
        inits.append((lab, None, None, y))
    atts, runs = [], []
    for lab, th, c, y in inits:
        res = relax(prob, phi, y, **kw)
        run = {"init": lab, "theta0": th, "c0": c, "status": res["status"], "theta_c": res["theta_c"],
               "eta": res["eta"], "t_end": res["t_end"], "resid": res["resid"], "wall_s": res["wall_s"]}
        if res["status"] == "steady":
            a = {"type": "steady", "theta_c": res["theta_c"], "eta": res["eta"], "resid": res["resid"]}
        elif res["status"] == "cycle":
            cy = res["cycle"]
            a = {"type": "cycle", "theta_c_mean": cy["theta_c_mean"], "theta_c_min": cy["theta_c_min"],
                 "theta_c_max": cy["theta_c_max"], "amplitude_pp": cy["amplitude_pp"], "period": cy["period"],
                 "omega": cy["omega"], "eta_mean": cy["eta_mean"]}
            run["cycle"] = cy
        else:
            a = None
        runs.append(run)
        if verbose:
            print("   probe phi=%g init=%s th0=%s c0=%s -> %s %.6f (%.1fs)" % (
                phi, lab, th, c, res["status"], attractor_key(res), res["wall_s"]), file=sys.stderr)
        if a is None:
            continue
        for b in atts:
            if same(a, b):
                b["n_basin"] += 1
                b["inits"].append(lab if th is None else [round(th, 6), round(c, 6)])
                break
        else:
            a["n_basin"] = 1
            a["inits"] = [lab if th is None else [round(th, 6), round(c, 6)]]
            atts.append(a)
    atts.sort(key=lambda q: q.get("theta_c", q.get("theta_c_mean")))
    return {"phi": phi, "n_runs": len(runs), "n_unresolved": int(sum(q["status"] not in ("steady", "cycle") for q in runs)),
            "attractors": atts, "n_steady_attractors": int(sum(a["type"] == "steady" for a in atts)),
            "n_cycle_attractors": int(sum(a["type"] == "cycle" for a in atts)), "runs": runs,
            "wall_s": time.time() - t0}


def print_probe(p):
    print("probe phi=%g: %d runs, %d unresolved, %d steady + %d cycle attractors (%.1fs)" % (
        p["phi"], p["n_runs"], p["n_unresolved"], p["n_steady_attractors"], p["n_cycle_attractors"], p["wall_s"]))
    for a in p["attractors"]:
        if a["type"] == "steady":
            print("    steady thc=%.7f eta=%.7f  basin %d/%d" % (a["theta_c"], a["eta"], a["n_basin"], p["n_runs"]))
        else:
            print("    cycle  thc mean=%.6f [%.5f, %.5f] P=%.6f omega=%.4f eta mean=%.6f  basin %d/%d" % (
                a["theta_c_mean"], a["theta_c_min"], a["theta_c_max"], a["period"], a["omega"], a["eta_mean"],
                a["n_basin"], p["n_runs"]))


# ----------------------------------------------------------------------------- io / commands


def jsonable(o):
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items() if not isinstance(v, np.ndarray) or v.ndim == 0}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def dump(path, obj):
    if path:
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(jsonable(obj), fh, indent=1)


def kw_from(args):
    kw = {"method": args.method, "rtol": args.rtol, "atol": args.atol, "ss_tol": args.ss_tol}
    if args.tmax:
        kw["tmax"] = args.tmax
    return kw


def load_state(path, branch, phi, prob):
    z = np.load(path)
    if int(z["cells"]) != prob.N or abs(float(z["cluster_a"]) - prob.g.a) > 1e-12:
        raise SystemExit("state file grid (N=%d, a=%g) differs from this grid" % (int(z["cells"]), float(z["cluster_a"])))
    ph = z["phi_" + branch]
    k = int(np.argmin(np.abs(np.log(ph / phi))))
    return z["Y_" + branch][k], float(ph[k])


def pencil(t, d, M):
    """matrix-pencil estimate of M exponents lambda in d(t) ~ sum A_k exp(lambda_k t)"""
    dt = t[1] - t[0]
    n = len(d)
    L = n // 3
    Y = np.array([d[i:i + L + 1] for i in range(n - L)])
    Y0, Y1 = Y[:, :-1], Y[:, 1:]
    U, sv, Vh = np.linalg.svd(Y0, full_matrices=False)
    M = min(M, int(np.sum(sv > 1e-10 * sv[0])))
    A = np.diag(1.0 / sv[:M]) @ U[:, :M].T @ Y1 @ Vh[:M].T
    z = np.linalg.eigvals(A)
    lam = np.log(z.astype(complex)) / dt
    V = np.exp(np.outer(t - t[0], lam))
    amp = np.linalg.lstsq(V, d.astype(complex), rcond=None)[0]
    return lam, amp


def trace_departure(prob, phi, ybase, y0, T, method, rtol, atol, kick_growth=1e3, modes=3):
    """Integrate the kicked and the un-kicked state over [0, T]; fit the exponents of the
    difference in theta_c while it is still small (linear regime)."""
    te = np.linspace(0.0, T, 8001)
    kw = dict(method=method, jac=prob.jac, args=(phi,), rtol=rtol, atol=atol, t_eval=te)
    s1 = solve_ivp(prob.rhs, (0.0, T), y0, **kw)
    s0 = solve_ivp(prob.rhs, (0.0, T), ybase, **kw)
    d = prob.theta_c(s1.y) - prob.theta_c(s0.y)
    k0 = abs(prob.theta_c(y0) - prob.theta_c(ybase)) or 1e-12
    big = np.nonzero(np.abs(d) > kick_growth * k0)[0]
    i1 = int(big[0]) if big.size else len(te) - 1
    i0 = max(1, i1 // 10)
    out = {"trace": {"t": te[::20].tolist(), "dtheta_c": d[::20].tolist()},
           "trace_window": [float(te[i0]), float(te[i1])]}
    if i1 - i0 >= 60:
        step = max(1, (i1 - i0) // 400)
        tt, dd = te[i0:i1 + 1:step], d[i0:i1 + 1:step]
        lam, amp = pencil(tt, dd, modes)
        order = np.argsort(-lam.real)
        modes = []
        for k in order:
            if lam[k].imag < -1e-9:
                continue
            modes.append({"re": float(lam[k].real), "im": float(abs(lam[k].imag)), "abs_amp": float(abs(amp[k]))})
        out["trace_modes"] = modes
    return out


def cmd_relax(a):
    r = load_recipe(a.recipe)
    prob = Problem(r, a.cells, a.cluster)
    if a.state:
        y0, phs = load_state(a.state, a.branch, a.phi, prob)
        src = "state of %s branch at phi=%.8g from %s" % (a.branch, phs, a.state)
    else:
        y0 = prob.uniform(a.theta0, a.c0)
        src = "uniform theta=%g c=%g" % (a.theta0, a.c0)
    ybase = y0.copy()
    if a.perturb:
        y0 = y0.copy()
        y0[0::2] += a.perturb
    res = relax(prob, a.phi, y0, verbose=a.verbose, **kw_from(a))
    res["initial"] = src
    res["cells"], res["cluster_a"] = prob.N, prob.g.a
    print("relax %s phi=%g N=%d from %s: %s at t=%.5g  theta_c=%.8f eta=%.8f resid=%.2e steps=%d (%.1fs)" % (
        r["recipe_id"], a.phi, prob.N, src, res["status"], res["t_end"], res["theta_c"], res["eta"], res["resid"],
        res["n_steps"], res["wall_s"]))
    if "cycle" in res:
        c = res["cycle"]
        print("  limit cycle: period=%.6f omega=%.5f theta_c mean=%.6f min=%.6f max=%.6f pp=%.6f eta mean=%.6f" % (
            c["period"], c["omega"], c["theta_c_mean"], c["theta_c_min"], c["theta_c_max"], c["amplitude_pp"], c["eta_mean"]))
    if a.trace:
        res.update(trace_departure(prob, a.phi, ybase, y0, a.trace, a.method, a.rtol, a.atol))
        tf = res.get("trace_modes")
        if tf:
            print("  early departure (base-subtracted theta_c, matrix pencil on t in [%.4g, %.4g]):" % tuple(res["trace_window"]))
            for md in tf:
                print("    lambda = %+.5g %+.5gi   |amplitude| %.3e" % (md["re"], md["im"], md["abs_amp"]))
    dump(a.out, res)


def cmd_kick(a):
    """Steady state of a companion recipe with the same steady parameters but a Lewis number at
    which the state is an attractor (steady states do not depend on Le): relax there at the
    exact phi from the nearest saved sweep state, then kick theta uniformly and follow the
    departure under the target recipe's Le."""
    r = load_recipe(a.recipe)
    rb = load_recipe(a.base_recipe)
    for k in ("beta", "gamma", "Bi_m", "Bi_h"):
        if float(r[k]) != float(rb[k]):
            raise SystemExit("base recipe differs in %s" % k)
    pb = Problem(rb, a.cells, a.cluster)
    prob = Problem(r, a.cells, pb.g.a)
    y0, phs = load_state(a.state, a.branch, a.phi, pb)
    rel = relax(pb, a.phi, y0, ss_tol=1e-10, rtol=1e-9, atol=1e-13, method=a.method)
    if rel["status"] != "steady":
        raise SystemExit("base relaxation did not settle: %s" % rel["status"])
    yb = rel["y"]
    yk = yb.copy()
    yk[0::2] += a.kick
    out = {"recipe_id": r["recipe_id"], "base_recipe_id": rb["recipe_id"], "phi": a.phi, "cells": prob.N,
           "cluster_a": prob.g.a, "base_state": {"theta_c": rel["theta_c"], "eta": rel["eta"], "resid": rel["resid"],
                                                 "Le_base": pb.Le, "from_sweep_phi": phs},
           "kick": a.kick}
    out.update(trace_departure(prob, a.phi, yb, yk, a.trace, a.method, a.rtol, a.atol, modes=a.modes))
    print("kick %s phi=%.6g on steady state of %s (theta_c=%.7f eta=%.7f) kick %.1e:" % (
        r["recipe_id"], a.phi, rb["recipe_id"], rel["theta_c"], rel["eta"], a.kick))
    for md in out.get("trace_modes", []):
        print("    lambda = %+.5g %+.5gi   |amplitude| %.3e" % (md["re"], md["im"], md["abs_amp"]))
    if a.follow:
        fin = relax(prob, a.phi, yk, method=a.method, rtol=1e-7, atol=1e-11)
        out["fate"] = {k: fin[k] for k in ("status", "theta_c", "eta", "t_end")}
        if "cycle" in fin:
            out["fate"]["cycle"] = fin["cycle"]
        print("  fate under Le=%g: %s theta_c=%.6f%s" % (prob.Le, fin["status"], fin["theta_c"],
              (" period=%.5f omega=%.4f pp=%.5f" % (fin["cycle"]["period"], fin["cycle"]["omega"], fin["cycle"]["amplitude_pp"])) if "cycle" in fin else ""))
    dump(a.out, out)


def cmd_sweep(a):
    r = load_recipe(a.recipe)
    prob = Problem(r, a.cells, a.cluster)
    out, states = run_sweep(prob, a.per_decade, a.resolution, kw=kw_from(a), verbose=a.verbose)
    print_sweep(out)
    dump(a.out, out)
    if a.save_states:
        np.savez_compressed(a.save_states, **states)


def cmd_probe(a):
    r = load_recipe(a.recipe)
    prob = Problem(r, a.cells, a.cluster)
    res = []
    for phi in (a.phi or r["phi_query"]):
        extra = []
        if a.extra:
            for br in ("up", "down"):
                y, phs = load_state(a.extra, br, phi, prob)
                extra.append(("sweep_%s@%.6g" % (br, phs), y))
        p = run_probe(prob, phi, a.ntheta, a.nc, extra, kw_from(a), a.verbose)
        print_probe(p)
        res.append(p)
    dump(a.out, {"recipe_id": r["recipe_id"], "cells": prob.N, "cluster_a": prob.g.a, "probes": res})


def cmd_summary(a):
    r = load_recipe(a.recipe)
    prob = Problem(r, a.cells, a.cluster)
    os.makedirs(a.outdir, exist_ok=True)
    tag = "N%d" % prob.N
    kw = kw_from(a)
    T0 = time.time()
    sw, states = run_sweep(prob, a.per_decade, a.resolution, kw=kw, verbose=a.verbose)
    print_sweep(sw)
    sys.stdout.flush()
    dump(os.path.join(a.outdir, "sweep_%s.json" % tag), sw)
    np.savez_compressed(os.path.join(a.outdir, "states_%s.npz" % tag), **states)
    probes = []
    for phi in r["phi_query"]:
        extra = []
        for br in ("up", "down"):
            ph = states["phi_" + br]
            k = int(np.argmin(np.abs(np.log(ph / phi))))
            extra.append(("sweep_%s" % br, states["Y_" + br][k]))
        p = run_probe(prob, phi, a.ntheta, a.nc, extra, dict(kw, rtol=a.probe_rtol), a.verbose)
        print_probe(p)
        sys.stdout.flush()
        probes.append(p)
    dump(os.path.join(a.outdir, "probe_%s.json" % tag), {"recipe_id": r["recipe_id"], "probes": probes})
    # condensed summary
    summ = {"recipe_id": r["recipe_id"], "recipe": {k: r[k] for k in r if k != "recipe_id"},
            "cells": prob.N, "cluster_a": prob.g.a, "h_min": sw["h_min"],
            "integrator": dict(kw, probe_rtol=a.probe_rtol), "sweep_step_ratio": sw["step_ratio"],
            "bisection_resolution_ln_phi": sw["bisection_resolution_ln_phi"],
            "events": [{k: e[k] for k in ("direction", "kind", "phi_old_side", "phi_new_side", "phi_estimate",
                                           "rel_width", "key_old_side", "key_new_side", "from", "to")}
                       for e in sw["events"]],
            "ignition_phi": [e["phi_estimate"] for e in sw["events"] if e["kind"].startswith("ignition")],
            "extinction_phi": [e["phi_estimate"] for e in sw["events"] if e["kind"].startswith("extinction")],
            "oscillation_onsets": [{"direction": e["direction"], "phi": e["phi_estimate"]} for e in sw["events"]
                                   if "oscillation" in e["kind"]],
            "n_cycle_steps_in_sweep": sw["n_cycle_steps"], "n_unresolved_steps_in_sweep": sw["n_unresolved_steps"],
            "queries": []}
    for q, p in zip(sw["queries"], probes):
        ent = {"phi": q["phi"], "n_attractors": len(p["attractors"]),
               "n_steady_attractors": p["n_steady_attractors"], "n_cycle_attractors": p["n_cycle_attractors"],
               "attractors": [{k: v for k, v in at.items() if k != "inits"} for at in p["attractors"]],
               "sweep_up": {k: q["up"][k] for k in ("status", "theta_c", "eta")},
               "sweep_down": {k: q["down"][k] for k in ("status", "theta_c", "eta")},
               "probe_unresolved_runs": p["n_unresolved"], "probe_runs": p["n_runs"]}
        for lab in ("up", "down"):
            if q[lab]["status"] == "cycle":
                ent["sweep_" + lab]["cycle"] = q[lab]["cycle"]
        summ["queries"].append(ent)
    summ["wall_s"] = {"sweep": sw["wall_s"], "probe": sum(p["wall_s"] for p in probes), "total": time.time() - T0}
    dump(os.path.join(a.outdir, "summary_%s.json" % tag), summ)
    print("summary written, total %.1fs" % summ["wall_s"]["total"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--recipe", required=True)
        p.add_argument("--cells", type=int, default=200)
        p.add_argument("--cluster", type=float, default=None, help="sinh clustering a (0 uniform; default auto)")
        p.add_argument("--method", default="BDF", choices=["BDF", "Radau", "LSODA"])
        p.add_argument("--rtol", type=float, default=1e-8)
        p.add_argument("--atol", type=float, default=1e-11)
        p.add_argument("--ss-tol", type=float, default=1e-9, dest="ss_tol",
                       help="steady when max|f|/max(1,phi^2) < this (theta rows times Le)")
        p.add_argument("--tmax", type=float, default=None, help="per relaxation (default 3000 max(1,Le))")
        p.add_argument("--out", default=None)
        p.add_argument("--verbose", action="store_true")

    p = sub.add_parser("relax")
    common(p)
    p.add_argument("--phi", type=float, required=True)
    p.add_argument("--theta0", type=float, default=0.0)
    p.add_argument("--c0", type=float, default=1.0)
    p.add_argument("--state", default=None, help="npz from sweep --save-states")
    p.add_argument("--branch", default="down", choices=["up", "down"])
    p.add_argument("--perturb", type=float, default=0.0, help="add this to theta everywhere at t=0")
    p.add_argument("--trace", type=float, default=0.0, help="also record theta_c deviation over [0, trace]")
    p.set_defaults(fn=cmd_relax)

    for name, fn in (("sweep", cmd_sweep), ("summary", cmd_summary)):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--per-decade", type=int, default=None, dest="per_decade",
                       help="sweep steps per decade of phi (default max(60, 150/decades))")
        p.add_argument("--resolution", type=float, default=5e-5, help="bisection stop, in ln phi")
        if name == "sweep":
            p.add_argument("--save-states", default=None, dest="save_states")
        else:
            p.add_argument("--outdir", required=True)
            p.add_argument("--ntheta", type=int, default=7)
            p.add_argument("--nc", type=int, default=5)
            p.add_argument("--probe-rtol", type=float, default=1e-6, dest="probe_rtol")
        p.set_defaults(fn=fn)

    p = sub.add_parser("kick")
    common(p)
    p.add_argument("--phi", type=float, required=True)
    p.add_argument("--base-recipe", required=True, dest="base_recipe")
    p.add_argument("--state", required=True, help="sweep states npz of the base recipe")
    p.add_argument("--branch", default="down", choices=["up", "down"])
    p.add_argument("--kick", type=float, default=1e-8)
    p.add_argument("--trace", type=float, default=1.2)
    p.add_argument("--modes", type=int, default=3)
    p.add_argument("--follow", action="store_true", help="also relax the kicked state to its attractor")
    p.set_defaults(fn=cmd_kick)

    p = sub.add_parser("probe")
    common(p)
    p.add_argument("--phi", type=float, nargs="*", default=None)
    p.add_argument("--ntheta", type=int, default=7)
    p.add_argument("--nc", type=int, default=5)
    p.add_argument("--extra", default=None, help="npz of sweep states: also start from both sweep branches")
    p.set_defaults(fn=cmd_probe)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
