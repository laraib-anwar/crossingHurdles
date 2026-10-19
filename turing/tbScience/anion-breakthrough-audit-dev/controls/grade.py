"""Grade a directory of reports against expected reports with the verifier's own validate and
compare functions (dev tool, not shipped).

usage: grade.py <test_outputs.py> <recipes_dir> <expected.json> <reports_dir> [--verbose]
Each report is <reports_dir>/<recipe_id>.json. Prints pass count and, with --verbose, the first
failure per recipe.
"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("test_outputs", sys.argv[1])
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
recipes = {p.stem: json.loads(p.read_text()) for p in Path(sys.argv[2]).glob("*.json")}
expected = json.loads(Path(sys.argv[3]).read_text())
reports = Path(sys.argv[4])
verbose = "--verbose" in sys.argv
passed, total, worst = 0, 0, {}
for rid in sorted(recipes):
    total += 1
    rp = reports / f"{rid}.json"
    if not rp.exists():
        if verbose:
            print(f"  {rid}: no report")
        continue
    rep = json.loads(rp.read_text())
    try:
        T.validate_report(rep, recipes[rid], rid)
    except AssertionError as e:
        if verbose:
            print(f"  {rid}: CONTRACT {str(e)[:160]}")
        continue
    errs = T.compare(rep, expected[rid], rid)
    if errs:
        if verbose:
            print(f"  {rid}: FAIL {errs[0][:200]}" + (f" (+{len(errs) - 1} more)" if len(errs) > 1 else ""))
    else:
        passed += 1
print(f"passed {passed}/{total}")
