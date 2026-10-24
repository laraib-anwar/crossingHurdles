# HETERO_SPEC: bound states and transmission of a layered semiconductor heterostructure

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Structure.** A one-dimensional conduction-band profile `V(x)` (eV) along the growth direction
`x` (nm). The structure occupies `0 <= x <= X` and is made of `N` layers; layer `j` (`j = 1, ...,
N`) occupies `x_{j-1} <= x <= x_j` (`x_0 = 0`, `x_N = X`, `x_j - x_{j-1} = d_j`), has the
effective mass `m_j` (in units of the free-electron mass) and a potential that is linear inside
the layer, from `vl_j` at its left edge to `vr_j` at its right edge. Every layer is either flat
(`vl_j = vr_j` exactly) or sloped with a slope in the range of section 2. The potential may jump
at an interface. The **left lead** `x < 0` has the constant
potential `V_L` and mass `m_L`; the **right lead** `x > X` has `V_R` and `m_R`.

**Equation.** The envelope function `psi(x)` obeys the effective-mass Schrodinger equation with
BenDaniel-Duke boundary conditions,

```
-C d/dx [ (1 / m(x)) d psi / dx ] + V(x) psi = E psi,      C = 0.0380998212 eV nm^2,
```

so that inside every region `psi'' = (m / C) (V(x) - E) psi`, and at every interface `psi` and
`psi' / m` are continuous. Inside a sloped layer the solutions are Airy functions of an argument
linear in `x`; inside a flat layer and in the leads they are exponentials or trigonometric
functions.

**Bound states.** An energy `E < E_th = min(V_L, V_R)` is a bound state when a solution decays
at both `x -> -infinity` and `x -> +infinity`. Bound states are simple and finite in number; the
`n`-th one in increasing energy (`n = 0, 1, ...`) has exactly `n` nodes on the whole line. All of them are reported.

**Transmission.** For `E > max(V_L, V_R)` an electron incident from the left lead has the
scattering solution `psi = e^{i k_L x} + r e^{-i k_L x}` (`x < 0`) and `psi = t e^{i k_R (x - X)}`
(`x > X`) with `k = sqrt(m (E - V) / C)` in each lead. The transmission coefficient is the ratio
of transmitted to incident probability current,

```
T(E) = (k_R / m_R) / (k_L / m_L) |t|^2.
```

**Transmission maxima.** For the energy window `[E_lo, E_hi]` given in the file (it lies above
the maximum of the potential everywhere, leads included), every local maximum of `T(E)` strictly
inside the window (a point where `dT/dE = 0` and `T` changes from increasing to decreasing) is
reported with its energy and its transmission.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| layers `N` | 2 to 14 |
| thickness `d_j` | 0.3 to 30 nm; total thickness `X` at most 150 nm |
| masses `m_j`, `m_L`, `m_R` | 0.03 to 1.0 |
| potentials `vl_j`, `vr_j`, `V_L`, `V_R` | -1.0 to 2.0 eV |
| slope of a sloped layer, `(vr_j - vl_j) / d_j` | magnitude 1e-3 to 0.5 eV/nm |
| transmission queries | 2 to 8 energies |
| window `[E_lo, E_hi]` | width 0.01 to 1.0 eV |

Every structure in the domain satisfies these guarantees:

1. Bound states: there are at most 40; consecutive bound-state energies differ by at least
   `1e-6` eV; the highest is at least `1e-4` eV below `E_th`.
2. Every queried energy `E` satisfies `E >= max(V_L, V_R) + 1e-3` eV, `T(E) >= 1e-30` and
   `|d ln T / dE| <= 1e3` per eV at `E`.
3. The window satisfies `E_lo >= max_x V(x) + 0.01` eV (the maximum over the structure and the
   leads). Inside the window, consecutive local extrema of `T` are at least `2e-4` eV apart and
   at least `2e-4` eV from the window ends, and at every local maximum `T` is at least `1.001`
   times the adjacent local minima (or the value at the window end, where there is no minimum
   between the maximum and that end).

## 3. Structure file

A JSON object with exactly these keys:

- `structure_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `left_lead`, `right_lead`: objects with exactly the keys `mass` and `v_eV` (numbers).
- `layers`: list of 2 to 14 objects with exactly the keys `thickness_nm`, `mass`, `vl_eV`,
  `vr_eV` (numbers), from left to right.
- `transmission_energies_eV`: list of 2 to 8 numbers, strictly increasing.
- `window_eV`: list of exactly two numbers `[E_lo, E_hi]`.

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision.

- `structure_id`: the structure's id, exactly.
- `bound_states`: list of all bound states in increasing energy, each an object with exactly the
  key `E_eV`. Empty list if there is none.
- `transmission`: one object per entry of `transmission_energies_eV`, in the same order, each
  with exactly the keys `E_eV` (the energy exactly as given) and `T`.
- `maxima`: list of all local maxima of `T` inside the window in increasing energy, each an
  object with exactly the keys `E_eV` and `T`. Empty list if there is none.

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that structure:

1. The report meets section 4 exactly.
2. The numbers of bound states and of maxima equal the reference numbers.
3. Element by element in the stated orders: every bound-state `E_eV` is within `1e-9` eV of the
   reference; every `T` (transmission and maxima) is within `1e-9` relative of the reference;
   every maximum's `E_eV` is within `1e-8` eV of the reference.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/qwell.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `structure`: a complete structure object meeting sections 2 and 3 (a shipped structure or one
  you construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"bound_count"`, `"bound_energy"`, `"transmission"`,
  `"maxima_count"`, `"maximum_energy"`.
- `index`: for `"bound_energy"` and `"maximum_energy"`, the 0-based index into `bound_states`
  or `maxima` (it must exist in both reports); for `"transmission"`, the 0-based index into
  `transmission_energies_eV`; `null` for the two counts.
- `legacy_value` and `correct_value`: the count (integer) or the value (`E_eV` or `T`, a number).

The verifier runs a pristine copy of the legacy script on the witness structure and requires
`legacy_value` to match its report (integers exactly, energies within the section 5 tolerance of
their kind, `T` within `1e-9` relative), computes the exact value independently and requires
`correct_value` to match it under the same rules, and requires the two values to differ (integers
by at least 1, energies by more than `1e-6` eV, `T` by more than `1e-6` relative).
At least three distinct `quantity` values must appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/hetero.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/hetero.py` on the 6 structures
shipped in `/root/data/structures/` and on 22 held-out structures of the same schema and
domain, 28 fresh calls in total. The held-out structures cover: single and multiple quantum
wells, symmetric and asymmetric double wells with closely spaced levels, triangular and graded
wells under bias, thick and thin barriers with transmission down to 1e-30, leads with different
masses and band edges, structures with no bound state, superlattices with many transmission
maxima, and windows with no maximum. Their contents are not disclosed.

Each call is `python /root/results/hetero.py --structure <structure.json> --output <report.json>`
and must exit with status 0 within 120 seconds of wall-clock time measured by the verifier from
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
