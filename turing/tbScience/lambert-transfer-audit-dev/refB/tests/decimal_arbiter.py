#!/usr/bin/env python3
"""40-digit decimal arbiter for object states and transfer angles (no numpy, no refB code).

usage: python decimal_arbiter.py SYSTEM.json REPORT.json

Prints, for every ephemeris query, the relative position error of the report against a 40-digit
Kepler solution of the system file, and for every transfer the report's theta error in degrees.
Times enter as exact (t - t0) * 86400 on the given binary doubles.  Used to arbitrate when the
referee and a report disagree about ephemerides or theta.
"""
import json
import sys
from decimal import Decimal as D, getcontext

getcontext().prec = 40


def _pi():
    getcontext().prec += 6

    def atan_inv(x):
        x = D(x)
        s = t = 1 / x
        x2, n, sign = x * x, 1, -1
        while True:
            t /= x2
            n += 2
            term = t / n
            if term < D(10) ** -(getcontext().prec + 2):
                break
            s += sign * term
            sign = -sign
        return s

    p = 4 * (4 * atan_inv(5) - atan_inv(239))
    getcontext().prec -= 6
    return +p


PI = _pi()
TINY = D(10) ** -46


def sin(x):
    x = x % (2 * PI)
    s = t = x
    n = 1
    while abs(t) > TINY:
        t = -t * x * x / ((n + 1) * (n + 2))
        n += 2
        s += t
    return s


def cos(x):
    return sin(x + PI / 2)


def exp(x):
    s = t = D(1)
    n = 0
    while abs(t) > TINY * max(D(1), abs(s)):
        n += 1
        t = t * x / n
        s += t
    return s


def sinh(x):
    return (exp(x) - exp(-x)) / 2


def cosh(x):
    return (exp(x) + exp(-x)) / 2


def atan2(y, x):
    import math
    t = D(math.atan2(float(y), float(x)))
    for _ in range(6):
        t = t - (sin(t) * x - cos(t) * y) / (cos(t) * x + sin(t) * y)
    return t


def state(mu, o, t):
    mu, a, e = D(mu), D(o["a_km"]), D(o["e"])
    A = abs(a)
    n = (mu / (A * A * A)).sqrt()
    M = D(o["M0_deg"]) * PI / 180 + n * (D(t) - D(o["t0_days"])) * 86400
    i, Om, om = [D(o[k]) * PI / 180 for k in ("i_deg", "Omega_deg", "omega_deg")]
    cO, sO, ci, si, co, so = cos(Om), sin(Om), cos(i), sin(i), cos(om), sin(om)
    P = [cO * co - sO * so * ci, sO * co + cO * so * ci, so * si]
    Q = [-cO * so - sO * co * ci, -sO * so + cO * co * ci, co * si]
    if a > 0:
        E = M
        for _ in range(60):
            E = E - (E - e * sin(E) - M) / (1 - e * cos(E))
        x, y = a * (cos(E) - e), a * (1 - e * e).sqrt() * sin(E)
    else:
        import math
        H = D(math.asinh(float(M / e)))
        for _ in range(80):
            H = H - (e * sinh(H) - H - M) / (e * cosh(H) - 1)
        x, y = A * (e - cosh(H)), A * (e * e - 1).sqrt() * sinh(H)
    return [x * P[k] + y * Q[k] for k in range(3)]


def main():
    S = json.load(open(sys.argv[1]))
    R = json.load(open(sys.argv[2]))
    objs = {o["name"]: o for o in S["objects"]}
    mu = S["mu_km3_s2"]
    for q, ent in zip(S["ephemeris_queries"], R["ephemeris"]):
        r = state(mu, objs[q["object"]], q["t_days"])
        nr = sum(x * x for x in r).sqrt()
        d = sum((D(repr(ent["r_km"][k])) - r[k]) ** 2 for k in range(3)).sqrt() / nr
        print("ephemeris %-8s t=%-12s |r_report - r_exact| / |r| = %.2e" % (q["object"], q["t_days"], d))
    for k, (q, tr) in enumerate(zip(S["transfer_queries"], R["transfers"])):
        r1 = state(mu, objs[q["from"]], q["t1_days"])
        r2 = state(mu, objs[q["to"]], q["t2_days"])
        cr = [r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2], r1[0] * r2[1] - r1[1] * r2[0]]
        th = atan2(sum(x * x for x in cr).sqrt(), sum(a * b for a, b in zip(r1, r2)))
        if cr[2] < 0:
            th = 2 * PI - th
        thd = th * 180 / PI
        print("transfer %d %s->%s theta_exact %.15f report %.15f  error %.2e deg" % (
            k, q["from"], q["to"], thd, tr["theta_deg"], abs(thd - D(repr(tr["theta_deg"])))))


if __name__ == "__main__":
    main()
