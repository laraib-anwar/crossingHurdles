"""Oracle checks against closed forms (dev tool)."""
import importlib.util, math, json, numpy as np
spec = importlib.util.spec_from_file_location("fd", "../../tasks/engineering-sciences/civil-engineering/frame-vibration-audit/solution/framedyn.py")
fd = importlib.util.module_from_spec(spec); spec.loader.exec_module(fd)
E, A, I, rho = 2.1e11, 1e-3, 1e-6, 7850.0
def node(i, x, y, sup=(False, False, False), m=0.0): return dict(id=i, x=x, y=y, mass_kg=m, support=dict(ux=sup[0], uy=sup[1], rz=sup[2]))
def mem(k, i, j, **kw): d = dict(id=k, i=i, j=j, E=E, A=A, I=I, rho=rho); d.update(kw); return d
def frame(nodes, members, nl=(), ml=(), q=(1,), n_modes=5, fmax=100.0, hq=()):
    return dict(frame_id="t", nodes=nodes, members=members, nodal_loads=list(nl), member_loads=list(ml), static_query_nodes=list(q), n_modes=n_modes, f_max_Hz=fmax, harmonic_queries=list(hq))
L = 6.0
# cantilever of 3 collinear members, tip load and uniform load
F = fd.Frame(frame([node(1, 0, 0, (True, True, True)), node(2, 2, 0), node(3, 4, 0), node(4, 6, 0)], [mem(1, 1, 2), mem(2, 2, 3), mem(3, 3, 4)], nl=[dict(node=4, Fx=0, Fy=-1000, Mz=0)], ml=[dict(member=k, wx=0, wy=-500) for k in (1, 2, 3)], q=[4], n_modes=4))
r = F.report(); P, w = 1000, 500
print("cantilever tip uy: oracle %.12e  exact %.12e" % (r["static"][0]["uy"], -(P * L**3 / (3 * E * I) + w * L**4 / (8 * E * I))))
print("cantilever tip rz: oracle %.12e  exact %.12e" % (r["static"][0]["rz"], -(P * L**2 / (2 * E * I) + w * L**3 / (6 * E * I))))
bl = [1.8751040687119611, 4.694091132974175, 7.854757438237613, 10.995540734722]
fex = [(b / L) ** 2 * math.sqrt(E * I / (rho * A)) / (2 * math.pi) for b in bl]
fax = 0.25 * math.sqrt(E / rho) / L      # fixed-free axial bar fundamental
allex = sorted(fex + [fax])[:4]
print("cantilever f: oracle", ["%.10f" % f for f in r["frequencies_Hz"]]); print("            exact ", ["%.10f" % f for f in allex])
# simply supported beam of 2 members
F = fd.Frame(frame([node(1, 0, 0, (True, True, False)), node(2, 3, 0), node(3, 6, 0, (False, True, False))], [mem(1, 1, 2), mem(2, 2, 3)], n_modes=4))
r = F.report()
fss = sorted([(n * math.pi / L) ** 2 * math.sqrt(E * I / (rho * A)) / (2 * math.pi) for n in (1, 2, 3)] + [0.5 * math.sqrt(E / rho) / L])[:4]
print("SS beam f: oracle", ["%.10f" % f for f in r["frequencies_Hz"]]); print("          exact ", ["%.10f" % f for f in fss])
# fixed-fixed single member: all modes are member-local (no free DOF)
F = fd.Frame(frame([node(1, 0, 0, (True, True, True)), node(2, 4, 0, (True, True, True))], [mem(1, 1, 2)], q=[1], n_modes=4, fmax=300.0))
r = F.report(); Lc = 4.0
fcc = sorted([(b / Lc) ** 2 * math.sqrt(E * I / (rho * A)) / (2 * math.pi) for b in fd.CC_ROOTS[:4]] + [n * 0.5 * math.sqrt(E / rho) / Lc for n in (1, 2)])[:4]
print("fixed-fixed f: oracle", ["%.10f" % f for f in r["frequencies_Hz"]], "count<300Hz", r["count_below"]); print("              exact ", ["%.10f" % f for f in fcc])
# harmonic reciprocity on a portal frame
nodes = [node(1, 0, 0, (True, True, True)), node(2, 0, 4), node(3, 6, 4), node(4, 6, 0, (True, True, False))]
mems = [mem(1, 1, 2), mem(2, 2, 3, I=2e-6), mem(3, 3, 4)]
hq = [dict(load_node=2, load_dof="ux", amplitude=1000.0, f_Hz=7.0, response_node=3, response_dof="rz"), dict(load_node=3, load_dof="rz", amplitude=1000.0, f_Hz=7.0, response_node=2, response_dof="ux")]
F = fd.Frame(frame(nodes, mems, n_modes=6, hq=hq)); r = F.report()
print("portal f:", ["%.6f" % f for f in r["frequencies_Hz"]], "reciprocity U:", r["harmonic"][0]["U"], r["harmonic"][1]["U"])
