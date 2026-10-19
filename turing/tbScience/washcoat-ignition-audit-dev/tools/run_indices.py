"""Build the listed PLAN indices (rerun helper). usage: run_indices.py <lightoff_exact.py> <out> i j k ..."""
import sys
sys.argv, idx = sys.argv[:3] + ["0", "0"], [int(v) for v in sys.argv[3:]]
import importlib.util
spec = importlib.util.spec_from_file_location("gen", __file__.replace("run_indices.py", "gen_recipes.py"))
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
for i in idx:
    gen.build(i)
