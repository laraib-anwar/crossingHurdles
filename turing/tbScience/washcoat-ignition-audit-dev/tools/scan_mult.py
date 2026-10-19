"""Scan the parameter domain for cross-sections cs with more than one centre root (isolas need them)."""
import json, sys, numpy as np
from steady_core import Steady
rng = np.random.RandomState(int(sys.argv[1]))
z = np.linspace(-25, 23, 97); css = 1/(1+np.exp(-z))
out = []
for k in range(int(sys.argv[2])):
    beta = float(np.exp(rng.uniform(np.log(0.05), np.log(1.0))))
    gamma = float(rng.uniform(8, 40))
    Bim = float(np.exp(rng.uniform(np.log(0.5), np.log(500))))
    Bih = float(np.exp(rng.uniform(np.log(0.5), np.log(500))))
    S = Steady(beta, gamma, Bim, Bih)
    m, phis = [], []
    for cs in css:
        try:
            rr = S.roots(cs)
        except Exception:
            rr = []
        m.append(len(rr)); phis.append(S.state(cs, rr[0])[0] if rr else np.nan)
    m = np.array(m); p = np.array(phis)
    ok = np.isfinite(p)
    nfold = int(np.sum(np.diff(np.sign(np.diff(p[ok]))) != 0))
    out.append(dict(beta=beta, gamma=gamma, Bim=Bim, Bih=Bih, max_roots=int(m.max()), zero_root=int((m == 0).sum()), nfold=nfold))
    print(json.dumps(out[-1]), flush=True)
