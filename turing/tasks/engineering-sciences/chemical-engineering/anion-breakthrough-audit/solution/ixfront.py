"""Exact effluent history of a fixed-bed anion exchanger under local equilibrium with
constant separation factors (IX_SPEC.md).

Method: equilibrium theory in characteristic coordinates. For n ions with separation factors
a_i and liquid equivalent fractions x_i, the n-1 roots h_k of
    P(h) = sum_i a_i x_i prod_{j != i} (a_j - h) = 0
interlace the a_i. Across a wave of family k only h_k changes (the other roots are Riemann
invariants, and the jump loci coincide with the characteristic paths), so a step change in feed
resolves into n-1 waves ordered by family. With S = sum_i a_i x_i = prod a / prod h:
    characteristic:  dxi/dBV = 1 / (eps + Lambda lambda_k),  lambda_k = h_k^2 prod_{j!=k} h_j / prod a
    jump (family k, h_k^- -> h_k^+):  sigma = h_k^- h_k^+ prod_{j!=k} h_j / prod a
A family-k wave is a shock when h_k is smaller on the feed side than on the bed side (its
characteristics converge), a spreading wave when larger, absent when equal. The composition is
recovered from the roots by x_m = (-1)^(n-1) S prod_k (a_m - h_k) / (a_m prod_{j!=m} (a_j - a_m)).

One feed: the Riemann fan evaluated at the outlet, in closed form.

Two feeds: front tracking. The second Riemann fan is launched into the plateau left by the
first and its waves overtake the slower first-feed waves. Because the jump loci are the
characteristic paths (Temple class), a spreading wave discretised into small jumps is exact at
the geometric mean of each jump's two values, every crossing of two jumps of different
families is an instantaneous exchange of states, and a same-family catch-up is a merge. The
engine computes all crossings of two waves on a lattice (each lattice point is the intersection
of two straight segments whose speeds follow from the states around it), handles same-family
absorption as a chain of merges with exact markers for the edges of the surviving fans, reads
every jump's arrival at the outlet, interpolates the smooth variation inside spreading waves,
and extrapolates the discretisation error (second order) from two resolutions.
"""
import argparse
import json
import math
import sys

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq, minimize_scalar

IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]
NIT = IONS.index("nitrate")
N_PIECES = 400                       # fan discretisation of the two-feed engine (and 2x for the extrapolation)


# ------------------------------------------------------------------ equilibrium theory
class System:
    def __init__(self, alpha, eps, Lambda):
        self.a = np.asarray(alpha, float)          # fixed ion order
        self.order = np.argsort(self.a)            # ascending separation factor
        self.asort = self.a[self.order]
        self.n = len(self.a)
        self.eps = float(eps)
        self.Lam = float(Lambda)
        self.prod_a = float(np.prod(self.a))
        self.den = np.array([self.a[m] * np.prod([self.a[j] - self.a[m] for j in range(self.n) if j != m])
                             for m in range(self.n)])
        self.sign = (-1.0) ** (self.n - 1)

    # roots h_1 < ... < h_{n-1} (ascending). P(h) has a root exactly at a_m for every absent
    # ion (x_m = 0) and one root strictly between each pair of consecutive present ions; the
    # absent ions' factors are common to every term of P and are dropped before bracketing.
    def roots(self, x):
        x = np.asarray(x, float)
        a, xs = self.asort, x[self.order]
        present = [i for i in range(self.n) if xs[i] > 0.0]
        absent = [i for i in range(self.n) if xs[i] <= 0.0]
        assert present, "empty composition"

        def P(h):
            return sum(a[i] * xs[i] * np.prod([a[j] - h for j in present if j != i]) for i in present)
        h = [a[m] for m in absent]
        for p, q in zip(present[:-1], present[1:]):
            lo, hi = a[p], a[q]
            assert P(lo) * P(hi) < 0.0, "root bracket lost"
            h.append(brentq(P, lo, hi, xtol=1e-15, rtol=4 * np.finfo(float).eps, maxiter=500))
        return np.sort(np.array(h, float))

    def S_of(self, h):
        return self.prod_a / float(np.prod(h))

    def x_of(self, h):
        """Liquid equivalent fractions (fixed ion order) from the roots."""
        S = self.S_of(h)
        x = np.array([self.sign * S * np.prod(self.a[m] - h) / self.den[m] for m in range(self.n)])
        return np.where(np.abs(x) < 1e-15, 0.0, x)

    def lam(self, h, k):
        return h[k] * h[k] * float(np.prod(np.delete(h, k))) / self.prod_a

    def sigma(self, h, k, hk_other):
        return h[k] * hk_other * float(np.prod(np.delete(h, k))) / self.prod_a

    def speed(self, lam_value):
        """d xi / d BV for an eigenvalue (characteristic or jump)."""
        return 1.0 / (self.eps + self.Lam * lam_value)

    def hk_from_lam(self, h, k, lam_value):
        return math.sqrt(lam_value * self.prod_a / float(np.prod(np.delete(h, k))))


# ------------------------------------------------------------------ Riemann problem
def riemann_waves(sysm, hU, hD):
    """Waves of the Riemann problem feed (hU, behind) | bed (hD, ahead), ordered by family
    (family 1 fastest). Each wave: dict(kind, k, h_ahead, h_behind, ...)."""
    waves = []
    h = hD.copy()
    for k in range(sysm.n - 1):
        ahead, behind = h.copy(), h.copy()
        behind[k] = hU[k]
        if hU[k] < hD[k]:
            waves.append(dict(kind="shock", k=k, h_ahead=ahead, h_behind=behind, sig=sysm.sigma(ahead, k, hU[k])))
        elif hU[k] > hD[k]:
            waves.append(dict(kind="fan", k=k, h_ahead=ahead, h_behind=behind,
                              lam_ahead=sysm.lam(ahead, k), lam_behind=sysm.lam(behind, k)))
        h = behind
    return waves


# ------------------------------------------------------------------ one feed (closed form)
def outlet_history_single(sysm, hU, hD, run_bv):
    eps, Lam = sysm.eps, sysm.Lam
    segs, cursor, h_now = [], 0.0, hD.copy()
    for w in riemann_waves(sysm, hU, hD):
        if w["kind"] == "shock":
            b = eps + Lam * w["sig"]
            if b > run_bv:
                break
            if b > cursor:
                segs.append(("plateau", cursor, b, h_now))
            segs.append(("shock", b, w["h_ahead"], w["h_behind"]))
            cursor, h_now = b, w["h_behind"]
        else:
            b0, b1 = eps + Lam * w["lam_ahead"], eps + Lam * w["lam_behind"]
            if b0 >= run_bv:
                break
            if b0 > cursor:
                segs.append(("plateau", cursor, b0, h_now))
            segs.append(("fan", b0, min(b1, run_bv), w["k"], w["h_ahead"], w["h_behind"]))
            cursor, h_now = b1, w["h_behind"]
            if b1 >= run_bv:
                break
    if cursor < run_bv:
        segs.append(("plateau", cursor, run_bv, h_now))
    return segs


def fan_state(sysm, seg, bv):
    _, b0, b1, k, h_ahead, h_behind = seg
    h = h_ahead.copy()
    h[k] = sysm.hk_from_lam(h_ahead, k, (bv - sysm.eps) / sysm.Lam)
    return h


def state_at_single(sysm, segs, bv):
    for seg in segs:
        if seg[0] == "plateau" and seg[1] <= bv <= seg[2]:
            return seg[3]
        if seg[0] == "fan" and seg[1] <= bv <= seg[2]:
            return fan_state(sysm, seg, bv)
        if seg[0] == "shock" and seg[1] == bv:
            return seg[3]
    raise ValueError(f"bv {bv} outside the history")


def comp(sysm, h, CT):
    return [float(v) for v in sysm.x_of(h) * CT]


def report_single(sysm, segs, recipe, CT):
    """Report from the closed-form segments: within a fan every fraction is monotone in BV,
    so the nitrate extremes sit at plateau starts, shock afters and fan ends."""
    shocks, transitions, plateaus, cand = [], [], [], []
    for seg in segs:
        if seg[0] == "plateau":
            plateaus.append(dict(bv_start=seg[1], bv_end=seg[2], composition_meq_per_L=comp(sysm, seg[3], CT)))
            cand.append((seg[1], comp(sysm, seg[3], CT)[NIT]))
        elif seg[0] == "shock":
            shocks.append(dict(bv=seg[1], before_meq_per_L=comp(sysm, seg[2], CT), after_meq_per_L=comp(sysm, seg[3], CT)))
            cand.append((seg[1], comp(sysm, seg[3], CT)[NIT]))
        else:
            h_end = fan_state(sysm, seg, seg[2])
            transitions.append(dict(bv_start=seg[1], bv_end=seg[2], start_meq_per_L=comp(sysm, seg[4], CT),
                                    end_meq_per_L=comp(sysm, h_end, CT)))
            cand.append((seg[1], comp(sysm, seg[4], CT)[NIT]))
            cand.append((seg[2], comp(sysm, h_end, CT)[NIT]))
    peak = max(v for _, v in cand)
    peak_bv = min(b for b, v in cand if v == peak)
    limit, limit_bv = recipe["nitrate_limit_meq_per_L"], None
    nit = lambda b: comp(sysm, state_at_single(sysm, segs, b), CT)[NIT]
    for seg in segs:
        if seg[0] in ("plateau", "shock"):
            if comp(sysm, seg[3], CT)[NIT] > limit:
                limit_bv = seg[1]
                break
        else:
            if nit(seg[1]) > limit:
                limit_bv = seg[1]
                break
            if nit(seg[2]) > limit:
                limit_bv = brentq(lambda b: nit(b) - limit, seg[1], seg[2], xtol=1e-13,
                                  rtol=4 * np.finfo(float).eps, maxiter=500)
                break
    samples = [comp(sysm, state_at_single(sysm, segs, b), CT) for b in recipe["sample_bv"]]
    return dict(recipe_id=recipe["recipe_id"], ions=IONS, shocks=shocks, transitions=transitions, plateaus=plateaus,
                nitrate_peak=dict(meq_per_L=float(peak), bv=float(peak_bv)),
                nitrate_limit_bv=None if limit_bv is None else float(limit_bv), samples=samples)


# ------------------------------------------------------------------ two feeds: front tracking
class Jump:
    """One jump of family k: h_k = ea ahead (outlet side), eb behind (inlet side); H is the full
    root vector on the ahead side (H[k] == ea); the jump moves on a straight line from
    (xi0, bv0). ea == eb marks the exact edge of a spreading wave (a characteristic)."""
    __slots__ = ("k", "ea", "eb", "H", "xi0", "bv0", "alive", "block", "is_shock")

    def __init__(self, k, ea, eb, H, xi0, bv0, block, is_shock):
        self.k, self.ea, self.eb = k, float(ea), float(eb)
        self.H = np.array(H, float)
        self.H[k] = self.ea
        self.xi0, self.bv0, self.alive, self.block, self.is_shock = float(xi0), float(bv0), True, block, is_shock

    def sig(self, sysm):
        return self.ea * self.eb * float(np.prod(np.delete(self.H, self.k))) / sysm.prod_a

    def speed(self, sysm):
        return sysm.speed(self.sig(sysm))

    def H_behind(self):
        Hb = self.H.copy()
        Hb[self.k] = self.eb
        return Hb

    def exit_bv(self, sysm):
        return self.bv0 + (1.0 - self.xi0) / self.speed(sysm)


def make_block(sysm, wave, bv0, block, n_pieces, extra=None):
    """Jumps of one Riemann wave launched at (xi = 0, bv0), ordered from the outlet side to the
    inlet side. A shock is one jump; a fan is a head marker, n_pieces jumps on a grid of h_k
    values (plus the value `extra` when it lies inside the range) and a tail marker."""
    k, ha, hb = wave["k"], wave["h_ahead"], wave["h_behind"]
    if wave["kind"] == "shock":
        return [Jump(k, ha[k], hb[k], ha, 0.0, bv0, block, True)]
    grid = np.linspace(ha[k], hb[k], n_pieces + 1)
    if extra is not None and min(ha[k], hb[k]) < extra < max(ha[k], hb[k]):
        grid = np.sort(np.append(grid, extra)) if ha[k] < hb[k] else np.sort(np.append(grid, extra))[::-1]
    jumps = [Jump(k, grid[0], grid[0], ha, 0.0, bv0, block, False)]
    for g0, g1 in zip(grid[:-1], grid[1:]):
        jumps.append(Jump(k, g0, g1, ha, 0.0, bv0, block, False))
    jumps.append(Jump(k, grid[-1], grid[-1], ha, 0.0, bv0, block, False))
    return jumps


def reachable(jumps, k, target):
    """Jumps whose invariants other than family k equal the expected ones. A jump whose
    invariants were never updated by an earlier (faster) wave left the bed before that wave
    could reach it, so no slower wave reaches it either."""
    out = []
    for jp in jumps:
        if not jp.alive:
            continue
        idx = [i for i in range(len(target)) if i != k]
        if np.allclose(jp.H[idx], target[idx], rtol=0, atol=1e-12):
            out.append(jp)
    return out


def cross(sysm, A, B, target):
    """All crossings of block A (family k, behind) through block B (family j > k, ahead).
    Lattice point (m, n): A's m-th jump meets B's n-th jump counted from B's tail. Each point is
    the intersection of two straight segments: A_m coming from its crossing with B_{n-1}, B_n
    from its crossing with A_{m-1}. Origins and states of both blocks are updated in place.
    `target` holds the invariants of the region where the two blocks meet (its k and j entries
    are ignored); jumps that do not carry them are unreachable and are left alone."""
    if not A or not B:
        return
    k, j = A[0].k, B[0].k
    assert k < j
    tA, tB = target.copy(), target.copy()
    tA[j] = tB[k] = np.nan
    A = [a for a in A if a.alive and np.allclose(np.delete(a.H, [k, j]), np.delete(target, [k, j]), rtol=0, atol=1e-12)]
    Bt = [b for b in B if b.alive and np.allclose(np.delete(b.H, [k, j]), np.delete(target, [k, j]), rtol=0, atol=1e-12)][::-1]
    if not A or not Bt:
        return
    M, L = len(A), len(Bt)
    ea = np.array([a.ea for a in A]); eb = np.array([a.eb for a in A])
    ba = np.array([b.ea for b in Bt]); bb = np.array([b.eb for b in Bt])
    others = [i for i in range(sysm.n - 1) if i not in (k, j)]
    rest = float(np.prod(target[others])) / sysm.prod_a if others else 1.0 / sysm.prod_a
    # speeds on the lattice: A_m between B_{n-1} and B_n has h_j = bb[n]; B_n between A_{m-1} and A_m has h_k = ea[m]
    sigA = (ea * eb)[:, None] * bb[None, :] * rest                 # (M, L)
    sigB = (ba * bb)[None, :] * ea[:, None] * rest
    vA, vB = 1.0 / (sysm.eps + sysm.Lam * sigA), 1.0 / (sysm.eps + sysm.Lam * sigB)
    Xi = np.full((M + 1, L + 1), np.nan); Bv = np.full((M + 1, L + 1), np.nan)
    valid = np.zeros((M + 1, L + 1), bool)
    Xi[1:, 0] = [a.xi0 for a in A]; Bv[1:, 0] = [a.bv0 for a in A]; valid[1:, 0] = True
    Xi[0, 1:] = [b.xi0 for b in Bt]; Bv[0, 1:] = [b.bv0 for b in Bt]; valid[0, 1:] = True
    for d in range(2, M + L + 1):                   # anti-diagonals m + n = d, 1 <= m <= M, 1 <= n <= L
        m = np.arange(max(1, d - L), min(M, d - 1) + 1)
        n = d - m
        xa, ta = Xi[m, n - 1], Bv[m, n - 1]         # A_m after B_{n-1}
        xb, tb = Xi[m - 1, n], Bv[m - 1, n]         # B_n after A_{m-1}
        va, vb = vA[m - 1, n - 1], vB[m - 1, n - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (xb - xa - vb * tb + va * ta) / (va - vb)
            x = xa + va * (t - ta)
        ok = valid[m, n - 1] & valid[m - 1, n] & (va > vb) & np.isfinite(t) & (x <= 1.0) & (t >= np.maximum(ta, tb) - 1e-9)
        Xi[m, n], Bv[m, n], valid[m, n] = x, t, ok
    # write back: last valid crossing of every jump
    for mi, a in enumerate(A):
        row = valid[mi + 1, 1:]
        nl = int(np.argmin(row)) if not row.all() else L        # first invalid index = number crossed
        if nl > 0:
            a.xi0, a.bv0 = float(Xi[mi + 1, nl]), float(Bv[mi + 1, nl])
            a.H[j] = ba[nl - 1]                                   # ahead value of the last crossed B jump
    for ni, b in enumerate(Bt):
        col = valid[1:, ni + 1]
        ml = int(np.argmin(col)) if not col.all() else M
        if ml > 0:
            b.xi0, b.bv0 = float(Xi[ml, ni + 1]), float(Bv[ml, ni + 1])
            b.H[k] = eb[ml - 1]                                   # behind value of the last A jump that crossed it


def merge_same_family(sysm, A, B, target):
    """Same-family catch-up of block A (behind) on block B (ahead): a chain of merges at the
    junction. Returns every surviving jump of both blocks (outlet side first); jumps that do not
    carry the expected invariants `target` are unreachable and pass through untouched."""
    k = (A or B)[0].k
    reach_B, reach_A = reachable(B, k, target), reachable(A, k, target)
    untouched = [c for c in A + B if c.alive and c not in reach_A and c not in reach_B]
    chain = reach_B + reach_A
    q = len(reach_B)                                 # index of the first A element
    if q == 0 or q == len(chain):
        return untouched + chain

    def meet(front, back):
        """Intersection of `back` catching `front`, or None."""
        vf, vb = front.speed(sysm), back.speed(sysm)
        if vb <= vf:
            return None
        t = (front.xi0 - back.xi0 - vf * front.bv0 + vb * back.bv0) / (vb - vf)
        x = back.xi0 + vb * (t - back.bv0)
        if x > 1.0 or t < max(front.bv0, back.bv0) - 1e-9:
            return None
        return x, t

    # Only the junction element can collide: pristine fan pieces of one block spread apart, and a
    # block is a single shock otherwise. q indexes the junction element (the one just behind the
    # junction, or the merged element after a merge, which may sit at either end of the chain).
    while len(chain) >= 2:
        best = None
        for i in (q - 1, q):
            if 0 <= i < len(chain) - 1:
                hit = meet(chain[i], chain[i + 1])
                if hit is not None and (best is None or hit[1] < best[1][1]):
                    best = (i, hit)
        if best is None:
            break
        i, (x, t) = best
        front, back = chain[i], chain[i + 1]
        front.alive = back.alive = False
        if back.eb == front.ea:
            # zero strength: the shock has died exactly on a grid value. The surviving fan on
            # either side continues with an exact edge characteristic from this point.
            v = back.eb
            del chain[i:i + 2]
            marker = None
            if i < len(chain) and not chain[i].is_shock and chain[i].ea == v:
                nb = chain[i]
                marker = Jump(nb.k, v, v, nb.H, x, t, nb.block, False)
            elif i - 1 >= 0 and not chain[i - 1].is_shock and chain[i - 1].eb == v:
                nb = chain[i - 1]
                marker = Jump(nb.k, v, v, nb.H_behind(), x, t, nb.block, False)
            if marker is not None:
                chain.insert(i, marker)
            q = min(max(i, 0), max(len(chain) - 1, 0))
            continue
        is_shock = back.eb < front.ea
        if is_shock:
            block = back.block if back.is_shock else front.block
        else:
            block = front.block if not front.is_shock else back.block
        merged = Jump(back.k, front.ea, back.eb, front.H, x, t, block, is_shock)
        chain[i:i + 2] = [merged]
        q = i
    return untouched + [c for c in chain if c.alive]


def two_feed_jumps(sysm, hD, hU1, hU2, bv_s, n_pieces):
    """All jumps after every interaction, with their final straight trajectories."""
    W1 = riemann_waves(sysm, hU1, hD)
    W2 = riemann_waves(sysm, hU2, hU1)
    byk1 = {w["k"]: w for w in W1}
    byk2 = {w["k"]: w for w in W2}
    blocks1 = {k: make_block(sysm, w, 0.0, f"W1_{k}", n_pieces, extra=hU2[k]) for k, w in byk1.items()}
    blocks2 = {k: make_block(sysm, w, bv_s, f"W2_{k}", n_pieces, extra=hD[k]) for k, w in byk2.items()}
    nf = sysm.n - 1

    def target(k, j):
        """Invariants of the region where W2_k meets W1_j: components below k already changed
        by the faster second-feed waves, those between k and j still at the first feed, those
        above j already at the bed state."""
        t = np.empty(nf)
        for i in range(nf):
            t[i] = hU2[i] if i < k else (hU1[i] if i < j else hD[i])
        return t
    for k in range(nf):                               # W2_k crosses W1_j for j > k, then meets W1_k
        if k not in blocks2:
            continue
        for j in range(nf - 1, k, -1):
            if j in blocks1:
                cross(sysm, blocks2[k], blocks1[j], target(k, j))
        if k in blocks1:
            survivors = merge_same_family(sysm, blocks2[k], blocks1[k], target(k, k))
            blocks1[k] = [c for c in survivors if c.block == f"W1_{k}"]
            blocks2[k] = [c for c in survivors if c.block == f"W2_{k}"]
    return [jp for blk in list(blocks1.values()) + list(blocks2.values()) for jp in blk if jp.alive]


class Outlet:
    """Effluent history from the jumps' arrivals at xi = 1."""

    def __init__(self, sysm, jumps, hD, run_bv):
        self.sysm, self.run_bv, self.hD = sysm, run_bv, hD
        allev = sorted(((jp.exit_bv(sysm), jp) for jp in jumps if jp.exit_bv(sysm) >= 0.0), key=lambda e: e[0])
        self.events = [e for e in allev if e[0] <= run_bv]          # inside the window
        self.ev_bv = np.array([e[0] for e in self.events])
        shocks = [(b, jp) for b, jp in allev if jp.is_shock]
        # spreading waves: per block, the exits of its fan jumps with their characteristic values
        # (exact at a marker, the geometric mean of the two values for a piece). A shock that is
        # absorbing the wave at the outlet bounds its span; the wave's value at the shock is the
        # interpolant extrapolated to the shock (the shock's own discrete edge value lags by one
        # piece), so the shock itself adds no knot.
        fans = {}
        for b, jp in allev:
            if not jp.is_shock:
                eta = jp.ea if jp.ea == jp.eb else math.sqrt(jp.ea * jp.eb)
                fans.setdefault(jp.block, []).append((b, eta, jp))
        self.splines = {}            # block -> (span start, span end, k, first jump, last jump, spline)
        self.bounded = {}            # shock exit bv -> True when a spreading wave reaches it
        for blk, pts in fans.items():
            pts.sort(key=lambda p: p[0])
            first, last, k = pts[0][2], pts[-1][2], pts[0][2].k
            b0, b1 = pts[0][0], pts[-1][0]
            # a shock bounds the wave when it carries the wave's edge state AND sits where the
            # absorbed edge jump would have arrived: within a few piece spacings of the span
            spacing = (b1 - b0) / max(len(pts) - 1, 1)
            for b, sj in shocks:
                if sj.k == k and b <= b0 and b0 - b <= 4.0 * spacing + 1e-9 and np.array_equal(sj.H_behind(), first.H):
                    b0 = min(b0, b); self.bounded[b] = True
                if sj.k == k and b >= b1 and b - b1 <= 4.0 * spacing + 1e-9 and np.array_equal(sj.H, last.H_behind()):
                    b1 = max(b1, b); self.bounded[b] = True
            bs = np.array([p[0] for p in pts]); es = np.array([p[1] for p in pts])
            keep = np.concatenate([[True], np.diff(bs) > 0])
            spl = PchipInterpolator(bs[keep], es[keep], extrapolate=True) if keep.sum() >= 2 else None
            if b0 <= run_bv:
                self.splines[blk] = (b0, min(b1, run_bv), k, first, last, spl)

    def state(self, bv, before=False):
        """Roots of the effluent at bv: the state behind the last jump that has left (with
        before=True, the last jump that left strictly before bv, i.e. the state ahead of a jump
        arriving exactly at bv), with the smooth variation of every spreading wave open at bv."""
        i = int(np.searchsorted(self.ev_bv, bv, side="left" if before else "right")) - 1
        H = self.hD.copy() if i < 0 else self.events[i][1].H_behind()
        for b0, b1, k, _, _, spl in self.splines.values():
            # a wave bounded by a shock applies only on its own side of that shock
            inside = b0 < bv < b1 or (bv == b0 and not before) or (bv == b1 and before)
            if spl is not None and inside:
                H[k] = float(spl(bv))
        return H

    def edge_state(self, bv, start):
        """State at a transition edge: just behind the jump arriving at bv (start of a
        transition) or just ahead of it (end), with the spreading wave's own value at bv."""
        return self.state(bv, before=not start)

    def structure(self):
        """Shocks, and transitions as maximal continuous non-constant stretches: the union of the
        spreading waves' spans at the outlet, each span extended to a shock that bounds it (the
        shock's state on the span's side equals the span's edge state, which happens when the
        edge jump was absorbed), merged where they overlap or touch, and split at interior shocks."""
        shocks = [(b, jp) for b, jp in self.events if jp.is_shock]
        spans = sorted([b0, b1] for b0, b1, _, _, _, _ in self.splines.values())
        merged = []
        for s in spans:
            if merged and s[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], s[1])
            else:
                merged.append(list(s))
        trans = []
        for s in merged:
            cuts = [s[0]] + [b for b, _ in shocks if s[0] < b < s[1]] + [s[1]]
            trans += [[c0, c1] for c0, c1 in zip(cuts[:-1], cuts[1:]) if c1 > c0]
        return shocks, trans


def report_two_feed(sysm, recipe, CT, hD, hU1, hU2, bv_s, n_pieces):
    run_bv = recipe["run_bv"]
    jumps = two_feed_jumps(sysm, hD, hU1, hU2, bv_s, n_pieces)
    out = Outlet(sysm, jumps, hD, run_bv)
    shocks_ev, trans = out.structure()
    shock_bvs = [b for b, _ in shocks_ev]
    # plateaus: the complement of transitions, split at shocks
    cuts = sorted(set([0.0, run_bv] + shock_bvs + [t[0] for t in trans] + [t[1] for t in trans]))
    plateaus = []
    for c0, c1 in zip(cuts[:-1], cuts[1:]):
        if c1 - c0 <= 0:
            continue
        if any(t[0] <= c0 and c1 <= t[1] for t in trans):
            continue
        plateaus.append((c0, c1))
    # a shock's two sides come from the outlet state just before and just after it, so a
    # spreading wave it is absorbing contributes its interpolated (not discrete) edge value
    shocks = [dict(bv=b, before_meq_per_L=comp(sysm, out.state(b, before=True), CT),
                   after_meq_per_L=comp(sysm, out.state(b), CT)) for b, jp in shocks_ev]
    transitions = [dict(bv_start=t0, bv_end=t1, start_meq_per_L=comp(sysm, out.edge_state(t0, True), CT),
                        end_meq_per_L=comp(sysm, out.edge_state(t1, False), CT)) for t0, t1 in trans]
    plats = [dict(bv_start=c0, bv_end=c1, composition_meq_per_L=comp(sysm, out.state(0.5 * (c0 + c1)), CT))
             for c0, c1 in plateaus]

    def nit_in(t0, t1):
        """Nitrate along the transition [t0, t1], continuous up to and including both edges."""
        def f(b):
            if b <= t0:
                return float(sysm.x_of(out.edge_state(t0, True))[NIT] * CT)
            if b >= t1:
                return float(sysm.x_of(out.edge_state(t1, False))[NIT] * CT)
            return float(sysm.x_of(out.state(b))[NIT] * CT)
        return f
    nit = lambda b: float(sysm.x_of(out.state(b))[NIT] * CT)
    # nitrate peak and first exceedance
    cand = [(c0, comp(sysm, out.state(0.5 * (c0 + c1)), CT)[NIT]) for c0, c1 in plateaus]
    cand += [(b, nit(b)) for b, jp in shocks_ev]
    for t0, t1 in trans:
        f = nit_in(t0, t1)
        grid = np.linspace(t0, t1, 401)
        vals = np.array([f(b) for b in grid])
        i = int(np.argmax(vals))
        lo, hi = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
        r = minimize_scalar(lambda b: -f(b), bounds=(lo, hi), method="bounded", options=dict(xatol=1e-12))
        cand.append((t0, vals[0]))
        cand.append((float(r.x), -float(r.fun)))
        cand.append((t1, vals[-1]))
    peak = max(v for _, v in cand)
    peak_bv = min(b for b, v in cand if v >= peak - 1e-12 * max(1.0, abs(peak)))
    limit, limit_bv = recipe["nitrate_limit_meq_per_L"], None
    items = [("p", c0, c1) for c0, c1 in plateaus] + [("s", b, b) for b in shock_bvs] + [("t", t0, t1) for t0, t1 in trans]
    items.sort(key=lambda it: (it[1], 0 if it[0] == "s" else 1))
    for kind, b0, b1 in items:
        if kind == "p":
            if comp(sysm, out.state(0.5 * (b0 + b1)), CT)[NIT] > limit:
                limit_bv = b0
                break
        elif kind == "s":
            if nit(b0) > limit:
                limit_bv = b0
                break
        else:
            f = nit_in(b0, b1)
            grid = np.linspace(b0, b1, 401)
            vals = np.array([f(b) for b in grid])
            if vals[0] > limit:
                limit_bv = b0
                break
            above = np.flatnonzero(vals > limit)
            if above.size:
                i = int(above[0])
                limit_bv = brentq(lambda b: f(b) - limit, grid[i - 1], grid[i], xtol=1e-13,
                                  rtol=4 * np.finfo(float).eps, maxiter=500)
                break
    samples = [comp(sysm, out.state(b), CT) for b in recipe["sample_bv"]]
    return dict(recipe_id=recipe["recipe_id"], ions=IONS, shocks=shocks, transitions=transitions, plateaus=plats,
                nitrate_peak=dict(meq_per_L=float(peak), bv=float(peak_bv)),
                nitrate_limit_bv=None if limit_bv is None else float(limit_bv), samples=samples)


def extrapolate(r1, r2):
    """Richardson extrapolation of two reports (resolutions N and 2N, second-order error)."""
    def ex(a, b):
        return b + (b - a) / 3.0

    def ex_list(a, b):
        return [ex(u, v) for u, v in zip(a, b)]
    assert len(r1["shocks"]) == len(r2["shocks"]) and len(r1["transitions"]) == len(r2["transitions"]) \
        and len(r1["plateaus"]) == len(r2["plateaus"]), "structure differs between resolutions"
    out = json.loads(json.dumps(r2))
    for s1, s2, so in zip(r1["shocks"], r2["shocks"], out["shocks"]):
        so["bv"] = ex(s1["bv"], s2["bv"])
    for t1, t2, to in zip(r1["transitions"], r2["transitions"], out["transitions"]):
        to["bv_start"], to["bv_end"] = ex(t1["bv_start"], t2["bv_start"]), ex(t1["bv_end"], t2["bv_end"])
        to["start_meq_per_L"] = ex_list(t1["start_meq_per_L"], t2["start_meq_per_L"])
        to["end_meq_per_L"] = ex_list(t1["end_meq_per_L"], t2["end_meq_per_L"])
    for p1, p2, po in zip(r1["plateaus"], r2["plateaus"], out["plateaus"]):
        po["bv_start"], po["bv_end"] = ex(p1["bv_start"], p2["bv_start"]), ex(p1["bv_end"], p2["bv_end"])
    out["nitrate_peak"]["meq_per_L"] = ex(r1["nitrate_peak"]["meq_per_L"], r2["nitrate_peak"]["meq_per_L"])
    out["nitrate_peak"]["bv"] = ex(r1["nitrate_peak"]["bv"], r2["nitrate_peak"]["bv"])
    if r1["nitrate_limit_bv"] is not None and r2["nitrate_limit_bv"] is not None:
        out["nitrate_limit_bv"] = ex(r1["nitrate_limit_bv"], r2["nitrate_limit_bv"])
    out["samples"] = [ex_list(a, b) for a, b in zip(r1["samples"], r2["samples"])]
    # the window edges are exact
    for po in out["plateaus"]:
        po["bv_start"] = 0.0 if abs(po["bv_start"]) < 1e-9 else po["bv_start"]
    return out


# ------------------------------------------------------------------ driver
def solve(recipe, n_pieces=N_PIECES, verbose=False):
    assert recipe["ions"] == IONS
    a = [recipe["alpha"][i] for i in IONS]
    CT = float(recipe["C_T_meq_per_L"])
    Lam = 1000.0 * float(recipe["Q_eq_per_L_bed"]) / CT
    sysm = System(a, recipe["eps"], Lam)
    y0 = np.array([recipe["initial_resin_fraction"][i] for i in IONS], float)
    x0 = (y0 / sysm.a) / np.sum(y0 / sysm.a)
    feeds = recipe["feed_program"]
    xF1 = np.array([feeds[0]["composition_meq_per_L"][i] for i in IONS], float) / CT
    hD, hU1 = sysm.roots(x0), sysm.roots(xF1)
    if len(feeds) == 1:
        return report_single(sysm, outlet_history_single(sysm, hU1, hD, recipe["run_bv"]), recipe, CT)
    xF2 = np.array([feeds[1]["composition_meq_per_L"][i] for i in IONS], float) / CT
    hU2, bv_s = sysm.roots(xF2), float(feeds[1]["start_bv"])
    r1 = report_two_feed(sysm, recipe, CT, hD, hU1, hU2, bv_s, n_pieces)
    r2 = report_two_feed(sysm, recipe, CT, hD, hU1, hU2, bv_s, 2 * n_pieces)
    if verbose:
        d = max([abs(s1["bv"] - s2["bv"]) / max(1.0, s2["bv"]) for s1, s2 in zip(r1["shocks"], r2["shocks"])] +
                [abs(t1["bv_start"] - t2["bv_start"]) / max(1.0, t2["bv_start"]) for t1, t2 in zip(r1["transitions"], r2["transitions"])] +
                [abs(t1["bv_end"] - t2["bv_end"]) / max(1.0, t2["bv_end"]) for t1, t2 in zip(r1["transitions"], r2["transitions"])] + [0.0])
        print(f"two-feed engine: N={n_pieces} vs {2 * n_pieces}: largest relative BV change {d:.2e}", file=sys.stderr)
    return extrapolate(r1, r2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--pieces", type=int, default=N_PIECES)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    with open(args.recipe, encoding="utf-8") as fh:
        recipe = json.load(fh)
    report = solve(recipe, args.pieces, args.verbose)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
