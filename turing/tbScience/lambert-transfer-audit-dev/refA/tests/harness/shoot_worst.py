import json, sys, numpy as np
from decimal import Decimal as D
sys.path.insert(0, '.')
import hp
W = json.load(open(sys.argv[1]))
for rr, r1, v1, r2, v2, T, mu, N, a, e in W:
    rx, vx = hp.kepler([D(t) for t in r1], [D(t) for t in v1], D(T), D(mu))
    rd = float(hp.dsqrt(sum((p - D(q)) ** 2 for p, q in zip(rx, r2)))) / np.linalg.norm(r2)
    vx1, vx2, res = hp.lambert_shoot(r1, v1, r2, D(T), D(mu))
    ve1 = np.array([float(t) for t in vx1]); ve2 = np.array([float(t) for t in vx2])
    ev1 = np.linalg.norm(np.array(v1) - ve1) / np.linalg.norm(ve1); ev2 = np.linalg.norm(np.array(v2) - ve2) / np.linalg.norm(ve2)
    print("N=%d a=%.3e e=%.4f  reprop double %.1e decimal %.1e | v1 err %.1e v2 err %.1e" % (N, a, e, rr, rd, ev1, ev2), flush=True)
