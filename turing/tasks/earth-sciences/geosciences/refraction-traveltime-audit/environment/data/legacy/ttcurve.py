#!/usr/bin/env python3
"""ttcurve.py - refraction survey traveltime predictor (field processing group, rev 5).

Same command line and report layout as the new program:

    python ttcurve.py --model <model.json> --output <report.json>

Method (unchanged since rev 2). Each layer is represented by its mean velocity (top plus half the
gradient times the thickness; the half-space by its top velocity), so the model becomes a stack
of constant-velocity layers and the classical refraction formulas apply: the direct wave, one
head wave along every interface below which the velocity increases, and the reflection from
every interface for angles up to the critical angle. The first-arrival curve is the lower
envelope of the direct and head-wave lines, as used for picking.
"""
import argparse
import json
import math


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.model, encoding="utf-8") as fh:
        m = json.load(fh)
    L = m["layers"]
    v, h = [], []
    for k, l in enumerate(L):
        if l["thickness_km"] is None:
            v.append(l["v_top_km_s"]); h.append(None)
        else:
            v.append(l["v_top_km_s"] + 0.5 * l["gradient_per_s"] * l["thickness_km"]); h.append(l["thickness_km"])

    def one_way(p, upto):
        X = T = 0.0
        for j in range(upto):
            e = math.sqrt(1.0 - (p * v[j]) ** 2)
            X += h[j] * p * v[j] / e
            T += h[j] / (v[j] * e)
        return X, T

    lines = [("direct", 0, 1.0 / v[0], 0.0, 0.0)]       # (kind, index, p, X_start, intercept)
    for i in range(1, len(L)):
        if v[i] > v[i - 1] and all(v[i] > v[j] for j in range(i)):
            p = 1.0 / v[i]
            Xc, Tc = one_way(p, i)
            lines.append(("head", i, p, 2 * Xc, 2 * Tc - p * 2 * Xc))

    def reflections(x):
        out = []
        for i in range(1, len(L)):
            pmax = 1.0 / max(v[:i])
            if v[i] > max(v[:i]):
                pmax = min(pmax, 1.0 / v[i])            # up to the critical angle
            f = lambda p: 2 * one_way(p, i)[0] - x
            lo, hi = 0.0, pmax * (1 - 1e-12)
            if f(hi) < 0:
                continue
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
            p = 0.5 * (lo + hi)
            out.append(dict(kind="reflection", index=i, p_s_km=p, t_s=2 * one_way(p, i)[1]))
        return out

    arrivals = []
    for x in m["offsets_km"]:
        rays = [dict(kind=k, index=i, p_s_km=p, t_s=p * x + tau) for k, i, p, xs, tau in lines if x >= xs]
        rays += reflections(x)
        rays.sort(key=lambda r: r["t_s"])
        arrivals.append(dict(x_km=x, rays=rays))
    # lower envelope of the direct and head lines
    xmax = m["x_max_km"]
    first, x = [], 0.0
    cur = lines[0]
    while True:
        nxt, xn = None, xmax
        for ln in lines:
            if ln is cur or ln[2] >= cur[2]:
                continue
            xc = (ln[4] - cur[4]) / (cur[2] - ln[2])
            xc = max(xc, ln[3])
            if x < xc < xn:
                nxt, xn = ln, xc
        first.append(dict(kind=cur[0], index=cur[1], x_start_km=x, x_end_km=xn))
        if nxt is None:
            break
        cur, x = nxt, xn
    rep = dict(model_id=m["model_id"], arrivals=arrivals, caustics=[], first_arrival=first)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
