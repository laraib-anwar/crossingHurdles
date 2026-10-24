# lambert-transfer-audit

Compute exact two-body ephemerides of objects on elliptic and hyperbolic orbits and the complete
set of prograde Lambert transfer solutions between them: every zero- and multi-revolution arc up
to a requested revolution count, the minimum time of flight of each revolution family, the
impulsive cost of each arc and the cheapest one. Then diagnose a legacy mission-design script by
executable witnesses.

| | |
| --- | --- |
| Domain | physical-sciences / astronomy / astrodynamics |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Lambert's problem is the kernel of mission design: every porkchop plot, every gravity-assist
sequence and every rendezvous schedule is a grid of Lambert solutions. The zero-revolution
short-way case is in every textbook; the complete problem (both directions, every revolution
count, both branches, the minimum time of flight of each family, hyperbolic arcs) is where
production tools differ from student code. All quantities are exact, so every answer has a
definite value. The spec states the model and the definitions and no method.

What a competent solver gets right: a Hohmann-like circular-to-circular transfer (`dev` checks
reproduce the textbook Hohmann cost to 2e-14), the zero-revolution arc for a short flight, states on
near-circular orbits. Where the difficulty is, each exercised by several of the 28 systems:

1. **Prograde arcs through more than 180 degrees.** The spec fixes the direction by `h_z > 0`,
   so when `(r1 x r2)_z < 0` the transfer angle is above 180 degrees and the short-way solution
   is on the wrong plane. The `shortway` control (and the legacy script) fails every such query.
2. **Complete multi-revolution families.** For each `N >= 1` there are two solutions or none,
   depending on `T` against `T_min(N)`; queries with `n_max` up to 4 have 1, 3, 5, 7 or 9
   solutions, and families can be empty (`held_06`). Reporting the zero-revolution arc only
   (`zero_rev`) or one branch per family (`one_branch`) fails every multi-revolution query.
3. **The minimum time of flight of each family**, graded to `1e-9` relative: an exact root of
   `dT/dx = 0` (or the minimum of the family's time-of-flight curve), not the `N + 1/2` Hohmann
   periods of the legacy script (`tmin_hohmann` control, errors of a few percent).
4. **Which solution is cheapest.** With the objects' own velocities at departure and arrival,
   the best arc is often on a multi-revolution branch, sometimes the high one (`model_06`,
   `held_10`, `held_11`, `held_21`); any missing or mislabelled solution changes `best`.
5. **Kepler's equation done properly.** Eccentricities up to 0.95, epochs up to 2000 periods
   away (the mean anomaly must be wrapped before solving), hyperbolic objects with `|M|` up to
   50; fixed-point iteration with a fixed sweep count (`fixedpoint` control) is wrong at the
   `1e-8` to `4e-5` level on eccentric and far-epoch states. Elapsed times must also be formed
   exactly (`86400 (t - t0)`, not `86400 t - 86400 t0`): the rounded form costs about `1e-10` of
   phase on orbits with periods of minutes, which the reference referee detected in a first draft
   of the oracle.
6. **Precision.** Velocities to `1e-9` relative on hyperbolic zero-revolution arcs, near-parabolic
   transfers and long multi-revolution arcs: the time-of-flight function needs a series near
   `x = 1`, and the roots need a high-order iteration with a final polish.
7. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `porkchop.py` is a plausible mission-analysis script: fixed-point Kepler,
short-way universal-variable Lambert by bisection, multi-revolution "solutions" from a resonant
orbit estimate, `T_min(N)` as `N + 1/2` Hohmann periods.

## Reference solution

`solution/lambert.py`:

- **Ephemerides**: Kepler's equation in the eccentric or hyperbolic anomaly, mean anomaly wrapped
  first, Newton-Halley from a safe start with a final Newton clean-up; perifocal-to-inertial
  rotation.
- **Lambert**: Izzo's (2015) formulation in the Lancaster-Blanchard variable `x` with
  `lambda = +-sqrt(1 - c/s)` (sign from the prograde transfer angle), the dimensionless time of
  flight by the Lagrange form away from `x = 1` and Battin's hypergeometric series near it,
  Householder (third-order) iterations from Izzo's initial guesses for `N = 0` and both
  branches of each `N >= 1`, `T_min(N)` from Halley on `dT/dx = 0`, velocities from the
  radial/tangential decomposition, `a` from the vis-viva of the departure state and `e` from the
  eccentricity vector. Branches are named by `a` after solving.
- **Checks in the dev pipeline**: every solution is re-propagated from `(r1, v1)` over `T` with
  the Kepler solver and by numerical integration, and the problem's conditioning (relative change
  of `v1` per relative change of `T` or `r2`) is at most 11 on every arc of the 28 systems.

`solution/diagnose.py` runs the legacy script and the program on the shipped systems and writes
witnesses for the five diagnosis quantities; nothing is stored.

## Verification

Every expected value in `tests/expected.json` comes from Reference A (`tests/reference/reference.py`),
an independent implementation built without access to the oracle: universal-variable Kepler
propagation from the periapsis state with Lagrange coefficients and exact (decimal) elapsed
times, and Lambert in Vallado's universal variable `z`, every solution a bracketed root of
`TOF(z) - T` on the monotone halves of each revolution interval, `T_min(N)` from the analytic
derivative, velocities from radial/transverse components. Reference B (`refB/referee.py` in the
dev folder) shares nothing with analytic Lambert solvers: it recovers elements and time since
periapsis from each reported state in long double, integrates every reported arc in regularised
(Kustaanheimo-Stiefel) form in long double and converts the end-point miss into the implied
velocity error, counts revolutions and checks the prograde sense, and rebuilds every family
from a 6001-point scan of Lagrange's time equation (turning points, `T_min(N)`, crossings).

| Check | Result |
| --- | --- |
| Oracle vs Reference A, 28 systems | every solution count, label and `best` equal; worst ephemeris position 5.0e-12 and velocity 3.6e-12, transfer velocities 1.5e-13, `a` 1.1e-12, `e` 3.7e-14, `dv` 9.2e-14, `T_min` 4.6e-15 relative, theta 2.2e-12 degrees |
| Reference A against 60- to 80-digit decimal solutions (own tests, 28 systems, 600 random arcs) | velocities 1.8e-14, ephemerides 1.8e-15, `T_min` 9.8e-16 |
| Reference B referee, 28 systems | 28 pass with no domain warning: ephemeris states 7.7e-15, time since periapsis 9.7e-15 of a period, transfer velocities about 3e-15 after the integration correction (integration error estimate 2e-16), theta 1.7e-13 degrees, `T_min` 1.2e-15; negative tests (3e-9 perturbations, a dropped solution, swapped labels, moved `best`) all fail |
| Totals graded | 152 ephemeris states, 124 transfers with 348 solutions (20 hyperbolic arcs); 78 queries with 1 solution, 15 with 3, 10 with 5, 7 with 7, 14 with 9; 52 transfers through more than 180 degrees; best arc on a multi-revolution branch in 44 transfers (21 high, 23 low) |
| Oracle in the environment image (`solve.sh`) | base case + diagnosis in 6 s; witnesses: `solution_count` (model_04), `t_min`, `theta`, `best_dv` (model_01) |
| Verifier on the oracle artifacts | 30 passed, reward 1, 20 s; fresh calls 0.3 to 1.0 s |
| Verifier on empty `/root/results` | 30 failed, reward 0 |
| Verifier with a FIFO as `lambert.py` | 30 failed, reward 0 |
| Domain | all 28 systems pass the verifier's `validate_system`; guarantees 1 to 5 screened by the generator and re-checked by the referee |

### Controls (wrong methods, graded with the verifier's comparison against Reference A)

| Control | Shortcut | Fails |
| --- | --- | --- |
| `legacy` | the shipped script | 28 / 28 |
| `tmin_hohmann` | `T_min(N)` as `N + 1/2` Hohmann periods | 27 / 28 (error 4.5e-2 to 1.05 relative) |
| `shortway` | transfer angle always below 180 degrees | 24 / 28 (every system with a long-way transfer; theta off by 61 to 318 degrees) |
| `zero_rev` | zero-revolution arc only | 22 / 28 (every system with a non-empty family) |
| `one_branch` | low branch only | 22 / 28 |
| `fixedpoint` | Kepler by 50 fixed-point sweeps | 8 / 28 (every system with an eccentric or far-epoch state; error 8.7e-9 to 4.2e-5) |

### Tolerances

| Quantity | Tolerance | Method spread (oracle vs Reference A / referee) | Nearest wrong answer |
| --- | --- | --- | --- |
| state and velocity vectors | 1e-9 relative (norm) | 5.0e-12 / 7.7e-15 | 8.7e-9 (`fixedpoint`) |
| `a`, `e`, `dv`, `T_min` | 1e-9 relative | 1.1e-12 / 1.2e-15 | 4.5e-2 (`tmin_hohmann`) |
| `theta_deg` | 1e-9 degrees | 2.2e-12 / 1.7e-13 | 61 degrees (`shortway`) |

The tolerances sit more than two orders of magnitude above the method spread; the problem's
conditioning is at most 11 on every graded arc, so any correct double-precision method lands well
inside them, while the closest wrong method (a fixed-point Kepler solver on mildly eccentric
orbits) is an order of magnitude outside.

### Coverage of the 28 systems

| System | mu (km^3/s^2) | objects | ephemeris | solutions per transfer | long-way transfers | largest N of a best arc | structure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `held_01` | 3.986e+05 | 4 (0 hyp.) | 6 | 1, 1 | 1 | 0 | zero-revolution queries only |
| `held_02` | 2.405e+04 | 5 (1 hyp.) | 8 | 1, 1, 5, 1, 1, 1 | 2 | 2 | hyperbolic object and hyperbolic arc |
| `held_03` | 8.443e+08 | 4 (0 hyp.) | 5 | 1, 1 | 1 | 0 | short flights: hyperbolic transfer arcs |
| `held_04` | 1.725e+09 | 4 (1 hyp.) | 8 | 1, 5, 1, 7, 1, 1 | 1 | 3 | long flights, five or more solutions |
| `held_05` | 1.327e+11 | 5 (0 hyp.) | 8 | 9, 9, 9, 9, 9 | 2 | 4 | nine solutions |
| `held_06` | 1.005e+08 | 6 (0 hyp.) | 4 | 1, 1, 1, 3, 5 | 2 | 2 | n_max above 0 with an empty family |
| `held_07` | 1.387e+09 | 2 (0 hyp.) | 4 | 1, 3, 1, 1, 1 | 1 | 1 | retrograde object orbits |
| `held_08` | 1.327e+11 | 4 (0 hyp.) | 7 | 1, 1, 1, 1 | 2 | 0 | highly eccentric orbits |
| `held_09` | 3.986e+05 | 4 (0 hyp.) | 6 | 5, 1, 3, 9, 1, 1 | 2 | 4 | epochs thousands of periods away |
| `held_10` | 4.283e+04 | 5 (0 hyp.) | 3 | 1, 1, 3, 1, 1, 1 | 3 | 1 | long way and multi-revolution best |
| `held_11` | 1.327e+11 | 4 (0 hyp.) | 6 | 5, 1, 1, 1, 1, 3 | 0 | 2 | best solution on a high branch |
| `held_12` | 1.327e+11 | 2 (0 hyp.) | 2 | 5, 1, 1, 1, 7, 5 | 3 | 3 | heliocentric system |
| `held_13` | 1.327e+11 | 3 (0 hyp.) | 6 | 1, 1, 1, 3, 1, 1 | 5 | 1 | coplanar orbits |
| `held_14` | 7.987e+06 | 6 (0 hyp.) | 8 | 3, 1, 1, 3, 5, 3 | 3 | 1 | counts 1, 3 and 5 in one system |
| `held_15` | 1.214e+06 | 2 (1 hyp.) | 2 | 1, 1, 1 | 2 | 0 | hyperbolic object, long way |
| `held_16` | 4.283e+04 | 5 (0 hyp.) | 8 | 7, 9, 9, 9, 9, 9 | 4 | 4 | seven solutions |
| `held_17` | 9.273e+06 | 4 (0 hyp.) | 7 | 1, 1, 1, 9 | 0 | 4 | near-circular, five solutions |
| `held_18` | 3.986e+05 | 2 (0 hyp.) | 6 | 1, 5, 3, 1, 3, 1 | 2 | 1 | eccentric orbits, long way |
| `held_19` | 6.432e+04 | 4 (0 hyp.) | 3 | 1, 1, 7 | 1 | 3 | far epochs with multi-revolution transfers |
| `held_20` | 2.157e+05 | 3 (0 hyp.) | 2 | 1, 1, 1 | 2 | 0 | short flights |
| `held_21` | 1.327e+11 | 2 (0 hyp.) | 6 | 1, 7, 7, 7 | 2 | 3 | long flights with multi-revolution best |
| `held_22` | 1.327e+11 | 6 (1 hyp.) | 4 | 3, 1, 1, 1, 1 | 2 | 1 | mixed system with a hyperbolic object |
| `model_01` | 4.283e+04 | 6 (0 hyp.) | 7 | 3, 1, 1, 1, 1 | 3 | 1 | near-circular orbits, a multi-revolution family (base case) |
| `model_02` | 1.267e+08 | 3 (1 hyp.) | 5 | 1, 1 | 1 | 0 | a hyperbolic object |
| `model_03` | 1.267e+08 | 6 (0 hyp.) | 7 | 1, 1, 5 | 2 | 2 | transfer through more than 180 degrees |
| `model_04` | 1.917e+07 | 3 (0 hyp.) | 8 | 9, 9 | 0 | 4 | seven or more solutions in one query |
| `model_05` | 4.283e+04 | 5 (0 hyp.) | 4 | 1, 3 | 0 | 1 | eccentric orbits, epochs hundreds of periods away |
| `model_06` | 1.327e+11 | 2 (0 hyp.) | 2 | 1, 3, 1, 1, 1 | 3 | 1 | best solution on a multi-revolution branch |

### Reproduction (dev folder `turing/tbScience/lambert-transfer-audit-dev`)

`tools/gen_systems.py` (28-slot plan, guarantee screening including the verifier's domain check),
`tools/agree.py`, `tools/check.py`, `controls/controls.py`, `tools/controls_study.py`,
`tools/docker_chain.sh`, `refA/` (Reference A with METHOD.md and tests), `refB/` (referee with
METHOD.md, tests and `run_set.sh`), `evidence/` (Docker logs, CTRF, rewards), `tools/build_zip.py`.
