#!/usr/bin/env python
"""Passive electrotonic properties of a branched dendritic tree (CABLE_SPEC.md).

Exact cable theory on every segment: admittances are propagated from the terminals to the soma
with the hyperbolic recursion, potentials from the injection site outwards with the two-point
transfer ratio of a loaded cable (written with decaying exponentials so that long or fast cables
never overflow). DC is the Laplace variable s = 0, AC is s = j 2 pi f. The equalization time
constants are the roots of the entire characteristic function E(s) built by clearing the
denominators of the admittance recursion (cosh(gamma a), gamma sinh(gamma a) and
sinh(gamma a)/gamma are all even in gamma, hence single-valued in s); they are bracketed on a
geometric scan of s finer than the guaranteed separation and polished with brentq; the somatic
step-response coefficients are tau_k times the residue of Z_soma = prod(D) / E at each root, the
derivative of E coming from a complex step.

usage: cabletree.py --neuron <neuron.json> --output <report.json>
"""
import argparse
import cmath
import json
import math

import numpy as np
from scipy.optimize import brentq

SCAN_RATIO = 1.0 + 2e-4      # geometric step of the root scan in s (guaranteed separation 1e-3)


class Seg:
    def __init__(self, d):
        self.id, self.parent = d["id"], d["parent"]
        L, dia = d["L_um"] * 1e-4, d["d_um"] * 1e-4                      # cm
        Rm, Ri, Cm = d["Rm_ohm_cm2"], d["Ri_ohm_cm"], d["Cm_uF_cm2"] * 1e-6
        self.L = L
        self.lam = math.sqrt(Rm * dia / (4.0 * Ri))                         # cm
        self.tau = Rm * Cm                                                  # s
        self.G = 0.5 * math.pi * dia ** 1.5 / math.sqrt(Rm * Ri) * 1e9      # nS
        self.a = L / self.lam                                               # electrotonic length
        self.end = d["end"]
        self.children = []


def cable_in(G, g, a, YL):
    """Admittance at the near end of a cable of electrotonic length a (at s: gamma g), load YL at
    the far end (YL = None for a killed end)."""
    t = cmath.tanh(g * a)
    if YL is None:
        return G * g / t
    return G * g * (YL + G * g * t) / (G * g + YL * t)


def ratio(G, g, a, YL, xa):
    """V(xa) / V(0) along a cable of electrotonic length a with load YL at the far end, xa the
    electrotonic distance from the near end (0 <= xa <= a)."""
    # V(x)/V(0) = [YL sinh(a-x) + G g cosh(a-x)] / [YL sinh(a) + G g cosh(a)], written with
    # e^{-(..)} factors: numerator ~ e^{g(a-x)} [...], denominator ~ e^{g a} [...]
    r, b = g * (a - xa), g * a
    e_r, e_b = cmath.exp(-2 * r), cmath.exp(-2 * b)
    if YL is None:                                                          # killed: sinh ratio
        return cmath.exp(r - b) * (1 - e_r) / (1 - e_b)
    num = YL * (1 - e_r) + G * g * (1 + e_r)
    den = YL * (1 - e_b) + G * g * (1 + e_b)
    return cmath.exp(r - b) * num / den


class Tree:
    def __init__(self, d):
        self.id = d["neuron_id"]
        so = d["soma"]
        area = math.pi * (so["d_um"] * 1e-4) ** 2                            # cm2
        self.Gs = area / so["Rm_ohm_cm2"] * 1e9 + so["shunt_nS"]           # nS
        self.Cs = area * so["Cm_uF_cm2"] * 1e-6 * 1e9                       # nF (nS * s)
        self.segs = {s["id"]: Seg(s) for s in d["segments"]}
        self.soma_children = []
        for s in self.segs.values():
            if s.parent == 0:
                self.soma_children.append(s)
            else:
                self.segs[s.parent].children.append(s)
        self.order = sorted(self.segs.values(), key=lambda s: -self.depth(s))   # leaves first
        self.d = d

    def depth(self, s):
        n = 0
        while s.parent != 0:
            s = self.segs[s.parent]
            n += 1
        return n

    # ------------------------------------------------------------ admittances at s
    def gammas(self, s):
        return {i: cmath.sqrt(1 + s * seg.tau) for i, seg in self.segs.items()}

    def load(self, seg, Ydown):
        """Load at the distal end of seg: children or terminal boundary (None = killed)."""
        if seg.children:
            return sum(Ydown[c.id] for c in seg.children)
        if seg.end["type"] == "sealed":
            return 0.0
        if seg.end["type"] == "shunt":
            return complex(seg.end["g_nS"])
        return None

    def downward(self, s, gam):
        Ydown = {}
        for seg in self.order:
            Ydown[seg.id] = cable_in(seg.G, gam[seg.id], seg.a, self.load(seg, Ydown))
        return Ydown

    def upward(self, s, gam, Ydown):
        """Yup[i]: admittance seen at the proximal node of segment i looking away from i."""
        Yup = {}
        Ysoma = self.Gs + s * self.Cs
        for seg in sorted(self.segs.values(), key=self.depth):
            if seg.parent == 0:
                Yup[seg.id] = Ysoma + sum(Ydown[c.id] for c in self.soma_children if c is not seg)
            else:
                p = self.segs[seg.parent]
                Yp_rev = cable_in(p.G, gam[p.id], p.a, Yup[p.id])               # parent looking proximal
                Yup[seg.id] = Yp_rev + sum(Ydown[c.id] for c in p.children if c is not seg)
        return Yup

    # ------------------------------------------------------------ response at s
    def respond(self, s, src, targets):
        """Potentials at the target locations for unit current at src, at Laplace variable s."""
        gam = self.gammas(s)
        Ydown = self.downward(s, gam)
        Yup = self.upward(s, gam, Ydown)
        Ysoma = self.Gs + s * self.Cs
        node_V = {}                      # potentials at nodes: 0 = soma, i = distal node of segment i
        direction = {}                   # segment id -> 'down' (prox->dist) or 'up' (dist->prox)
        si, f = src["segment"], src["fraction"]
        if si == 0:
            Vsrc = 1.0 / (Ysoma + sum(Ydown[c.id] for c in self.soma_children))
            node_V[0] = Vsrc
            start_nodes = [0]
        else:
            seg = self.segs[si]
            g = gam[si]
            YL = self.load(seg, Ydown)
            Yd = cable_in(seg.G, g, seg.a * (1 - f), YL) if f < 1 else (YL if YL is not None else None)
            Yp = cable_in(seg.G, g, seg.a * f, Yup[si]) if f > 0 else Yup[si]
            if Yd is None:
                raise ValueError("current injected at a killed end")
            Vsrc = 1.0 / (Yd + Yp)
            # distal node of the segment and its proximal node
            node_V[si] = Vsrc * (ratio(seg.G, g, seg.a * (1 - f), YL, seg.a * (1 - f)) if f < 1 else 1.0)
            prox = seg.parent
            node_V[prox] = Vsrc * (ratio(seg.G, g, seg.a * f, Yup[si], seg.a * f) if f > 0 else 1.0)
            direction[si] = "split"
            start_nodes = [si, prox]
        # propagate outwards over the tree
        visited = set(start_nodes)
        stack = list(start_nodes)
        while stack:
            n = stack.pop()
            V = node_V[n]
            # children of node n (segments whose proximal node is n) propagate downward
            kids = self.soma_children if n == 0 else self.segs[n].children
            for c in kids:
                if c.id in direction:
                    continue
                direction[c.id] = "down"
                node_V[c.id] = V * ratio(c.G, gam[c.id], c.a, self.load(c, Ydown), c.a)
                if c.id not in visited:
                    visited.add(c.id)
                    stack.append(c.id)
            # the segment whose distal node is n propagates upward
            if n != 0 and n not in direction:
                seg = self.segs[n]
                direction[n] = "up"
                p = seg.parent
                node_V[p] = V * ratio(seg.G, gam[n], seg.a, Yup[n], seg.a)
                if p not in visited:
                    visited.add(p)
                    stack.append(p)
        out = []
        for tg in targets:
            ti, gfrac = tg["segment"], tg["fraction"]
            if ti == 0:
                out.append(node_V[0])
                continue
            seg, g = self.segs[ti], gam[ti]
            if ti == si:
                if gfrac >= f:
                    out.append(Vsrc * ratio(seg.G, g, seg.a * (1 - f), self.load(seg, Ydown), seg.a * (gfrac - f)))
                else:
                    out.append(Vsrc * ratio(seg.G, g, seg.a * f, Yup[si], seg.a * (f - gfrac)))
            elif direction[ti] == "down":
                out.append(node_V[seg.parent] * ratio(seg.G, g, seg.a, self.load(seg, Ydown), seg.a * gfrac))
            else:
                out.append(node_V[ti] * ratio(seg.G, g, seg.a, Yup[ti], seg.a * (1 - gfrac)))
        return Vsrc, out

    # ------------------------------------------------------------ characteristic function
    def char(self, s):
        """E(s) (entire) and prod D over the soma's children, in nS units (Z_soma = prodD / E)."""
        gam = self.gammas(s)
        ND = {}
        for seg in self.order:
            g, a, G = gam[seg.id], seg.a, seg.G
            C, S1, S2 = cmath.cosh(g * a), g * cmath.sinh(g * a), (cmath.sinh(g * a) / g if g != 0 else complex(a))
            if seg.children:
                NL, DL = self.combine([ND[c.id] for c in seg.children])
            elif seg.end["type"] == "sealed":
                NL, DL = 0.0, 1.0
            elif seg.end["type"] == "shunt":
                NL, DL = complex(seg.end["g_nS"]), 1.0
            else:
                NL, DL = 1.0, 0.0
            ND[seg.id] = (G * (NL * C + G * DL * S1), G * DL * C + NL * S2)
        Nc, Dc = self.combine([ND[c.id] for c in self.soma_children])
        E = (self.Gs + s * self.Cs) * Dc + Nc
        return E, Dc

    @staticmethod
    def combine(pairs):
        D = 1.0
        for _, d in pairs:
            D *= d
        N = 0.0
        for k, (n, _) in enumerate(pairs):
            prod = n
            for j, (_, d) in enumerate(pairs):
                if j != k:
                    prod *= d
            N += prod
        return N, D

    def modes(self, tau_min):
        tau_max = max([seg.tau for seg in self.segs.values()] + [self.Cs / self.Gs if self.Gs > 0 else 0.0])
        s_lo, s_hi = -1.0 / tau_min, -(1.0 - 1e-6) / tau_max
        E = lambda s: self.char(s)[0].real
        n = int(math.ceil(math.log(s_lo / s_hi) / math.log(SCAN_RATIO))) + 1
        grid = s_lo / SCAN_RATIO ** np.arange(n + 1)
        grid = grid[grid <= s_hi * (1 + 1e-15)]
        grid = np.append(grid, s_hi)
        vals = np.array([E(s) for s in grid])
        out = []
        for k in range(len(grid) - 1):
            if vals[k] == 0.0:
                out.append(grid[k])
            elif vals[k] * vals[k + 1] < 0:
                out.append(brentq(E, grid[k], grid[k + 1], xtol=1e-300, rtol=1e-15, maxiter=300))
        res = []
        for s in sorted(out):
            tau = -1.0 / s
            if tau < tau_min:
                continue
            h = 1e-7 * abs(s)
            Eh, Dc = self.char(complex(s, h))
            dE = Eh.imag / h
            Dc0 = self.char(s)[1].real
            res.append((tau, tau * Dc0 / dE))              # GOhm * s
        res.sort(key=lambda t: -t[0])
        return res

    # ------------------------------------------------------------ report
    def report(self):
        d = self.d
        rin = []
        for site in d["input_resistance_sites"]:
            V, _ = self.respond(0.0, site, [])
            rin.append(dict(site=site, R_MOhm=V.real * 1e3))                    # GOhm -> MOhm
        att = []
        for pr in d["attenuation_pairs"]:
            V, (Vt,) = self.respond(0.0, pr["source"], [pr["target"]])
            att.append(dict(source=pr["source"], target=pr["target"], factor=(Vt / V).real))
        imp = []
        for q in d["impedance_queries"]:
            s = complex(0.0, 2 * math.pi * q["frequency_Hz"])
            _, (Z,) = self.respond(s, q["source"], [q["target"]])
            ph = math.degrees(cmath.phase(Z))
            if ph <= -180.0:
                ph += 360.0
            imp.append(dict(source=q["source"], target=q["target"], frequency_Hz=q["frequency_Hz"],
                            magnitude_MOhm=abs(Z) * 1e3, phase_deg=ph))
        modes = [dict(tau_ms=tau * 1e3, coefficient_MOhm=c * 1e3) for tau, c in self.modes(d["tau_min_ms"] * 1e-3)]
        return dict(neuron_id=self.id, input_resistance=rin, attenuation=att, impedance=imp, modes=modes)


def solve(d):
    return Tree(d).report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neuron", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.neuron, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
