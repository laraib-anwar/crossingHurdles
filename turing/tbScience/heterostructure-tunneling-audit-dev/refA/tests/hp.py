"""Independent high-precision checker (test-only; not used by reference.py).

Integrates psi'' = (m / C) (V(x) - E) psi through every layer with Taylor series in Python's
decimal arithmetic (no Airy functions, no global matrix, no transfer-matrix closed forms), with
psi and psi'/m continuous at the interfaces. The input numbers are taken as the exact binary
doubles that the reference program reads.

  T(E)      from the 2x2 real transfer matrix M of (psi, psi'/m) across the structure:
            T = 4ab / ((ab M12 - M21)^2 + (b M11 + a M22)^2),  a = k_L/m_L, b = k_R/m_R.
  bound     F(E) = w_X + (kappa_R/m_R) u_X for the solution (1, kappa_L/m_L) decaying at -inf;
            secant iteration started at the reference value.
  maxima    secant on the central difference of T(E) (step 1e-15 eV) started at the reference.
The working precision is 50 digits plus the decimal growth of the solution through barriers.
"""
import math
from decimal import Decimal, getcontext

getcontext().Emax = 10 ** 8
getcontext().Emin = -(10 ** 8)

C = Decimal(0.0380998212)
CF = 0.0380998212


def _dec(x):
    return Decimal(float(x))


class HPModel:
    def __init__(self, s):
        self.mL = _dec(s["left_lead"]["mass"])
        self.VL = _dec(s["left_lead"]["v_eV"])
        self.mR = _dec(s["right_lead"]["mass"])
        self.VR = _dec(s["right_lead"]["v_eV"])
        self.layers = [(_dec(L["thickness_nm"]), _dec(L["mass"]), _dec(L["vl_eV"]), _dec(L["vr_eV"]))
                       for L in s["layers"]]
        self.flayers = [(float(L["thickness_nm"]), float(L["mass"]), float(L["vl_eV"]),
                         float(L["vr_eV"])) for L in s["layers"]]

    def growth_digits(self, E):
        g = 0.0
        for d, m, vl, vr in self.flayers:
            vmax = max(vl, vr)
            if vmax > E:
                g += math.sqrt(m * (vmax - E) / CF) * d
        return g / math.log(10.0)


def _set_prec(model, E, extra=50):
    getcontext().prec = int(extra + 1.15 * model.growth_digits(float(E)))


def _propagate(model, E, vecs):
    """Propagate a list of (u, w) vectors from x = 0 to x = X."""
    vecs = [list(v) for v in vecs]
    eps = Decimal(10) ** (-(getcontext().prec + 3))
    for d, m, vl, vr in model.layers:
        alpha = m * (vl - E) / C
        beta = m * (vr - vl) / (d * C)
        # state: u and du/dx
        st = [[v[0], m * v[1]] for v in vecs]
        s = Decimal(0)
        last = False
        while not last:
            a0 = alpha + beta * s
            hf = min(1.0, 0.5 / math.sqrt(abs(float(a0)) + 1e-30), 0.5 / (abs(float(beta)) + 1e-30) ** (1.0 / 3.0))
            h = Decimal(hf)
            if s + h >= d:                      # final step closes the layer exactly
                h = d - s
                last = True
                if h <= 0:
                    break
            A = a0 * h * h
            B3 = beta * h * h * h
            for v in st:
                b0 = v[0]
                b1 = v[1] * h
                bm3, bm2, bm1 = Decimal(0), b0, b1   # b_{n-3}, b_{n-2}, b_{n-1}
                usum = b0 + b1
                dsum = b1
                scale = abs(b0) + abs(b1)
                n = 2
                small = 0
                while True:
                    bn = (A * bm2 + B3 * bm3) / (n * (n - 1))
                    usum += bn
                    dsum += n * bn
                    if abs(bn) <= eps * scale:
                        small += 1
                        if small >= 3:
                            break
                    else:
                        small = 0
                    bm3, bm2, bm1 = bm2, bm1, bn
                    n += 1
                v[0] = usum
                v[1] = dsum / h
            s += h
        vecs = [[v[0], v[1] / m] for v in st]
    return vecs


def transmission(model, E):
    E = _dec(E) if not isinstance(E, Decimal) else E
    _set_prec(model, E)
    (M11, M21), (M12, M22) = _propagate(model, E, [(Decimal(1), Decimal(0)), (Decimal(0), Decimal(1))])
    a = (model.mL * (E - model.VL) / C).sqrt() / model.mL
    b = (model.mR * (E - model.VR) / C).sqrt() / model.mR
    x = a * b * M12 - M21
    y = b * M11 + a * M22
    return 4 * a * b / (x * x + y * y)


def bound_F(model, E):
    E = _dec(E) if not isinstance(E, Decimal) else E
    _set_prec(model, E)
    kL = (model.mL * (model.VL - E) / C).sqrt()
    kR = (model.mR * (model.VR - E) / C).sqrt()
    (u, w), = _propagate(model, E, [(Decimal(1), kL / model.mL)])
    return (w + kR / model.mR * u) / (abs(u) + abs(w))


def bound_root(model, E0, h0=1e-13, resolve=Decimal("1e-19")):
    """Root of F near E0: find a sign change in [E0 - h, E0 + h] (h = h0, 10 h0, ...), then bisect
    on the sign of F (behind thick barriers F is a step function of E, so no secant)."""
    E0 = _dec(E0)
    h = Decimal(h0)
    while True:
        a, b = E0 - h, E0 + h
        fa, fb = bound_F(model, a), bound_F(model, b)
        if (fa > 0) != (fb > 0):
            break
        h *= 10
        if h > Decimal("1e-5"):
            raise RuntimeError("no sign change near the reference value")
    while b - a > resolve:
        m = (a + b) / 2
        fm = bound_F(model, m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def dT(model, E, h=Decimal("1e-15")):
    E = _dec(E) if not isinstance(E, Decimal) else E
    return (transmission(model, E + h) - transmission(model, E - h)) / (2 * h)


def maximum(model, E0, h=1e-9, tol=Decimal("1e-22"), maxit=40):
    x0 = _dec(E0 - h)
    x1 = _dec(E0 + h)
    f0 = dT(model, x0)
    f1 = dT(model, x1)
    for _ in range(maxit):
        if f1 == f0:
            break
        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
        x0, f0 = x1, f1
        x1 = x2
        f1 = dT(model, x1)
        if abs(x1 - x0) < tol:
            break
    return x1, transmission(model, x1)
