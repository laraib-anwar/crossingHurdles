# WASHCOAT_SPEC: steady states, ignition, extinction and stability of a catalytic washcoat layer

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

A porous catalytic washcoat layer of uniform thickness lies on an impermeable, adiabatic wall
and is exposed on its other face to a gas of fixed composition and temperature. One reactant is
consumed by an irreversible first-order exothermic reaction with Arrhenius kinetics. Transport
inside the layer is by effective diffusion and conduction. Position `x` runs from the wall
(`x = 0`) to the exposed face (`x = 1`), scaled with the layer thickness. The dimensionless
reactant concentration `c(x, t)` and temperature rise `theta(x, t)` (both relative to the bulk
gas, so the bulk gas has `c = 1`, `theta = 0`) obey

```
Le dtheta/dt = d2theta/dx2 + beta phi^2 c R(theta)
   dc/dt    = d2c/dx2     -      phi^2 c R(theta)
R(theta) = exp(gamma theta / (1 + theta))
```

with the wall conditions `dtheta/dx = 0`, `dc/dx = 0` at `x = 0` and the film conditions

```
-dc/dx     = Bi_m (c - 1)   at x = 1
-dtheta/dx = Bi_h theta     at x = 1
```

`phi` is the Thiele modulus (based on the bulk-gas rate constant and the layer thickness),
`beta` the Prater number (adiabatic temperature rise, dimensionless), `gamma` the Arrhenius
number, `Bi_m` and `Bi_h` the mass and heat Biot numbers of the external film, and `Le` the
Lewis number (ratio of the thermal to the mass time constant of the layer). The reaction order
is 1 and the kinetics are exactly as written; there is no other physics.

**Steady states.** A steady state is a solution with `d/dt = 0`. Its reported quantities are
the centre temperature rise `theta_c = theta(0)`, and the effectiveness factor
`eta = (dc/dx at x = 1) / phi^2`, the observed rate relative to the rate at bulk-gas conditions
throughout the layer.

**Steady-state set and folds.** For fixed `beta`, `gamma`, `Bi_m`, `Bi_h`, the steady states
form a one-dimensional set of points `(phi, theta_c)`. A **fold** is a point of that set at which
`phi` has a local extremum along the set: an **ignition** point where `phi` has a local maximum
(the set turns back towards smaller `phi` as `theta_c` increases through it) and an
**extinction** point where `phi` has a local minimum. Fold positions do not depend on `Le`.
Every recipe in the domain has exactly one steady state at `phi_min` and exactly one at
`phi_max`, and every fold whose `phi` lies in the window lies strictly inside it.

**Stability.** The stability of a steady state is that of the linearised time-dependent
problem (the two equations above linearised about the steady state, with the same boundary
conditions, homogeneous). Its spectrum consists of discrete eigenvalues `lambda` (growth rates
of perturbations proportional to `exp(lambda t)`). A steady state is `"stable"` when every
eigenvalue has negative real part, `"unstable_real"` when the eigenvalue of largest real part is
real and positive, and `"unstable_complex"` when the eigenvalues of largest real part are a
complex-conjugate pair with positive real part. A **Hopf point** is a steady state at which a
complex-conjugate pair of eigenvalues has zero real part and non-zero imaginary part
`omega > 0`; it is reported with its `phi`, `theta_c`, `eta` and `omega`. The number of Hopf
points and their positions depend on `Le`. No recipe in the domain has a steady state whose
rightmost eigenvalue `lambda_1` has `|Re(lambda_1)| < 1e-4 max(1, |lambda_1|)` at a query value
of `phi`, or has `0 < |Im(lambda_1)| < 1e-3 max(1, |lambda_1|)` there; every Hopf point has
`omega >= 0.05`; and no fold or Hopf point lies within `1e-3` relative in `phi` of a query value
or of another fold or Hopf point.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| `beta` | 0.05 to 0.6 |
| `gamma` | 8 to 40 |
| `Bi_m` | 1 to 200 |
| `Bi_h` | 0.5 to 50, with `Bi_h <= Bi_m` and `beta Bi_m / Bi_h <= 1` |
| `Le` | 0.1 to 20 |
| `phi_min` | 0.01 to 1 |
| `phi_max` | 0.3 to 30, with `phi_max >= 3 phi_min` |
| `phi_query` | 2 to 8 values, strictly increasing, in `[phi_min, phi_max]` |

`beta Bi_m / Bi_h` is the largest possible temperature rise of the layer (the surface
temperature rise at complete conversion with the film limiting both transfers). The domain
includes parameter sets with a unique steady state at every `phi` (no fold), with one ignition
and one extinction fold, with two ignition and two extinction folds, and with zero, one or two
Hopf points.

## 3. Recipe file

A JSON object with exactly these keys: `recipe_id` (string, 1 to 64 characters, letters,
digits, underscore, hyphen; carries no information about the answer), `beta`, `gamma`, `Bi_m`,
`Bi_h`, `Le`, `phi_min`, `phi_max` (numbers), `phi_query` (list of numbers).

## 4. Report file

A JSON object with exactly these keys and no others. All numbers are finite JSON numbers at
full double precision; integers are JSON integers.

- `recipe_id`: the recipe's id, exactly.
- `folds`: list of the folds in increasing `phi`, each an object with exactly the keys `phi`,
  `theta_c`, `eta`, `kind` (`"ignition"` or `"extinction"`, as defined in section 1). Empty list
  when the steady state is unique throughout the window.
- `hopf_points`: list of the Hopf points in increasing `phi`, each an object with exactly the
  keys `phi`, `theta_c`, `eta`, `omega`. Empty list when there is none.
- `states`: list with one object per entry of `phi_query`, in the same order, each with exactly
  the keys `phi` (the query value, exactly as given) and `branches`: the list of all steady
  states at that `phi`, in increasing `theta_c`, each an object with exactly the keys `theta_c`,
  `eta`, `stability` (`"stable"`, `"unstable_real"` or `"unstable_complex"`).

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that recipe:

1. The report meets section 4 exactly.
2. The numbers of folds and Hopf points, and the number of steady states at every query value,
   equal the reference numbers.
3. Element by element in the stated orders: every `phi` is within
   `TOL_PHI = 1e-6` relative of the reference; every `theta_c` and every `eta` of a fold or of a
   steady state at a query value is within `TOL_VAL = 1e-6` relative of the reference (that is,
   within `1e-6 max(1, |reference|)`); every `theta_c` and every `eta` of a Hopf point is within
   `TOL_HOPF_VAL = 5e-5` relative in the same sense; every `omega` is within
   `TOL_OMEGA = 2.5e-4` relative; every `kind` and `stability` is equal.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/lightoff.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to
8 objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `recipe`: a complete recipe object meeting sections 2 and 3 (a shipped recipe or one you
  construct inside the domain; its window must satisfy the guarantees of section 1).
- `quantity`: one of exactly `"fold_count"`, `"hopf_count"`, `"state_count"`, `"stability"`,
  `"fold_phi"`.
- `selector`: for `"state_count"`, the query `phi` value (a number present in the recipe's
  `phi_query`); for `"stability"`, a list `[phi, index]` of a query value and the index
  (integer, from 0) of the steady state in increasing `theta_c` order at that value; for
  `"fold_phi"`, the index (integer, from 0) of the fold in increasing `phi`; `null` for
  `"fold_count"` and `"hopf_count"`. A `"stability"` or `"fold_phi"` witness is valid only when
  the legacy report and the exact solution have the same number of steady states at that query
  value, respectively the same number of folds.
- `legacy_value` and `correct_value`: integers for the counts, a string for `"stability"`, a
  number for `"fold_phi"`.

The verifier runs a pristine copy of the legacy script on the witness recipe and requires
`legacy_value` to match its report (integers and strings exactly, `fold_phi` within `TOL_PHI`),
computes the exact value independently and requires `correct_value` to match it under the same
rules, and requires the two values to differ (integers by at least 1, strings unequal, `fold_phi`
by more than `TOL_PHI`). At least three distinct `quantity` values must appear. Every witness
must pass.

## 7. Execution contract

The verifier evaluates `/root/results/lightoff_exact.py`, `/root/results/base_case_report.json`
and `/root/results/diagnosis.json`, and fresh runs of `/root/results/lightoff_exact.py` on the
6 recipes shipped in `/root/data/recipes/` and on 22 held-out recipes of the same schema and
domain, 28 fresh calls in total. The held-out recipes cover: unique steady states throughout the
window (empty fold list); one ignition and one extinction fold; two of each (two hysteresis
loops); no, one and two Hopf points; Lewis numbers below and above 1; Biot
numbers at both ends of the domain; nearly coincident folds (a near-cusp parameter set); a Hopf
point close to a fold; and query values on every branch. Their contents are not disclosed.

Each call is `python /root/results/lightoff_exact.py --recipe <recipe.json> --output
<report.json>` and must exit with status 0 within 120 seconds of wall-clock time measured by the
verifier from process start to exit; the legacy script runs on each diagnosis witness under the
same contract. The verifier as a whole has 7200 seconds of wall-clock time. All time limits are
wall-clock limits, not CPU-time limits. Calls run in a separate verifier container, offline, as
an unprivileged user in a fresh, empty, writable working directory that is the only writable
location, with Python 3.11, NumPy 1.26.4 and SciPy 1.11.4 and nothing else; the program may rely
only on its own source and its arguments, and must require neither other files nor state from
earlier calls. The verifier environment is allocated 1 CPU, 2048 MB of memory, 10240 MB of
storage and no GPU, and sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to
`1`; the environment passed to the program holds only `PATH`, `PYTHONHASHSEED=0`, those three
variables, and `HOME` and `TMPDIR` set to the working directory. The program must be a single
regular file of at most 1 MB, and every report it writes must follow the file conventions of
section 4. Anything the program writes to standard output or standard error is ignored.
