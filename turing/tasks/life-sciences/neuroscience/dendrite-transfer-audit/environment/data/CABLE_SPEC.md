# CABLE_SPEC: passive electrotonic properties of a branched dendritic tree

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Neuron.** A passive neuron made of an isopotential soma and `N` cylindrical dendritic
segments forming a tree. Segment `i` (`i = 1, ..., N`) has length `L_i` (um), diameter `d_i`
(um), specific membrane resistance `Rm_i` (ohm cm2), axial resistivity `Ri_i` (ohm cm) and
specific membrane capacitance `Cm_i` (uF/cm2); its proximal end is attached to the distal end of
its parent, which is either another segment or the soma (`parent = 0`). Any number of segments may
attach to one parent. A segment without children is a **terminal**; its distal end has one of
three boundary conditions: `"sealed"` (zero axial current), `"killed"` (membrane potential
clamped to rest, `V = 0`) or `"shunt"` (a conductance `g_end` in nS to rest). The soma is a
sphere of diameter `d_s` (um) with specific parameters `Rm_s`, `Cm_s` and an additional somatic
shunt conductance `g_s` (nS, possibly `0`), so that its membrane conductance and capacitance are
`G_s = pi d_s^2 / Rm_s + g_s` and `C_s = pi d_s^2 Cm_s` (consistent units). All potentials are
deviations from rest; the system is linear.

**Cable equations.** With `x` the distance from the proximal end of segment `i`, the membrane
potential obeys `lambda_i^2 d2V/dx2 = V + tau_i dV/dt` with

```
lambda_i = sqrt( Rm_i d_i / (4 Ri_i) )            (length constant)
tau_i    = Rm_i Cm_i                              (membrane time constant)
G_inf,i  = (pi / 2) d_i^(3/2) / sqrt(Rm_i Ri_i)   (input conductance of the semi-infinite cable)
```

At a branch point the potential is continuous and axial currents sum to zero (Kirchhoff); at the
soma the potential is the somatic potential and the axial currents of the soma's children, the
somatic membrane current and the injected current balance. Current is injected at a **location**
`(segment, fraction)`: `fraction = f` in `[0, 1]` is the distance from the proximal end divided by
`L_i`; the soma is location `(0, 0)`. No other location on the soma exists. Location `(i, 0)` is
the proximal node of segment `i` (the distal end of its parent, or the soma for a child of the
soma) and `(i, 1)` its distal end.

**Steady state (DC).** For a constant injected current `I` at a location `a`, the potential is
`V(a <- a) = R_in(a) I` with `R_in(a)` the **input resistance** (megaohm, MOhm) at `a`, and the
potential at another location `b` is `V(b) = A(a -> b) V(a)` with `A(a -> b)` the **steady-state
attenuation factor** from `a` to `b` (dimensionless, in `(0, 1)` for `a != b`; it depends on the
direction).

**Frequency domain (AC).** For a sinusoidal current `I e^{j 2 pi f t}` at `a`, the potential at
`b` is `Z(a -> b, f) I e^{j 2 pi f t}` with the complex **transfer impedance** `Z` (input
impedance when `b = a`), reported as its modulus `|Z|` (MOhm) and its phase `arg Z` in degrees as
the principal value in `(-180, 180]` (`0` at `f = 0`; the lag of a distal transfer at a high
frequency can exceed 180 degrees, and the principal value is then positive).

**Equalization time constants.** With `s` the Laplace variable, the somatic input impedance
`Z_soma(s) = V_soma(s) / I(s)` for current injected at the soma is a meromorphic function of `s`
whose poles are real and negative, `s_k = -1 / tau_k`. The `tau_k` (ms) are the **equalization
time constants** of the neuron: the eigenvalues of the passive tree, equivalently the decay time
constants of its voltage modes. They are the roots of the entire function obtained by clearing the
denominators of the admittance recursion (section 1 formulas with `gamma_i = sqrt(1 + s tau_i)`:
`G_inf,i gamma_i`, `tanh(gamma_i L_i / lambda_i)`), each root is simple, and the one with the
largest `tau` is not larger than the largest of the membrane time constants `tau_i` and
`tau_s = Rm_s Cm_s`. The somatic voltage for a unit current step at the soma is

```
V_soma(t) = sum_k C_k ( 1 - exp(-t / tau_k) ),     C_k = tau_k * Res_{s = s_k} Z_soma(s)
```

and `C_k` (MOhm) is the **coefficient** of mode `k`; `sum_k C_k = R_in(soma)` over all modes.
Modes whose spatial profile is nearly zero at the soma have small but nonzero coefficients. The
report lists every mode with `tau_k >= tau_min` (a value given in the neuron file), in decreasing
`tau_k`, with its coefficient.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| number of segments `N` | 3 to 12 |
| `L_i` | 20 to 600 um |
| `d_i` | 0.3 to 6 um |
| `Rm_i`, `Rm_s` | 2000 to 60000 ohm cm2 |
| `Ri_i` | 70 to 300 ohm cm |
| `Cm_i`, `Cm_s` | 0.6 to 2 uF/cm2 |
| `d_s` | 8 to 40 um |
| `g_s` | 0 to 20 nS |
| terminal `g_end` (shunt) | 0.5 to 20 nS |
| `tau_min` | 0.1 to 20 ms, at most `0.5 min_i tau_i` |
| frequencies | 1 to 2000 Hz |
| queries | 2 to 8 input resistance sites, 2 to 8 attenuation pairs, 2 to 8 impedance queries |

Every neuron in the domain satisfies these guarantees:

1. Every equalization time constant is a simple root; consecutive time constants differ by at
   least `1e-3` relative; no time constant lies within `1e-3` relative of `tau_min`; the number
   of modes with `tau_k >= tau_min` is between 2 and 60.
2. Every coefficient satisfies `|C_k| >= 1e-6 R_in(soma)`.
3. Every attenuation factor queried is at least `1e-6`; the two locations of an attenuation pair
   or of an impedance query may coincide (then `A = 1` and `Z` is the input impedance).
4. No two sibling segments (same parent) have identical `(L, d, Rm, Ri, Cm)` and identical
   subtrees; every pair of consecutive time constants is separated as in guarantee 1 even when
   subtrees are nearly symmetric.

## 3. Neuron file

A JSON object with exactly these keys:

- `neuron_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `soma`: object with exactly the keys `d_um`, `Rm_ohm_cm2`, `Cm_uF_cm2`, `shunt_nS` (numbers).
- `segments`: list of `N` objects with exactly the keys `id` (integer `1..N`, in increasing
  order), `parent` (integer, `0` for the soma or the `id` of an earlier segment), `L_um`, `d_um`,
  `Rm_ohm_cm2`, `Ri_ohm_cm`, `Cm_uF_cm2` (numbers) and `end`: `null` for a segment with children,
  otherwise an object with exactly the keys `type` (`"sealed"`, `"killed"` or `"shunt"`) and
  `g_nS` (a number for `"shunt"`, `null` otherwise).
- `input_resistance_sites`: list of locations, each an object with exactly the keys `segment`
  (integer, `0` for the soma) and `fraction` (number in `[0, 1]`, `0` for the soma).
- `attenuation_pairs`: list of objects with exactly the keys `source` and `target` (locations).
- `impedance_queries`: list of objects with exactly the keys `source`, `target` (locations) and
  `frequency_Hz` (number).
- `tau_min_ms`: number.

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision.

- `neuron_id`: the neuron's id, exactly.
- `input_resistance`: one object per entry of `input_resistance_sites`, in the same order, each
  with exactly the keys `site` (the location object exactly as given) and `R_MOhm`.
- `attenuation`: one object per entry of `attenuation_pairs`, in order, each with exactly the
  keys `source`, `target` (as given) and `factor`.
- `impedance`: one object per entry of `impedance_queries`, in order, each with exactly the keys
  `source`, `target`, `frequency_Hz` (as given), `magnitude_MOhm` and `phase_deg`.
- `modes`: every mode with `tau_k >= tau_min`, in decreasing `tau_ms`, each with exactly the keys
  `tau_ms` and `coefficient_MOhm`.

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that neuron:

1. The report meets section 4 exactly.
2. The number of modes equals the reference number.
3. Every `R_MOhm`, `factor`, `magnitude_MOhm` and `tau_ms` is within `1e-9` relative of the
   reference; every `phase_deg` is within `1e-7` degrees absolute; every `coefficient_MOhm` is
   within `1e-9 * R_in(soma)` absolute of the reference, where `R_in(soma)` is the reference
   somatic input resistance.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/cableprop.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `neuron`: a complete neuron object meeting sections 2 and 3 (a shipped neuron or one you
  construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"input_resistance"`, `"attenuation"`, `"impedance_magnitude"`,
  `"mode_count"`, `"tau"`.
- `index`: for `"input_resistance"`, `"attenuation"` and `"impedance_magnitude"`, the 0-based
  index into the neuron's corresponding query list; for `"tau"`, the 0-based index into the
  mode list (decreasing `tau`); `null` for `"mode_count"`.
- `legacy_value` and `correct_value`: the quantity (`R_MOhm`, `factor`, `magnitude_MOhm`, the
  number of modes as an integer, or `tau_ms`).

The verifier runs a pristine copy of the legacy script on the witness neuron and requires
`legacy_value` to match its report (integers exactly, numbers within `1e-9` relative), computes
the exact value independently and requires `correct_value` to match it under the same rules, and
requires the two values to differ (integers by at least 1, numbers by more than `1e-6` relative).
For `"tau"` the index must exist in both reports. At least three distinct `quantity` values must
appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/cabletree.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/cabletree.py` on the 6 neurons
shipped in `/root/data/neurons/` and on 22 held-out neurons of the same schema and domain, 28
fresh calls in total. The held-out neurons cover: unbranched cables with each boundary condition;
symmetric and asymmetric bifurcations; trees of up to 12 segments with 2 to 4 branch orders;
non-uniform membrane resistance and capacitance along the tree; killed and shunted terminals
next to sealed ones; somata that dominate and somata that are negligible; nearly symmetric
sibling subtrees; frequencies from 1 to 2000 Hz; and mode lists from 2 to about 50 entries.
Their contents are not disclosed.

Each call is `python /root/results/cabletree.py --neuron <neuron.json> --output <report.json>`
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
