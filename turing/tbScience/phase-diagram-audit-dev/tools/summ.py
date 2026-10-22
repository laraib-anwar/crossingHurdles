"""Compact summary of a phase diagram report."""
import json, sys
for f in sys.argv[1:]:
    r = json.load(open(f))
    print("==", r["system_id"])
    for iso in r["isotherms"]:
        regs = " ".join(f"{g['phase']}[{g['x_lo']:.5f},{g['x_hi']:.5f}]" for g in iso["single_phase_regions"])
        ties = " ".join(f"{t['left_phase']}({t['x_left']:.5f})-{t['right_phase']}({t['x_right']:.5f})" for t in iso["tie_lines"])
        print(f"  T={iso['temperature_K']}: {regs} | {ties}")
    for e in r["invariants"]:
        print(f"  INV {e['temperature_K']:.6f} {e['class']}/{e['name']}: " + " ".join(f"{p['phase']}@{p['x']:.6f}" for p in e["phases"]))
    for e in r["congruent_points"]:
        print(f"  CON {e['temperature_K']:.6f} x={e['x']:.6f} above={e['phase_above']} below={e['phase_below']} lens={e['two_phase_side']}")
    for e in r["critical_points"]:
        print(f"  CRI {e['temperature_K']:.6f} x={e['x']:.6f} {e['phase']} gap={e['gap_side']}")
