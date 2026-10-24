"""Closed-form checks of refA/reference.py (BenDaniel-Duke conditions throughout).

  t1  finite square well (outer barriers identical to the leads): even/odd equations
      (k/m_w) tan(k L/2) = kappa/m_b,  -(k/m_w) cot(k L/2) = kappa/m_b; above the barrier the
      single-layer formula T = 1 / (1 + (K/Q - Q/K)^2 sin^2(q L) / 4) and maxima T = 1 at q L = n pi
  t2  symmetric double well (outer barriers = leads): even/odd equations matched at the well edge
      with (psi'/m)/psi = (kappa/m_b) tanh(kappa b) (even) or coth (odd) from the central barrier
  t3  triangular well against a step: (beta/m) Ai'(z0) = (kappa_L/m_L) Ai(z0), z0 = -lambda E,
      for the low states that do not reach the end of the linear ramp (Airy closed form)
  t7, t8  rectangular barrier: T = 1/(1 + (K/Q + Q/K)^2 sinh^2(kappa d)/4) below the top, the
      sin form above, maxima at E = V + C (n pi / d)^2 / m_b with T = 1
  limit   infinite square well: E_n -> C (n pi / L)^2 / m_w as the barrier height grows
"""
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import brentq
from scipy.special import airy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import reference as R  # noqa: E402

C = 0.0380998212


def roots(f, a, b, n=400001):
    xs = np.linspace(a, b, n)
    v = np.array([f(x) for x in xs])
    out = []
    for i in np.nonzero(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]:
        r = brentq(f, xs[i], xs[i + 1], xtol=1e-16, rtol=8.9e-16, maxiter=500)
        if abs(f(r)) < 1e-6 * (abs(v[i]) + abs(v[i + 1])):     # skip tan/cot poles
            out.append(r)
    return sorted(out)


def T_layer(E, mlead, Vlead, mlay, Vlay, d):
    K = math.sqrt(mlead * (E - Vlead) / C) / mlead
    q2 = mlay * (E - Vlay) / C
    if q2 > 0:
        Q = math.sqrt(q2) / mlay
        return 1.0 / (1.0 + 0.25 * (K / Q - Q / K) ** 2 * math.sin(math.sqrt(q2) * d) ** 2)
    Q = math.sqrt(-q2) / mlay
    return 1.0 / (1.0 + 0.25 * (K / Q + Q / K) ** 2 * math.sinh(math.sqrt(-q2) * d) ** 2)


def load(name):
    return json.load(open(os.path.join(HERE, "structures", name + ".json")))


def report(name):
    p = os.path.join(HERE, "reports", name + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    return R.compute_report(load(name))


def check_single_layer(name, s, rep, mlead, Vlead, mlay, Vlay, d):
    res = {}
    res["T_rel"] = max(abs(q["T"] / T_layer(q["E_eV"], mlead, Vlead, mlay, Vlay, d) - 1)
                       for q in rep["transmission"])
    lo, hi = s["window_eV"]
    nmin = math.ceil(d * math.sqrt(mlay * (lo - Vlay) / C) / math.pi)
    Ex = []
    n = nmin
    while True:
        e = Vlay + C * (n * math.pi / d) ** 2 / mlay
        if e >= hi:
            break
        if e > lo:
            Ex.append(e)
        n += 1
    res["n_max"] = (len(rep["maxima"]), len(Ex))
    if len(Ex) == len(rep["maxima"]):
        res["max_dE"] = max([abs(m["E_eV"] - e) for m, e in zip(rep["maxima"], Ex)], default=0.0)
        res["max_T_minus_1"] = max([abs(m["T"] - 1.0) for m in rep["maxima"]], default=0.0)
    return res


def main():
    out = {}
    # ---- t1
    s = load("t1_single_well")
    rep = report("t1_single_well")
    mb, V0 = 0.0919, 0.32
    mw, Lw = 0.0665, 9.4

    def fe(E):
        k = math.sqrt(mw * E / C)
        kap = math.sqrt(mb * (V0 - E) / C)
        return (k / mw) * math.sin(k * Lw / 2) - (kap / mb) * math.cos(k * Lw / 2)

    def fo(E):
        k = math.sqrt(mw * E / C)
        kap = math.sqrt(mb * (V0 - E) / C)
        return -(k / mw) * math.cos(k * Lw / 2) - (kap / mb) * math.sin(k * Lw / 2)

    ex = sorted(roots(fe, 1e-12, V0 - 1e-12) + roots(fo, 1e-12, V0 - 1e-12))
    bs = [b["E_eV"] for b in rep["bound_states"]]
    r = {"n_bound": (len(bs), len(ex)),
         "bound_dE": max(abs(a - b) for a, b in zip(bs, ex)) if len(bs) == len(ex) else None}
    r.update(check_single_layer("t1", s, rep, mb, V0, mw, 0.0, Lw))
    out["t1_single_well"] = r
    # ---- t2
    rep = report("t2_sym_double_well")
    mb, V0, mw, Lw, b = 0.0919, 0.28, 0.0665, 6.5, 6.5

    def fdw(E, parity):
        k = math.sqrt(mw * E / C)
        kap = math.sqrt(mb * (V0 - E) / C)
        P = (kap / mb) * (math.tanh(kap * b) if parity == 0 else 1.0 / math.tanh(kap * b))
        A, Bc = 1.0, P * mw / k
        c, sn = math.cos(k * Lw), math.sin(k * Lw)
        return (k / mw) * (-A * sn + Bc * c) + (kap / mb) * (A * c + Bc * sn)

    ex = sorted(roots(lambda E: fdw(E, 0), 1e-12, V0 - 1e-12) + roots(lambda E: fdw(E, 1), 1e-12, V0 - 1e-12))
    bs = [x["E_eV"] for x in rep["bound_states"]]
    out["t2_sym_double_well"] = {
        "n_bound": (len(bs), len(ex)),
        "bound_dE": max(abs(a - c) for a, c in zip(bs, ex)) if len(bs) == len(ex) else None,
        "splittings": [bs[i + 1] - bs[i] for i in range(0, len(bs) - 1, 2)]}
    # ---- t3: low states against the Airy closed form
    s = load("t3_triangular_bias")
    rep = report("t3_triangular_bias")
    mL, VL = 0.5, 1.95
    m1, slope = 0.35, 1.2 / 24.0
    lam = (m1 / (C * slope * slope)) ** (1.0 / 3.0)
    beta = (m1 * slope / C) ** (1.0 / 3.0)

    def ftri(E):
        z0 = -lam * E
        ai, aip, _, _ = airy(z0)
        kap = math.sqrt(mL * (VL - E) / C)
        return (beta / m1) * aip - (kap / mL) * ai

    ex = roots(ftri, 1e-9, 1.0, n=200001)                  # states below 1.0 eV
    bs = [x["E_eV"] for x in rep["bound_states"]]
    nlow = len(ex)
    a_n = [-x for x in __import__("scipy.special", fromlist=["ai_zeros"]).ai_zeros(nlow)[0]]
    inf_wall = [(C * slope * slope / m1) ** (1.0 / 3.0) * a for a in a_n]
    out["t3_triangular_bias"] = {
        "n_bound_total": len(bs), "n_compared": nlow,
        "bound_dE_low": max(abs(a - c) for a, c in zip(bs[:nlow], ex)),
        "infinite_wall_shift_eV": [round(a - c, 6) for a, c in zip(ex[:4], inf_wall[:4])]}
    # ---- t7, t8
    for name, mlay, Vb, d in (("t7_rect_barrier", 0.0919, 0.35, 7.0), ("t8_thick_barrier", 0.5, 1.6, 7.0)):
        s = load(name)
        rep = report(name)
        r = check_single_layer(name, s, rep, 0.067, 0.0, mlay, Vb, d)
        r["T_query_min"] = min(q["T"] for q in rep["transmission"])
        out[name] = r
    # ---- infinite-well limit (outside the domain on purpose: barrier height up to 1e6 eV)
    lim = []
    for Vb in (1e2, 1e4, 1e6):
        st = {"structure_id": "lim", "left_lead": {"mass": 0.5, "v_eV": Vb},
              "right_lead": {"mass": 0.5, "v_eV": Vb},
              "layers": [{"thickness_nm": 1.0, "mass": 0.5, "vl_eV": Vb, "vr_eV": Vb},
                         {"thickness_nm": 10.0, "mass": 0.067, "vl_eV": 0.0, "vr_eV": 0.0}],
              "transmission_energies_eV": [Vb + 1, Vb + 2], "window_eV": [Vb + 1, Vb + 1.01]}
        M = R.Model(st)
        E = R.bound_states(M)[:3]
        Einf = [C * (n * math.pi / 10.0) ** 2 / 0.067 for n in (1, 2, 3)]
        # penetration depth m_b / (m_w kappa) at each wall: E_n / Einf - 1 ~ -4 m_b / (m_w kappa L)
        kap = math.sqrt(0.5 * Vb / C)
        lim.append({"Vb": Vb, "rel_dev": [e / ei - 1 for e, ei in zip(E, Einf)],
                    "first_order_prediction": -4 * 0.5 / (0.067 * kap * 10.0)})
    out["infinite_well_limit"] = lim
    # ---- triangular well with an infinite wall: E_n -> (C F^2 / m)^(1/3) |a_n| as the wall grows
    from scipy.special import ai_zeros
    an = -ai_zeros(3)[0]
    tri = []
    for Vw in (1e2, 1e4, 1e6):
        st = {"structure_id": "tri", "left_lead": {"mass": 0.5, "v_eV": Vw},
              "right_lead": {"mass": 0.35, "v_eV": 1.8},
              "layers": [{"thickness_nm": 24.0, "mass": 0.35, "vl_eV": 0.0, "vr_eV": 1.2},
                         {"thickness_nm": 12.0, "mass": 0.35, "vl_eV": 1.2, "vr_eV": 1.8}],
              "transmission_energies_eV": [Vw + 1, Vw + 2], "window_eV": [Vw + 1, Vw + 1.01]}
        E = R.bound_states(R.Model(st))[:3]
        Einf = [(C * 0.05 ** 2 / 0.35) ** (1.0 / 3.0) * a for a in an]
        kap = math.sqrt(0.5 * Vw / C)
        # wall penetration m_wall/(m kappa) shifts the wall by delta: E_n - Einf ~ -F delta (2/3 rule
        # for the linear well: dE/dx_wall = -(2/3) E_n / x_turn ... first order: -(2/3) E_n delta / l_n)
        tri.append({"Vw": Vw, "rel_dev": [e / ei - 1 for e, ei in zip(E, Einf)],
                    "penetration_nm": 0.5 / (0.35 * kap)})
    out["triangular_infinite_wall_limit"] = tri
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
