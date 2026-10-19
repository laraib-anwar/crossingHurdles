import importlib.util, json, math, sys, time, numpy as np
spec = importlib.util.spec_from_file_location("lo", "../../tasks/engineering-sciences/chemical-engineering/washcoat-ignition-audit/solution/lightoff_exact.py")
lo = importlib.util.module_from_spec(spec); spec.loader.exec_module(lo)
rng = np.random.RandomState(int(sys.argv[1]))
for k in range(int(sys.argv[2])):
    beta = round(rng.uniform(0.15, 0.6), 3); gamma = round(rng.uniform(12, 38), 2)
    Bim = round(math.exp(rng.uniform(math.log(5), math.log(200))), 2)
    ratio = math.exp(rng.uniform(0, math.log(min(Bim / 0.5, 1 / beta, 4.0))))
    Bih = round(Bim / ratio, 3)
    if Bih > 50 or Bih < 0.5 or beta * Bim / Bih > 1: continue
    Le = round(math.exp(rng.uniform(math.log(0.05), math.log(0.6))), 3)
    r = dict(recipe_id="p", beta=beta, gamma=gamma, Bi_m=Bim, Bi_h=Bih, Le=Le, phi_min=0.01, phi_max=30.0, phi_query=[0.02, 20.0])
    t = time.time()
    try:
        rep = lo.solve(r)
    except Exception as e:
        print(json.dumps(dict(err=str(e)[:80]))); continue
    print(json.dumps(dict(beta=beta, gamma=gamma, Bim=Bim, Bih=Bih, Le=Le, folds=[round(f["phi"],4) for f in rep["folds"]],
        hopf=[(round(h["phi"],4), round(h["omega"],3)) for h in rep["hopf_points"]], secs=round(time.time()-t,1))), flush=True)
