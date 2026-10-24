"""High-precision (Decimal, 60 digits) universal-variable propagation and Lambert shooting.

Validation only.  Independent of reference.py's Lambert formulas: it propagates (r1, v1)
by T with a Decimal Kepler solve and Newton-corrects v1 with a finite-difference Jacobian
until r(T) = r2 to ~40 digits.  Also a Decimal Kepler-equation ephemeris (E / H anomaly)."""
from decimal import Decimal as D, getcontext, localcontext
import math

getcontext().prec = 80
PI = D("3.14159265358979323846264338327950288419716939937510582097494459230781640628620899863")


def dsqrt(x):
    return x.sqrt()


def stumpff(z):
    # series; for large |z| raise precision locally
    with localcontext() as ctx:
        ctx.prec = 60 + int(abs(float(z)) ** 0.5 / 2.3) + 10
        c = D(0); s = D(0)
        tc = D(1) / 2; ts = D(1) / 6
        k = 0
        eps = D(10) ** (-(ctx.prec + 5))
        while True:
            c += tc; s += ts
            k += 1
            tc = tc * (-z) / ((2 * k + 1) * (2 * k + 2))
            ts = ts * (-z) / ((2 * k + 2) * (2 * k + 3))
            if k > 5 and abs(tc) < eps and abs(ts) < eps:
                break
    return +c, +s


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def kepler(r0v, v0v, dt, mu, chi0=None):
    """Universal Kepler in Decimal with a safeguarded (bracketed) Newton iteration."""
    r0 = dsqrt(dot(r0v, r0v))
    sm = dsqrt(mu)
    sig = dot(r0v, v0v) / sm
    alpha = 2 / r0 - dot(v0v, v0v) / mu
    if alpha > 0:
        a = 1 / alpha
        P = 2 * PI * a * dsqrt(a) / sm
        k = (dt / P + D("0.5")).to_integral_value(rounding="ROUND_FLOOR")
        dt = dt - k * P

    def FR(chi):
        z = alpha * chi * chi
        C, S = stumpff(z)
        Fv = sm * dt - (chi ** 3 * S + sig * chi * chi * C + r0 * chi * (1 - z * S))
        r = chi * chi * C + sig * chi * (1 - z * S) + r0 * (1 - z * C)
        return Fv, r

    # bracket: F decreasing in chi
    if alpha > 0:
        lo = -2 * PI * dsqrt(1 / alpha); hi = -lo
    else:
        scale = dsqrt(-1 / alpha) if alpha < 0 else dsqrt(r0)
        if dt >= 0:
            lo = D(0); hi = scale
            while FR(hi)[0] > 0:
                lo = hi; hi *= 2
        else:
            hi = D(0); lo = -scale
            while FR(lo)[0] < 0:
                hi = lo; lo *= 2
    chi = (lo + hi) / 2
    tol = D(10) ** -50
    for it in range(2000):
        Fv, r = FR(chi)
        if Fv > 0:
            lo = chi
        else:
            hi = chi
        new = chi + Fv / r
        if not (lo < new < hi):
            new = (lo + hi) / 2
        if abs(new - chi) <= tol * (1 + abs(chi)):
            chi = new
            break
        chi = new
    z = alpha * chi * chi
    C, S = stumpff(z)
    r = chi * chi * C + sig * chi * (1 - z * S) + r0 * (1 - z * C)
    f = 1 - chi * chi * C / r0
    g = dt - chi ** 3 * S / sm
    gd = 1 - chi * chi * C / r
    fd = sm / (r * r0) * chi * (z * S - 1)
    rv = [f * x + g * y for x, y in zip(r0v, v0v)]
    vv = [fd * x + gd * y for x, y in zip(r0v, v0v)]
    return rv, vv


def solve3(J, b):
    # Gaussian elimination
    M = [row[:] + [bb] for row, bb in zip(J, b)]
    n = 3
    for i in range(n):
        p = max(range(i, n), key=lambda k: abs(M[k][i]))
        M[i], M[p] = M[p], M[i]
        for k in range(i + 1, n):
            f = M[k][i] / M[i][i]
            for j in range(i, n + 1):
                M[k][j] -= f * M[i][j]
    x = [D(0)] * n
    for i in reversed(range(n)):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def lambert_shoot(r1, v1, r2, T, mu, iters=8):
    """Newton shooting from a double guess v1; returns (v1, v2) in Decimal."""
    r1 = [D(x) for x in r1]; r2 = [D(x) for x in r2]; v = [D(x) for x in v1]
    T = D(T); mu = D(mu)
    for it in range(iters):
        rT, vT = kepler(r1, v, T, mu)
        res = [a - b for a, b in zip(rT, r2)]
        nres = max(abs(x) for x in res)
        if nres < D(10) ** -40 * dsqrt(dot(r2, r2)):
            break
        J = [[D(0)] * 3 for _ in range(3)]
        vn = dsqrt(dot(v, v))
        h = vn * D(10) ** -25
        for j in range(3):
            vp = v[:]; vp[j] += h
            rp, _ = kepler(r1, vp, T, mu)
            for i in range(3):
                J[i][j] = (rp[i] - rT[i]) / h
        dx = solve3(J, [-x for x in res])
        v = [a + b for a, b in zip(v, dx)]
    rT, vT = kepler(r1, v, T, mu)
    return v, vT, max(abs(a - b) for a, b in zip(rT, r2))


# ---- Decimal trig -----------------------------------------------------------

def dsin_cos(x):
    x = x % (2 * PI)
    s = D(0); c = D(0)
    t = x; k = 1
    while abs(t) > D(10) ** -70:
        s += t
        t = -t * x * x / ((k + 1) * (k + 2)); k += 2
    t = D(1); k = 0
    while abs(t) > D(10) ** -70:
        c += t
        t = -t * x * x / ((k + 1) * (k + 2)); k += 2
    return s, c


def dsinh_cosh(x):
    ex = x.exp(); em = (-x).exp()
    return (ex - em) / 2, (ex + em) / 2


def ephemeris(obj, mu, t):
    """Kepler-equation ephemeris in Decimal (E or H anomaly), validation only."""
    mu = D(mu); a = D(obj["a_km"]); e = D(obj["e"])
    deg = PI / 180
    n = dsqrt(mu / abs(a) ** 3)
    M = D(obj["M0_deg"]) * deg + n * (D(t) - D(obj["t0_days"])) * 86400
    if a > 0:
        M = M % (2 * PI)
        E = M if e < D("0.8") else PI
        for _ in range(100):
            s, c = dsin_cos(E)
            dE = (E - e * s - M) / (1 - e * c)
            E -= dE
            if abs(dE) < D(10) ** -50:
                break
        s, c = dsin_cos(E)
        x = a * (c - e); y = a * dsqrt(1 - e * e) * s
        r = a * (1 - e * c)
        vx = -dsqrt(mu * a) / r * s; vy = dsqrt(mu * a * (1 - e * e)) / r * c
    else:
        H = (M / e).ln() if False else D(0)
        # asinh guess
        H = D(math.asinh(float(M / e)))
        for _ in range(200):
            sh, ch = dsinh_cosh(H)
            dH = (e * sh - H - M) / (e * ch - 1)
            H -= dH
            if abs(dH) < D(10) ** -50:
                break
        sh, ch = dsinh_cosh(H)
        aa = -a
        x = aa * (e - ch); y = aa * dsqrt(e * e - 1) * sh
        r = aa * (e * ch - 1)
        vx = -dsqrt(mu * aa) / r * sh; vy = dsqrt(mu * aa * (e * e - 1)) / r * ch
    O = D(obj["Omega_deg"]) * deg; I = D(obj["i_deg"]) * deg; w = D(obj["omega_deg"]) * deg
    sO, cO = dsin_cos(O); sI, cI = dsin_cos(I); sw, cw = dsin_cos(w)
    R = [[cO * cw - sO * sw * cI, -cO * sw - sO * cw * cI, sO * sI],
         [sO * cw + cO * sw * cI, -sO * sw + cO * cw * cI, -cO * sI],
         [sw * sI, cw * sI, cI]]
    rv = [R[i][0] * x + R[i][1] * y for i in range(3)]
    vv = [R[i][0] * vx + R[i][1] * vy for i in range(3)]
    return rv, vv
