#!/usr/bin/env python
"""Conservative finite-volume referee solver for the four-anion fixed-bed ion exchange model.

Model (IX_SPEC section 1): for each ion i

    d/dBV [ eps x_i + Lambda y_i(x) ] + d/dxi [ x_i ] = 0,   0 < xi < 1,
    y_i = alpha_i x_i / S,  S = sum_j alpha_j x_j,  sum_i x_i = 1,
    Lambda = 1000 Q / C_T.

Conserved variable w_i = eps x_i + Lambda y_i(x). The flux is the liquid composition x itself
(velocity +1 in xi per BV in the liquid frame), so the scheme is upwind in x. After every update
w -> x is inverted exactly: x_i = w_i / (eps + Lambda alpha_i / S), with S the unique root of
sum_i x_i(S) = 1 on [alpha_min, alpha_max] (safeguarded Newton, |sum x - 1| <= 1e-14).

Scheme: MUSCL reconstruction of x with a cell-wise common limiter (minmod by default; van Leer
optional) so that the reconstructed face compositions sum to one exactly, upwind face flux,
SSP-RK2 (or RK3) in time; --order 1 gives plain first-order upwind with forward Euler. The time step is
CFL * dx / lambda_max with lambda_max the largest characteristic speed actually present in the
bed, 1/(eps + Lambda omega_min/S), omega_min the smallest root of the h-transform equation
sum_i alpha_i x_i / (alpha_i - omega) = 0 (eigenvalue of dy/dx on the simplex).

CLI:
    python fv_referee.py --recipe <recipe.json> --cells N --out <dir>
        [--order 2] [--limiter minmod|vanleer] [--rk 2|3] [--cfl 0.4] [--no-early-exit] [--analyze-only]

Writes <dir>/effluent.npz (bv, c_meq_per_L, final bed profile) and <dir>/summary.json.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]


# ----------------------------------------------------------------------------------------------
# recipe
# ----------------------------------------------------------------------------------------------
class Recipe:
    def __init__(self, path):
        with open(path) as f:
            r = json.load(f)
        if r["ions"] != IONS:
            raise ValueError("unexpected ion list in recipe")
        self.raw = r
        self.recipe_id = r["recipe_id"]
        self.alpha = np.array([float(r["alpha"][k]) for k in IONS])
        self.eps = float(r["eps"])
        self.Q = float(r["Q_eq_per_L_bed"])
        self.CT = float(r["C_T_meq_per_L"])
        self.Lam = 1000.0 * self.Q / self.CT
        self.y0 = np.array([float(r["initial_resin_fraction"][k]) for k in IONS])
        q = self.y0 / self.alpha
        self.x0 = q / q.sum()  # liquid in equilibrium with the initial resin
        feeds = sorted(r["feed_program"], key=lambda e: float(e["start_bv"]))
        self.feed_bv = [float(e["start_bv"]) for e in feeds]
        self.feed_x = [np.array([float(e["composition_meq_per_L"][k]) for k in IONS]) / self.CT
                       for e in feeds]
        self.run_bv = float(r["run_bv"])
        self.sample_bv = [float(v) for v in r["sample_bv"]]
        self.nitrate_limit = float(r["nitrate_limit_meq_per_L"])


# ----------------------------------------------------------------------------------------------
# thermodynamics
# ----------------------------------------------------------------------------------------------
def y_of_x(x, alpha):
    ax = alpha[:, None] * x
    return ax / ax.sum(axis=0)


def w_of_x(x, alpha, eps, Lam):
    return eps * x + Lam * y_of_x(x, alpha)


def invert(w, alpha, eps, Lam, S, tol=1e-14, maxit=60):
    """Invert w -> x for all cells at once (w shape (4, N)); S (N,) is the warm start.

    Solves h(S) = sum_i w_i S / (eps S + Lam alpha_i) - 1 = 0. Every term is increasing and
    concave in S, so h is increasing and concave and Newton converges globally for S > 0
    (monotonically from the right after at most one overshoot). We iterate until
    |h| <= tol (1e-14, about 50 ulp of the unit sum) for every cell; cells that have not
    converged after maxit Newton steps (never observed) are finished by bisection on
    [alpha_min, alpha_max]. Returns x, S and the number of cells that fell back to bisection."""
    La = Lam * alpha[:, None]
    Smin = alpha.min() * (1.0 - 1e-9)
    S = np.maximum(S, Smin)
    nfail = 0
    for _ in range(maxit):
        den = eps * S + La
        t = w / den
        x = S * t
        h = x.sum(axis=0) - 1.0
        if np.abs(h).max() <= tol:
            return x, S, nfail
        dh = (t * (La / den)).sum(axis=0)
        S = np.maximum(S - h / dh, Smin)
    bad = np.flatnonzero(np.abs(h) > tol)
    nfail = int(bad.size)
    lo = np.full(bad.size, Smin)
    hi = np.full(bad.size, alpha.max() * (1.0 + 1e-9))
    wb = w[:, bad]
    for _ in range(200):
        Sm = 0.5 * (lo + hi)
        hm = (wb * Sm / (eps * Sm + La)).sum(axis=0) - 1.0
        lo = np.where(hm < 0.0, Sm, lo)
        hi = np.where(hm >= 0.0, Sm, hi)
        if ((hi - lo) <= 2e-16 * hi).all():
            break
    S[bad] = 0.5 * (lo + hi)
    den = eps * S + La
    x = S * (w / den)
    return x, S, nfail


class OmegaTracker:
    """Tracks, cell by cell, a rigorous lower bound on the smallest eigenvalue omega_min of the
    h-transform equation (so 1/(eps + Lambda*omega/S) is an upper bound on the fastest
    characteristic speed), cheaply enough to be called every time step.

    omega_min lies in [a1, a2] (the two smallest separation factors) and is the root of
    G(om) = (a1-om)(a2-om) * sum_i a_i x_i/(a_i-om), which is smooth on the closed bracket,
    positive left of the root and negative right of it. Cells without the least-preferred ion
    have omega_min = a1 exactly.

    Every call evaluates G at the stored omega. Where G >= 0 the stored value is at or left of
    the root and is kept (a valid lower bound). Where G < 0 the root has moved left and those
    cells (few: the cells a front is crossing) are re-solved to convergence. Every `refresh`
    calls all cells are re-solved so the bound stays tight."""

    def __init__(self, alpha, N, refresh=20):
        order = np.argsort(alpha)
        self.a1 = alpha[order[0]]
        self.a2 = alpha[order[1]]
        self.i1 = order[0]
        self.i2 = order[1]
        self.rest = order[2:]
        self.rest_a = alpha[self.rest][:, None]
        self.om = np.full(N, self.a1)
        self.refresh = refresh
        self.calls = 0
        self.fallbacks = 0
        self.exact_fixes = 0
        self.fresh = np.zeros(N, dtype=bool)

    def _G(self, om, x1, x2, rest_ax):
        P = (self.a1 - om) * (self.a2 - om)
        R = (rest_ax / (self.rest_a - om)).sum(axis=0)
        return self.a1 * x1 * (self.a2 - om) + self.a2 * x2 * (self.a1 - om) + P * R

    def _solve(self, om, x1, x2, rest_ax, maxit=60, tol=1e-10):
        a1, a2 = self.a1, self.a2
        present = x1 > 0.0
        om = np.where(present, np.clip(om, a1, a2), a1)
        moving = present.copy()
        for _ in range(maxit):
            P = (a1 - om) * (a2 - om)
            dP = 2.0 * om - a1 - a2
            q = rest_ax / (self.rest_a - om)
            R = q.sum(axis=0)
            dR = (q / (self.rest_a - om)).sum(axis=0)
            G = a1 * x1 * (a2 - om) + a2 * x2 * (a1 - om) + P * R
            dG = -a1 * x1 - a2 * x2 + dP * R + P * dR
            step = np.where(moving, G / dG, 0.0)
            step[~np.isfinite(step)] = 0.0
            omn = np.clip(om - step, a1, a2)
            moving = moving & (np.abs(omn - om) > tol)
            om = omn
            if not moving.any():
                break
        G = self._G(om, x1, x2, rest_ax)
        scale = a1 * x1 * (a2 - a1) + a2 * x2 * (a2 - a1) + (a2 - a1) ** 2 * np.abs(rest_ax).sum(axis=0)
        bad = np.flatnonzero(present & (moving | (np.abs(G) > 1e-9 * scale)))
        if bad.size:
            self.fallbacks += int(bad.size)
            lo = np.full(bad.size, a1)
            hi = np.full(bad.size, a2)
            for _ in range(100):
                m = 0.5 * (lo + hi)
                Gm = self._G(m, x1[bad], x2[bad], rest_ax[:, bad])
                lo = np.where(Gm > 0.0, m, lo)
                hi = np.where(Gm <= 0.0, m, hi)
                if ((hi - lo) <= 1e-13).all():
                    break
            om[bad] = lo  # lower end of the final bracket: a rigorous lower bound
        return om

    def _halve_to_bound(self, om, x1, x2, rest_ax):
        """Cells whose root moved left of the stored value (G(om) < 0): halve the distance to a1
        (where G >= 0 always) until G >= 0. Cheap and rigorous; the result is only a bound, and
        is refined exactly in lambda_max if it turns out to set the time step."""
        for _ in range(60):
            G = self._G(om, x1, x2, rest_ax)
            right = G < 0.0
            if not right.any():
                break
            om = np.where(right, 0.5 * (om + self.a1), om)
        return om

    def update(self, x):
        """Returns (om, fresh): om[j] <= omega_min(x_j) for every cell; fresh[j] True where
        om[j] is the root to 1e-9 relative (so 1/(eps+Lambda om/S) is the exact speed there)."""
        x1 = x[self.i1]
        x2 = x[self.i2]
        rest_ax = self.rest_a * x[self.rest]
        self.calls += 1
        if self.calls % self.refresh == 1:
            self.om = self._solve(self.om, x1, x2, rest_ax)
            self.fresh = np.ones(self.om.shape, dtype=bool)
            return self.om, self.fresh
        G = self._G(self.om, x1, x2, rest_ax)
        absent = x1 <= 0.0
        if absent.any():
            self.om = np.where(absent, self.a1, self.om)
            G = np.where(absent, 0.0, G)
        scale = (self.a2 - self.a1) * (self.a1 * x1 + self.a2 * x2 + (self.a2 - self.a1) * np.abs(rest_ax).sum(axis=0))
        fresh = np.abs(G) <= 1e-9 * scale
        moved = np.flatnonzero(G < 0.0)
        if moved.size:
            self.om[moved] = self._halve_to_bound(self.om[moved], x1[moved], x2[moved], rest_ax[:, moved])
            fresh[moved] = False
        self.fresh = fresh
        return self.om, fresh

    def solve_cell(self, x, j):
        """Exact root for one cell, in scalar Python arithmetic (microseconds): bracketing
        Newton on G with bisection fallback, to 1e-12 absolute."""
        a1, a2 = float(self.a1), float(self.a2)
        x1 = float(x[self.i1, j])
        x2 = float(x[self.i2, j])
        if x1 <= 0.0:
            return a1
        rest = [(float(a), float(a) * float(x[i, j])) for a, i in zip(self.rest_a[:, 0], self.rest)]
        lo, hi = a1, a2
        om = min(max(float(self.om[j]), a1), a2)
        for _ in range(100):
            P = (a1 - om) * (a2 - om)
            dP = 2.0 * om - a1 - a2
            R = 0.0
            dR = 0.0
            for a, ax in rest:
                q = ax / (a - om)
                R += q
                dR += q / (a - om)
            G = a1 * x1 * (a2 - om) + a2 * x2 * (a1 - om) + P * R
            dG = -a1 * x1 - a2 * x2 + dP * R + P * dR
            if G > 0.0:
                lo = om
            elif G < 0.0:
                hi = om
            else:
                return om
            if hi - lo <= 1e-12:
                return lo
            omn = om - G / dG if dG != 0.0 else 0.5 * (lo + hi)
            if not (lo < omn < hi):
                omn = 0.5 * (lo + hi)
            if abs(omn - om) <= 1e-12:
                return omn
            om = omn
        return lo


def omega_min(x, alpha, om=None):
    """Converged smallest eigenvalue per cell (convenience wrapper used by tests)."""
    tr = OmegaTracker(alpha, x.shape[1])
    if om is not None:
        tr.om = np.array(om, dtype=float)
    return tr._solve(tr.om, x[tr.i1], x[tr.i2], tr.rest_a * x[tr.rest])


def lambda_max(x, S, alpha, eps, Lam, tracker):
    """Largest characteristic speed in the bed (exact at the cell that attains it; rigorous upper
    bound elsewhere)."""
    om, fresh = tracker.update(x)
    lam = 1.0 / (eps + Lam * om / S)
    for _ in range(12):
        j = int(np.argmax(lam))
        if fresh[j]:
            break
        om[j] = tracker.solve_cell(x, j)
        fresh[j] = True
        tracker.exact_fixes += 1
        lam[j] = 1.0 / (eps + Lam * om[j] / S[j])
    return float(lam.max())


# ----------------------------------------------------------------------------------------------
# spatial discretisation
# ----------------------------------------------------------------------------------------------
def right_face_values(x, xF, order, limiter, tiny=1e-12):
    """Upwind (right-face) composition of every cell; x (4, N), inlet composition xF (4,).

    Second order: MUSCL with one limiter value per cell, phi = min over ions of the per-ion
    limiter phi_k(r_k), r_k = dL_k/dR_k (minmod: max(0, min(1, r)); van Leer: (r+|r|)/(1+|r|)).
    Because the same factor multiplies every ion's forward difference, and the forward
    differences sum to zero, the face compositions sum to one exactly. Ions whose forward
    difference is below `tiny` do not constrain the cell; a cell in which no ion varies beyond
    `tiny` is reconstructed piecewise constant. Left ghost = inlet composition; right ghost =
    linear extrapolation (so the outlet face is second-order accurate)."""
    if order == 1:
        return x
    xl = np.concatenate([xF[:, None], x[:, :-1]], axis=1)
    xr = np.concatenate([x[:, 1:], (2.0 * x[:, -1] - x[:, -2])[:, None]], axis=1)
    dL = x - xl
    dR = xr - x
    r = dL / dR
    if limiter == "minmod":
        phik = np.clip(r, 0.0, 1.0)
    else:
        ar = np.abs(r)
        phik = (r + ar) / (1.0 + ar)
    constrains = np.abs(dR) > tiny
    phik = np.where(constrains, phik, 2.0)
    phi = phik.min(axis=0)
    # a cell in which no ion varies beyond roundoff gets phi = 0 (plain upwind for the noise);
    # phi = 2 there would be a downwind reconstruction of roundoff noise and is unstable
    phi = np.where(constrains.any(axis=0), phi, 0.0)
    return x + 0.5 * phi * dR


def divergence(x, xF, dx, order, limiter):
    xR = right_face_values(x, xF, order, limiter)
    xLf = np.concatenate([xF[:, None], xR[:, :-1]], axis=1)
    return (xR - xLf) / dx, xR[:, -1]


# ----------------------------------------------------------------------------------------------
# time integration
# ----------------------------------------------------------------------------------------------
def solve(rec, N, order=2, limiter="minmod", rk=2, cfl=0.4, early_exit=True, verbose=True,
          snap_bv=()):
    alpha, eps, Lam = rec.alpha, rec.eps, rec.Lam
    dx = 1.0 / N
    old_err = np.seterr(divide="ignore", invalid="ignore")
    x = np.repeat(rec.x0[:, None], N, axis=1)
    w = w_of_x(x, alpha, eps, Lam)
    S = (alpha[:, None] * x).sum(axis=0)
    tracker = OmegaTracker(alpha, N)
    W0 = w.sum(axis=1) * dx

    feed_idx = 0
    xF = rec.feed_x[0].copy()
    pending = [bv for bv in rec.feed_bv[1:]]
    snaps = {}
    snap_pending = sorted(float(b) for b in snap_bv if 0.0 < float(b) <= rec.run_bv)

    t = 0.0
    step = 0
    cap = 200000
    hist_bv = np.empty(cap)
    hist_c = np.empty((cap, 4))
    hist_cc = np.empty((cap, 4))
    nh = 0

    def record(tt, xout, xcell):
        nonlocal hist_bv, hist_c, hist_cc, nh, cap
        if nh >= cap:
            cap *= 2
            hist_bv = np.concatenate([hist_bv, np.empty(cap - nh)])
            hist_c = np.concatenate([hist_c, np.empty((cap - nh, 4))], axis=0)
            hist_cc = np.concatenate([hist_cc, np.empty((cap - nh, 4))], axis=0)
        hist_bv[nh] = tt
        hist_c[nh] = xout
        hist_cc[nh] = xcell
        nh += 1

    inflow = np.zeros(4)
    outflow = np.zeros(4)
    dt_min, dt_max = np.inf, 0.0
    nfail_total = 0
    steady_bv = None
    switch_log = []
    t0 = time.time()
    run_bv = rec.run_bv

    while t < run_bv * (1.0 - 1e-13):
        lam = lambda_max(x, S, alpha, eps, Lam, tracker)
        dt = cfl * dx / lam
        t_next = run_bv
        if pending:
            t_next = min(t_next, pending[0])
        if snap_pending:
            t_next = min(t_next, snap_pending[0])
        if t + dt >= t_next * (1.0 - 1e-14):
            dt = t_next - t
        xcell0 = x[:, -1].copy()
        if rk == 2 or order == 1:
            if order == 1:
                div1, out1 = divergence(x, xF, dx, 1, limiter)
                w = w - dt * div1
                x, S, nf = invert(w, alpha, eps, Lam, S)
                nfail_total += nf
                out_avg = out1
            else:
                div1, out1 = divergence(x, xF, dx, order, limiter)
                w1 = w - dt * div1
                x1, S1, nf1 = invert(w1, alpha, eps, Lam, S)
                div2, out2 = divergence(x1, xF, dx, order, limiter)
                w2 = w1 - dt * div2
                w = 0.5 * (w + w2)
                x, S, nf2 = invert(w, alpha, eps, Lam, S1)
                nfail_total += nf1 + nf2
                out_avg = 0.5 * (out1 + out2)
        else:  # SSP-RK3 (Shu-Osher)
            div1, out1 = divergence(x, xF, dx, order, limiter)
            w1 = w - dt * div1
            x1, S1, nf1 = invert(w1, alpha, eps, Lam, S)
            div2, out2 = divergence(x1, xF, dx, order, limiter)
            w2 = 0.75 * w + 0.25 * (w1 - dt * div2)
            x2, S2, nf2 = invert(w2, alpha, eps, Lam, S1)
            div3, out3 = divergence(x2, xF, dx, order, limiter)
            w = (w + 2.0 * (w2 - dt * div3)) / 3.0
            x, S, nf3 = invert(w, alpha, eps, Lam, S2)
            nfail_total += nf1 + nf2 + nf3
            out_avg = (out1 + out2 + 4.0 * out3) / 6.0
        record(t, out1, xcell0)
        inflow += dt * xF
        outflow += dt * out_avg
        t += dt
        step += 1
        dt_min = min(dt_min, dt)
        dt_max = max(dt_max, dt)
        if snap_pending and abs(t - snap_pending[0]) <= 1e-12 * run_bv:
            t = snap_pending[0]
            snaps[snap_pending.pop(0)] = x.copy()
        if pending and abs(t - pending[0]) <= 1e-12 * run_bv:
            t = pending[0]
            pending.pop(0)
            feed_idx += 1
            xF = rec.feed_x[feed_idx].copy()
            switch_log.append({"bv": t, "step": step})
            if verbose:
                print(f"  feed switch at BV={t:.6g} (step {step})", flush=True)
        if verbose and step % 20000 == 0:
            print(f"  step {step:8d}  BV={t:10.4f}  dt={dt:.3e}  lam_max={lam:.4e}  "
                  f"{time.time() - t0:7.1f}s", flush=True)
        if early_exit and not pending and not snap_pending and step % 50 == 0:
            if np.abs(x - xF[:, None]).max() < 1e-12:
                steady_bv = t
                _, xout = divergence(x, xF, dx, order, limiter)
                record(t, xout, x[:, -1])
                inflow += (run_bv - t) * xF
                outflow += (run_bv - t) * xout
                t = run_bv
                if verbose:
                    print(f"  bed uniform at feed composition (max dev < 1e-12) at BV={steady_bv:.4f}; "
                          f"effluent constant to run_bv", flush=True)
                break
    _, xout = divergence(x, xF, dx, order, limiter)
    record(t, xout, x[:, -1])
    wall = time.time() - t0
    np.seterr(**old_err)

    W1 = w.sum(axis=1) * dx
    mb_err = (W1 - W0) - (inflow - outflow)
    bv = hist_bv[:nh].copy()
    c = rec.CT * hist_c[:nh].copy()
    c_cell = rec.CT * hist_cc[:nh].copy()
    # history-based outflow integral (trapezoid on the recorded face values)
    out_hist = np.trapz(hist_c[:nh], bv, axis=0)
    info = {
        "cells": N, "order": order, "limiter": limiter if order == 2 else None, "rk": rk if order == 2 else 1,
        "cfl": cfl, "n_steps": step, "dt_min": dt_min, "dt_max": dt_max, "runtime_s": wall,
        "inversion_failures": nfail_total, "eigenvalue_bisection_fallbacks": tracker.fallbacks,
        "eigenvalue_argmax_exact_fixes": tracker.exact_fixes,
        "steady_state_exit_bv": steady_bv,
        "feed_switches": switch_log,
        "mass_balance": {
            "W0_total_per_ion": W0.tolist(), "W_end_total_per_ion": W1.tolist(),
            "inflow_per_ion": inflow.tolist(), "outflow_per_ion": outflow.tolist(),
            "error_per_ion": mb_err.tolist(),
            "relative_error_per_ion": (mb_err / np.maximum(W0 + inflow, 1e-300)).tolist(),
            "history_trapezoid_outflow_minus_stage_outflow": (out_hist - outflow).tolist(),
        },
        "final_bed_x": x, "final_bed_S": S, "snapshots": snaps, "c_cell": c_cell,
    }
    return bv, c, info


# ----------------------------------------------------------------------------------------------
# effluent analysis
# ----------------------------------------------------------------------------------------------
def first_crossing(bv, f, level, up=True):
    """First BV at which f reaches `level` (f >= level if up else f <= level), linear interpolation.
    Returns None if never."""
    hit = (f >= level) if up else (f <= level)
    idx = np.flatnonzero(hit)
    if idx.size == 0:
        return None
    i = idx[0]
    if i == 0:
        return float(bv[0])
    f0, f1 = f[i - 1], f[i]
    if f1 == f0:
        return float(bv[i])
    s = (level - f0) / (f1 - f0)
    return float(bv[i - 1] + s * (bv[i] - bv[i - 1]))


def runs_of(mask):
    """Start/end index pairs (inclusive/exclusive) of maximal True runs."""
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def analyze(bv, c, rec, N, c_cell=None, tol_flat=1e-6, vis_jump=1e-3):
    """Event detection on the effluent history.

    c is the outlet-face history (second-order extrapolated flux value; it can over/undershoot
    by a few percent of a jump just ahead of a shock). c_cell is the last-cell-average history
    (monotone where the scheme is, lagging the outlet by half a cell transit). Plateaus,
    crossings and samples come from c; extremes, monotonicity, roll-up and the nitrate peak
    value come from c_cell (with c reported alongside); crossings and the nitrate limit are
    also reported from c_cell as a cross-check."""
    from scipy.ndimage import maximum_filter1d, minimum_filter1d
    if c_cell is None:
        c_cell = c

    run_bv = rec.run_bv
    CT = rec.CT
    Mu = int(min(400000, max(50000, 2 * len(bv))))
    bvu = np.linspace(0.0, run_bv, Mu)
    h = bvu[1] - bvu[0]
    cu = np.stack([np.interp(bvu, bv, c[:, k]) for k in range(4)], axis=1)

    # flatness window: half-width W (BV); 10 cells-worth at the window's end or 0.1% of run_bv
    W = max(1e-3 * run_bv, 10.0 * run_bv / N)
    wn = max(1, int(round(W / h)))
    size = 2 * wn + 1
    spread = np.zeros(Mu)
    for k in range(4):
        mx = maximum_filter1d(cu[:, k], size=size, mode="nearest")
        mn = minimum_filter1d(cu[:, k], size=size, mode="nearest")
        spread = np.maximum(spread, mx - mn)
    flat = spread < tol_flat
    min_len_pts = int(round(4.0 * W / h))
    plateau_runs = [(s, e) for (s, e) in runs_of(flat) if (e - s) >= min_len_pts]

    plateaus = []
    for (s, e) in plateau_runs:
        n = e - s
        s2 = s + n // 4
        e2 = e - n // 4
        seg = cu[s2:e2]
        comp = seg.mean(axis=0)
        plateaus.append({
            "bv_start": float(bvu[s]), "bv_end": float(bvu[min(e, Mu - 1)]),
            "composition_meq_per_L": comp.tolist(),
            "spread_central_half_meq_per_L": float((seg.max(axis=0) - seg.min(axis=0)).max()),
            "note": "bounds are where the windowed spread crosses tol_flat; a bounding shock lies "
                    "inside the adjacent front, see fronts[].crossings",
        })

    # fronts = gaps between plateaus (and window edges)
    gaps = []
    prev_end = 0
    for i, (s, e) in enumerate(plateau_runs):
        if s > prev_end:
            gaps.append((prev_end, s, i - 1, i))
        prev_end = e
    if prev_end < Mu:
        gaps.append((prev_end, Mu, len(plateau_runs) - 1, None))

    slope = np.zeros((Mu, 4))
    for k in range(4):
        slope[:, k] = np.gradient(cu[:, k], h)

    fronts = []
    for (gs, ge, ip, inext) in gaps:
        bs, be = float(bvu[gs]), float(bvu[min(ge, Mu - 1)])
        if ip is not None and ip >= 0:
            before = np.array(plateaus[ip]["composition_meq_per_L"])
        else:
            before = c[0].copy()
        if inext is not None:
            after = np.array(plateaus[inext]["composition_meq_per_L"])
            cut = False
        else:
            after = c[-1].copy()
            cut = True
        jump = after - before
        seg_bv = bvu[gs:ge]
        seg_c = cu[gs:ge]
        if seg_bv.size < 3:
            continue
        bv_mid = 0.5 * (bs + be)
        bv_cell = bv_mid / N  # BV needed for a front arriving at bv_mid to cross one cell
        lead = int(np.argmax(np.abs(jump)))
        crossings = {}
        widths = {}
        monot = {}
        raw_mask = (bv >= bs) & (bv <= be)
        rbv = bv[raw_mask]
        for k in range(4):
            jk = jump[k]
            seg_k = c[raw_mask, k]
            seg_cell = c_cell[raw_mask, k]
            monot[IONS[k]] = {
                "min_in_front_cell": float(seg_cell.min()) if seg_cell.size else None,
                "max_in_front_cell": float(seg_cell.max()) if seg_cell.size else None,
                "overshoot_beyond_ends_cell": float(max(seg_cell.max() - max(before[k], after[k]),
                                                        min(before[k], after[k]) - seg_cell.min(), 0.0))
                if seg_cell.size else None,
                "overshoot_beyond_ends_face": float(max(seg_k.max() - max(before[k], after[k]),
                                                        min(before[k], after[k]) - seg_k.min(), 0.0))
                if seg_k.size else None,
            }
            if abs(jk) < vis_jump or rbv.size < 3:
                continue
            frac = (seg_k - before[k]) / jk
            b10 = first_crossing(rbv, frac, 0.10)
            b50 = first_crossing(rbv, frac, 0.50)
            b90 = first_crossing(rbv, frac, 0.90)
            fracc = (seg_cell - before[k]) / jk
            crossings[IONS[k]] = {"bv10": b10, "bv50": b50, "bv90": b90,
                                  "bv50_cell": first_crossing(rbv, fracc, 0.50)}
            widths[IONS[k]] = (b90 - b10) if (b10 is not None and b90 is not None) else None
        # steep decomposition: normalised slope relative to the leading ion's jump
        jl = abs(jump[lead])
        steep_parts = []
        steep_fraction = None
        if jl >= vis_jump:
            sn = np.abs(slope[gs:ge]).max(axis=1) / jl
            thr = 1.0 / (20.0 * bv_cell)
            steep = sn > thr
            # merge gaps shorter than 2 cells-worth
            gap_pts = max(1, int(round(2.0 * bv_cell / h)))
            for (a, b) in runs_of(~steep):
                if (b - a) < gap_pts and a > 0 and b < steep.size:
                    steep[a:b] = True
            tot = 0.0
            for (a, b) in runs_of(steep):
                b = min(b, seg_c.shape[0] - 1)
                ca = seg_c[a]
                cb = seg_c[b]
                dj = cb - ca
                tot += abs(dj[lead])
                steep_parts.append({
                    "bv_start": float(seg_bv[a]), "bv_end": float(seg_bv[b]),
                    "jump_meq_per_L": dj.tolist(),
                    "fraction_of_front_jump_leading_ion": float(abs(dj[lead]) / jl),
                })
            steep_fraction = float(min(tot / jl, 1.0))
        lead_width = widths.get(IONS[lead])
        if lead_width is None:
            kind = "weak_or_unresolved"
        elif steep_fraction is not None and steep_fraction > 0.95 and lead_width < 15.0 * bv_cell:
            kind = "shock_like"
        elif steep_fraction is not None and steep_fraction < 0.05:
            kind = "spreading"
        else:
            kind = "mixed"
        fronts.append({
            "bv_start": bs, "bv_end": be, "cut_by_window_end": cut,
            "before_meq_per_L": before.tolist(), "after_meq_per_L": after.tolist(),
            "jump_meq_per_L": jump.tolist(), "leading_ion": IONS[lead],
            "bv_per_cell_at_front": bv_cell,
            "width_10_90_bv": widths, "width_10_90_in_cells": {k: (v / bv_cell if v is not None else None)
                                                             for k, v in widths.items()},
            "crossings": crossings,
            "max_abs_slope_meq_per_L_per_bv": float(np.abs(slope[gs:ge]).max()),
            "steep_fraction_of_jump": steep_fraction,
            "steep_parts": steep_parts,
            "kind_single_resolution": kind,
            "monotonicity": monot,
        })

    # nitrate peak (value from the monotone cell history; the face history can overshoot)
    cn = c_cell[:, 1]
    imax = int(np.argmax(cn))
    cmax = float(cn[imax])
    first_att = first_crossing(bv, cn, cmax - 1e-7)
    nitrate_peak = {"meq_per_L": cmax, "bv_of_argmax": float(bv[imax]),
                    "bv_first_within_1e-7": first_att,
                    "meq_per_L_face_history": float(c[:, 1].max())}
    # location of the peak
    loc = None
    for i, p in enumerate(plateaus):
        if p["bv_start"] <= bv[imax] <= p["bv_end"]:
            loc = f"plateau[{i}]"
    if loc is None:
        for i, f in enumerate(fronts):
            if f["bv_start"] <= bv[imax] <= f["bv_end"]:
                loc = f"front[{i}]"
    nitrate_peak["location"] = loc
    # the exact solution attains a plateau maximum at the plateau's start; when that start is a
    # shock-like front the FV estimate of the peak BV is that front's midpoint crossing
    est = nitrate_peak["bv_first_within_1e-7"]
    if loc is not None and loc.startswith("plateau"):
        ip = int(loc[8:-1])
        if ip == 0:
            est = 0.0
        else:
            fr = [f for f in fronts if abs(f["bv_end"] - plateaus[ip]["bv_start"]) < 1e-9]
            if fr:
                f0 = fr[0]
                cr = f0["crossings"].get("nitrate") or next(iter(f0["crossings"].values()), None)
                if f0["kind_single_resolution"] == "shock_like" and cr and cr["bv50"] is not None:
                    est = cr["bv50"]
                elif cr and cr["bv90"] is not None:
                    est = cr["bv90"]
    nitrate_peak["bv_estimate"] = est

    lim = rec.nitrate_limit

    def limit_bv(series):
        if series[0] > lim:
            return 0.0
        idx = np.flatnonzero(series > lim)
        if idx.size == 0:
            return None
        i = idx[0]
        f0, f1 = series[i - 1], series[i]
        return float(bv[i - 1] + (lim - f0) / (f1 - f0) * (bv[i] - bv[i - 1]))

    nlb = limit_bv(c[:, 1])
    nlb_cell = limit_bv(cn)

    samples = [[float(np.interp(sb, bv, c[:, k])) for k in range(4)] for sb in rec.sample_bv]

    c0 = CT * rec.x0
    feeds_c = [CT * xf for xf in rec.feed_x]
    rollup = {}
    for k in range(4):
        ref_max = max([c0[k]] + [fc[k] for fc in feeds_c])
        ref_min = min([c0[k]] + [fc[k] for fc in feeds_c])
        mx = float(c_cell[:, k].max())
        mn = float(c_cell[:, k].min())
        rollup[IONS[k]] = {
            "max_effluent": mx, "min_effluent": mn, "initial": float(c0[k]),
            "max_effluent_face": float(c[:, k].max()), "min_effluent_face": float(c[:, k].min()),
            "feeds": [float(fc[k]) for fc in feeds_c],
            "exceeds_feed_and_initial_by": float(mx - ref_max),
            "roll_up": bool(mx > ref_max + 1e-6),
            "undershoots_feed_and_initial_by": float(ref_min - mn),
            "roll_down": bool(mn < ref_min - 1e-6),
        }

    return {
        "analysis_parameters": {
            "uniform_resample_points": Mu, "flatness_half_window_bv": W,
            "flatness_tol_meq_per_L": tol_flat, "min_plateau_length_bv": 4.0 * W,
            "visible_jump_meq_per_L": vis_jump,
            "steep_slope_threshold": "normalised slope > 1/(20 cells-worth of BV)",
            "shock_like_if": "steep fraction > 0.95 and 10-90 width < 15 cells",
        },
        "n_plateaus": len(plateaus), "n_fronts": len(fronts),
        "plateaus": plateaus, "fronts": fronts,
        "nitrate_peak": nitrate_peak, "nitrate_limit_bv": nlb, "nitrate_limit_bv_cell": nlb_cell,
        "samples": samples, "sample_bv": rec.sample_bv,
        "rollup": rollup,
        "effluent_at_run_bv": c[-1].tolist(),
        "effluent_at_0": c[0].tolist(),
    }


# ----------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--cells", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--order", type=int, default=2, choices=[1, 2])
    ap.add_argument("--limiter", default="minmod", choices=["minmod", "vanleer"],
                    help="minmod (default) gives monotone discrete shocks; vanleer is sharper but, limited "
                         "ion by ion, emits small waves at shocks that leave 1e-4..1e-3 noise on the plateau "
                         "downstream of each shock")
    ap.add_argument("--rk", type=int, default=2, choices=[2, 3])
    ap.add_argument("--cfl", type=float, default=0.4)
    ap.add_argument("--no-early-exit", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--analyze-only", action="store_true",
                    help="re-run the effluent analysis on an existing <out>/effluent.npz and rewrite summary.json")
    ap.add_argument("--snap", default="samples",
                    help="comma-separated BVs at which to store the bed profile; 'samples' (default) "
                         "uses the recipe's sample_bv; 'none' disables")
    args = ap.parse_args(argv)

    rec = Recipe(args.recipe)
    os.makedirs(args.out, exist_ok=True)
    if args.analyze_only:
        d = np.load(os.path.join(args.out, "effluent.npz"))
        with open(os.path.join(args.out, "summary.json")) as f:
            old = json.load(f)
        ana = analyze(d["bv"], d["c_meq_per_L"], rec, old["solver"]["cells"],
                      c_cell=d["c_cell_meq_per_L"] if "c_cell_meq_per_L" in d else None)
        summary = {"recipe_id": rec.recipe_id, "ions": IONS, "Lambda": rec.Lam,
                   "solver": old["solver"], **ana}
        with open(os.path.join(args.out, "summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
        if not args.quiet:
            print(f"re-analysed: {ana['n_plateaus']} plateaus, {ana['n_fronts']} fronts")
        return 0
    if not args.quiet:
        print(f"{rec.recipe_id}: N={args.cells} order={args.order} limiter={args.limiter} rk={args.rk} "
              f"cfl={args.cfl} Lambda={rec.Lam:.4f} run_bv={rec.run_bv}", flush=True)
    if args.snap == "samples":
        snap_bv = list(rec.sample_bv)
    elif args.snap == "none":
        snap_bv = []
    else:
        snap_bv = [float(v) for v in args.snap.split(",") if v.strip()]
    bv, c, info = solve(rec, args.cells, order=args.order, limiter=args.limiter, rk=args.rk,
                        cfl=args.cfl, early_exit=not args.no_early_exit, verbose=not args.quiet,
                        snap_bv=snap_bv)
    xi = (np.arange(args.cells) + 0.5) / args.cells
    snaps = info.pop("snapshots")
    c_cell = info.pop("c_cell")
    snap_keys = sorted(snaps)
    np.savez_compressed(os.path.join(args.out, "effluent.npz"), bv=bv, c_meq_per_L=c, c_cell_meq_per_L=c_cell,
                        xi=xi, x_bed_final=info.pop("final_bed_x"), S_bed_final=info.pop("final_bed_S"),
                        snapshot_bv=np.array(snap_keys),
                        snapshot_x=np.array([snaps[k] for k in snap_keys]) if snap_keys else np.zeros((0, 4, args.cells)))
    info["snapshot_bv"] = snap_keys
    ana = analyze(bv, c, rec, args.cells, c_cell=c_cell)
    summary = {"recipe_id": rec.recipe_id, "ions": IONS, "Lambda": rec.Lam,
               "solver": info, **ana}
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    if not args.quiet:
        print(f"done: {info['n_steps']} steps, {info['runtime_s']:.1f} s, "
              f"{ana['n_plateaus']} plateaus, {ana['n_fronts']} fronts, "
              f"mass balance max |err| = {np.abs(info['mass_balance']['error_per_ion']).max():.2e}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
