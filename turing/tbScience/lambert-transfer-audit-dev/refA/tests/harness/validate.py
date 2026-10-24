"""Validate reference.py on system files.  Usage: validate.py REFERENCE_DIR system.json [...]"""
import json
import math
import sys
import time
import importlib.util
from decimal import Decimal as D

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import hp

spec = importlib.util.spec_from_file_location("reference", sys.argv[1] + "/reference.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)

SHOOT = "--noshoot" not in sys.argv
files = [f for f in sys.argv[2:] if not f.startswith("--")]


def rel(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return float(np.linalg.norm(a - b) / np.linalg.norm(b))


def naive_tof(r1, r2, A, z, mu):
    C, S = ref.stumpff(z)
    y = r1 + r2 + A * (z * S - 1.0) / math.sqrt(C)
    if y <= 0.0:
        return None
    chi = math.sqrt(y / C)
    return (chi ** 3 * S + A * math.sqrt(y)) / math.sqrt(mu)


def dec_tof(lam, x):
    """Decimal TOF at z = x^2 (x Decimal) for the exact r1, r2 (as doubles)."""
    r1v = [D(float(t)) for t in lam.r1v]; r2v = [D(float(t)) for t in lam.r2v]
    r1 = hp.dsqrt(hp.dot(r1v, r1v)); r2 = hp.dsqrt(hp.dot(r2v, r2v))
    cr = [r1v[1] * r2v[2] - r1v[2] * r2v[1], r1v[2] * r2v[0] - r1v[0] * r2v[2], r1v[0] * r2v[1] - r1v[1] * r2v[0]]
    sn = hp.dsqrt(hp.dot(cr, cr)) / (r1 * r2)
    if cr[2] < 0:
        sn = -sn
    cs = hp.dot(r1v, r2v) / (r1 * r2)
    A = sn * hp.dsqrt(r1 * r2 / (1 - cs))
    z = x * x
    C, S = hp.stumpff(z)
    y = r1 + r2 + A * (z * S - 1) / hp.dsqrt(C)
    chi = hp.dsqrt(y / C)
    return (chi ** 3 * S + A * hp.dsqrt(y)) / hp.dsqrt(D(lam.mu))


worst = {}


def upd(k, v):
    worst[k] = max(worst.get(k, 0.0), v)


for fn in files:
    sysd = json.load(open(fn))
    mu = float(sysd["mu_km3_s2"])
    objs = {o["name"]: o for o in sysd["objects"]}
    t0 = time.time()
    diags = []
    rep = ref.compute_report(sysd, diags)
    ref.check_finite(rep)
    elapsed = time.time() - t0
    upd("runtime_s", elapsed)
    msgs = []
    # ---- ephemeris
    for q, e in zip(sysd["ephemeris_queries"], rep["ephemeris"]):
        rx, vx = hp.ephemeris(objs[q["object"]], mu, q["t_days"])
        er = rel(e["r_km"], [float(t) for t in rx]); ev = rel(e["v_km_s"], [float(t) for t in vx])
        upd("eph_r", er); upd("eph_v", ev)
        o = objs[q["object"]]
        r = np.array(e["r_km"]); v = np.array(e["v_km_s"])
        en = v @ v / 2 - mu / np.linalg.norm(r)
        upd("eph_energy", abs(en - (-mu / (2 * o["a_km"]))) / abs(mu / (2 * o["a_km"])))
        h = np.linalg.norm(np.cross(r, v))
        hp_ = math.sqrt(mu * abs(o["a_km"]) * abs(1 - o["e"] ** 2))
        upd("eph_h", abs(h - hp_) / hp_)
    # ---- transfers
    for qi, (q, tr, dg) in enumerate(zip(sysd["transfer_queries"], rep["transfers"], diags)):
        lam = dg["lam"]
        T = dg["T"]
        # exact endpoint states
        r1x, vAx = hp.ephemeris(objs[q["from"]], mu, q["t1_days"])
        r2x, vBx = hp.ephemeris(objs[q["to"]], mu, q["t2_days"])
        upd("endpoint_r", max(rel(dg["r1"], [float(t) for t in r1x]), rel(dg["r2"], [float(t) for t in r2x])))
        # theta in Decimal
        nN = len(tr["solutions"])
        # dense naive scan per N
        r1 = lam.r1; r2 = lam.r2; A = lam.A
        n_max = q["n_max"]
        counts = {0: 0}
        for N in range(1, n_max + 1):
            zl = (2 * math.pi * N) ** 2; zh = (2 * math.pi * (N + 1)) ** 2
            xs = np.linspace(2 * math.pi * N, 2 * math.pi * (N + 1), 40001)[1:-1]
            vals = np.array([naive_tof(r1, r2, A, x * x, mu) for x in xs])
            i = int(np.argmin(vals))
            # derivative sign changes (unimodality)
            dsg = np.sign(np.diff(vals))
            changes = int(np.sum(dsg[1:] != dsg[:-1]))
            if changes != 1:
                msgs.append("q%d N=%d TOF scan has %d slope changes" % (qi, N, changes))
            # golden refine in x
            lo, hi = xs[max(i - 1, 0)], xs[min(i + 1, len(xs) - 1)]
            g = (math.sqrt(5) - 1) / 2
            for _ in range(200):
                c1 = hi - g * (hi - lo); c2 = lo + g * (hi - lo)
                if naive_tof(r1, r2, A, c1 * c1, mu) < naive_tof(r1, r2, A, c2 * c2, mu):
                    hi = c2
                else:
                    lo = c1
            tmin_scan = naive_tof(r1, r2, A, (0.5 * (lo + hi)) ** 2, mu) / 86400
            upd("tmin_vs_scan", abs(tmin_scan - tr["t_min_days"][N - 1]) / tr["t_min_days"][N - 1])
            # Decimal TOF at our minimiser
            N_, side, tm, Fm = dg["minima"][N - 1]
            x = 2 * hp.PI * N + 2 * D(tm) if side == 0 else 2 * hp.PI * (N + 1) - 2 * D(tm)
            tdec = float(dec_tof(lam, x)) / 86400
            upd("tmin_vs_decimal", abs(tdec - tr["t_min_days"][N - 1]) / tdec)
            sgn = np.sign(vals - T)
            counts[N] = int(np.sum(sgn[1:] != sgn[:-1]))
        # N = 0 count (z from hyperbolic side to 4 pi^2)
        zs = np.concatenate([-np.logspace(4, -6, 3000), np.linspace(1e-9, (2 * math.pi) ** 2 * (1 - 1e-9), 8000)])
        vals0 = [naive_tof(r1, r2, A, z, mu) for z in zs]
        vals0 = np.array([v if v is not None else 0.0 for v in vals0])
        s0 = np.sign(vals0 - T)
        counts[0] = int(np.sum(s0[1:] != s0[:-1]))
        expect = sum(counts.values())
        if expect != nN:
            msgs.append("q%d count %d vs scan %s" % (qi, nN, counts))
        # per solution
        for si, (s, sd) in enumerate(zip(tr["solutions"], dg["solutions"])):
            v1 = np.array(s["v1_km_s"]); v2 = np.array(s["v2_km_s"])
            rT, vT, _ = ref.kepler_universal(dg["r1"], v1, T, mu)
            upd("reprop_r2", rel(rT, dg["r2"])); upd("reprop_v2", rel(vT, v2))
            fv1, fv2 = lam.velocities_fg(sd["y"])
            upd("fg_vs_rt_v1", rel(fv1, v1)); upd("fg_vs_rt_v2", rel(fv2, v2))
            upd("a_vis_vs_lambert", abs(sd["a_vis_viva"] - sd["a_lambert"]) / abs(sd["a_lambert"]))
            # decimal re-propagation of the double v1 (separates conditioning from double propagation error)
            if SHOOT:
                rx_, vx_ = hp.kepler([D(float(t)) for t in dg["r1"]], [D(float(t)) for t in v1], D(T), D(mu))
                upd("reprop_r2_decimal", rel([float(t) for t in rx_], dg["r2"]))
            # prograde
            hz = np.cross(dg["r1"], v1)[2]
            if hz <= 0:
                msgs.append("q%d sol%d not prograde" % (qi, si))
            if SHOOT:
                vx1, vx2, res = hp.lambert_shoot([float(t) for t in r1x], v1, [float(t) for t in r2x], D(T), D(mu)) \
                    if False else hp.lambert_shoot(r1x, v1, r2x, D(T), D(mu))
                ve1 = [float(t) for t in vx1]; ve2 = [float(t) for t in vx2]
                upd("v1_vs_exact", rel(v1, ve1)); upd("v2_vs_exact", rel(v2, ve2))
                # a, e, dv in Decimal from the exact solution
                rr = hp.dsqrt(hp.dot(r1x, r1x)); vv2 = hp.dot(vx1, vx1); mud = D(mu)
                aex = 1 / (2 / rr - vv2 / mud)
                rdv = hp.dot(r1x, vx1)
                ev = [((vv2 - mud / rr) * a - rdv * b) / mud for a, b in zip(r1x, vx1)]
                eex = hp.dsqrt(hp.dot(ev, ev))
                dvex = hp.dsqrt(sum((a - b) ** 2 for a, b in zip(vx1, vAx))) + hp.dsqrt(sum((a - b) ** 2 for a, b in zip(vBx, vx2)))
                upd("a_vs_exact", abs(s["a_km"] - float(aex)) / abs(float(aex)))
                upd("a_visviva_vs_exact", abs(sd["a_vis_viva"] - float(aex)) / abs(float(aex)))
                upd("e_vs_exact", abs(s["e"] - float(eex)) / float(eex))
                upd("dv_vs_exact", abs(s["dv_km_s"] - float(dvex)) / float(dvex))
                if s["N"] >= 1:
                    # verify N by true anomaly advance: compare exact z? use alpha & chi via period count
                    pass
        # labels by vis-viva a agree
        for N in range(1, n_max + 1):
            ii = [k for k, s in enumerate(tr["solutions"]) if s["N"] == N]
            if ii:
                av = [dg["solutions"][k]["a_vis_viva"] for k in ii]
                assert av[0] < av[1], "vis-viva order disagrees"
        # best
        dvs = [s["dv_km_s"] for s in tr["solutions"]]
        assert tr["best"] == int(np.argmin(dvs))
        # labels
        for N in range(1, n_max + 1):
            ss = [s for s in tr["solutions"] if s["N"] == N]
            if ss:
                assert [s["branch"] for s in ss] == ["low", "high"] and ss[0]["a_km"] < ss[1]["a_km"]
    print("%-14s %5.2fs  %s" % (sysd["system_id"], elapsed, "; ".join(msgs) if msgs else "ok"), flush=True)

for k, v in worst.items():
    print("worst %-20s %.3e" % (k, v))
