"""Oracle checks against closed forms and fine staircases (dev tool)."""
import importlib.util, math, sys, numpy as np
from scipy.optimize import brentq
spec = importlib.util.spec_from_file_location("ht", "../../tasks/physical-sciences/physics/heterostructure-tunneling-audit/solution/hetero.py")
ht = importlib.util.module_from_spec(spec); spec.loader.exec_module(ht)
C = ht.C
def S(layers, lead=(0.067, 0.3), right=None, tq=(0.35, 0.5), win=(0.31, 0.6)):
    right = right or lead
    return dict(structure_id="t", left_lead=dict(mass=lead[0], v_eV=lead[1]), right_lead=dict(mass=right[0], v_eV=right[1]),
                layers=[dict(thickness_nm=d, mass=m, vl_eV=a, vr_eV=b) for d, m, a, b in layers], transmission_energies_eV=list(tq), window_eV=list(win))
m, V0, a = 0.067, 0.3, 10.0
st = ht.Structure(S([(a, m, 0.0, 0.0), (1.0, m, 0.3, 0.3)]))
bs = st.bound_states()
def even(E): k = math.sqrt(m*E/C); kap = math.sqrt(m*(V0-E)/C); return k*math.tan(k*a/2) - kap
def odd(E): k = math.sqrt(m*E/C); kap = math.sqrt(m*(V0-E)/C); return -k/math.tan(k*a/2) - kap
ex = []
grid = np.linspace(1e-9, V0-1e-9, 200001)
for f in (even, odd):
    v = np.array([f(E) for E in grid])
    for i in range(len(grid)-1):
        if v[i]*v[i+1] < 0 and abs(v[i]-v[i+1]) < 10: ex.append(brentq(f, grid[i], grid[i+1], xtol=1e-16))
ex.sort()
print("well: max |oracle - exact| = %.2e eV over %d/%d states" % (max(abs(x-y) for x, y in zip(bs, ex)), len(bs), len(ex)))
d, Vb = 3.0, 0.3
st = ht.Structure(S([(d, m, Vb, Vb), (0.5, m, 0.0, 0.0)], lead=(m, 0.0)))
for E in (0.05, 0.2, 0.29, 0.45):
    kap2 = m*(Vb-E)/C
    Tex = 1/(1 + Vb**2*math.sinh(math.sqrt(kap2)*d)**2/(4*E*(Vb-E))) if kap2 > 0 else 1/(1 + Vb**2*math.sin(math.sqrt(-kap2)*d)**2/(4*E*(E-Vb)))
    print("barrier E=%.2f rel err %.1e" % (E, abs(st.T(E)[0]/Tex-1)))
st = ht.Structure(S([(8.0, 0.08, 0.5, 0.1)], lead=(0.067, 0.0)))
prev = None
for n in (200, 400, 800):
    stair = [(8.0/n, 0.08, 0.5 + (0.1-0.5)*(i+0.5)/n, 0.5 + (0.1-0.5)*(i+0.5)/n) for i in range(n)]
    t = ht.Structure(S(stair, lead=(0.067, 0.0))).T(0.2)[0]
    print("stair n=%d T(0.2)=%.12e" % (n, t))
print("airy        T(0.2)=%.12e" % st.T(0.2)[0])
st = ht.Structure(S([(25.0, 0.1, 1.2, 1.2), (5.0, 0.067, 0.0, 0.0), (25.0, 0.1, 1.2, 1.2)], lead=(0.067, 0.0)))
print("thick double barrier T(0.1) = %.6e" % st.T(0.1)[0])
tri = [(40.0, 0.067, 0.0, 0.4)]
st = ht.Structure(S(tri, lead=(0.067, 0.5), right=(0.067, 0.5)))
b0 = st.bound_states()
for n in (400, 800):
    stair = [(40.0/n, 0.067, 0.4*(i+0.5)/n, 0.4*(i+0.5)/n) for i in range(n)]
    print("stair n=%d" % n, ["%.9f" % e for e in ht.Structure(S(stair, lead=(0.067, 0.5), right=(0.067, 0.5))).bound_states()[:4]])
print("airy       ", ["%.9f" % e for e in b0[:4]], "count", len(b0))
