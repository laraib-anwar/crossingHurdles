# PHASE_SPEC: equilibrium phase diagram of a binary system from Gibbs energy models

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**System.** Two components `A` and `B` at fixed pressure. Composition is the mole fraction of `B`,
`x`, with `0 <= x <= 1`; temperature is `T` in kelvin. All Gibbs energies are molar Gibbs energies
per mole of atoms in J/mol, on one common reference scale for the whole system (the file gives
every end member and compound on that scale). `R = 8.314462618 J/(mol K)`.

**Solution phases.** A solution phase `phi` exists at every composition `0 < x < 1` with

```
G_phi(x, T) = (1 - x) GA_phi(T) + x GB_phi(T)
            + R T [ x ln x + (1 - x) ln(1 - x) ]
            + x (1 - x) * sum_{k=0}^{2} ( a_k^phi + b_k^phi T ) (1 - 2x)^k
```

with end members `GA_phi(T) = hA_phi - sA_phi T` and `GB_phi(T) = hB_phi - sB_phi T` (pure `A`
and pure `B` in the structure of `phi`) and a Redlich-Kister excess term with three coefficients
`L_k = a_k + b_k T`. At `x = 0` and `x = 1` the function is continued by its limit (`GA_phi` and
`GB_phi`). Exactly one solution phase is named `liquid`; every other phase is solid.

**Stoichiometric compounds.** A compound `theta` exists only at its composition `x_theta`, with
`G_theta(T) = h_theta - s_theta T` (per mole of atoms). It is a point in the `(x, G)` plane.

**Equilibrium at a temperature.** At fixed `T` the equilibrium Gibbs energy `G_eq(x, T)` is the
lower convex envelope (lower convex hull) over `0 <= x <= 1` of the union of all solution-phase
curves and all compound points. The hull is composed, from `x = 0` to `x = 1`, of pieces of
exactly two kinds:

- a **single-phase region** of a solution phase `phi`: a maximal interval `[x_lo, x_hi]` with
  `x_lo < x_hi` on which `G_eq = G_phi` (the phase is stable on its own there);
- a **tie-line**: a maximal straight segment of the hull joining two stable states,
  `(left_phase, x_left)` and `(right_phase, x_right)` with `x_left < x_right`, each state being a
  point of a solution-phase curve or a compound point; the two phases may be the same solution
  phase (a miscibility gap). Between `x_left` and `x_right` the two phases coexist.

Because every solution-phase curve has infinite negative slope at `x -> 0` and infinite positive
slope at `x -> 1`, the hull begins and ends with a single-phase region. A compound that is stable
appears as a hull vertex shared by the tie-line to its left and the tie-line to its right; it
forms no single-phase region. A solution phase or compound is **stable at `(x, T)`** when the hull
passes through its own point there. Everything that is not on the hull (metastable common
tangents, metastable compounds) is not part of the equilibrium diagram.

**Events in a temperature window.** As `T` varies, the sequence of hull pieces (the topology) is
constant except at isolated temperatures, the events. Three kinds of events are reported:

- **Three-phase (invariant) equilibrium.** At `T_inv` one straight line of the hull passes
  through three stable states `(P1, x1)`, `(P2, x2)`, `(P3, x3)` with `x1 < x2 < x3` (any of them
  may be a compound; two of them may be the same solution phase, as in a monotectic). The
  **class** is `"eutectic"` when the middle state `(P2, x2)` is on the hull just above `T_inv`
  (the middle phase is stable there, so on cooling through `T_inv` it decomposes:
  `P2 -> P1 + P3`) and `"peritectic"` when it is on the hull just below `T_inv` (on cooling it
  forms: `P1 + P3 -> P2`). The **name** follows from the class and from which of the three
  phases is the liquid:

  | class | middle phase | outer phases | name |
  | --- | --- | --- | --- |
  | eutectic | liquid | both solid | `"eutectic"` |
  | eutectic | liquid | at least one liquid | `"monotectic"` |
  | eutectic | solid | both solid | `"eutectoid"` |
  | eutectic | solid | at least one liquid | `"metatectic"` |
  | peritectic | solid | one liquid, one solid | `"peritectic"` |
  | peritectic | solid | both liquid | `"syntectic"` |
  | peritectic | solid | both solid | `"peritectoid"` |
  | peritectic | liquid | any | `"inverse_monotectic"` |

- **Congruent point.** At `(x_c, T_c)` two different phases are stable at the same composition:
  either two solution phases `P` and `Q` whose curves are tangent there (`G_P = G_Q` and
  `dG_P/dx = dG_Q/dx` at `x_c`), or a solution phase `P` and a compound `theta` with
  `G_P(x_theta, T_c) = G_theta(T_c)` (then `x_c = x_theta`). A two-phase lens made of the
  tie-lines between the two phases closes at this point; `two_phase_side` is `"below"` when the
  lens lies at temperatures below `T_c` (a congruent maximum, for example congruent melting) and
  `"above"` when it lies above `T_c` (a congruent minimum). On the lens side the hull at `x_c`
  is a single-phase region of the inner phase (or the compound vertex) flanked by the two
  tie-lines of the lens, on the other side it is the outer phase; `phase_above` is the phase
  stable at `x_c` just above `T_c` and `phase_below` the one stable just below.
- **Critical (consolute) point.** At `(x_c, T_c)` a solution phase `P` is stable and
  `d2G_P/dx2 = 0` and `d3G_P/dx3 = 0`: a miscibility gap of `P` (tie-lines with both ends on `P`)
  closes. `gap_side` is `"below"` for an upper consolute point (gap at lower temperatures) and
  `"above"` for a lower consolute point.

Temperatures at which the stable phase at a pure end (`x = 0` or `x = 1`) changes (melting or
allotropic transition of a pure component) are events of the topology but are **not reported**.
Metastable three-phase lines, metastable tangencies and metastable critical points (not on the
hull) are not events and are not reported.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| solution phases | 2 to 4, with distinct names from `liquid`, `alpha`, `beta`, `gamma`, `delta`; exactly one is `liquid` |
| compounds | 0 to 3, distinct names (1 to 12 characters, letters and digits, none equal to a solution-phase name), `x_theta` in `[0.1, 0.9]`, any two at least `0.02` apart |
| `h` of every end member and compound | `-60000` to `60000` J/mol |
| `s` of every end member and compound | `-60` to `60` J/(mol K) |
| `a_k` (k = 0, 1, 2) | `-60000` to `60000` J/mol |
| `b_k` (k = 0, 1, 2) | `-30` to `30` J/(mol K) |
| window `[T_lo, T_hi]` | `250 <= T_lo < T_hi <= 2500`, width `100` to `1200` K |
| requested isotherms | 2 to 6 values, strictly increasing, strictly inside the window |

Every system in the domain satisfies these guarantees:

1. Any two events of the topology (reported or not) are at least `0.5` K apart; every event is at
   least `0.5` K from both window ends and from every requested isotherm.
2. At every requested isotherm: every tie-line has `x_right - x_left >= 1e-4`; every single-phase
   region has `x_hi - x_lo >= 1e-4`; every tie-line end on a solution phase has `x` in
   `[1e-5, 1 - 1e-5]`; and every solution phase that is stable nowhere at that isotherm, and
   every compound that is not a hull vertex there, lies at least `0.05` J/mol above the hull at
   every composition.
3. At every reported event: every composition lies in `[1e-5, 1 - 1e-5]`; at a three-phase
   equilibrium the three compositions are pairwise at least `1e-4` apart.
4. No two solution phases have equal `GA` (or equal `GB`) over an interval of temperature; no
   two phases coincide over an interval of composition.

## 3. System file

A JSON object with exactly these keys:

- `system_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `solution_phases`: list of 2 to 4 objects, each with exactly the keys `name` (string),
  `end_members` (object with exactly the keys `A` and `B`, each an object with exactly the keys
  `h` and `s`, numbers) and `redlich_kister` (list of exactly 3 objects with exactly the keys `a`
  and `b`, numbers, in the order `k = 0, 1, 2`).
- `compounds`: list of 0 to 3 objects, each with exactly the keys `name`, `x_b` (the composition
  `x_theta`), `h`, `s`.
- `window_K`: list of exactly two numbers `[T_lo, T_hi]`.
- `isotherms_K`: list of 2 to 6 numbers.

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision; names are strings equal to the system file's names.

- `system_id`: the system's id, exactly.
- `isotherms`: one object per entry of `isotherms_K`, in the same order, each with exactly the
  keys `temperature_K` (the value exactly as given), `single_phase_regions` and `tie_lines`.
  `single_phase_regions` is the list of the single-phase regions of the hull at that `T` in
  increasing `x`, each with exactly the keys `phase`, `x_lo`, `x_hi` (the first has `x_lo = 0`
  and the last has `x_hi = 1`, exactly). `tie_lines` is the list of the tie-lines in increasing
  `x`, each with exactly the keys `left_phase`, `x_left`, `right_phase`, `x_right` (a compound end
  has its `x_theta` exactly). Empty list if there is no tie-line.
- `invariants`: every three-phase equilibrium with `T_lo < T_inv < T_hi`, in increasing
  `temperature_K`, each with exactly the keys `temperature_K`, `class`, `name` and `phases`, a list
  of exactly three objects with exactly the keys `phase` and `x`, in increasing `x`.
- `congruent_points`: every congruent point in the window, in increasing `temperature_K`, each
  with exactly the keys `temperature_K`, `x`, `phase_above`, `phase_below`, `two_phase_side`.
- `critical_points`: every critical point in the window, in increasing `temperature_K`, each
  with exactly the keys `temperature_K`, `x`, `phase`, `gap_side`.

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that system:

1. The report meets section 4 exactly.
2. At every isotherm the numbers of single-phase regions and of tie-lines equal the reference
   numbers; the numbers of invariants, congruent points and critical points equal the reference
   numbers.
3. Element by element in the stated orders: every phase name, `class`, `name`, `two_phase_side`
   and `gap_side` is equal; every composition (`x_lo`, `x_hi`, `x_left`, `x_right`, `x`) is within
   `1e-8` **absolute** of the reference; every event `temperature_K` is within `1e-7` **relative**
   of the reference. The outer region bounds `0` and `1`, the isotherm temperatures and compound
   compositions are exact.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/tangentdiag.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `system`: a complete system object meeting sections 2 and 3 (a shipped system or one you
  construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"tie_line_count"`, `"two_phase_fraction"`, `"invariant_count"`,
  `"peritectic_count"`, `"critical_count"`.
- `temperature_K`: for `"tie_line_count"` and `"two_phase_fraction"`, a number present in the
  system's `isotherms_K`; `null` otherwise.
- `legacy_value` and `correct_value`: for `"tie_line_count"`, the number of tie-lines at that
  isotherm; for `"two_phase_fraction"`, the sum of `x_right - x_left` over the tie-lines at that
  isotherm (a number); for `"invariant_count"`, the number of invariants in the window; for
  `"peritectic_count"`, the number of invariants of class `"peritectic"`; for
  `"critical_count"`, the number of critical points. Counts are integers.

The verifier runs a pristine copy of the legacy script on the witness system and requires
`legacy_value` to match its report (integers exactly, fractions within `1e-6` absolute), computes
the exact value independently and requires `correct_value` to match it under the same rules, and
requires the two values to differ (integers by at least 1, fractions by more than `1e-6`
absolute). At least three distinct `quantity` values must appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/phasediagram.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/phasediagram.py` on the 6 systems
shipped in `/root/data/systems/` and on 22 held-out systems of the same schema and domain, 28
fresh calls in total. The held-out systems cover: simple eutectics and peritectics between two
terminal solid solutions; lens-shaped diagrams with congruent maxima and minima; miscibility gaps
in solid phases and in the liquid (monotectics, eutectoids, upper and lower consolute points);
stoichiometric compounds that melt congruently, that decompose peritectically, that are stable
only inside part of the window and that are never stable; intermediate solid solutions; several
invariants close in temperature; allotropic transitions of a pure component inside the window;
and windows with no event at all. Their contents are not disclosed.

Each call is `python /root/results/phasediagram.py --system <system.json> --output <report.json>`
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
