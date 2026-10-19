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
        """LAPACK packed band form, lband = uband = 2: B[2 + i - j, j] = J[i, j]"""
        B = np.zeros((5, self.n))
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


def _extrema(t, s):
    i = np.arange(1, len(s) - 1)
    mx = i[(s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:])]
    mn = i[(s[1:-1] < s[:-2]) & (s[1:-1] <= s[2:])]
    return mx, mn


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


def relax(prob, phi, y0, tmax=None, ss_tol=1e-9, rtol=1e-8, atol=1e-11, method="BDF",
          sub=8, w0=None, wmax=None, verbose=False):
    """Integrate from y0 until (a) steady: resid < ss_tol, or (b) a settled limit cycle, or
    (c) t = tmax.  Returns a dict; 'y' is the final state."""
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
    status, nst, cyc = "unresolved", 0, None
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
        fr = np.linspace(0.0, 1.0, sub, endpoint=False)
        tt = np.concatenate([(ts[:-1, None] + np.diff(ts)[:, None] * fr[None, :]).ravel(), ts[-1:]])
        Y = sol.sol(tt)
        s = prob.theta_c(Y)
        y = sol.y[:, -1].copy()
        t = t + W
        r = prob.resid(y, phi)
        if verbose:
            print("   t=%9.3f res=%.2e thc=%.6f steps=%d" % (t, r, s[-1], nst), file=sys.stderr)
        if r < ss_tol:
            status = "steady"
            break
        # limit-cycle test on this window (concatenate with the previous one)
        hist_t = np.concatenate([hist_t, tt[1:] if hist_t.size else tt])
        hist_s = np.concatenate([hist_s, s[1:] if hist_s.size else s])
        if hist_t.size > 400000:
            hist_t, hist_s = hist_t[-200000:], hist_s[-200000:]
        mx, mn = _extrema(hist_t, hist_s)
        if mx.size >= 8 and mn.size >= 7:
            pk = np.array([_parab(hist_t, hist_s, i) for i in mx[-7:]])
            tr = np.array([_parab(hist_t, hist_s, i) for i in mn[-6:]])
            per = np.diff(pk[:, 0])
            amp = pk[1:, 1] - tr[-per.size:, 1] if tr.shape[0] >= per.size else None
            if amp is not None and amp.size and np.all(amp > 1e-7):
                pspread = (per.max() - per.min()) / per.mean()
                aspread = (amp.max() - amp.min()) / amp.mean()
                if pspread < 2e-3 and aspread < 2e-3:
                    status = "cycle"
                    cyc = (sol, pk, per)
                    break
        W = min(2.0 * W, Wmax)
        # if a few periods are already visible, keep windows at ~30 periods
        if mx.size >= 3:
            p_est = float(np.mean(np.diff(hist_t[mx[-3:]])))
            W = min(W, max(30.0 * p_est, 1e-3))
    out = {"phi": float(phi), "status": status, "t_end": float(t), "resid": prob.resid(y, phi),
           "theta_c": float(prob.theta_c(y)), "eta": float(prob.eta(y, phi)), "n_steps": int(nst),
           "wall_s": time.time() - t_wall}
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
    sa, sb = row_a["status"], row_b["status"]
    hist = []
    while abs(math.log(b / a)) > resolution:
        m = math.sqrt(a * b)
        res = relax(prob, m, y_a, **kw)
        km = attractor_key(res)
        if sa != sb:
            jumped = (res["status"] == sb) if res["status"] in (sa, sb) else abs(km - kb) < abs(km - ka)
        else:
            jumped = abs(km - kb) < abs(km - ka)
        hist.append({"phi": m, "status": res["status"], "key": km, "jumped": bool(jumped), "t_end": res["t_end"]})
        if verbose:
            print("    bisect phi=%.8g -> %s key=%.6f %s (t=%.4g)" % (m, res["status"], km,
                                                                    "JUMP" if jumped else "stay", res["t_end"]), file=sys.stderr)
        if jumped:
            b, kb = m, km
        else:
            a, ka, y_a = m, km, res["y"]
    return {"phi_old_side": a, "phi_new_side": b, "phi_estimate": math.sqrt(a * b),
            "rel_width": abs(b - a) / math.sqrt(a * b),
            "key_old_side": ka, "key_new_side": kb, "gap": kb - ka, "bisection": hist}


def run_sweep(prob, per_decade=60, resolution=2e-5, gap_min=None, kw=None, verbose=False):
    r = prob.r
    kw = kw or {}
    t0 = time.time()
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
        typ = [w["status"] for w in rows]
        smooth = np.median(dk) if dk.size else 0.0
        for i in range(1, len(rows)):
            cand = (dk[i - 1] > gap_min and dk[i - 1] > 4.0 * max(dk[max(0, i - 3):i - 1].max(initial=0.0),
                                                                    dk[i:i + 2].max(initial=0.0), smooth)) \
                or (typ[i] != typ[i - 1])
            if not cand:
                continue
            ev = _bisect(prob, rows[i - 1], store[i - 1], rows[i], kw, resolution, verbose)
            ev["direction"] = label
            ev["from"] = rows[i - 1]["status"]
            ev["to"] = rows[i]["status"]
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


def cmd_relax(a):
    r = load_recipe(a.recipe)
    prob = Problem(r, a.cells, a.cluster)
    if a.state:
        y0, phs = load_state(a.state, a.branch, a.phi, prob)
        src = "state of %s branch at phi=%.8g from %s" % (a.branch, phs, a.state)
    else:
        y0 = prob.uniform(a.theta0, a.c0)
        src = "uniform theta=%g c=%g" % (a.theta0, a.c0)
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
        # early-time deviation record: growth rate and frequency of departure from y0
        sol = solve_ivp(prob.rhs, (0.0, a.trace), y0, method=a.method, jac=prob.jac, args=(a.phi,),
                        rtol=a.rtol, atol=a.atol, t_eval=np.linspace(0.0, a.trace, 4001))
        d = prob.theta_c(sol.y) - prob.theta_c(y0)
        res["trace"] = {"t": sol.t[::10].tolist(), "dtheta_c": d[::10].tolist()}
        mx, mn = _extrema(sol.t, np.abs(d))
        pk = np.array([_parab(sol.t, np.abs(d), i) for i in mx]) if mx.size else np.empty((0, 2))
        if pk.shape[0] >= 3:
            g = np.polyfit(pk[:, 0], np.log(pk[:, 1]), 1)[0]
            half = np.mean(np.diff(pk[:, 0]))
            res["trace_fit"] = {"growth_rate": float(g), "omega_from_half_periods": float(math.pi / half),
                                "n_peaks": int(pk.shape[0])}
            print("  early transient: |dtheta_c| peaks grow at rate %.5g, omega ~ %.5g (%d half-cycles)" % (
                g, math.pi / half, pk.shape[0]))
    dump(a.out, res)


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
        p = run_probe(prob, phi, a.ntheta, a.nc, extra, kw, a.verbose)
        print_probe(p)
        sys.stdout.flush()
        probes.append(p)
    dump(os.path.join(a.outdir, "probe_%s.json" % tag), {"recipe_id": r["recipe_id"], "probes": probes})
    # condensed summary
    summ = {"recipe_id": r["recipe_id"], "recipe": {k: r[k] for k in r if k != "recipe_id"},
            "cells": prob.N, "cluster_a": prob.g.a, "h_min": sw["h_min"],
            "integrator": kw, "sweep_step_ratio": sw["step_ratio"],
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
        p.add_argument("--per-decade", type=int, default=60, dest="per_decade")
        p.add_argument("--resolution", type=float, default=2e-5, help="bisection stop, in ln phi")
        if name == "sweep":
            p.add_argument("--save-states", default=None, dest="save_states")
        else:
            p.add_argument("--outdir", required=True)
            p.add_argument("--ntheta", type=int, default=7)
            p.add_argument("--nc", type=int, default=5)
        p.set_defaults(fn=fn)

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
