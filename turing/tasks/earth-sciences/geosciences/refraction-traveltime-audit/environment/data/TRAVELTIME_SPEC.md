# TRAVELTIME_SPEC: ray-theoretical P-wave traveltimes in a layered crust

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Medium.** A flat, layered, isotropic acoustic medium. Depth `z` (km) increases downwards from
the free surface `z = 0`. Layer `k = 0, 1, ..., N-1` occupies `z_k <= z < z_{k+1}` with `z_0 = 0`;
the last layer `N-1` is a half-space (`z_N = infinity`). Inside layer `k` the P-wave velocity
(km/s) is linear in depth,

```
v(z) = a_k + b_k (z - z_k),    z_k <= z < z_{k+1},
```

with `a_k > 0` the velocity at the top of the layer and `b_k` (1/s) its gradient, which may be
positive, zero or negative. The velocity may jump up or down at an interface: `a_k` need not equal
the velocity at the bottom of layer `k-1`. Interface `i` (`i = 1, ..., N-1`) is the depth `z_i`
separating layer `i-1` above from layer `i` below. Notation: `v_k^top = a_k`, `v_k^bot = a_k +
b_k h_k` with `h_k = z_{k+1} - z_k` (not defined for the half-space), `V_i^-` the maximum of `v`
over `0 <= z < z_i` (everything above interface `i`).

**Source, receivers, rays.** A point source and the receivers are at the surface `z = 0`; offset
`X` (km) is the horizontal source-receiver distance, `X > 0`. Arrivals are those of ray theory for
P waves only (no mode conversion, no amplitude criterion: an arrival exists if its path exists),
each labelled by its ray parameter `p` (s/km), the constant horizontal slowness along the path,
`p = sin(angle from vertical) / v`. Only **primary** paths are considered: the path goes down
once and comes up once, symmetric about its deepest point, and contains no other reflection.
Transmission through an interface is possible only where `p v < 1` on both sides of it.

Every arrival is of exactly one of these kinds:

- **`"direct"`** (index `0`): only when `b_0 = 0`. The ray along the surface with `p = 1/a_0`,
  `T = X / a_0`, at every offset.
- **`"turning"`** (index `k`, the layer in which the ray turns): the ray turns smoothly at the
  depth inside layer `k` where `v = 1/p`. It exists for every `p` with `p v < 1` at every depth
  above that turning depth and `v` reaching `1/p` inside layer `k` at a depth where `b_k > 0`
  (rays cannot turn where the gradient is zero or negative). In the half-space with `b_{N-1} > 0`
  every sufficiently small `p` turns.
- **`"reflection"`** (index `i`, the interface): the ray reflects from the top side of
  interface `i`. It exists for every `p` with `0 <= p < 1 / V_i^-`, whatever the velocity below
  the interface (pre-critical and post-critical reflections are both arrivals).
- **`"head"`** (index `i`): only when layer `i` has `b_i = 0` and `a_i > V_i^-`. The wave travels
  along the top of layer `i` with `p = 1/a_i`; it exists at every offset `X >= X_c,i`, where
  `X_c,i` is the offset of the reflection from interface `i` with `p = 1/a_i` (the critical
  reflection). Its time is `T = X / a_i + tau_i`, `tau_i` the intercept of that critical
  reflection (`tau = T - p X`).

**Branches, caustics.** For a fixed kind and index, `X(p)` and `T(p)` are continuous functions
of `p` on an interval; such a family is a **branch**. Several values of `p` on the same branch
can arrive at the same offset. A **caustic** is a point of a branch where `dX/dp = 0` with `p`
strictly inside the branch's interval; it is reported with its kind, index, `p`, `X` and `T`.
Direct and head arrivals have no caustics.

**First arrival.** The first-arrival time `T_1(X)` is the minimum of `T` over all arrivals at
offset `X`. A **segment** of a turning or reflection branch is a part of it between consecutive
caustics or branch ends, on which `X(p)` is monotone; a direct or head branch is one segment.
Over the window `0 < X <= X_max` the first arrival is made of maximal offset intervals on each of
which it comes from one segment. Consecutive intervals are separated by a **crossover** (two
segments have equal time and the minimum passes from one to the other) or by the end or the start
of a segment's offset range. Two consecutive intervals can have the same kind and index (two
segments of one branch, inside a triplication). Each interval is reported with the kind and index
of its branch.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| number of layers `N` | 2 to 6 (the last one a half-space) |
| layer thickness `h_k` | 0.5 to 15 km |
| `a_k` | 1.5 to 8.5 km/s |
| `b_k` | -0.3 to 1.5 1/s, or exactly 0; inside a layer `v` stays between 1.5 and 9.0 km/s |
| `X_max` | 5 to 300 km |
| `offsets` | 2 to 10 values, strictly increasing, in `(0, X_max]` |

Every recipe in the domain satisfies: no queried offset lies within `1e-4 X` of an offset where
the number of arrivals changes (a caustic, the critical offset of a head wave, or the end of a
branch) or within `1e-4 X` of a crossover; no two caustics or crossovers lie within `1e-3`
relative of each other; at every queried offset any two arrivals differ in `T` by at least `1e-6`
s or in `p` by at least `1e-6` s/km; no ray parameter of an arrival at a queried offset lies
within `1e-8` relative of `1/v` for a velocity `v` at an interface or at the top of a layer
(grazing paths); the first arrival has no tie except at isolated crossovers; and every offset in `(0, X_max]` has
at least one arrival.

## 3. Model file

A JSON object with exactly these keys: `model_id` (string, 1 to 64 characters, letters, digits,
underscore, hyphen; carries no information about the answer), `layers` (list of 2 to 6 objects,
each with exactly the keys `thickness_km` (number; `null` for the last layer and only for it),
`v_top_km_s` and `gradient_per_s` (numbers)), `x_max_km` (number), `offsets_km` (list of numbers).

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision; indices are JSON integers.

- `model_id`: the model's id, exactly.
- `arrivals`: one object per entry of `offsets_km`, in the same order, each with exactly the
  keys `x_km` (the offset exactly as given) and `rays`: all arrivals at that offset, in increasing
  `t_s` (time; ties do not occur), each an object with exactly the keys `kind` (`"direct"`,
  `"turning"`, `"reflection"` or `"head"`), `index` (integer as defined in section 1), `p_s_km`,
  `t_s`.
- `caustics`: every caustic with `0 < X <= X_max`, in increasing `x_km`, each with exactly the
  keys `kind` (`"turning"` or `"reflection"`), `index`, `p_s_km`, `x_km`, `t_s`. Empty list if none.
- `first_arrival`: the intervals of section 1 over `(0, X_max]`, in increasing offset, each with
  exactly the keys `kind`, `index`, `x_start_km`, `x_end_km` (`x_start_km` of the first interval is
  `0`, `x_end_km` of the last is `X_max`, consecutive intervals share their boundary exactly).

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that model:

1. The report meets section 4 exactly.
2. The number of arrivals at every offset, the number of caustics and the number of first-arrival
   intervals equal the reference numbers.
3. Element by element in the stated orders: every `kind` and `index` is equal; every `t_s` and
   `p_s_km` is within `1e-9` relative of the reference; every `x_km` of a caustic and every
   interior boundary `x_end_km` / `x_start_km` of the first-arrival intervals is within `1e-7`
   relative of the reference. The outer boundaries `0` and `X_max` are exact.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/ttcurve.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `model`: a complete model object meeting sections 2 and 3 (a shipped model or one you construct
  inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"arrival_count"`, `"first_arrival_time"`, `"caustic_count"`,
  `"first_arrival_count"`.
- `offset_km`: for `"arrival_count"` and `"first_arrival_time"`, a number present in the model's
  `offsets_km`; `null` otherwise.
- `legacy_value` and `correct_value`: integers for the counts; for `"first_arrival_time"`, the
  time `t_s` of the earliest arrival at that offset (a number).

The verifier runs a pristine copy of the legacy script on the witness model and requires
`legacy_value` to match its report (integers exactly, times within `1e-9` relative), computes the
exact value independently and requires `correct_value` to match it under the same rules, and
requires the two values to differ (integers by at least 1, times by more than `1e-9` relative). At
least three distinct `quantity` values must appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/raytimes.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/raytimes.py` on the 6 models
shipped in `/root/data/models/` and on 22 held-out models of the same schema and domain, 28 fresh
calls in total. The held-out models cover: constant-velocity layers with head waves and a direct
wave; gradient layers with turning waves; velocity increases and decreases at interfaces;
low-velocity zones (negative gradients and velocity drops); triplications with three or more
arrivals at one offset; reflection branches with caustics; head waves whose critical offset lies
inside the window and beyond it; gradient half-spaces and constant-velocity half-spaces; and first
arrivals with several crossovers. Their contents are not disclosed.

Each call is `python /root/results/raytimes.py --model <model.json> --output <report.json>` and
must exit with status 0 within 60 seconds of wall-clock time measured by the verifier from process
start to exit; the legacy script runs on each diagnosis witness under the same contract. The
verifier as a whole has 7200 seconds of wall-clock time. All time limits are wall-clock limits,
not CPU-time limits. Calls run in a separate verifier container, offline, as an unprivileged user
in a fresh, empty, writable working directory that is the only writable location, with Python
3.11, NumPy 1.26.4 and SciPy 1.11.4 and nothing else; the program may rely only on its own source
and its arguments, and must require neither other files nor state from earlier calls. The
verifier environment is allocated 1 CPU, 2048 MB of memory, 10240 MB of storage and no GPU, and
sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to `1`; the environment
passed to the program holds only `PATH`, `PYTHONHASHSEED=0`, those three variables, and `HOME`
and `TMPDIR` set to the working directory. The program must be a single regular file of at most
1 MB, and every report it writes must follow the file conventions of section 4. Anything the
program writes to standard output or standard error is ignored.
