# LAMBERT_SPEC: Keplerian ephemerides and complete multi-revolution Lambert transfers

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Dynamics.** Point masses in the gravity field of one central body with gravitational parameter
`mu` (km^3/s^2); no perturbations. Positions are in km, velocities in km/s, times in days from
the system's reference epoch (`86400` s per day), in a fixed inertial right-handed frame
`(x, y, z)`. Every elapsed time (`t - t0` for a state, `t2 - t1` for a time of flight) is
`86400` times the exact difference of the two given numbers (the file's values as binary
doubles), converted to seconds after the subtraction.

**Objects.** Each object is given by its classical orbital elements at its own epoch `t0`:
semi-major axis `a` (km; positive for an ellipse, negative for a hyperbola), eccentricity `e`
(`0 <= e < 1` or `e > 1`; parabolas do not occur), inclination `i`, longitude of the ascending
node `Omega`, argument of periapsis `omega` (degrees) and the mean anomaly at epoch `M0`
(degrees; for a hyperbola the hyperbolic mean anomaly `M = n (t - t_p)` with `n = sqrt(mu /
|a|^3)`). The state `(r, v)` at any time follows from Kepler's equation (`M = E - e sin E` or
`M = e sinh H - H`) and the usual perifocal-to-inertial rotation `R_z(Omega) R_x(i) R_z(omega)`.

**Transfer.** A transfer query names a departure object `A` at time `t1` and an arrival object
`B` at time `t2 > t1`; `r1 = r_A(t1)`, `r2 = r_B(t2)`, time of flight `T = t2 - t1`. A
**solution** is a Keplerian arc from `r1` to `r2` in exactly time `T` that is **prograde**: its
orbital angular momentum `h = r1 x v1` has `h_z > 0`. The transfer angle `theta` in `(0, 2 pi)`
is then fixed by `r1`, `r2` and the prograde requirement: `theta < pi` when `(r1 x r2)_z > 0` and
`theta > pi` when `(r1 x r2)_z < 0`. A solution is characterised by its number of complete
revolutions `N >= 0` of the transfer orbit between departure and arrival (the true anomaly
advances by `theta + 2 pi N`). For `N = 0` exactly one solution exists for every `T > 0`. For
each `N >= 1` the time of flight over all prograde `N`-revolution arcs between `r1` and `r2` has
a minimum `T_min(N)` (`T_min` increases with `N`); for `T > T_min(N)` exactly two solutions
exist, for `T < T_min(N)` none, and `T = T_min(N)` does not occur in the domain. The two
`N`-revolution solutions are distinguished by their semi-major axis: **`"low"`** is the one with
the smaller `a`, **`"high"`** the one with the larger `a`. The query's `n_max` bounds `N`: every
solution with `0 <= N <= n_max` is reported.

**Quantities of a solution.** The departure velocity `v1` and arrival velocity `v2` of the
transfer arc (km/s), its semi-major axis `a` (km, positive for an ellipse, negative for a
hyperbola; only `N = 0` arcs can be hyperbolic) and eccentricity `e`, and the total impulsive
cost `dv = |v1 - v_A(t1)| + |v_B(t2) - v2|` (km/s), where `v_A(t1)` and `v_B(t2)` are the objects'
velocities. The **best** solution of a query is the one with the smallest `dv`.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| `mu` | `1e4` to `2e11` km^3/s^2 |
| objects | 2 to 6 |
| `a` (ellipse) | `1e4` to `1e9` km; (hyperbola) `-1e9` to `-1e4` km |
| `e` | `0` to `0.95` (ellipse), `1.05` to `4` (hyperbola) |
| `i` | `0` to `180` degrees; `Omega`, `omega`, `M0` in `[0, 360)` |
| `t0` and queried times | `-2e4` to `2e4` days |
| ephemeris queries | 2 to 8 (object, time) pairs |
| transfer queries | 2 to 6, each between two different objects, with `n_max` from `0` to `4` and `T` from `0.1` to `6000` days |

Every system in the domain satisfies these guarantees:

1. For every transfer query the transfer angle satisfies `1 <= theta <= 179` or `181 <= theta
   <= 359` degrees, `|(r1 x r2)_z| >= 1e-3 |r1 x r2|` (the side of the plane is never in
   doubt), `|r1|, |r2| >= 1e3` km, and `T` differs from every `T_min(N)` (`1 <= N <= n_max`) by
   at least `1e-6` relative.
2. For every transfer query the best solution is unique: its `dv` is smaller than every other
   solution's by at least `1e-6` relative; the two solutions of one `N` have semi-major axes
   that differ by at least `1e-6` relative.
3. Every queried time (of an ephemeris query, and `t1` and `t2` of a transfer query for its
   departure and arrival object) lies within `2000` orbital periods of the object's epoch for an
   ellipse (`|t - t0| <= 2000 P`); for a hyperbola `|M| <= 50` at that time.
4. Every object's periapsis radius `a (1 - e)` (ellipse) or `|a| (e - 1)` (hyperbola) is at
   least `1e3` km.
5. Every solution of every transfer query has a periapsis radius of at least `1e3` km, an
   eccentricity between `1e-3` and `20`, speeds `|v1|` and `|v2|` of at most `200` km/s, and
   `dv` of at least `1e-3 max(|v1|, |v2|)`.

## 3. System file

A JSON object with exactly these keys:

- `system_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `mu_km3_s2`: number.
- `objects`: list of 2 to 6 objects with exactly the keys `name` (string, 1 to 32 characters,
  letters, digits, underscore, hyphen, distinct), `t0_days`, `a_km`, `e`, `i_deg`, `Omega_deg`,
  `omega_deg`, `M0_deg` (numbers).
- `ephemeris_queries`: list of objects with exactly the keys `object` (a name) and `t_days`.
- `transfer_queries`: list of objects with exactly the keys `from` (a name), `t1_days`, `to` (a
  name different from `from`), `t2_days`, `n_max` (integer).

## 4. Report file

A JSON object with exactly these keys and no others. Vectors are lists of exactly three finite
JSON numbers; numbers are finite JSON numbers at full double precision.

- `system_id`: the system's id, exactly.
- `ephemeris`: one object per entry of `ephemeris_queries`, in order, each with exactly the keys
  `object` and `t_days` (as given), `r_km` (vector) and `v_km_s` (vector).
- `transfers`: one object per entry of `transfer_queries`, in order, each with exactly the keys
  `from`, `t1_days`, `to`, `t2_days`, `n_max` (as given), `theta_deg` (the transfer angle in
  degrees, in `(0, 360)`), `t_min_days` (list of `n_max` numbers: `T_min(1), ..., T_min(n_max)`;
  empty list when `n_max = 0`), `solutions` and `best`. `solutions` is the list of all solutions
  ordered by `N` increasing and, within one `N`, `"low"` before `"high"`, each an object with
  exactly the keys `N` (integer), `branch` (`"low"` or `"high"`; the `N = 0` solution has branch
  `"single"`), `v1_km_s`, `v2_km_s` (vectors), `a_km`, `e`, `dv_km_s`. `best` is the 0-based index
  of the best solution in `solutions`.

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that system:

1. The report meets section 4 exactly.
2. For every transfer the number of solutions, their `N` and `branch` labels and `best` equal
   the reference.
3. Every vector `w` (`r_km`, `v_km_s`, `v1_km_s`, `v2_km_s`) satisfies `|w - w_ref| <= 1e-9
   |w_ref|` (Euclidean norms); every `a_km`, `e`, `dv_km_s` and `T_min` is within `1e-9` relative
   of the reference (`e = 0` exactly does not occur); `theta_deg` is within `1e-9` degrees
   absolute.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/porkchop.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `system`: a complete system object meeting sections 2 and 3 (a shipped system or one you
  construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"position"`, `"solution_count"`, `"theta"`, `"best_dv"`,
  `"t_min"`.
- `index`: the 0-based index into `ephemeris_queries` (for `"position"`) or into
  `transfer_queries` (for the others).
- `legacy_value` and `correct_value`: for `"position"` the norm `|r_km|` of the reported
  position; for `"solution_count"` the number of solutions (integer); for `"theta"` the
  transfer angle in degrees; for `"best_dv"` the `dv_km_s` of the best solution; for `"t_min"`
  the value `T_min(1)` (the query must have `n_max >= 1`).

The verifier runs a pristine copy of the legacy script on the witness system and requires
`legacy_value` to match its report (integers exactly, numbers within `1e-9` relative), computes
the exact value independently and requires `correct_value` to match it under the same rules, and
requires the two values to differ (integers by at least 1, numbers by more than `1e-6` relative).
At least three distinct `quantity` values must appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/lambert.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/lambert.py` on the 6 systems
shipped in `/root/data/systems/` and on 22 held-out systems of the same schema and domain, 28
fresh calls in total. The held-out systems cover: circular and highly eccentric ellipses,
retrograde orbits, hyperbolic objects, epochs thousands of periods away; transfers with angles
below and above 180 degrees, short and long flights, `n_max` from 0 to 4 with every count of
solutions from 1 to 9, hyperbolic zero-revolution arcs, and best solutions on multi-revolution
branches. Their contents are not disclosed.

Each call is `python /root/results/lambert.py --system <system.json> --output <report.json>`
and must exit with status 0 within 60 seconds of wall-clock time measured by the verifier from
process start to exit; the legacy script runs on each diagnosis witness under the same contract.
The verifier as a whole has 7200 seconds of wall-clock time. All time limits are wall-clock
limits, not CPU-time limits. Calls run in a separate verifier container, offline, as an
unprivileged user in a fresh, empty, writable working directory that is the only writable
location, with Python 3.11, NumPy 1.26.4 and SciPy 1.11.4 and nothing else; the program may rely
only on its own source and its arguments, and must require neither other files nor state from
earlier calls. The verifier environment is allocated 1 CPU, 2048 MB of memory, 10240 MB of
storage and no GPU, and sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to
`1`; the environment passed to the program holds only `PATH`, `PYTHONHASHSEED=0`, those three
variables, and `HOME` and `TMPDIR` set to the working directory. The program must be a single
regular file of at most 1 MB, and every report it writes must follow the file conventions of
section 4. Anything the program writes to standard output or standard error is ignored.
