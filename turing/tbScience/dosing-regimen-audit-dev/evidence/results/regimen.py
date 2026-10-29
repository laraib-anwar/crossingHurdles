#!/usr/bin/env python
"""regimen.py - plasma concentration, exposure and steady state of multi-dose regimens.

Reference solution for REGIMEN_SPEC.md. The compartment system is integrated between dose events
(impulses, lagged oral arrivals, infusion starts and ends) with an 8th-order Dormand-Prince
integrator at tight tolerance and dense output; the integral of the concentration is carried as an
extra state. The periodic steady state of the maintenance cycle is found by Newton shooting on
the period map with the monodromy matrix from the variational equations. Extrema and window
crossings are roots of the exact derivative or of C - level, bracketed on a fine grid of the dense
output, solved there with Brent's method and polished with Newton steps on states obtained by
integrating from the nearest accepted step; every reported value is such an exactly integrated
state, never an interpolant.

usage: regimen.py --regimen <regimen.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

RTOL = 2.5e-14        # just above the DOP853 floor of 10 eps
GRID_H = 0.005          # bracketing grid for extrema and crossings (h)
N_CYCLES = 60


class Model:
    def __init__(self, d):
        m = d["model"]
        self.V1, self.CL, self.Vmax, self.Km = float(m["V1"]), float(m["CL"]), float(m["Vmax"]), float(m["Km"])
        self.per = [(float(p["Q"]), float(p["V"])) for p in m["peripheral"]]
        # state layout: 0 central, 1..np peripheral, then per formulation n_transit + 1 slots, then AUC
        self.slot = {}
        pos = 1 + len(self.per)
        for f in d["formulations"]:
            self.slot[f["id"]] = pos
            pos += f["n_transit"] + 1
        self.n = pos            # dynamic states (without AUC)
        self.dim = pos + 1
        self.J0 = np.zeros((self.n, self.n))
        for k, (Q, V) in enumerate(self.per, start=1):
            self.J0[0, 0] -= Q / self.V1
            self.J0[0, k] += Q / V
            self.J0[k, 0] += Q / self.V1
            self.J0[k, k] -= Q / V
        self.J0[0, 0] -= self.CL / self.V1
        for f in d["formulations"]:
            s, ntr, ktr, ka = self.slot[f["id"]], f["n_transit"], float(f["ktr"]), float(f["ka"])
            for i in range(ntr):
                self.J0[s + i, s + i] -= ktr
                self.J0[s + i + 1, s + i] += ktr
            self.J0[s + ntr, s + ntr] -= ka
            self.J0[0, s + ntr] += ka

    def rhs(self, x, rate):
        """dx/dt for the n dynamic states plus the AUC state, at infusion rate `rate`."""
        n = self.n
        dx = np.empty(n + 1)
        dx[:n] = self.J0 @ x[:n]
        C = x[0] / self.V1
        if self.Vmax:
            dx[0] -= self.Vmax * C / (self.Km + C)
        dx[0] += rate
        dx[n] = C
        return dx

    def jac(self, x):
        J = self.J0.copy()
        if self.Vmax:
            C = x[0] / self.V1
            J[0, 0] -= self.Vmax * self.Km / (self.Km + C) ** 2 / self.V1
        return J

    def dC(self, x, rate):
        return self.rhs(x, rate)[0] / self.V1

    def d2C(self, x, rate):
        f = self.rhs(x, rate)[: self.n]
        return float((self.jac(x) @ f)[0] / self.V1)


def dose_events(d, dose, t, ev):
    """Append the events of one dose given at time t: ('imp', target slot id, amount) or ('rate', delta)."""
    if dose["route"] == "iv_bolus":
        ev.append((t, "imp", (0, float(dose["amount"]))))
    elif dose["route"] == "iv_infusion":
        r = float(dose["amount"]) / float(dose["duration"])
        ev.append((t, "rate", r))
        ev.append((t + float(dose["duration"]), "rate", -r))
    else:
        f = next(f for f in d["formulations"] if f["id"] == dose["formulation"])
        ev.append((t + float(f["tlag"]), "imp", (f["id"], float(f["F"]) * float(dose["amount"]))))


def events_of(d, cycles):
    """All events of the regimen (loading doses and the first `cycles` maintenance cycles), sorted."""
    ev = []
    for dose in d["loading_doses"]:
        dose_events(d, dose, float(dose["time"]), ev)
    start, period = float(d["maintenance"]["start"]), float(d["maintenance"]["period"])
    for m in range(cycles):
        for dose in d["maintenance"]["doses"]:
            dose_events(d, dose, start + m * period + float(dose["offset"]), ev)
    ev.sort(key=lambda e: e[0])
    return ev


def periodic_events(d):
    """Events of the maintenance cycle folded into one period [0, period) of the periodic solution, and
    the infusion rate running at the period start from infusions of earlier cycles."""
    period = float(d["maintenance"]["period"])
    ev, rate0 = [], 0.0
    for dose in d["maintenance"]["doses"]:
        off = float(dose["offset"])
        if dose["route"] == "iv_bolus":
            ev.append((off, "imp", (0, float(dose["amount"]))))
        elif dose["route"] == "iv_infusion":
            dur = float(dose["duration"])
            r = float(dose["amount"]) / dur
            ev.append((off, "rate", r))
            k = 0
            while True:
                t_end = off + dur - k * period
                if t_end <= 0.0:
                    break
                if t_end < period:
                    ev.append((t_end, "rate", -r))
                if k >= 1:
                    rate0 += r
                k += 1
        else:
            f = next(f for f in d["formulations"] if f["id"] == dose["formulation"])
            t = (off + float(f["tlag"])) % period
            ev.append((t, "imp", (f["id"], float(f["F"]) * float(dose["amount"]))))
    ev.sort(key=lambda e: e[0])
    return ev, rate0


class Trajectory:
    """Piecewise dense solution of the model under a list of events on [t0, t1]."""

    def __init__(self, model, x0, t0, t1, events, rate0=0.0, variational=False, apply_at_start=True):
        self.model, self.t0, self.t1 = model, t0, t1
        self.pieces = []        # (ta, tb, rate, sol); the state at ta is post-event, at tb pre-event
        self.jumps = []         # (t, x_pre, x_post) for impulses into the central compartment
        n = model.n
        x = np.array(x0, dtype=float)
        rate = rate0
        Phi = np.eye(n) if variational else None
        evs = [e for e in events if t0 <= e[0] <= t1]
        idx = 0
        while idx < len(evs) and evs[idx][0] <= t0:
            if apply_at_start:
                x, rate = self._apply(evs[idx], x, rate, t0)
            idx += 1
        t = t0
        for tb in sorted(set([e[0] for e in evs if e[0] > t0] + [t1])):
            if tb > t:
                sol, PhiPiece = self._integrate(x, t, tb, rate, variational)
                self.pieces.append((t, tb, rate, sol))
                x = sol.y[: n + 1, -1].copy()
                if variational:
                    Phi = PhiPiece @ Phi
                t = tb
            while idx < len(evs) and evs[idx][0] <= tb:
                x, rate = self._apply(evs[idx], x, rate, tb)
                idx += 1
        self.x_end, self.rate_end, self.Phi = x, rate, Phi

    def _apply(self, e, x, rate, t):
        x = x.copy()
        if e[1] == "imp":
            tgt, amt = e[2]
            if tgt == 0:
                self.jumps.append((t, x.copy(), None))
                x[0] += amt
                self.jumps[-1] = (t, self.jumps[-1][1], x.copy())
            else:
                x[self.model.slot[tgt]] += amt
        else:
            rate = rate + e[2]
            if abs(rate) < 1e-12 * abs(e[2]):
                rate = 0.0
        return x, rate

    def _integrate(self, x, ta, tb, rate, variational):
        m = self.model
        n = m.n
        if variational:
            def f(t, y):
                dx = m.rhs(y[: n + 1], rate)
                Phi = y[n + 1:].reshape(n, n)
                return np.concatenate([dx, (m.jac(y[: n + 1]) @ Phi).ravel()])
            y0 = np.concatenate([x, np.eye(n).ravel()])
        else:
            def f(t, y):
                return m.rhs(y, rate)
            y0 = x
        scale = max(1.0, float(np.max(np.abs(x[:n]))) * 1e-3)
        sol = solve_ivp(f, (ta, tb), y0, method="DOP853", rtol=RTOL, atol=1e-16 * scale, dense_output=True)
        if not sol.success:
            raise RuntimeError(sol.message)
        PhiPiece = sol.y[n + 1:, -1].reshape(n, n) if variational else None
        return sol, PhiPiece

    def _exact(self, sol, rate, t):
        """State at t inside a piece by integrating from the last accepted step node before t (the
        dense-output interpolant is only used for bracketing; reported values come from here)."""
        k = int(np.searchsorted(sol.t, t, side="right")) - 1
        k = max(0, min(k, len(sol.t) - 1))
        n = self.model.n
        x0 = sol.y[: n + 1, k]
        if sol.t[k] == t:
            return x0.copy()
        m = self.model
        scale = max(1.0, float(np.max(np.abs(x0[:n]))) * 1e-3)
        r = solve_ivp(lambda tt, y: m.rhs(y, rate), (sol.t[k], t), x0, method="DOP853", rtol=RTOL, atol=1e-16 * scale)
        if not r.success:
            raise RuntimeError(r.message)
        return r.y[:, -1]

    def state(self, t):
        """Right-continuous state at t (post-event) and the infusion rate there."""
        for ta, tb, rate, sol in self.pieces:
            if ta <= t < tb:
                return self._exact(sol, rate, t), rate
        if t == self.t1:
            return self.x_end, self.rate_end
        raise ValueError("time outside trajectory")

    def pre_state(self, t):
        """Left limit of the state at t (t > t0)."""
        for ta, tb, rate, sol in self.pieces:
            if ta < t <= tb:
                return self._exact(sol, rate, t)
        raise ValueError("time outside trajectory")

    def _polish_root(self, sol, rate, t, g, dg):
        """Two Newton steps on g(t) with exact states, starting from the dense-output root t."""
        m = self.model
        for _ in range(2):
            x = self._exact(sol, rate, t)
            d = dg(x)
            if d == 0.0:
                break
            step = g(x) / d
            t_new = t - step
            if not (sol.t[0] <= t_new <= sol.t[-1]):
                break
            t = t_new
            if abs(step) < 1e-15 * max(1.0, abs(t)):
                break
        return t

    def C(self, t):
        return float(self.state(t)[0][0] / self.model.V1)

    def _grid(self, ta, tb, sol):
        ng = max(4, int(math.ceil((tb - ta) / GRID_H)))
        ts = np.linspace(ta, tb, ng + 1)
        Y = sol.sol(ts)[: self.model.n + 1]
        return ng, ts, Y, Y[0] / self.model.V1

    def local_maxima(self, t_max=None):
        """Every local maximum of C on [t0, t_max]: (time, value, kind) with kind 'interior', 'kink' or
        'jump'. Used for cmax and for the isolation guarantee."""
        m = self.model
        t_max = self.t1 if t_max is None else t_max
        out = []
        prev_dC = None      # derivative at the end of the previous piece (pre-event)
        for ta, tb, rate, sol in self.pieces:
            if ta >= t_max:
                break
            tb_c = min(tb, t_max)
            ng, ts, Y, Cs = self._grid(ta, tb_c, sol)
            dCs = np.array([m.dC(Y[:, i], rate) for i in range(ng + 1)])
            jumped = any(j[0] == ta for j in self.jumps)
            if dCs[0] < 0 and (jumped or ta == self.t0 or (prev_dC is not None and prev_dC > 0)):
                out.append((ta, float(Cs[0]), "jump" if jumped else "kink"))
            for i in range(ng):
                if dCs[i] > 0 and dCs[i + 1] < 0:
                    tr = brentq(lambda t: m.dC(sol.sol(t)[: m.n + 1], rate), ts[i], ts[i + 1], xtol=1e-14, rtol=1e-15, maxiter=200)
                    tr = self._polish_root(sol, rate, tr, lambda x: m.dC(x, rate), lambda x: m.d2C(x, rate))
                    out.append((tr, float(self._exact(sol, rate, tr)[0] / m.V1), "interior"))
                elif dCs[i] == 0.0 and i > 0 and dCs[i - 1] > 0 and dCs[i + 1] < 0:
                    out.append((ts[i], float(Cs[i]), "interior"))
            prev_dC = dCs[-1]
        # the closed end of the interval is a candidate for the maximum (right-continuous value)
        out.append((t_max, self.C(t_max), "end"))
        return out

    def global_min(self):
        m = self.model
        worst = math.inf
        for ta, tb, rate, sol in self.pieces:
            ng, ts, Y, Cs = self._grid(ta, tb, sol)
            worst = min(worst, float(Cs[0]), float(Cs[-1]))
            dCs = np.array([m.dC(Y[:, i], rate) for i in range(ng + 1)])
            for i in range(ng):
                if dCs[i] < 0 and dCs[i + 1] > 0:
                    tr = brentq(lambda t: m.dC(sol.sol(t)[: m.n + 1], rate), ts[i], ts[i + 1], xtol=1e-14, rtol=1e-15, maxiter=200)
                    tr = self._polish_root(sol, rate, tr, lambda x: m.dC(x, rate), lambda x: m.d2C(x, rate))
                    worst = min(worst, float(self._exact(sol, rate, tr)[0] / m.V1))
        return worst

    def crossings(self, level):
        """Continuous crossings of `level`: (time, dC/dt there); and jump crossings: (time, C_pre, C_post)."""
        m = self.model
        cont, jumps = [], []
        for ta, tb, rate, sol in self.pieces:
            ng, ts, Y, Cs = self._grid(ta, tb, sol)
            for i in range(ng):
                a, b = Cs[i] - level, Cs[i + 1] - level
                if a * b < 0:
                    tr = brentq(lambda t: sol.sol(t)[0] / m.V1 - level, ts[i], ts[i + 1], xtol=1e-14, rtol=1e-15, maxiter=200)
                    tr = self._polish_root(sol, rate, tr, lambda x: x[0] / m.V1 - level, lambda x: m.dC(x, rate))
                    cont.append((tr, m.dC(self._exact(sol, rate, tr), rate)))
                elif a == 0.0:
                    cont.append((ts[i], m.dC(Y[:, i], rate)))
        for t, xpre, xpost in self.jumps:
            cpre, cpost = xpre[0] / m.V1, xpost[0] / m.V1
            if (cpre - level) * (cpost - level) <= 0:
                jumps.append((t, cpre, cpost))
        return cont, jumps

    def time_in_window(self, low, high):
        """Total time with low <= C <= high on [t0, t1]."""
        m = self.model
        total = 0.0
        for ta, tb, rate, sol in self.pieces:
            ng, ts, Y, Cs = self._grid(ta, tb, sol)
            cut = [ta, tb]
            for i in range(ng):
                for lv in (low, high):
                    a, b = Cs[i] - lv, Cs[i + 1] - lv
                    if a * b < 0:
                        tr = brentq(lambda t: sol.sol(t)[0] / m.V1 - lv, ts[i], ts[i + 1], xtol=1e-14, rtol=1e-15, maxiter=200)
                        cut.append(self._polish_root(sol, rate, tr, lambda x, lv=lv: x[0] / m.V1 - lv, lambda x: m.dC(x, rate)))
            cut.sort()
            for a, b in zip(cut, cut[1:]):
                if b > a and low <= sol.sol(0.5 * (a + b))[0] / m.V1 <= high:
                    total += b - a
        return total


def periodic_state(model, d):
    """Newton shooting for the periodic steady state of the maintenance cycle. Returns the state at
    the cycle start and the trajectory over one period."""
    period = float(d["maintenance"]["period"])
    folded, rate0 = periodic_events(d)
    n = model.n
    x = np.zeros(n + 1)
    for _ in range(3):
        x = Trajectory(model, x, 0.0, period, folded, rate0).x_end.copy()
        x[n] = 0.0
    for _ in range(60):
        tr = Trajectory(model, x, 0.0, period, folded, rate0, variational=True)
        g = tr.x_end[:n] - x[:n]
        dx = np.linalg.solve(tr.Phi - np.eye(n), -g)
        x[:n] += dx
        if float(np.max(np.abs(dx))) <= 1e-14 * max(1e-300, float(np.max(np.abs(x[:n])))):
            break
    x[n] = 0.0
    return x, Trajectory(model, x, 0.0, period, folded, rate0)


def solve(d):
    model = Model(d)
    start, period, horizon = float(d["maintenance"]["start"]), float(d["maintenance"]["period"]), float(d["horizon"])
    events = events_of(d, N_CYCLES + 2)
    traj = Trajectory(model, np.zeros(model.dim), 0.0, max(horizon, start + period), events)
    conc = [traj.C(float(t)) for t in d["query_times"]]
    auc = float(traj.pre_state(horizon)[model.n])
    maxima = traj.local_maxima(horizon)
    cmax, t_cmax = max((v, t) for t, v, _ in maxima)
    xs, ptr = periodic_state(model, d)
    ss_max = max(v for _, v, _ in ptr.local_maxima())
    ss_min = ptr.global_min()
    trough = float(ptr.x_end[0] / model.V1)
    tiw = ptr.time_in_window(float(d["window"]["low"]), float(d["window"]["high"]))
    # troughs of the actual regimen, cycle by cycle. Compartmental systems with common inputs are
    # L1-contractive, so once the amounts at a cycle end are within 0.009 trough * V1 (in L1) of the
    # periodic state, every later trough is inside the 1 % band and the remaining cycles need not be run.
    segments, troughs, certified_at = [traj], [], None
    xs_end = ptr.x_end[: model.n]
    for m_ in range(1, N_CYCLES + 1):
        te = start + m_ * period
        if te > segments[-1].t1:
            prev = segments[-1]
            segments.append(Trajectory(model, prev.x_end, prev.t1, te, events, prev.rate_end, apply_at_start=False))
        seg = next(sg for sg in segments if sg.t0 < te <= sg.t1)
        xpre = seg.pre_state(te)
        troughs.append(float(xpre[0] / model.V1))
        if float(np.sum(np.abs(xpre[: model.n] - xs_end))) / model.V1 <= 0.009 * trough:
            certified_at = m_
            break
    n_cycles = 1
    for m_, tr_ in enumerate(troughs, start=1):
        if abs(tr_ - trough) > 0.01 * trough:
            n_cycles = m_ + 1
    rep = dict(regimen_id=d["regimen_id"], concentrations=conc, auc=auc, cmax=float(cmax), t_cmax=float(t_cmax),
               steady_state=dict(cmax=float(ss_max), cmin=float(ss_min), trough=trough,
                                 time_in_window=float(tiw), n_cycles_to_steady=int(n_cycles)))
    return rep, dict(troughs=troughs, xs=xs, traj=traj, ptr=ptr, model=model, maxima=maxima, certified_at=certified_at)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regimen", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.regimen, encoding="utf-8") as fh:
        d = json.load(fh)
    rep, _ = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
