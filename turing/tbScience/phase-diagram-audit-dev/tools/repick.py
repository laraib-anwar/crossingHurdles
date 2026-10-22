"""Re-pick the isotherms of systems whose sections show no tie-lines (dev tool).
usage: repick.py <phasediagram.py> <out_dir> <system ids...>"""
import sys, json
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]] + sys.argv[3:]
src = open(__file__.replace("repick.py", "gen_systems.py")).read().split('if __name__ == "__main__":')[0]
ids = sys.argv[3:]; sys.argv = sys.argv[:3]
exec(src)
for sid in ids:
    path = OUT / "systems" / f"{sid}.json"
    m = json.load(open(path))
    plan = next(p for p in PLAN if p[0] == sid)
    want = dict(plan[3]); want["min_tie"] = max(1, want.get("min_tie", 1))
    rng = np.random.RandomState(777 + sum(map(ord, sid)))
    m0 = dict(m, isotherms_K=[])
    S = pd.System(m0); _, events = S.solve()
    n = max(len(m["isotherms_K"]), int(rng.randint(2, 7)))
    iso = choose_isotherms(rng, S, events, m["window_K"], n, want)
    if len(iso) < 2 or not guarantee_1(events, m["window_K"], iso):
        print(sid, "FAILED repick", iso); continue
    m["isotherms_K"] = iso
    S2 = pd.System(m); report = S2.report(); _, events2 = pd.System(m).solve()
    ok = guarantee_1(events2, m["window_K"], iso) and predicate(want, m, report, events2)
    print(sid, "ok" if ok else "PREDICATE FAIL", iso, [len(i["tie_lines"]) for i in report["isotherms"]], flush=True)
    if ok:
        json.dump(m, open(path, "w"), indent=1)
        lg = json.load(open(OUT / "log" / f"{sid}.json")); lg["isotherms"] = iso; lg["summary"] = summarize(report, events2)
        json.dump(lg, open(OUT / "log" / f"{sid}.json", "w"), indent=1, default=str)
