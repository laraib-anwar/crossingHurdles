"""Generate the graded systems and screen them with the oracle for every guarantee of
PHASE_SPEC.md section 2. One random stream per slot (deterministic).

usage: gen_systems.py <phasediagram.py> <out_dir> [indices...]
"""
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("pd", sys.argv[1])
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)
OUT = Path(sys.argv[2])
(OUT / "systems").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
R = pd.R
import os
DEBUG = bool(os.environ.get("GEN_DEBUG"))
COMPOUNDS = {"A4B": 0.2, "A3B": 0.25, "A2B": 1 / 3, "A3B2": 0.4, "AB": 0.5, "A2B3": 0.6, "AB2": 2 / 3, "AB3": 0.75, "AB4": 0.8}


def r6(v):
    return float(f"{v:.6g}")


def sol(name, A, B, rk):
    rk = (list(rk) + [(0.0, 0.0)] * 3)[:3]
    return {"name": name, "end_members": {"A": {"h": r6(A[0]), "s": r6(A[1])}, "B": {"h": r6(B[0]), "s": r6(B[1])}},
            "redlich_kister": [{"a": r6(a), "b": r6(b)} for a, b in rk]}


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


# ------------------------------------------------------------------ random systems
def liquid_phase(rng, TmA, TmB, a0, a1=None, a2=None, b0=None):
    dSA, dSB = U(rng, 8, 12), U(rng, 8, 12)
    a1 = U(rng, -5000, 5000) if a1 is None else a1
    a2 = U(rng, -1500, 1500) if a2 is None else a2
    b0 = U(rng, -5, 5) if b0 is None else b0
    return sol("liquid", (dSA * TmA, dSA), (dSB * TmB, dSB), [(a0, b0), (a1, U(rng, -1.5, 1.5)), (a2, U(rng, -1, 1))])


def terminal(rng, name, side, a0=None, a1=None):
    a0 = U(rng, 6000, 30000) if a0 is None else a0
    a1 = U(rng, -6000, 6000) if a1 is None else a1
    other = (U(rng, 2000, 10000), U(rng, -2, 2))
    rk = [(a0, U(rng, -4, 4)), (a1, U(rng, -1.5, 1.5)), (U(rng, -1500, 1500), 0.0)]
    return sol(name, (0.0, 0.0), other, rk) if side == "A" else sol(name, other, (0.0, 0.0), rk)


def compound(rng, name, hf, s=None):
    return {"name": name, "x_b": COMPOUNDS[name], "h": r6(hf), "s": r6(U(rng, -6, 6) if s is None else s)}


def build(rng, style):
    """Random system (without window and isotherms) for a style, plus hints for the window."""
    TmA, TmB = U(rng, 700, 1900), U(rng, 600, 1800)
    hints = dict(Tm=[TmA, TmB])
    if style in ("eutectic", "peritectic", "close"):
        liq = liquid_phase(rng, TmA, TmB, U(rng, -15000, 10000))
        if style == "peritectic":
            TmA = U(rng, 1200, 2000)
            TmB = TmA - U(rng, 400, 900)
            liq = liquid_phase(rng, TmA, TmB, U(rng, -25000, -5000), a1=U(rng, -12000, 12000))
            hints["Tm"] = [TmA, TmB]
        sols = [liq, terminal(rng, "alpha", "A"), terminal(rng, "beta", "B")]
        comps = []
    elif style in ("lens_min", "lens_max"):
        if style == "lens_min":
            liq = liquid_phase(rng, TmA, TmB, U(rng, -14000, -3000))
            solid = sol("alpha", (0.0, 0.0), (0.0, 0.0), [(U(rng, 2000, 10000), U(rng, -3, 3)), (U(rng, -3000, 3000), 0.0), (0.0, 0.0)])
        else:
            liq = liquid_phase(rng, TmA, TmB, U(rng, 3000, 11000))
            solid = sol("alpha", (0.0, 0.0), (0.0, 0.0), [(U(rng, -14000, -3000), U(rng, -3, 3)), (U(rng, -3000, 3000), 0.0), (0.0, 0.0)])
        sols, comps = [liq, solid], []
    elif style == "solid_gap":
        a0 = U(rng, 19000, 30000)
        Tc = a0 / (2 * R)
        TmA, TmB = Tc + U(rng, 450, 900), Tc + U(rng, 450, 900)
        hints["Tm"] = [TmA, TmB]
        liq = liquid_phase(rng, TmA, TmB, U(rng, 0, 9000))
        solid = sol("alpha", (0.0, 0.0), (0.0, 0.0), [(a0, U(rng, -2, 2)), (U(rng, -4000, 4000), 0.0), (U(rng, -1000, 1000), 0.0)])
        sols, comps = [liq, solid], []
    elif style == "lower":
        a, b = U(rng, -26000, -9000), U(rng, 19.5, 27)
        Tc = a / (2 * R - b)
        TmA, TmB = Tc + U(rng, 200, 700), Tc + U(rng, 200, 700)
        hints["Tm"] = [TmA, TmB]
        liq = liquid_phase(rng, TmA, TmB, U(rng, -4000, 4000))
        solid = sol("alpha", (0.0, 0.0), (0.0, 0.0), [(a, b), (U(rng, -3000, 3000), 0.0), (0.0, 0.0)])
        sols, comps = [liq, solid], []
    elif style in ("liquid_gap", "syntectic"):
        a0 = U(rng, 22000, 36000)
        TmA, TmB = U(rng, 600, 1100), U(rng, 600, 1100)
        hints["Tm"] = [TmA, TmB]
        liq = liquid_phase(rng, TmA, TmB, a0, a1=U(rng, -4000, 4000), b0=U(rng, -3, 0))
        if style == "liquid_gap":
            sols = [liq, terminal(rng, "alpha", "A", a0=U(rng, 10000, 22000)), terminal(rng, "beta", "B", a0=U(rng, 10000, 22000))]
        else:
            solid = sol("alpha", (0.0, 0.0), (0.0, 0.0), [(U(rng, 2000, 9000), 0.0), (U(rng, -3000, 3000), 0.0), (0.0, 0.0)])
            sols = [liq, solid]
        comps = []
    elif style in ("compounds", "compound_partial", "compound_never"):
        liq = liquid_phase(rng, TmA, TmB, U(rng, -32000, -8000), a1=U(rng, -8000, 8000))
        sols = [liq, terminal(rng, "alpha", "A", a0=U(rng, 12000, 30000)), terminal(rng, "beta", "B", a0=U(rng, 12000, 30000))]
        names = list(rng.choice(list(COMPOUNDS), size=int(rng.randint(1, 3 if style == "compound_never" else 4)), replace=False))
        comps = []
        for n in names:
            x = COMPOUNDS[n]
            hf = U(rng, -32000, -6000) * 4 * x * (1 - x) * U(rng, 0.6, 1.0)
            comps.append(compound(rng, n, hf))
        if style == "compound_never":
            n = next(k for k in COMPOUNDS if k not in names)
            comps.append(compound(rng, n, U(rng, 1500, 8000)))
    elif style == "intermediate":
        liq = liquid_phase(rng, TmA, TmB, U(rng, -24000, -4000))
        gamma = sol("gamma", (U(rng, 3000, 9000), U(rng, -2, 2)), (U(rng, 3000, 9000), U(rng, -2, 2)),
                    [(U(rng, -48000, -22000), U(rng, -3, 3)), (U(rng, -8000, 8000), 0.0), (U(rng, -3000, 3000), 0.0)])
        sols = [liq, terminal(rng, "alpha", "A"), gamma, terminal(rng, "beta", "B")]
        comps = []
    elif style == "allotropy":
        liq = liquid_phase(rng, TmA, TmB, U(rng, -12000, 8000))
        Ttr, dS = U(rng, 500, min(1500, TmA - 150)), U(rng, 1, 5)
        gamma = sol("gamma", (dS * Ttr, dS), (U(rng, 3000, 10000), U(rng, -2, 2)),
                    [(U(rng, 5000, 24000), U(rng, -3, 3)), (U(rng, -5000, 5000), 0.0), (0.0, 0.0)])
        sols = [liq, terminal(rng, "alpha", "A"), gamma, terminal(rng, "beta", "B")]
        comps = []
        hints["Ttr"] = Ttr
    elif style == "mixed":
        liq = liquid_phase(rng, TmA, TmB, U(rng, -28000, -4000), a1=U(rng, -8000, 8000))
        sols = [liq, terminal(rng, "alpha", "A"), terminal(rng, "beta", "B")]
        comps = []
        if rng.rand() < 0.7:
            n = str(rng.choice(list(COMPOUNDS)))
            x = COMPOUNDS[n]
            comps.append(compound(rng, n, U(rng, -30000, -6000) * 4 * x * (1 - x)))
        if rng.rand() < 0.5:
            sols.insert(2, sol("gamma", (U(rng, 3000, 9000), U(rng, -2, 2)), (U(rng, 3000, 9000), U(rng, -2, 2)),
                               [(U(rng, -45000, -20000), U(rng, -3, 3)), (U(rng, -8000, 8000), 0.0), (0.0, 0.0)]))
    else:
        raise ValueError(style)
    return dict(solution_phases=sols, compounds=comps), hints


# ------------------------------------------------------------------ screening
def in_domain(d):
    for s in d["solution_phases"]:
        for e in ("A", "B"):
            if abs(s["end_members"][e]["h"]) > 60000 or abs(s["end_members"][e]["s"]) > 60:
                return False
        for c in s["redlich_kister"]:
            if abs(c["a"]) > 60000 or abs(c["b"]) > 30:
                return False
    if len(d["compounds"]) > 3 or not 2 <= len(d["solution_phases"]) <= 4:
        return False
    for c in d["compounds"]:
        if abs(c["h"]) > 60000 or abs(c["s"]) > 60 or not 0.1 <= c["x_b"] <= 0.9:
            return False
    xs = sorted(c["x_b"] for c in d["compounds"])
    if any(b - a < 0.02 for a, b in zip(xs, xs[1:])):
        return False
    names = [s["name"] for s in d["solution_phases"]] + [c["name"] for c in d["compounds"]]
    if len(set(names)) != len(names):
        return False
    ems = [(s["end_members"]["A"]["h"], s["end_members"]["A"]["s"]) for s in d["solution_phases"]]
    emb = [(s["end_members"]["B"]["h"], s["end_members"]["B"]["s"]) for s in d["solution_phases"]]
    return len(set(ems)) == len(ems) and len(set(emb)) == len(emb)


def run(d, window, isotherms):
    m = dict(system_id="probe", **d, window_K=[r6(window[0]), r6(window[1])], isotherms_K=[float(t) for t in isotherms])
    S = pd.System(m)
    t0 = time.time()
    anchors, events = S.solve()
    secs = time.time() - t0
    return S, anchors, events, secs, m


def event_temps(events):
    return sorted(e["T"] for e in events)


def guarantee_1(events, window, isotherms):
    Ts = event_temps(events)
    if any(b - a < 0.5 for a, b in zip(Ts, Ts[1:])):
        return False
    if any(t - window[0] < 0.5 or window[1] - t < 0.5 for t in Ts):
        return False
    return all(abs(t - iso) >= 0.5 for t in Ts for iso in isotherms)


def guarantee_3(events):
    for e in events:
        if e["kind"] == "invariant":
            xs = [s.x for s in e["states"]]
            if any(not 1e-5 <= x <= 1 - 1e-5 for x in xs) or any(b - a < 1e-4 for a, b in zip(xs, xs[1:])):
                return False
        elif e["kind"] in ("congruent", "critical"):
            if not 1e-5 <= e["x"] <= 1 - 1e-5:
                return False
    return True


def isotherm_ok(S, T):
    try:
        ties, sole = S.certified(T)
    except pd.NewtonFailure:
        return False
    for t in ties:
        if t.r.x - t.l.x < 1e-4:
            return False
        for st in (t.l, t.r):
            if st.ph.kind == "S" and not 1e-5 <= st.x <= 1 - 1e-5:
                return False
    for ph, lo, hi, _, _ in S.regions(ties, T, sole):
        if hi - lo < 1e-4:
            return False
    return S.margin(ties, sole, T) >= 0.05


def tie_count(S, T):
    ties, sole = S.certified(T)
    return len(ties)


def choose_isotherms(rng, S, events, window, n, want):
    Ts = [window[0]] + event_temps(events) + [window[1]]
    cands = []
    for a, b in zip(Ts, Ts[1:]):
        if b - a < 2.0:
            continue
        for _ in range(3):
            cands.append(round(U(rng, a + 0.8, b - 0.8), 2))
    rng.shuffle(cands)
    if want.get("min_tie"):
        # put the richest isothermal sections first
        cands.sort(key=lambda T: -tie_count(S, T))
    out = []
    for T in cands:
        if any(abs(T - u) < 0.5 for u in Ts) or any(abs(T - u) < 5 for u in out):
            continue
        if isotherm_ok(S, T):
            out.append(T)
        if len(out) >= n:
            break
    return sorted(out)


def summarize_events(events):
    return [(e["kind"], round(e["T"], 3), e.get("name", e.get("side", ""))) for e in events]


def summarize(report, events):
    inv = report["invariants"]
    return dict(names=[e["name"] for e in inv], classes=[e["class"] for e in inv],
                con=[(e["two_phase_side"], e["phase_above"], e["phase_below"]) for e in report["congruent_points"]],
                cri=[(e["gap_side"], e["phase"]) for e in report["critical_points"]],
                n_pure=sum(1 for e in events if e["kind"] == "pure"),
                n_events=len(events), inv_T=[e["temperature_K"] for e in inv])


def predicate(want, d, report, events):
    s = summarize(report, events)
    names, classes = s["names"], s["classes"]
    used = {p["phase"] for e in report["invariants"] for p in e["phases"]}
    used |= {e["phase_above"] for e in report["congruent_points"]} | {e["phase_below"] for e in report["congruent_points"]}
    for iso in report["isotherms"]:
        used |= {t["left_phase"] for t in iso["tie_lines"]} | {t["right_phase"] for t in iso["tie_lines"]}
    comp_names = {c["name"] for c in d["compounds"]}
    if "names" in want and not set(want["names"]) <= set(names): return False
    if "min_inv" in want and len(names) < want["min_inv"]: return False
    if want.get("peritectic_class") and "peritectic" not in classes: return False
    if want.get("eutectic_class") and "eutectic" not in classes: return False
    if "con_side" in want and not any(c[0] == want["con_side"] for c in s["con"]): return False
    if "cri_side" in want and not any(c[0] == want["cri_side"] for c in s["cri"]): return False
    if want.get("compound_used") and not (comp_names & used): return False
    if want.get("compound_absent") and not (comp_names - used): return False
    if want.get("compound_congruent") and not any(e["phase_below"] in comp_names or e["phase_above"] in comp_names for e in report["congruent_points"]): return False
    if want.get("compound_both"):
        ok = False
        for c in comp_names:
            cls = {e["class"] for e in report["invariants"] if any(p["phase"] == c for p in e["phases"])}
            if cls == {"eutectic", "peritectic"}:
                ok = True
        if not ok: return False
    if want.get("no_events") and s["n_events"] > 0: return False
    if want.get("pure") and s["n_pure"] == 0: return False
    if "min_events" in want and s["n_events"] - s["n_pure"] < want["min_events"]: return False
    if want.get("close"):
        Ts = sorted(s["inv_T"])
        if not any(b - a < 15.0 for a, b in zip(Ts, Ts[1:])): return False
    if want.get("gamma_congruent") and not any(e["phase_below"] == "gamma" for e in report["congruent_points"]): return False
    if want.get("gamma_used") and "gamma" not in used: return False
    if "min_tie" in want and max(len(iso["tie_lines"]) for iso in report["isotherms"]) < want["min_tie"]: return False
    if want.get("some_ties") and not any(iso["tie_lines"] for iso in report["isotherms"]): return False
    return True


PLAN = [
    ("model_01", True, "eutectic", dict(names=["eutectic"], some_ties=True), "simple eutectic between two terminal solid solutions (base case)"),
    ("model_02", True, "lens_min", dict(con_side="above"), "lens with a congruent minimum"),
    ("model_03", True, "compounds", dict(compound_used=True, peritectic_class=True, eutectic_class=True), "compounds: peritectic decomposition and eutectics"),
    ("model_04", True, "solid_gap", dict(cri_side="below", some_ties=True), "solid miscibility gap with an upper consolute point"),
    ("model_05", True, "allotropy", dict(pure=True, min_inv=1), "allotropic transition of pure A inside the window"),
    ("model_06", True, "liquid_gap", dict(names=["monotectic"]), "liquid miscibility gap: monotectic"),
    ("held_01", False, "eutectic", dict(names=["eutectic"], some_ties=True), "simple eutectic"),
    ("held_02", False, "peritectic", dict(names=["peritectic"]), "peritectic between terminal solid solutions"),
    ("held_03", False, "lens_max", dict(con_side="below"), "lens with a congruent maximum"),
    ("held_04", False, "lens_min", dict(con_side="above"), "lens with a congruent minimum"),
    ("held_05", False, "compound_never", dict(compound_used=True, compound_absent=True), "a compound that is never stable"),
    ("held_06", False, "compound_partial", dict(compound_both=True), "compound stable only inside part of the window"),
    ("held_07", False, "compounds", dict(compound_congruent=True, min_inv=2), "congruently melting compound with eutectics"),
    ("held_08", False, "solid_gap", dict(cri_side="below", min_tie=2), "solid miscibility gap, two tie-lines at an isotherm"),
    ("held_09", False, "lower", dict(cri_side="above"), "lower consolute point"),
    ("held_10", False, "syntectic", dict(names=["syntectic"]), "syntectic"),
    ("held_11", False, "eutectic", dict(no_events=True, some_ties=True), "window with no event"),
    ("held_12", False, "compounds", dict(close=True, min_inv=2), "two invariants close in temperature"),
    ("held_13", False, "allotropy", dict(pure=True, min_inv=2), "allotropic transition with two invariants"),
    ("held_14", False, "intermediate", dict(gamma_congruent=True, min_inv=2), "intermediate solid solution melting congruently"),
    ("held_15", False, "intermediate", dict(gamma_used=True, peritectic_class=True), "intermediate solid solution forming peritectically"),
    ("held_16", False, "liquid_gap", dict(names=["monotectic"], cri_side="below"), "monotectic and liquid consolute point"),
    ("held_17", False, "compounds", dict(compound_used=True, min_inv=3), "several compounds, three or more invariants"),
    ("held_18", False, "mixed", dict(min_events=4), "mixed system with four or more events"),
    ("held_19", False, "mixed", dict(min_tie=3), "mixed system with three or more tie-lines at one isotherm"),
    ("held_20", False, "lens_max", dict(con_side="below", min_tie=2), "congruent maximum, two tie-lines"),
    ("held_21", False, "eutectic", dict(names=["eutectic"], min_tie=2), "eutectic, two tie-lines at an isotherm"),
    ("held_22", False, "mixed", dict(min_events=2, compound_used=True), "mixed system with a compound"),
]


def choose_window(rng, hints, events_wide, wide, style, want):
    """Window around the interesting events of the wide run."""
    Ts = event_temps(events_wide)
    rep_T = [e["T"] for e in events_wide if e["kind"] != "pure"]
    lo_w, hi_w = wide
    if want.get("no_events"):
        gaps = [(a, b) for a, b in zip([lo_w] + Ts, Ts + [hi_w]) if b - a > 110]
        if not gaps:
            return None
        a, b = gaps[int(rng.randint(len(gaps)))]
        lo = U(rng, a + 1, min(b - 100, a + 1 + 200))
        hi = min(b - 1, lo + U(rng, 100, 600))
        return [lo, hi]
    if not rep_T:
        return None
    lo = min(rep_T) - U(rng, 30, 300)
    hi = max(rep_T) + U(rng, 30, 300)
    if style in ("eutectic", "peritectic", "compounds", "compound_partial", "compound_never", "mixed", "allotropy", "intermediate", "close"):
        hi = max(hi, max(hints["Tm"]) + U(rng, 5, 150))
    lo, hi = max(lo, 250.0, lo_w + 1), min(hi, 2500.0, hi_w - 1)
    if hi - lo > 1200:
        lo = hi - 1200 + U(rng, 0, 50)
    if hi - lo < 100:
        return None
    # keep every event at least 1 K from the ends
    for _ in range(20):
        bad = [t for t in Ts if abs(t - lo) < 1.0 or abs(t - hi) < 1.0]
        if not bad:
            break
        lo -= 2.0
        hi += 2.0
    if hi - lo > 1200 or lo < 250 or hi > 2500:
        return None
    return [round(lo, 1), round(hi, 1)]


def build_slot(index):
    sid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261022 + 104729 * index)
    t0 = time.time()
    for attempt in range(400):
        if time.time() - t0 > (int(os.environ.get("GEN_BUDGET", "2400"))):
            break
        if DEBUG:
            print(f"attempt {attempt}", flush=True)
        try:
            d, hints = build(rng, style)
            if not in_domain(d):
                continue
            wide = [300.0, min(2500.0, max(hints["Tm"]) + 250.0)]
            if style == "lower":
                wide = [300.0, min(2500.0, max(hints["Tm"]) + 100.0)]
            S, anchors, events, secs, _ = run(d, wide, [])
            window = choose_window(rng, hints, events, wide, style, want)
            if window is None:
                if DEBUG:
                    print("  reject window", json.dumps(summarize_events(events))[:300], flush=True)
                continue
            S, anchors, events, secs, _ = run(d, window, [])
            if not guarantee_1(events, window, []) or not guarantee_3(events):
                if DEBUG:
                    print("  reject guarantee", json.dumps(summarize_events(events))[:300], flush=True)
                continue
            n_iso = int(rng.randint(2, 7))
            isotherms = choose_isotherms(rng, S, events, window, n_iso, want)
            if len(isotherms) < 2:
                if DEBUG:
                    print("  reject isotherms", isotherms, flush=True)
                continue
            m = dict(system_id=sid, **d, window_K=[r6(window[0]), r6(window[1])], isotherms_K=isotherms)
            S = pd.System(m)
            t1 = time.time()
            report = S.report()
            secs = time.time() - t1
            S2 = pd.System(m)
            _, events = S2.solve()
            if secs > 45 or not guarantee_1(events, window, isotherms) or not guarantee_3(events):
                continue
            if not predicate(want, m, report, events):
                if DEBUG:
                    print("  reject predicate", json.dumps(summarize(report, events), default=str)[:300], flush=True)
                continue
        except (pd.NewtonFailure, ValueError, ZeroDivisionError, FloatingPointError) as error:
            if DEBUG:
                print("  reject error", repr(error)[:200], flush=True)
            continue
        json.dump(m, open(OUT / "systems" / f"{sid}.json", "w"), indent=1)
        log = dict(system_id=sid, shipped=shipped, style=style, label=label, attempts=attempt + 1, secs=round(secs, 2),
                   window=window, isotherms=isotherms, summary=summarize(report, events))
        json.dump(log, open(OUT / "log" / f"{sid}.json", "w"), indent=1, default=str)
        print(json.dumps(log, default=str), flush=True)
        return
    print(json.dumps(dict(system_id=sid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build_slot(i)
