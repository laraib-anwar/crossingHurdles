# Reference A: method, independence, measured precision

`reference.py` is a single-file answer key for LAMBERT_SPEC.md:
`python reference.py --system <system.json> --output <report.json>`. It needs Python 3.11, NumPy and
SciPy (only `scipy.optimize.brentq`). Every run is deterministic. Every number is checked for finiteness
before the file is written (`allow_nan=False`). It writes exactly the keys of section 4 in the order
given there, and it copies the query fields back as parsed.

## Independence

The oracle propagates with eccentric/hyperbolic anomaly iterations and solves Lambert in Izzo's x
variable with Householder steps. Reference A forms no eccentric or hyperbolic anomaly and no
Lancaster-Blanchard variable. While writing it I did not read the task `solution/` folder, `refB/`,
`fin/`, `out_oracle/`, `out_controls/` or `tools/`.

## Time arithmetic

Day values are turned into `Decimal` exactly, because `Decimal(float)` is exact. Then
`dt = 86400 (t - t0) + M0/n` is formed at 50 significant digits. The mean motion `n` and the period `P`
are also computed in Decimal. For an ellipse, `dt` is reduced into `[-P/2, P/2)` in Decimal, so the
time since periapsis is correct to about 1e-16 relative even 2000 periods from the epoch. The time of
flight is `T = 86400 (t2 - t1)`, formed the same way from the exact difference and rounded only once.
This matches the coordinator's clarification on exact elapsed times.

## Ephemerides: universal variable

The periapsis state is set directly from the elements in the perifocal frame:
`r_p = |a| |1 - e|` and `v_p = sqrt(mu (1 + e) / r_p)`. It is propagated by `dt` with the
universal-variable Kepler equation

    sqrt(mu) dt = chi^3 S(z) + sigma0 chi^2 C(z) + r0 chi (1 - z S(z)),   z = chi^2 / a,

with `alpha = 1/a` taken exactly from the element. The equation is solved for `chi` by `brentq` on a
bracket where it is monotone, since `dF/dchi = -r`:

- For an ellipse the bracket is `+-2 pi sqrt(a)`, which is valid after the reduction to half a period.
- For a hyperbola the bracket is doubled outward from `sqrt(|a|)`.

The root is then polished with guarded Newton steps. The Stumpff functions are summed as series for
`|z| < 1` and use half-angle forms otherwise: `C = 2 sin^2(x/2) / z` and `S = (x - sin x) / x^3`, with
`x - sin x` and `sinh x - x` summed as series when `x < 1`. The Lagrange coefficients are formed
without cancellation, for example `g = (sigma0 chi^2 C + r0 chi (1 - zS)) / sqrt(mu)` rather than
`dt - chi^3 S / sqrt(mu)`. Finally the state is rotated by `R_z(Omega) R_x(i) R_z(omega)`.

## Lambert: universal variable z (Bate-Mueller-White / Vallado)

The transfer angle comes from `atan2(|r1 x r2|, r1 . r2)`, and becomes `2 pi - theta` when
`(r1 x r2)_z < 0`. Then

    A = sqrt(2 r1 r2) cos(theta/2)
    y(z) = r1 + r2 + A (z S - 1) / sqrt(C)
    sqrt(mu) TOF(z) = (y/C)^(3/2) S + A sqrt(y)

The N-revolution arcs fill `z in ((2 pi N)^2, (2 pi (N+1))^2)`. The zero-revolution arc fills
`z < (2 pi)^2` down to the hyperbolic limit, which is `y = 0` when `A > 0` and `z -> -inf` when
`A < 0`.

### Half-angle evaluation

These are exact identities, not approximations. On the N-th elliptic interval, write
`z = (2 pi N + 2u)^2` with `u in (0, pi)`. Then

    sqrt C = sqrt2 sin u / sqrt z,     (zS - 1)/sqrt C = -sqrt2 cos u,
    y = y0 + 2 sqrt2 |A| sin^2(u/2)   (A > 0),   y = y0 + 2 sqrt2 |A| cos^2(u/2)   (A < 0),
    S / C^(3/2) = (2u + 2 pi N - sin 2u) / (2 sqrt2 sin^3 u),
    y0 = |r2 - r1|^2 / (r1 + r2 + sqrt2 |A|)   (= r1 + r2 - sqrt2 |A| without cancellation).

So on every elliptic interval y lies in `[y0, r1 + r2 + sqrt2 |A|]` and is positive. y can only reach 0
on the hyperbolic side, and only when `A > 0`. The end `u -> pi` is evaluated in the variable
`eps = pi - u`, so that `sin u = sin eps` keeps full relative precision.

On the hyperbolic side, write `z = -w^2`. Then `y = y0 - 2 sqrt2 A sinh^2(w/4)` when `A > 0`, and
`y = r1 + r2 + sqrt2 |A| + 2 sqrt2 |A| sinh^2(w/4)` when `A < 0`. The kernel is
`S/C^(3/2) = (sinh w - w) / (2 sqrt2 sinh^3(w/2))`. When `A < 0`, `y K - |A|` is rewritten as
`(r1+r2) K + |A| L(w)` with `L = (2 sinh(w/2) - w cosh(w/2)) / (2 sinh^3(w/2))`, so the large terms do
not cancel. When `A > 0` and the root has `y < y0/2`, the solve runs in y itself.

### Root finding

- **N = 0.** TOF is monotone in z, so there is exactly one bracketed root. If T is above the
  parabolic TOF, the root is elliptic and is solved in u, or in eps for `u > pi/2`. Otherwise it is
  hyperbolic and is solved in w, or in y.
- **N >= 1.** TOF tends to `+inf` at both ends of the interval and has one interior minimum. The
  minimiser is the bracketed `brentq` root of the analytic `dTOF/du`, which runs from `-inf` to
  `+inf`. `T_min(N)` is TOF at that minimiser; its error is second order in the minimiser's error.
  When `T > T_min(N)`, each monotone half has one bracketed root. Each bracket runs from the minimiser
  to a point halved toward the end until `TOF > T`, and it crosses `u = pi/2` when needed.

Every root is polished with guarded Newton steps, using the analytic derivative for elliptic arcs
and a central difference for hyperbolic ones.

### Velocities

Velocities are not taken from `v1 = (r2 - f r1)/g`. Near `theta = pi` that form subtracts nearly
equal numbers: on the dev Hohmann case it was wrong by 7e-9. Instead, the f, g relations with
`y = r1 + r2 - sqrt2 A cosU` are resolved into radial and transverse parts, with `cosU = cos u` or
`cosh(w/2)` and `k = sqrt(mu / (2y))`:

    v1 = 2k (sqrt(r2/r1) cos(theta/2) - cosU) r1^ + 2k sqrt(r2/r1) sin(theta/2) (h^ x r1^)
    v2 = 2k (cosU - sqrt(r1/r2) cos(theta/2)) r2^ + 2k sqrt(r1/r2) sin(theta/2) (h^ x r2^)

`h^` is the prograde normal, `+-(r1 x r2)/|r1 x r2|` chosen so that `h_z > 0`.

### Reported quantities

- **a:** `chi^2 / z`, which is `y / (2 sin^2 u)` for an elliptic arc and `-y / (2 sinh^2(w/2))` for a
  hyperbolic one. The vis-viva value from `v1` agrees to at most 1.8e-13 and is kept as a
  diagnostic. Both orderings agree on every case checked.
- **e:** the length of the eccentricity vector.
- **dv:** `|v1 - v_A| + |v_B - v2|`.
- **branch:** `"low"` is the smaller `a` of each pair. `best` is the argmin of dv.

## Measured precision

The errors below are measured against independent 60 to 80 digit computations; the harness is in
`tests/harness/`.

The 60-digit references are:

- Ephemerides solve Kepler's equation in E or H, using Decimal sin, cos and exp.
- Lambert solutions use Newton shooting. A Decimal universal-variable propagator with bracketed
  Newton steps is driven from each of my `v1`, until `r(T) = r2` to 1e-40.
- `T_min` is TOF evaluated in Decimal at my minimiser.

Two further checks are independent of my closed forms:

- A dense double-precision scan of the plain Vallado `TOF(z)` (40 000 points per interval, with
  golden-section refinement) gives `T_min` and the solution counts.
- The slope of TOF changes sign exactly once in every N >= 1 interval scanned.

| quantity (relative) | dev + 8 own tests + 28 current gen systems | random stress (7 780 in-domain solutions, 600 shot) |
| --- | --- | --- |
| ephemeris r, v | 1.8e-15 | (via endpoint states) |
| v1, v2 | 1.8e-14 | 1.1e-14 |
| a | 7.1e-15 | - |
| e | 1.6e-14 | - |
| dv | 9.1e-15 | - |
| T_min vs Decimal TOF at minimiser | 9.8e-16 | - |
| T_min vs independent dense scan | 3.9e-12 (scan-limited) | agrees, 0 mismatches |
| solution counts vs dense scan | all equal | all equal |

- **Hohmann.** On `dev_01` and `tests/systems/t1_hohmann_textbook`, the first transfer's dv is
  `3.770727233304179` and `3.770727233304142`. The textbook value is `3.7707272333041297`, a
  difference of 1.3e-14 and 3e-15. These transfers arrive 1.9 ms and 0.9 ms after the Hohmann time;
  the exact 60-digit answers agree with mine to better than 1e-14.
- **Vallado Example 7-5.** `v0 = (2.0589134, 2.9159644)` and `v = (-3.4515648, 0.9103142)` km/s.
  The book gives `(2.058913, 2.915965)` and `(-3.451565, 0.910315)`; the 1e-6 differences come from
  rebuilding the book's r vectors from circular-orbit elements, which gives theta = 40.0000012 degrees.
- **Re-propagation.** Each `(r1, v1)` is propagated for T and compared with r2. Over the
  gen/dev/test systems the double-precision miss is at most 3.2e-11, and the 60-digit miss of the
  same `v1` is at most 3.7e-11. These cases are conditioning-limited: e = 0.9986 arcs whose
  `|dr2/dv1| |v1|/|r2|` is about 6.5e4. The 60-digit shooting shows the velocities themselves are
  good to 1e-14. In random stress, long hyperbolic swing-bys (`r/|a|` around 1e5) miss by up to 5e-5
  in double. That loss is in my general-state double propagator, which is used only for this check:
  the same `v1` in 60 digits lands to 9e-12 and the shooting confirms `v1` to 7e-16. Ephemerides
  start at periapsis, where `sigma0 = 0`, so they are not affected.
- **Energy and angular momentum.** For ephemeris states they match `-mu/2a` and
  `sqrt(mu |a (1 - e^2)|)` to 4e-15 and 2e-14.
- **Runtime.** At most 0.03 s of compute and 0.8 s wall clock per system, including the
  NumPy/SciPy import. There were no exceptions and no non-finite output in 4 500 random systems:
  about 10 300 transfers, including 4 750 outside guarantee 5. In the 5 612 in-domain transfers the
  solution count always equals `1 + 2 #{N : T > T_min(N)}`, and `T_min` agrees with an independent
  4 000-point scan.
- **Determinism.** Two runs produce byte-identical outputs.

## Why every solution and the true minimum are found

- **N >= 1.** TOF is continuous on the open interval and tends to `+inf` at both ends, because
  `C -> 0` while `y >= y0 > 0`. If it has a single minimum, there are exactly 0 or 2 roots, each
  bracketed on a monotone half. The minimiser is bracketed by a sign change of the analytic
  derivative. The single minimum was confirmed on every scanned interval: one slope change in 40 000
  points.
- **N = 0.** TOF increases monotonically from 0 (A > 0) or from the `z -> -inf` limit (A < 0) to
  `+inf` at `z = (2 pi)^2`, so there is exactly one bracketed root.
