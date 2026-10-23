"""Internal checks of a report: reciprocity of transfer impedances, sum of coefficients vs R_in(soma)."""
import json, sys
for f in sys.argv[1:]:
    r = json.load(open(f)); print("==", r["neuron_id"], "modes", len(r["modes"]), "tau0 %.4f" % r["modes"][0]["tau_ms"] if r["modes"] else "")
    for i in r["input_resistance"]: print("  Rin", i["site"], "%.6f" % i["R_MOhm"])
    for a in r["attenuation"]: print("  A", a["source"], "->", a["target"], "%.9f" % a["factor"])
    for z in r["impedance"]: print("  Z", z["source"], "->", z["target"], z["frequency_Hz"], "%.9f" % z["magnitude_MOhm"], "%.7f" % z["phase_deg"])
    rs = [i["R_MOhm"] for i in r["input_resistance"] if i["site"]["segment"] == 0]
    if rs: print("  sum C %.4f vs Rin soma %.4f (missing %.2e rel)" % (sum(m["coefficient_MOhm"] for m in r["modes"]), rs[0], 1 - sum(m["coefficient_MOhm"] for m in r["modes"]) / rs[0]))
    print("  taus:", [round(m["tau_ms"], 4) for m in r["modes"]][:10]); print("  C:", ["%.3e" % m["coefficient_MOhm"] for m in r["modes"]][:10])
