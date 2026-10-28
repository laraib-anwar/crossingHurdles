# FRAME_SPEC: statics, natural frequencies and harmonic response of plane frames

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Frame.** A plane frame in the `(x, y)` plane made of straight prismatic members rigidly
connected at nodes. Node `n` has the three degrees of freedom `ux`, `uy` (translations, m) and
`rz` (rotation, rad, counterclockwise). A support constrains any subset of a node's degrees of
freedom to zero. A node may carry a lumped mass `m_n` (kg, acting on `ux` and `uy`, no rotary
inertia). Member `k` joins nodes `i` and `j`, has length `L` (from the node coordinates), Young's
modulus `E` (Pa), cross-section area `A` (m^2), second moment of area `I` (m^4) and density
`rho` (kg/m^3); its mass per unit length is `rho A`. Members are Euler-Bernoulli beams with
axial deformation: no shear deformation, no rotary inertia, no damping, no axial-bending
coupling, small displacements, mass distributed along the member.

**Statics.** Nodal loads `Fx`, `Fy` (N) and `Mz` (N m) act at nodes; a uniform member load
`wx`, `wy` (N/m, global directions) acts along a member. The static displacements are those of
the exact stiffness method: the member stiffness matrix of the axial bar and the Euler-Bernoulli
beam, and the uniform member load replaced by its exact fixed-end actions (axial and transverse
components in the member's local axes, end moments `+-q_t L^2 / 12`). Reported: the
displacements `ux`, `uy`, `rz` of the queried nodes.

**Natural frequencies.** The undamped free vibration of the frame with its distributed member
mass and lumped nodal masses. The natural frequencies `f` (Hz) are the values at which a
non-trivial motion `exp(i 2 pi f t)` exists: every member obeys the exact axial equation
`EA u'' = -rho A omega^2 u` and bending equation `EI v'''' = rho A omega^2 v` (`omega = 2 pi f`),
with continuity of displacements and rotations and equilibrium of forces and moments at every
node (including the inertia of lumped masses) and the support conditions. **All** natural
frequencies count, including those of modes in which every node is at rest (a member vibrating
between two nodes that do not move). Natural frequencies are counted with multiplicity; the
report lists the lowest `n_modes` of them in increasing order, and `count_below` is the number of
natural frequencies not exceeding `f_max`.

**Harmonic response.** A harmonic nodal force or moment `P cos(2 pi f_h t)` at node `n`, degree
of freedom `d` (an unconstrained one), at a frequency `f_h` that is not a natural frequency,
produces the steady-state motion `U cos(2 pi f_h t)` at every degree of freedom, with the same exact member equations (distributed
mass). Reported: the signed amplitude `U` (m or rad) at the queried node and degree of freedom.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| nodes | 2 to 12; coordinates in `[-30, 30]` m |
| members | 1 to 16; `L` from `0.5` to `20` m |
| `E` | `2e10` to `2.1e11` Pa; `A` `1e-4` to `5e-2` m^2; `I` `1e-7` to `5e-3` m^4; `rho` `1500` to `8000` kg/m^3 |
| lumped masses | `0` to `5e4` kg |
| loads | `|Fx|, |Fy|` up to `1e6` N, `|Mz|` up to `1e6` N m, `|wx|, |wy|` up to `1e5` N/m |
| `n_modes` | 3 to 12; `f_max` `1` to `500` Hz |
| harmonic queries | 1 to 4 |

Every frame in the domain satisfies these guarantees:

1. The frame is properly supported: with the supports applied, the static stiffness matrix is
   positive definite (no mechanism, no rigid-body motion).
2. Consecutive natural frequencies up to and including the `(n_modes + 1)`-th differ by at least
   `1e-6` relative; `f_max` differs from every natural frequency by at least `1e-6` relative;
   every harmonic frequency `f_h` differs from every natural frequency by at least `1e-2`
   relative.
3. For every member, the bending parameter `lambda = L (rho A omega^2 / (E I))^(1/4)` and the
   axial parameter `alpha = omega L sqrt(rho / E)` do not exceed `40` at the largest frequency
   among the `n_modes`-th natural frequency, `f_max` and the harmonic frequencies.
4. Every harmonic load acts on an unconstrained degree of freedom, and every reported static
   displacement and harmonic amplitude is non-zero with magnitude at least `1e-9` times the
   largest magnitude in its group; the four groups are the static translations (`ux`, `uy`),
   the static rotations (`rz`), the harmonic translational amplitudes and the harmonic
   rotational amplitudes.

## 3. Frame file

A JSON object with exactly these keys:

- `frame_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `nodes`: list of objects with exactly the keys `id` (integer, `1..N` in order), `x`, `y`
  (numbers), `mass_kg` (number), `support` (object with exactly the keys `ux`, `uy`, `rz`,
  booleans, `true` = constrained).
- `members`: list of objects with exactly the keys `id` (integer, `1..M` in order), `i`, `j`
  (node ids, different), `E`, `A`, `I`, `rho` (numbers).
- `nodal_loads`: list of objects with exactly the keys `node`, `Fx`, `Fy`, `Mz`; several entries
  for one node add up.
- `member_loads`: list of objects with exactly the keys `member`, `wx`, `wy` (force per unit
  member length); several entries for one member add up.
- `static_query_nodes`: list of 1 to 6 node ids.
- `n_modes`: integer; `f_max_Hz`: number.
- `harmonic_queries`: list of objects with exactly the keys `load_node`, `load_dof` (`"ux"`,
  `"uy"` or `"rz"`), `amplitude` (N or N m), `f_Hz`, `response_node`, `response_dof`.

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision.

- `frame_id`: the frame's id, exactly.
- `static`: one object per entry of `static_query_nodes`, in order, with exactly the keys `node`
  (as given), `ux`, `uy`, `rz`.
- `frequencies_Hz`: list of exactly `n_modes` numbers, the lowest natural frequencies in
  increasing order.
- `count_below`: integer, the number of natural frequencies not exceeding `f_max_Hz`.
- `harmonic`: one object per entry of `harmonic_queries`, in order, with exactly the keys
  `load_node`, `load_dof`, `amplitude`, `f_Hz`, `response_node`, `response_dof` (as given) and
  `U`.

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that frame:

1. The report meets section 4 exactly.
2. `count_below` equals the reference.
3. Every natural frequency is within `1e-9` relative of the reference; every static
   displacement and harmonic amplitude `v` satisfies `|v - v_ref| <= 1e-9 max(|v_ref|, S)` where
   `S` is the largest magnitude of the reference values of its group in the report (the four
   groups of section 2, guarantee 4).

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/framefreq.py` is the inherited script (same command line, same report keys).
`/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of 3 to 8
objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `frame`: a complete frame object meeting sections 2 and 3 (a shipped frame or one you
  construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"frequency"`, `"count_below"`, `"static"`, `"harmonic"`.
- `index`: for `"frequency"`, the 0-based index into `frequencies_Hz`; for `"static"`, the
  0-based index into `static_query_nodes` together with the field: the value `index` is then an
  object with exactly the keys `query` (integer) and `dof` (`"ux"`, `"uy"` or `"rz"`); for
  `"harmonic"`, the 0-based index into `harmonic_queries`; `null` for `"count_below"`.
- `legacy_value` and `correct_value`: the frequency (Hz), the count (integer), the displacement
  or the amplitude.

The verifier runs a pristine copy of the legacy script on the witness frame and requires
`legacy_value` to match its report (integers exactly, numbers under the section 5 rule of their
kind), computes the exact value independently and requires `correct_value` to match it under the
same rules, and requires the two values to differ (integers by at least 1, numbers by more than
`1e-6` under the same scale). At least three distinct `quantity` values must appear. Every witness
must pass.

## 7. Execution contract

The verifier evaluates `/root/results/framedyn.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/framedyn.py` on the 6 frames
shipped in `/root/data/frames/` and on 22 held-out frames of the same schema and domain, 28
fresh calls in total. The held-out frames cover: cantilevers and simply supported beams of
several members, portal frames of one to three bays and storeys, frames with lumped masses,
members between two fully fixed nodes (member-local modes), nearly symmetric frames with
closely spaced frequencies, slender and stocky members, distributed loads with fixed-end
moments, and harmonic loads above and below the first natural frequency. Their contents are not
disclosed.

Each call is `python /root/results/framedyn.py --frame <frame.json> --output <report.json>` and
must exit with status 0 within 120 seconds of wall-clock time measured by the verifier from
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
