"""Ray-theoretical P-wave traveltimes in a flat layered medium with linear velocity gradients
(TRAVELTIME_SPEC.md).

Closed forms. With eta(v) = sqrt(1 - p^2 v^2), a layer with velocities v1 (top) and v2 (bottom)
and gradient b contributes, one way,
    b != 0:  X = (eta1 - eta2) / (p b),   T = ln( v2 (1 + eta1) / (v1 (1 + eta2)) ) / b
    b == 0:  X = h p v / eta,             T = h / (v eta)
and a ray turning inside the layer at v = 1/p (b > 0) contributes X = eta1 / (p b),
T = ln((1 + eta1) / (p v1)) / b. dX/dp is differentiated analytically. Every branch (direct,
turning in a layer, reflection from an interface, head along an interface) is an interval of p;
it is split at its caustics (zeros of dX/dp, by Brent's method) into segments on which X(p) is
monotone, so an arrival at a given offset is the unique root of X(p) = X on each segment that
covers that offset. The first arrival is found by tabulating every segment, locating the switches
of the minimum on a fine offset grid, and refining each switch exactly (crossover root of
T_a(X) - T_b(X), or a segment end).
"""
import argparse
import json
import math

import numpy as np
from scipy.optimize import brentq

T_GRID = np.unique(np.concatenate([np.logspace(-15, -1, 240), np.linspace(0.1, 0.9, 1200),
                                   1.0 - np.logspace(-1, -15, 240)]))
N_X = 6000                                # offset samples for locating first-arrival switches


class Model:
    def __init__(self, m):
        self.id = m["model_id"]
        L = m["layers"]
        self.a = [float(l["v_top_km_s"]) for l in L]
        self.b = [float(l["gradient_per_s"]) for l in L]
        self.h = [float(l["thickness_km"]) if l["thickness_km"] is not None else math.inf for l in L]
        self.N = len(L)
        self.vbot = [self.a[k] + self.b[k] * self.h[k] if math.isfinite(self.h[k]) else math.inf for k in range(self.N)]
        # V^- of interface i (above it): max velocity over layers 0..i-1
        self.Vm = [None] + [max(max(self.a[j], self.vbot[j]) for j in range(i)) for i in range(1, self.N)]
        self.xmax = float(m["x_max_km"])
        self.offsets = [float(x) for x in m["offsets_km"]]
        self.offsets_raw = m["offsets_km"]

    # ------------------------------------------------------------------ one layer
    def full(self, k, p):
        """One-way (X, T, dX/dp) through the whole of layer k (finite layers), p array.
        Cancellation-free forms: eta1 - eta2 = p^2 (v2^2 - v1^2) / (eta1 + eta2) and
        v2^2 - v1^2 = b h (v1 + v2) give X = p h (v1 + v2) / (eta1 + eta2) for every b (b = 0
        included); T uses log1p so that small gradients lose no digits."""
        a, b, h = self.a[k], self.b[k], self.h[k]
        v1, v2 = a, a + b * h
        e1, e2 = np.sqrt(1.0 - (p * v1) ** 2), np.sqrt(1.0 - (p * v2) ** 2)
        S = e1 + e2
        C = h * (v1 + v2)
        X = p * C / S
        de1, de2 = -p * v1 * v1 / e1, -p * v2 * v2 / e2
        dX = C / S - p * C * (de1 + de2) / S ** 2
        if b == 0.0:
            T = h / (a * e1)
        else:
            T = (np.log1p(b * h / v1) + np.log1p(p * p * b * C / (S * (1.0 + e2)))) / b
        return X, T, dX

    def turn(self, k, p):
        """One-way (X, T, dX/dp) from the top of layer k to the turning depth, p array."""
        a, b = self.a[k], self.b[k]
        e1 = np.sqrt(1.0 - (p * a) ** 2)
        X = e1 / (p * b)
        T = np.log((1.0 + e1) / (p * a)) / b
        dX = ((-p * a * a / e1) / p - e1 / p ** 2) / b
        return X, T, dX

    # ------------------------------------------------------------------ branches
    def branches(self):
        """List of (kind, index, p_lo, p_hi, include_lo) for turning and reflection branches."""
        out = []
        for k in range(self.N):
            if self.b[k] > 0.0:
                upper = 1.0 / max(self.a[k], self.Vm[k] if k > 0 else 0.0)
                lower = 0.0 if not math.isfinite(self.h[k]) else 1.0 / self.vbot[k]
                if lower < upper:
                    out.append(("turning", k, lower, upper))
        for i in range(1, self.N):
            out.append(("reflection", i, 0.0, 1.0 / self.Vm[i]))
        return out

    def XT(self, kind, idx, p):
        """Two-way (X, T, dX/dp) of a branch, p array."""
        with np.errstate(all="ignore"):
            return self._XT(kind, idx, p)

    def _XT(self, kind, idx, p):
        p = np.asarray(p, float)
        X = np.zeros_like(p); T = np.zeros_like(p); D = np.zeros_like(p)
        top = idx  # layers fully crossed: 0..idx-1
        for j in range(top):
            x, t, d = self.full(j, p)
            X += x; T += t; D += d
        if kind == "turning":
            x, t, d = self.turn(idx, p)
            X += x; T += t; D += d
        return 2.0 * X, 2.0 * T, 2.0 * D

    def segments(self):
        """Monotone segments: dicts with kind, index, p0, p1 (ends), X0, X1, sign."""
        segs = []
        for kind, idx, lo, hi in self.branches():
            ps = lo + (hi - lo) * T_GRID
            if kind == "turning" and lo == 0.0:
                ps = ps[ps > 0]
            ps = ps[(ps > lo) | ((lo == 0.0) & (kind == "reflection") & (ps >= 0))]
            ps = ps[ps < hi]
            X, T, D = self.XT(kind, idx, ps)
            ok = np.isfinite(X) & np.isfinite(D)
            ps, X, D = ps[ok], X[ok], D[ok]
            cuts = []
            for j in range(len(ps) - 1):
                if D[j] * D[j + 1] < 0.0:
                    f = lambda q: float(self.XT(kind, idx, np.array([q]))[2][0])
                    cuts.append(brentq(f, ps[j], ps[j + 1], xtol=1e-300, rtol=4 * np.finfo(float).eps, maxiter=500))
            # branch ends: the exact limits wherever X is finite there (a turning ray grazing the
            # top of its layer at p = 1/a_k, a reflection grazing a gradient-layer bottom); only
            # divergent limits (p -> 0 for a half-space turning ray, grazing in a constant layer)
            # keep the last grid point
            def finite_at(q):
                with np.errstate(all="ignore"):
                    X_, T_, _ = self.XT(kind, idx, np.array([q]))
                return bool(np.isfinite(X_[0]) and np.isfinite(T_[0]))
            p_lo = lo if (lo > 0.0 or kind == "reflection") and finite_at(lo) else ps[0]
            p_hi = hi if finite_at(hi) else ps[-1]
            ends = [p_lo] + cuts + [p_hi]
            for j in range(len(ends) - 1):
                p0, p1 = ends[j], ends[j + 1]
                x0 = float(self.XT(kind, idx, np.array([p0]))[0][0])
                x1 = float(self.XT(kind, idx, np.array([p1]))[0][0])
                segs.append(dict(kind=kind, index=idx, p0=p0, p1=p1, X0=x0, X1=x1,
                                 caustic0=j > 0, caustic1=j < len(ends) - 2))
        return segs

    def caustics(self, segs):
        out = []
        for s in segs:
            if s["caustic1"]:
                p = s["p1"]
                X, T, _ = self.XT(s["kind"], s["index"], np.array([p]))
                if 0.0 < X[0] <= self.xmax:
                    out.append(dict(kind=s["kind"], index=s["index"], p_s_km=float(p), x_km=float(X[0]), t_s=float(T[0])))
        out.sort(key=lambda c: c["x_km"])
        return out

    # ------------------------------------------------------------------ arrivals at an offset
    def on_segment(self, s, x):
        """(p, T) of the segment's arrival at offset x, or None."""
        lo, hi = min(s["X0"], s["X1"]), max(s["X0"], s["X1"])
        if not (lo < x < hi):
            return None
        f = lambda q: float(self.XT(s["kind"], s["index"], np.array([q]))[0][0]) - x
        p = brentq(f, s["p0"], s["p1"], xtol=1e-300, rtol=4 * np.finfo(float).eps, maxiter=500)
        return p, float(self.XT(s["kind"], s["index"], np.array([p]))[1][0])

    def specials(self):
        """Direct and head 'segments': (kind, index, p, X_start, tau)."""
        out = []
        if self.b[0] == 0.0:
            out.append(("direct", 0, 1.0 / self.a[0], 0.0, 0.0))
        for i in range(1, self.N):
            if self.b[i] == 0.0 and self.a[i] > self.Vm[i]:
                ph = 1.0 / self.a[i]
                X, T, _ = self.XT("reflection", i, np.array([ph]))
                out.append(("head", i, ph, float(X[0]), float(T[0] - ph * X[0])))
        return out

    def arrivals_at(self, x, segs, spec):
        rays = []
        for s in segs:
            r = self.on_segment(s, x)
            if r is not None:
                rays.append(dict(kind=s["kind"], index=s["index"], p_s_km=r[0], t_s=r[1]))
        for kind, idx, p, xs, tau in spec:
            if x >= xs:
                rays.append(dict(kind=kind, index=idx, p_s_km=p, t_s=p * x + tau))
        rays.sort(key=lambda r: r["t_s"])
        return rays

    # ------------------------------------------------------------------ first arrival
    def first_arrival(self, segs, spec):
        units = []                                   # (key, kind, index, Xlo, Xhi, Tfun_exact, table)
        for n, s in enumerate(segs):
            ps = s["p0"] + (s["p1"] - s["p0"]) * T_GRID
            X, T, _ = self.XT(s["kind"], s["index"], ps)
            ok = np.isfinite(X) & np.isfinite(T)
            X, T = X[ok], T[ok]
            o = np.argsort(X)
            units.append(dict(key=("seg", n), kind=s["kind"], index=s["index"], lo=min(s["X0"], s["X1"]),
                              hi=max(s["X0"], s["X1"]), X=X[o], T=T[o], seg=s))
        for n, (kind, idx, p, xs, tau) in enumerate(spec):
            units.append(dict(key=("spec", n), kind=kind, index=idx, lo=xs, hi=math.inf, p=p, tau=tau))

        def t_approx(u, x):
            if "p" in u:
                return u["p"] * x + u["tau"] if x >= u["lo"] else math.inf
            if not (u["lo"] < x < u["hi"]):
                return math.inf
            return float(np.interp(x, u["X"], u["T"]))

        def t_exact(u, x):
            if "p" in u:
                return u["p"] * x + u["tau"] if x >= u["lo"] else math.inf
            r = self.on_segment(u["seg"], x)
            return math.inf if r is None else r[1]

        eps = 1e-9 * self.xmax
        grid = set(np.linspace(0.0, self.xmax, N_X + 1)[1:].tolist())
        for u in units:
            for e in (u["lo"], u["hi"]):
                if 0.0 < e < self.xmax:
                    grid.update([e - eps, e + eps])
        grid = np.array(sorted(g for g in grid if 0.0 < g <= self.xmax))
        best = []
        for x in grid:
            ts = [t_approx(u, x) for u in units]
            best.append(int(np.argmin(ts)))
        # runs of the approximate winner on the grid
        runs = [[best[0], grid[0], grid[0]]]
        for j in range(1, len(grid)):
            if best[j] == runs[-1][0]:
                runs[-1][2] = grid[j]
            else:
                runs.append([best[j], grid[j], grid[j]])

        def exact_winner(x):
            ts = [t_exact(u, x) for u in units]
            return int(np.argmin(ts))
        # short runs are tangency artefacts of the tables (two branches meeting at a cusp); the
        # spec guarantees that true intervals are at least 1e-3 X long, so a run shorter than
        # 1e-4 X_max is re-decided exactly at its centre and merged into a neighbour it matches
        changed = True
        while changed and len(runs) > 1:
            changed = False
            for n, r in enumerate(runs):
                if r[2] - r[1] < 1e-4 * self.xmax:
                    w = exact_winner(0.5 * (r[1] + r[2]))
                    nb = [m for m in (n - 1, n + 1) if 0 <= m < len(runs)]
                    target = next((m for m in nb if runs[m][0] == w), nb[0])
                    runs[target][1] = min(runs[target][1], r[1])
                    runs[target][2] = max(runs[target][2], r[2])
                    del runs[n]
                    merged = []
                    for q in runs:
                        if merged and merged[-1][0] == q[0]:
                            merged[-1][2] = q[2]
                        else:
                            merged.append(q)
                    runs = merged
                    changed = True
                    break

        def boundary(A, B, x1, x2):
            """Exact offset in [x1, x2] where the first arrival passes from unit A to unit B."""
            if A["hi"] <= x2 + eps and A["hi"] >= x1 - eps and math.isfinite(A["hi"]):
                return A["hi"]                               # A's segment ends
            if B["lo"] >= x1 - eps and B["lo"] <= x2 + eps and B["lo"] > 0.0:
                f = lambda x: t_exact(A, x) - t_exact(B, x)
                xs = B["lo"] + eps
                if not math.isfinite(f(xs)) or f(xs) > 0.0:
                    return B["lo"]                           # B starts and is first at once
            f = lambda x: t_exact(A, x) - t_exact(B, x)
            lo, hi = max(x1, A["lo"] + eps, B["lo"] + eps), min(x2, A["hi"] - eps, B["hi"] - eps)
            return brentq(f, lo, hi, xtol=1e-14 * self.xmax, rtol=4 * np.finfo(float).eps, maxiter=500)
        out = []
        for n, r in enumerate(runs):
            u = units[r[0]]
            x0 = 0.0 if n == 0 else out[-1]["x_end_km"]
            if n + 1 < len(runs):
                x1 = boundary(u, units[runs[n + 1][0]], r[2], runs[n + 1][1])
            else:
                x1 = self.xmax
            out.append(dict(kind=u["kind"], index=u["index"], x_start_km=float(x0), x_end_km=float(x1)))
        return out


def solve(m):
    M = Model(m)
    segs = M.segments()
    spec = M.specials()
    arrivals = [dict(x_km=xr, rays=M.arrivals_at(float(xr), segs, spec)) for xr in M.offsets_raw]
    return dict(model_id=M.id, arrivals=arrivals, caustics=M.caustics(segs), first_arrival=M.first_arrival(segs, spec))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.model, encoding="utf-8") as fh:
        m = json.load(fh)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(solve(m), fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
