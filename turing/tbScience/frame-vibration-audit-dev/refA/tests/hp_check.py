#!/usr/bin/env python3
"""High-precision (60-digit decimal) re-evaluation of the end-state formulation, used to
measure the floating-point precision of reference.py.

Same physics as reference.py, different arithmetic and a different (unstabilised) basis:
the member relation is the plain transfer y(1) = T y(0), T = exp(A) by scaling and squaring of
a Taylor sum in 60-digit decimals (the loss to exp(+-lambda) mixing, at most ~18 digits for
lambda = 40, is far below the working precision). The global matrix has the unknowns
[y(0) of every member, D of every node]; det is by Gaussian elimination with partial pivoting.
Each frequency of a report is re-solved by the secant method on det, started from the
double-precision value; harmonic amplitudes and static displacements (augmented state with the
uniform-load particular solution) are re-solved directly. Static errors are reported relative
to the largest magnitude of the same component among the query nodes.

    python hp_check.py <frame.json> <report.json>      -> JSON on stdout
"""
import json
import sys
from decimal import Decimal as D, getcontext

getcontext().prec = 60
PI = D("3.14159265358979323846264338327950288419716939937510582097494459")


def dsqrt(x):
    return x.sqrt()


def matmul(A, B):
    n, m, p = len(A), len(B), len(B[0])
    return [[sum((A[i][k] * B[k][j] for k in range(m)), D(0)) for j in range(p)] for i in range(n)]


def expm(A):
    n = len(A)
    nrm = max(sum(abs(v) for v in row) for row in A)
    s = 0
    while nrm > D("0.5"):
        nrm /= 2
        s += 1
    sc = D(2) ** s
    As = [[v / sc for v in row] for row in A]
    E = [[D(1) if i == j else D(0) for j in range(n)] for i in range(n)]
    T = [row[:] for row in E]
    for k in range(1, 80):
        T = [[v / k for v in row] for row in matmul(T, As)]
        E = [[E[i][j] + T[i][j] for j in range(n)] for i in range(n)]
        if max(abs(v) for row in T for v in row) < D("1e-70"):
            break
    for _ in range(s):
        E = matmul(E, E)
    return E


class HPFrame:
    def __init__(self, raw):
        self.raw = raw
        self.N = len(raw["nodes"])
        self.M = len(raw["members"])
        nd = raw["nodes"]
        self.x = [D(repr(float(n["x"]))) for n in nd]
        self.y = [D(repr(float(n["y"]))) for n in nd]
        self.mass = [D(repr(float(n["mass_kg"]))) for n in nd]
        self.sup = [[bool(n["support"][d]) for d in ("ux", "uy", "rz")] for n in nd]
        self.mem = []
        for m in raw["members"]:
            i, j = int(m["i"]) - 1, int(m["j"]) - 1
            E, A, I, rho = (D(repr(float(m[k]))) for k in ("E", "A", "I", "rho"))
            dx, dy = self.x[j] - self.x[i], self.y[j] - self.y[i]
            L = dsqrt(dx * dx + dy * dy)
            self.mem.append(dict(i=i, j=j, E=E, A=A, I=I, rho=rho, L=L, c=dx / L, s=dy / L))

    def member_T(self, m, om):
        """Transfer of (u, N L/EA, v, theta L, M L^2/EI, Q L^3/EI) over the member."""
        L, E, A, I, rho = m["L"], m["E"], m["A"], m["I"], m["rho"]
        a2 = rho * om * om * L * L / E
        l4 = rho * A * om * om * L ** 4 / (E * I)
        Z = [[D(0)] * 6 for _ in range(6)]
        Z[0][1] = D(1)
        Z[1][0] = -a2
        Z[2][3] = D(1)
        Z[3][4] = D(1)
        Z[4][5] = D(1)
        Z[5][2] = l4
        # balance the bending block by s = max(lambda, 1) before exponentiating
        lam = dsqrt(dsqrt(l4)) if l4 > 0 else D(0)
        sg = lam if lam > 1 else D(1)
        dg = [D(1), D(1), D(1), sg, sg * sg, sg * sg * sg]
        Zs = [[Z[r][c] * dg[c] / dg[r] for c in range(6)] for r in range(6)]
        Ts = expm(Zs)
        return [[Ts[r][c] * dg[r] / dg[c] for c in range(6)] for r in range(6)]

    def system(self, om):
        M, N = self.M, self.N
        n = 6 * M + 3 * N
        G = [[D(0)] * n for _ in range(n)]
        off = 6 * M
        for k, m in enumerate(self.mem):
            T = self.member_T(m, om)
            c, s, L = m["c"], m["s"], m["L"]
            kN = m["E"] * m["A"] / L
            kM = m["E"] * m["I"] / (L * L)
            kQ = m["E"] * m["I"] / (L * L * L)
            for e in (0, 1):
                node = m["i"] if e == 0 else m["j"]
                # end state as a linear form in y(0) of this member
                if e == 0:
                    st = [[D(1) if r == q else D(0) for q in range(6)] for r in range(6)]
                else:
                    st = T
                r0 = 6 * k + 3 * e
                for q in range(6):
                    G[r0][6 * k + q] = c * st[0][q] - s * st[2][q]
                    G[r0 + 1][6 * k + q] = s * st[0][q] + c * st[2][q]
                    G[r0 + 2][6 * k + q] = st[3][q]
                G[r0][off + 3 * node] = D(-1)
                G[r0 + 1][off + 3 * node + 1] = D(-1)
                G[r0 + 2][off + 3 * node + 2] = -L
                sgn = D(1) if e == 0 else D(-1)
                rn = off + 3 * node
                for q in range(6):
                    Fa = sgn * kN * st[1][q]
                    Ft = -sgn * kQ * st[5][q]
                    Mn = sgn * kM * st[4][q]
                    if not self.sup[node][0]:
                        G[rn][6 * k + q] += c * Fa - s * Ft
                    if not self.sup[node][1]:
                        G[rn + 1][6 * k + q] += s * Fa + c * Ft
                    if not self.sup[node][2]:
                        G[rn + 2][6 * k + q] += Mn
        for node in range(N):
            for d in range(3):
                r = off + 3 * node + d
                if self.sup[node][d]:
                    G[r] = [D(0)] * n
                    G[r][r] = D(1)
                elif d < 2:
                    G[r][r] += self.mass[node] * om * om
        return G


def static_system(hf):
    """Static end-state system with the uniform-load particular solution (augmented state)."""
    raw = hf.raw
    M, N = hf.M, hf.N
    n = 6 * M + 3 * N
    G = [[D(0)] * n for _ in range(n)]
    b = [D(0)] * n
    off = 6 * M
    w = [[D(0), D(0)] for _ in range(M)]
    for ld in raw["member_loads"]:
        k = int(ld["member"]) - 1
        w[k][0] += D(repr(float(ld["wx"])))
        w[k][1] += D(repr(float(ld["wy"])))
    P = [[D(0)] * 3 for _ in range(N)]
    for ld in raw["nodal_loads"]:
        nn = int(ld["node"]) - 1
        for d, key in enumerate(("Fx", "Fy", "Mz")):
            P[nn][d] += D(repr(float(ld[key])))
    for k, m in enumerate(hf.mem):
        c, s, L = m["c"], m["s"], m["L"]
        EA, EI = m["E"] * m["A"], m["E"] * m["I"]
        qa = w[k][0] * c + w[k][1] * s
        qt = -w[k][0] * s + w[k][1] * c
        Z = [[D(0)] * 7 for _ in range(7)]
        Z[0][1] = D(1)
        Z[1][6] = -qa * L * L / EA
        Z[2][3] = D(1)
        Z[3][4] = D(1)
        Z[4][5] = D(1)
        Z[5][6] = qt * L ** 4 / EI
        T = expm(Z)
        kN, kM, kQ = EA / L, EI / (L * L), EI / (L * L * L)
        for e in (0, 1):
            node = m["i"] if e == 0 else m["j"]
            if e == 0:
                st = [[D(1) if r == q else D(0) for q in range(7)] for r in range(6)]
            else:
                st = [row[:] for row in T[:6]]
            r0 = 6 * k + 3 * e
            rn = off + 3 * node
            sgn = D(1) if e == 0 else D(-1)
            rowsdef = [(r0, [c * st[0][q] - s * st[2][q] for q in range(7)]),
                       (r0 + 1, [s * st[0][q] + c * st[2][q] for q in range(7)]),
                       (r0 + 2, [st[3][q] for q in range(7)])]
            for r, coef in rowsdef:
                for q in range(6):
                    G[r][6 * k + q] = coef[q]
                b[r] -= coef[6]
            G[r0][rn] = D(-1)
            G[r0 + 1][rn + 1] = D(-1)
            G[r0 + 2][rn + 2] = -L
            Fa = [sgn * kN * st[1][q] for q in range(7)]
            Ft = [-sgn * kQ * st[5][q] for q in range(7)]
            Mn = [sgn * kM * st[4][q] for q in range(7)]
            for d, coef in ((0, [c * Fa[q] - s * Ft[q] for q in range(7)]),
                            (1, [s * Fa[q] + c * Ft[q] for q in range(7)]), (2, Mn)):
                if not hf.sup[node][d]:
                    for q in range(6):
                        G[rn + d][6 * k + q] += coef[q]
                    b[rn + d] -= coef[6]
    for node in range(N):
        for d in range(3):
            r = off + 3 * node + d
            if hf.sup[node][d]:
                G[r] = [D(0)] * n
                G[r][r] = D(1)
                b[r] = D(0)
            else:
                b[r] -= P[node][d]
    return G, b


def det(G):
    A = [row[:] for row in G]
    n = len(A)
    dt = D(1)
    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(A[r][k]))
        if A[p][k] == 0:
            return D(0)
        if p != k:
            A[k], A[p] = A[p], A[k]
            dt = -dt
        dt *= A[k][k]
        piv = A[k][k]
        for r in range(k + 1, n):
            f = A[r][k] / piv
            if f != 0:
                Ar, Ak = A[r], A[k]
                for c in range(k, n):
                    Ar[c] -= f * Ak[c]
    return dt


def solve(G, b):
    A = [row[:] + [bv] for row, bv in zip(G, b)]
    n = len(A)
    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(A[r][k]))
        A[k], A[p] = A[p], A[k]
        piv = A[k][k]
        for r in range(k + 1, n):
            f = A[r][k] / piv
            if f != 0:
                for c in range(k, n + 1):
                    A[r][c] -= f * A[k][c]
    x = [D(0)] * n
    for k in range(n - 1, -1, -1):
        x[k] = (A[k][n] - sum((A[k][c] * x[c] for c in range(k + 1, n)), D(0))) / A[k][k]
    return x


def hp_root(hf, f0):
    om0 = 2 * PI * D(repr(f0))
    om1 = om0 * (1 + D("1e-9"))
    d0, d1 = det(hf.system(om0)), det(hf.system(om1))
    for _ in range(60):
        if d1 == d0:
            break
        om2 = om1 - d1 * (om1 - om0) / (d1 - d0)
        om0, d0 = om1, d1
        om1, d1 = om2, det(hf.system(om2))
        if abs(om1 - om0) < D("1e-40") * abs(om1):
            break
    return om1 / (2 * PI)


def main():
    raw = json.load(open(sys.argv[1]))
    rep = json.load(open(sys.argv[2]))
    hf = HPFrame(raw)
    out = {"frame_id": raw["frame_id"], "freq": [], "harmonic": []}
    for f in rep["frequencies_Hz"]:
        fh = hp_root(hf, f)
        out["freq"].append([f, str(fh), float(abs(D(repr(f)) - fh) / fh)])
    dofs = {"ux": 0, "uy": 1, "rz": 2}
    Us = [abs(h["U"]) for h in rep["harmonic"]]
    for h in rep["harmonic"]:
        om = 2 * PI * D(repr(float(h["f_Hz"])))
        G = hf.system(om)
        b = [D(0)] * len(G)
        n, d = int(h["load_node"]) - 1, dofs[h["load_dof"]]
        if not hf.sup[n][d]:
            b[6 * hf.M + 3 * n + d] = -D(repr(float(h["amplitude"])))
        x = solve(G, b)
        U = x[6 * hf.M + 3 * (int(h["response_node"]) - 1) + dofs[h["response_dof"]]]
        out["harmonic"].append([h["U"], str(U), float(abs(D(repr(h["U"])) - U) / abs(U)) if U != 0 else 0.0])
    G, b = static_system(hf)
    x = solve(G, b)
    kinds = {"ux": 0, "uy": 1, "rz": 2}
    ex = {k: [x[6 * hf.M + 3 * (int(q["node"]) - 1) + d] for q in rep["static"]] for k, d in kinds.items()}
    out["static"] = {}
    for k in kinds:
        sc = max(abs(v) for v in ex[k])
        errs = [abs(D(repr(q[k])) - v) for q, v in zip(rep["static"], ex[k])]
        out["static"][k] = float(max(errs) / sc) if sc > 0 else float(max(errs))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
