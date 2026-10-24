# Reference B: method

`referee.py` checks a LAMBERT_SPEC report against its system file by methods that share nothing
with analytic Lambert solvers (no Izzo, no Gooding, no universal-variable iteration), and never
reads `solution/`, `refA/`, `tools/` or `controls/`.

```
python referee.py --system S.json --report R.json [--out verdict.json] [--quiet]   # exit 0 iff pass
python referee.py --solve --system S.json --output R.json                           # third opinion
sh run_set.sh SYSTEM_DIR REPORT_DIR OUT_DIR [PARALLEL]                              # a whole set
python tests/make_tests.py && python tests/run_tests.py [--oracle S.json R.json ...]
python tests/decimal_arbiter.py S.json R.json                                       # 40-digit arbiter
```

stdout (unless `--quiet`) is one line: `<id> pass=True|False` followed by the worst residual of each
kind, the runtime, the number of domain warnings and the first failure. The verdict JSON holds every
residual, per-solution diagnostics, `failures` and `domain_warnings`.

## Pass thresholds (the contract, LAMBERT_SPEC section 5)

| quantity | threshold |
| --- | --- |
| `r_km`, `v_km_s`, `v1_km_s`, `v2_km_s` | `|w - w_ref| <= 1e-9 |w_ref|` |
| `a_km`, `e`, `dv_km_s`, `T_min` | `1e-9` relative |
| `theta_deg` | `1e-9` deg absolute |
| counts, `N`, `branch`, order, `best`, schema | exact |

The referee is never stricter than the contract: the self-tests apply 0.3x-tolerance perturbations
that must pass, and 3x-tolerance perturbations that must fail.

## Checks

**Schema.** Section 4 keys, types, list lengths, echoed query fields, `N` range, branch labels,
ordering (N increasing, low before high), `best` in range, duplicate JSON keys.

**1. Ephemeris.** Object states come from a Kepler solver written from scratch in
`numpy.longdouble` (safeguarded Newton for `E - e sin E = M`, Newton for `e sinh H - H = M`,
`R_z(Omega) R_x(i) R_z(omega)`). The elapsed time is `(t - t0) * 86400` in longdouble, which is
exact for the given doubles. Checks:

- reported `r`, `v` against the longdouble state (the contract metric);
- elements recovered from the reported state (vis-viva `a`, eccentricity vector, orbit normal
  `W` from `h` (that is `i` and `Omega`), periapsis direction `P` (that is `omega`; skipped for
  `e < 1e-6`)) against the file;
- the time since periapsis implied by the reported state (true anomaly to `E` or `H` to mean
  anomaly, longdouble) against `M0 + n (t - t0)`, modulo the period for ellipses, reported as a
  fraction of the period (`eph_time_rel_period`).

Each recovered quantity is gated at the change that a `1e-9` relative error in `r` and in `v` can
produce (first order, central-difference Jacobian of the recovery), so these checks are exactly as
strict as the contract. The eccentricity is compared as a vector because `|e|` is not
differentiable at `e = 0` (circular objects occur).

**2. Lagrange-family completeness and T_min.** With `s`, `c` from `r1`, `r2` (`s - c` formed without
cancellation) the prograde N-revolution ellipses are parametrised by Lagrange's angle `alpha` in
`(0, 2 pi)`: `a = s / (2 sin^2(alpha/2))`, `sin(beta/2) = sqrt((s-c)/s) sin(alpha/2)`, `beta < 0`
when `theta > pi`, `sqrt(mu) T = a^1.5 (2 pi N + (alpha - sin alpha) - (beta - sin beta))`;
`alpha < pi` and `alpha > pi` are the two arcs of one `a`. For each `N = 1..n_max`: a 6001-point
scan, `minimize_scalar` (bounded, `xatol 1e-13`) around the grid minimum for `T_min(N)`, a count of
turning points (must be 1) and of crossings of `T` (refined minimum inserted, so `T` 1e-6 above
`T_min` is still seen), expected count 2 if `T > T_min(N)` else 0. `N = 0`: one root of the
monotone ellipse-parabola-hyperbola family (`u = alpha > 0`, parabola at `u = 0`, hyperbola
`u = -gamma` with `(sinh gamma - gamma) -/+ (sinh delta - delta)`). The semi-major axis of each
reported solution must match a Lagrange root to `1e-8` (cross-check, `a_vs_lagrange`).

**3. Solutions by integration.** From `r1` (own Kepler solver) and the reported `v1`, over
`T = (t2 - t1) * 86400`:

- longdouble Kustaanheimo-Stiefel integration (`u'' = (E/2) u`, `t' = |u|^2`, in-plane angle
  `phi' = |h| / |u|^2`) with a Gragg-Bulirsch-Stoer modified-midpoint extrapolation integrator
  (sequence 2..16), steps capped at 0.25 rad of oscillator phase, the end located by Newton on the
  last step length. This is the decisive propagator.
- its error estimate: a second KS run with 0.4 rad steps and the longdouble Kepler propagator;
  the spread, mapped to implied velocities (below), must stay below `1e-10` or the check is
  declared inconclusive (`integ_est`).
- scipy DOP853 (rtol `1e-13`, atol `1e-15`, normalised units) in physical time and in Sundman
  time (`dt/ds = r`, event at `t = T`, re-integrated to the event so the end point is a step end).
  Reported as `dop853_err`; gated only at `1e-6` as a guard against a referee bug.
- the miss `r_end - r2` is converted into the departure-velocity error it implies,
  `dv1 = -Phi_rv^-1 (r_end - r2)`, and the true arrival velocity `v_end + Phi_vv dv1`, with `Phi` from
  central differences of the longdouble Kepler propagator. Reported `v1` and `v2` are compared
  with these (contract metric). The raw end miss is reported (`end_miss`), not gated: a `v1` within
  `1e-9` can miss `r2` by far more after several revolutions (`cond(Phi_rv)` reaches 9e3 here).
- `a`, `e` from `(r1, v1_true)`, `dv = |v1_true - v_A| + |v_B - v2_true|`; `best` = argmin `dv`.
- revolutions: `floor(phi_total / 2 pi)` from KS and from DOP853 must equal `N`; `phi_total mod 360`
  must equal `theta` to `1e-2` deg; prograde: `(r1 x v1)_z > 0`.
- labels: within each `N`, `low` must have the smaller integrated `a`.

**4. theta** from `atan2(|r1 x r2|, r1 . r2)` in longdouble, `360 - ` that when `(r1 x r2)_z < 0`.

**Domain warnings** (not failures): the section 2 table and guarantees 1-5, evaluated with refB's
values (periods since epoch for every queried time, including transfer `t1`, `t2`).

## Why longdouble KS rather than DOP853 alone

- `numpy.longdouble ** k` is only double-accurate on this platform (`a**3` off by 2e-17 relative),
  which put `n` and therefore `M` off by 1e-17 relative and positions 2000+ periods out off by up
  to 1e-12. All powers are written as products; the Kepler states now agree with a 40-digit decimal
  solution (`tests/decimal_arbiter.py`) to <= 1.6e-17, and theta to <= 5e-12 deg.
- For near-radial arcs (`held_11` transfer 2, `e = 0.9986`, arrival near periapsis) DOP853 at
  rtol 1e-13 misses the Kepler end state by 2e-7 (Cartesian) and 9e-7 (Sundman); the timing error
  maps into an implied-`v2` error of 1.1e-9, above the tolerance. The longdouble KS run agrees with
  the longdouble Kepler propagator to 1.7e-14 in implied velocity on all 291 solutions.

## Measured precision (28 current systems, oracle reports and refB `--solve` reports)

- integration error estimate (implied velocity): <= 4.0e-14; KS vs Kepler-LD <= 1.7e-14.
- DOP853 vs KS (implied velocity): Cartesian <= 2.3e-10, Sundman <= 1.1e-9.
- T_min: Lagrange scan vs the empty-focus solver (different parametrisation, longdouble Kepler
  times) <= 6e-16 relative; reported `a` vs Lagrange roots <= 2.9e-14.
- refB `--solve` reports refereed by refB: all 28 pass, worst v1 2.6e-16, v2 4.1e-14, theta 2.7e-14 deg.
- runtime: 0.1 to 32 s per system single-threaded (`held_16`, 4 transfers with 7-9 solutions).

## Tests (`tests/`)

- `refB_hohmann_like.json`: circular coplanar orbits of 20000 and 40000 km, `mu = 398600`.
  Transfer 0 is built by hand: an ellipse with periapsis at the inner object (tangential
  departure) through r = 40000 km at true anomaly 170 deg, `e = (R2 - R1)/(R1 - R2 cos 170)`,
  `T` from Kepler's equation, closed-form `v1`, `v2`, `dv`; `T_min(1)` bounded by
  `P(a_m) < T_min(1) < sqrt(a_m^3/mu)(3 pi - (beta_m - sin beta_m))`; `T < P(a_m)`, so no N = 1
  arc. Transfer 1 (n_max 3, theta 201 deg) has 7 solutions with the best on N = 3 low.
- `refB_hyperbolic_long_way.json`: a hyperbolic visitor (`a = -3e8`, `e = 1.6`, `i = 12`) at
  periapsis (closed-form state) to a circular planet placed at 250 deg: theta = 250 exactly.
  Also an N = 0 hyperbolic arc with theta = 276 deg and a 3-solution transfer to an inclined rock.
- `hand_values.json` (from `make_tests.py`, plain `math`): the solver must match them (vectors
  1e-12 / 1e-10), and the referee must pass the solver's report.
- `run_tests.py`: on both constructed reports and on any `--oracle` pair: 3e-9 corruptions of v1,
  v2, ephemeris r, a, e, dv, theta (deg), T_min; dropped solution; moved best; swapped labels
  (values swapped, and labels swapped in place). All must fail. The continuous ones at 3e-10
  must pass. Command-line exit codes are checked. Last run: all passed (held_04, held_08 included).

## Ambiguities in LAMBERT_SPEC

1. "Every queried time lies within `2000` orbital periods of the object's epoch for an ellipse
   (`|t - t0| <= 2000 P`)": it is not stated whether transfer `t1_days`/`t2_days` are queried times.
   17 of the 28 current systems put a transfer endpoint 2161 to 1.9 million periods from the epoch.
2. "times in days from the system's reference epoch (`86400` s per day)" together with
   "`M = n (t - t_p)`": the spec does not say that the elapsed time is the exact
   `(t - t0) * 86400` of the given doubles. Forming `t * 86400 - t0 * 86400` in double (what the
   current oracle reports reproduce to 1e-15) moves `M` by up to `n * 1.2e-7 s` at |t| ~ 8000 d,
   which is 2.5e-9 to 6.5e-9 deg of theta for fast orbits (P ~ 700 s) even inside 2000 periods.
