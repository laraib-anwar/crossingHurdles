# IX_SPEC: fixed-bed anion exchange effluent history

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

A packed bed of strong-base anion exchange resin treats water containing four anions:
chloride, nitrate, sulfate and bicarbonate. Throughout this document and in every file the ions
are listed in this fixed order:

```
["chloride", "nitrate", "sulfate", "bicarbonate"]
```

Concentrations are in milliequivalents per litre (meq/L). The total normality of the liquid,
`C_T` (meq/L), is the same in the feed and in the bed at all times, so the liquid composition is
fully described by the equivalent fractions `x_i = c_i / C_T` with `sum_i x_i = 1`. The resin
composition is described by the resin-phase equivalent fractions `y_i` with `sum_i y_i = 1`.

**Equilibrium.** The resin and the liquid in contact with it are in local equilibrium at every
point and every instant. The equilibrium is of constant-separation-factor type: with `alpha_i`
the separation factor of ion `i` relative to chloride (`alpha_chloride = 1` exactly),

```
y_i = alpha_i x_i / sum_j alpha_j x_j        for every ion i.
```

**Bed.** Plug flow, isothermal, no axial dispersion, no mass-transfer resistance. The bed has
voidage `eps` (liquid volume fraction) and total exchange capacity `Q` in equivalents per litre
of packed bed. Throughput is measured in bed volumes, `BV = u t / L`, where `u` is the
superficial velocity, `t` the time since the start of the run and `L` the bed length; `xi = z/L`
is the dimensionless axial position, 0 at the inlet and 1 at the outlet. With
`Lambda = 1000 Q / C_T` (dimensionless; `Q` in eq/L of bed, `C_T` in meq/L) the balance for
each ion is

```
eps dx_i/dBV + Lambda dy_i/dBV + dx_i/dxi = 0 ,   0 < xi < 1,  BV > 0.
```

**Initial state.** At `BV = 0` the resin has the composition `y^0` given in the recipe,
uniformly along the bed, and the liquid in the bed is in equilibrium with it, so `x^0_i` is
proportional to `y^0_i / alpha_i`. The feed program fixes the liquid composition at the inlet
`xi = 0` for `BV > 0`: composition `x^F1` from `BV = 0`, and, when the recipe has a second feed
entry, composition `x^F2` from its `start_bv` onwards. Feed changes are instantaneous.

**Effluent.** The effluent history is the liquid composition at `xi = 1` as a function of `BV`
over the reporting window `0 <= BV <= run_bv`. At `BV = 0` it equals `x^0`.

**Solution.** The model is a system of first-order hyperbolic conservation laws. The required
solution is the physically admissible weak solution: the limit of the same model with a
vanishing axial dispersion. Across a discontinuity the integral balance (jump condition) of
every ion holds, and the discontinuity is admissible in the Lax sense (characteristics of its
family enter it from both sides). Where the composition varies continuously it is carried along
characteristics. No approximation of the model, such as a finite-difference discretisation, is
part of the model; the quantities below are defined for the exact solution.

**Effluent structure.** For the exact solution the reporting window `[0, run_bv]` partitions
into finitely many maximal intervals of positive length on each of which the effluent
composition is either constant (a **plateau**) or continuous and nowhere constant (a
**transition**), separated by isolated points at which the composition is either continuous
(the boundary between a plateau and a transition, or a point inside a transition where the
derivative jumps) or discontinuous (a **shock**). A shock is reported once, at its `BV`, with
the compositions immediately before and after it. A transition may contain points where the
derivative is discontinuous; it ends only where the composition becomes constant or jumps. Two
adjacent intervals of constant composition with the same composition are one plateau. An
interval counts as a plateau only if the composition is exactly constant on it in the exact
solution. The reporting window is closed: a shock at exactly `BV = run_bv` is reported, and a
plateau or transition is cut at `run_bv`.

## 2. Parameter domain

Every shipped and held-out recipe lies in this domain. The domain is not a hint about where
the interesting behaviour is.

| Quantity | Domain |
| --- | --- |
| `alpha_chloride` | exactly 1 |
| `alpha_nitrate` | 1.5 to 6.0 |
| `alpha_sulfate` | 2.0 to 25.0 |
| `alpha_bicarbonate` | 0.10 to 0.60 |
| any two separation factors (including chloride's 1) | differ by at least 0.05 |
| `eps` | 0.35 to 0.45 |
| `Q_eq_per_L_bed` | 0.8 to 1.6 |
| `C_T_meq_per_L` | 2.0 to 15.0 |
| `initial_resin_fraction` entries | 0 to 1, sum 1 within 1e-9; any entry may be exactly 0 |
| feed compositions | each entry 0 to `C_T`, sum equal to `C_T` within 1e-9 relative; any entry may be exactly 0 |
| number of feed entries | 1 or 2; the first has `start_bv = 0`; the second has `0 < start_bv < run_bv` |
| `run_bv` | 1 to 5000 |
| `sample_bv` | 0 to 12 values, strictly increasing, each in `(0, run_bv]`, none within 1e-6 of a shock of the exact solution |
| `nitrate_limit_meq_per_L` | 0.1 to 2.0 |

The ordering of `alpha_nitrate` and `alpha_sulfate` is not fixed: nitrate-selective resins
(`alpha_nitrate > alpha_sulfate`) are in the domain. No graded quantity of any recipe lies
within three tolerances of a bound of `[0, run_bv]` or of `nitrate_limit_meq_per_L` unless the
recipe is constructed so that the correct value is on a definite side of that bound.

## 3. Recipe file

A recipe is a JSON object with exactly these keys and no others:

- `recipe_id`: string, 1 to 64 characters, letters, digits, underscore and hyphen only. Carries
  no information about the answer.
- `ions`: the fixed list above, exactly.
- `alpha`: object with exactly the four ion names as keys and numbers as values;
  `alpha["chloride"]` is 1.
- `eps`, `Q_eq_per_L_bed`, `C_T_meq_per_L`: numbers.
- `initial_resin_fraction`: object with exactly the four ion names as keys, numbers in `[0, 1]`
  summing to 1.
- `feed_program`: list of 1 or 2 objects, each with exactly the keys `start_bv` (number) and
  `composition_meq_per_L` (object with exactly the four ion names as keys, numbers).
- `run_bv`: number.
- `sample_bv`: list of 0 to 12 numbers.
- `nitrate_limit_meq_per_L`: number.

## 4. Report file

The program writes a JSON object with exactly these keys and no others. Every composition is a
list of exactly 4 finite numbers in meq/L in the fixed ion order. Every `bv` value is a finite
number in `[0, run_bv]`. JSON `null` appears only where this section allows it. Integers are
written as JSON integers, numbers at full double precision.

- `recipe_id`: the recipe's id, exactly.
- `ions`: the fixed list, exactly.
- `shocks`: list of the shocks of the effluent history in increasing `bv`, each an object with
  exactly the keys `bv` (number), `before_meq_per_L` and `after_meq_per_L` (compositions
  immediately before and after the shock). Empty list if there are none.
- `transitions`: list of the transitions in increasing `bv_start`, each an object with exactly
  the keys `bv_start`, `bv_end` (numbers, `bv_start < bv_end`), `start_meq_per_L` and
  `end_meq_per_L` (compositions at the two ends, taken from inside the transition, so at a shock
  bounding a transition they are the side facing the transition). Empty list if there are none.
- `plateaus`: list of the plateaus in increasing `bv_start`, each an object with exactly the
  keys `bv_start`, `bv_end` (numbers, `bv_start < bv_end`) and `composition_meq_per_L`. The
  first plateau, if the effluent is constant from `BV = 0`, has `bv_start = 0`. Empty list if
  the effluent is nowhere constant.
- `nitrate_peak`: object with exactly the keys `meq_per_L` (the maximum effluent nitrate
  concentration over `[0, run_bv]`) and `bv` (the smallest `BV` at which that maximum is
  attained; `0` when it is attained at the start).
- `nitrate_limit_bv`: the smallest `BV` in `[0, run_bv]` at which the effluent nitrate
  concentration strictly exceeds `nitrate_limit_meq_per_L`, or `null` if it never does within
  the window. If the limit is exceeded immediately after a shock, the shock's `bv`; if it is
  first exceeded at `BV = 0`, `0`.
- `samples`: list with one composition per entry of the recipe's `sample_bv`, in the same
  order: the effluent composition at that `BV`. Empty list when `sample_bv` is empty.

The plateaus, transitions and shocks together cover `[0, run_bv]`: every point of the window
belongs to exactly one plateau or transition, or is a shock. Sorted by `bv_start`, the plateaus
and transitions tile the window: the first starts at exactly `0`, the last ends at exactly
`run_bv`, and each one's `bv_end` is exactly the same number as the next one's `bv_start`. The
`bv` of every shock is exactly the boundary value of the intervals it separates (or `run_bv`
for a shock at the end of the window).

**Counting rules.** A transition or plateau is reported only if its length is positive in the
exact solution. Two shocks arriving at the same `BV` in the exact solution are one shock. No
recipe in the domain has two distinct shocks, or a shock and the end of a transition, closer
than 1e-4 relative in `BV`.

**File conventions.** Every JSON file the verifier reads (the saved report, `diagnosis.json`,
and the report written by each fresh call) must be a regular file (not a symbolic link or other
special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when all of the following hold for
its report, compared with the verifier's reference values for that recipe:

1. The report meets section 4 exactly (key sets, types, finite numbers, order, lengths,
   coverage, `recipe_id`, `ions`).
2. The number of shocks, the number of transitions and the number of plateaus equal the
   reference counts.
3. Element by element in the stated order: every `bv`, `bv_start` and `bv_end` is within
   `TOL_BV` of the reference value, where `TOL_BV = max(2e-4 * reference, 1e-6)` (relative, with
   an absolute floor near zero); every composition entry is within `TOL_C = 1e-4` meq/L
   (absolute) of the reference entry.
4. `nitrate_peak.meq_per_L` within `TOL_C`; `nitrate_peak.bv` within `TOL_BV`.
5. `nitrate_limit_bv` is `null` exactly when the reference is `null`, otherwise within `TOL_BV`.
6. Every sample composition entry within `TOL_C`.

Absolute and relative tolerances are as written; no other tolerance applies. A value exactly on
a bound passes.

The rationale for each tolerance (method-to-method spread of two independent exact codes and a
high-resolution dispersive solver, against the distance to the nearest wrong answer) is recorded
in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/ixbreak.py` is the inherited script. It takes the same command line as the
required program and writes a report with the same key set. `/root/results/diagnosis.json` is a
JSON object with exactly one key, `defects`, a list of 3 to 8 objects, each with exactly these
keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `recipe`: a complete recipe object meeting sections 2 and 3, with a `recipe_id` of your
  choice. It may be a shipped recipe or one you construct inside the domain.
- `quantity`: one of exactly `"sample"`, `"nitrate_peak"`, `"nitrate_limit_bv"`,
  `"shock_count"`, `"transition_count"`.
- `bv`: for `quantity = "sample"`, a number in `(0, run_bv]` of that recipe, not within 1e-6 of
  a shock of the exact solution and present in the recipe's `sample_bv`; `null` for every other
  quantity.
- `legacy_value`: the value the legacy script reports for that quantity on that recipe.
- `correct_value`: the value of the exact solution.

Value types by quantity: `sample` is a composition (list of 4 numbers); `nitrate_peak` is the
`meq_per_L` number; `nitrate_limit_bv` is a number or `null`; `shock_count` and
`transition_count` are integers.

The verifier runs a pristine copy of the legacy script on each witness recipe and requires
`legacy_value` to match the legacy report (counts exactly, numbers within the tolerances of
section 5, `null` exactly). It computes the exact value independently and requires
`correct_value` to match it under the same rules. It requires `legacy_value` and
`correct_value` to differ: counts by at least 1, `null` against a number, or numbers by more
than the tolerance in at least one entry. At least three distinct `quantity` values must appear
among the defects. Every witness must pass for the diagnosis to pass.

## 7. Execution contract

The verifier evaluates `/root/results/ixfront.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/ixfront.py` on the 6 recipes
shipped in `/root/data/recipes/` and on 22 held-out recipes of the same schema and domain, 28
fresh calls in total. The held-out recipes cover: a chloride-form resin with a four-ion feed;
resins pre-loaded with sulfate or bicarbonate; complete elution of a loaded resin; an ion absent
from both the feed and the resin; an ion present at trace level; nitrate-selective resins;
nearly coincident effluent events; the nitrate limit exceeded inside a transition, at a shock,
at `BV = 0`, and never; feed changes whose waves overtake earlier waves before the outlet and
feed changes whose waves do not reach the outlet within the window; windows that end before the
first event; and empty `sample_bv` lists. Their contents are not disclosed.

Each call is `python /root/results/ixfront.py --recipe <recipe.json> --output <report.json>`
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
