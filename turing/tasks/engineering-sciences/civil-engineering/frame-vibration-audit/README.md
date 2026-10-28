# frame-vibration-audit

Compute the exact structural response of plane frames of Euler-Bernoulli members with axial
deformation and distributed mass: static nodal displacements under nodal and uniform member
loads, every natural frequency of free vibration (member-local modes included), the number of
frequencies below a limit, and the undamped steady-state response to a harmonic nodal load. Then
diagnose a legacy lumped-mass finite element script by executable witnesses.

| | |
| --- | --- |
| Domain | engineering-sciences / civil-engineering / structural-dynamics |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Frame statics and vibration are the core of structural engineering practice, and for prismatic
Euler-Bernoulli members the problem is exactly solvable: the member dynamic stiffness is a closed
form in `lambda = L (rho A omega^2 / EI)^(1/4)` and `alpha = omega L sqrt(rho/E)`, so every
natural frequency is a definite root of a transcendental determinant. The spec states the model
and the definitions and no method.

What a competent solver gets right: the statics (the stiffness method with fixed-end actions is
textbook), and the first few frequencies of a simple frame by a fine finite element model. Where
the difficulty is, each exercised by several of the 28 frames:

1. **Exactness.** Frequencies are graded to `1e-9` relative. A cubic finite element model
   converges as `h^4`; one element per member (`fe1_consistent` control) is percent-level wrong,
   four per member (`fe4_consistent`) is still `3e-5` to `8e-2` off on the higher modes. The
   answer needs the exact dynamic stiffness (or a converged extrapolation of a very fine mesh).
2. **Counting, not just root finding.** The dynamic stiffness determinant has poles at the
   clamped-clamped member frequencies, and modes in which no node moves (a member between two
   fully fixed nodes: `model_03`, `held_07`, `held_08`) are invisible to the assembled matrix.
   The Wittrick-Williams count `J = J0 + s{K(omega)}` is the standard remedy; dropping `J0`
   (`no_j0` control) skips those modes and the count, and misorders everything above them.
3. **Close pairs.** Nearly symmetric frames (`model_04`, `held_09`, `held_10`, `held_21`) have
   frequencies within `6e-3` to `1e-2` of each other, which coarse sign-change scans on the
   determinant merge or miss.
4. **Small-`lambda` cancellation.** Stiff short members at low frequencies have `lambda < 1`,
   where `1 - cos(lambda) cosh(lambda)` loses up to ten digits; the bending functions need a
   series or extended precision there.
5. **Axial deformation and fixed-end actions.** Suppressing axial deformation (`no_axial`
   control), the classic hand-analysis assumption, changes frequencies by `7e-3` to `3.7` and
   displacements by up to a factor 2; uniform member loads must carry their fixed-end moments (`lumped_loads` control
   fails every loaded frame on the rotations).
6. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `framefreq.py` is a plausible office script: one two-node element per member,
member mass lumped at the ends (massless rotations condensed out), uniform loads as end forces
without moments, harmonic response from the same lumped model.

## Reference solution

`solution/framedyn.py`:

- **Exact member dynamic stiffness** (axial and Euler-Bernoulli bending), with the six bending
  functions evaluated in 45-digit decimal arithmetic for `lambda < 1.5` to defeat cancellation.
- **Wittrick-Williams counting**: `J(omega) = sum_members [J0_bending + J0_axial] + s{K(omega)}`
  with `J0` from the clamped-clamped root table (`1 = cos lambda cosh lambda`, `sin alpha = 0`)
  and `s` from an `LDL^T` factorisation without pivoting of the diagonally scaled matrix in
  extended precision (the first draft lost `1e-10` of a frequency at `lambda = 12` to pivot growth,
  which the referee caught). Each natural frequency is isolated and
  located by bisection on `J` to a relative width of `1e-15`, so poles, member-local modes and
  near-repeated roots are all handled by counting rather than by root finding.
- **Statics**: exact stiffness method with fixed-end actions of the uniform loads in the member's
  local axes. **Harmonic**: `K(omega_h) U = F`.
- **Checks in the dev pipeline** (`tools/validate_oracle.py`): cantilever, simply supported and
  clamped-clamped closed forms to 12 digits, cantilever tip deflection under point and uniform
  load exact, harmonic reciprocity to `1e-16`.

`solution/diagnose.py` runs the legacy script and the program on the shipped frames and writes
witnesses for the diagnosis quantities; nothing is stored.

## Verification

Every expected value in `tests/expected.json` comes from Reference A (`tests/reference/reference.py`),
an independent implementation built without access to the oracle: every member is a six-state
first-order system whose propagator is a Taylor-series matrix exponential, marched over
segments with re-orthonormalisation, assembled into one global linear system in the member
end-state coordinates and the node displacements; natural frequencies are the sign-tracked roots
of its determinant, bracketed and counted by an independent p-version finite element model
(Hermite/Lagrange functions plus integrated-Legendre bubbles) so that no root is skipped and
member-local modes are kept; statics from the particular solution of the uniform load with
exact rational refinement. Reference B (`refB/referee.py` in the dev folder) shares nothing with
closed-form dynamic stiffness: conforming cubic Hermite / cubic Lagrange finite elements on five
nested meshes with exact rational element matrices, long-double Rayleigh-Ritz refinement (plain
double loses `1e-8` to rigid-body rounding), Romberg extrapolation with a verified order of 4
(6 for the axial modes), Sylvester inertia counts on two orderings, and a refusal to pass when
its own uncertainty exceeds `1e-7`.

| Check | Result |
| --- | --- |
| Oracle vs Reference A, 28 frames | every `count_below` equal; worst frequency 4.1e-13 relative, static displacement 1.9e-13 and harmonic amplitude 2.5e-13 of their scales |
| Reference A vs a 60-digit decimal re-solve and closed forms | frequencies 1e-15 (cantilever, simply supported, clamped-clamped member modes), statics 1e-15 of scale, harmonic 5e-14; reciprocity 1e-15 |
| Reference B referee, 28 frames | 28 pass with no domain warning: frequencies 4.1e-13 (its own uncertainty 1.1e-11), statics 1.9e-13, harmonic 1.9e-13; negative tests (3e-9 shifts, dropped frequency, count off by one, extra key) all fail |
| Totals graded | 215 natural frequencies (3 frames with member-local modes, closest pair 5.7e-3 relative), 189 static values (all 28 frames carry member loads), 57 harmonic amplitudes (4 frames with lumped masses), `count_below` up to 10, `lambda`/`alpha` up to 12.1 |
| Oracle in the environment image (`solve.sh`) | base case + diagnosis in 16 s; witnesses for all four quantities (model_01) |
| Verifier on the oracle artifacts | 30 passed, reward 1, 49 s; fresh calls 0.9 to 2.4 s |
| Verifier on empty `/root/results` | 30 failed, reward 0 |
| Verifier with a FIFO as `framedyn.py` | 30 failed, reward 0 |
| Domain | all 28 frames pass the verifier's `validate_frame`; guarantees 1 to 4 screened by the generator and re-checked by both references (one frame that queried a pinned node and five with harmonic loads on supported degrees of freedom were caught by the referee and regenerated) |

### Controls (wrong methods, graded with the verifier's comparison against Reference A)

| Control | Shortcut | Fails |
| --- | --- | --- |
| `legacy` | the shipped script | 28 / 28 |
| `fe1_consistent` | one cubic element per member, consistent mass | 28 / 28 (frequencies 3.3e-3 to 3.1 off) |
| `fe4_consistent` | four cubic elements per member | 28 / 28 (3.2e-5 to 7.9e-2) |
| `no_axial` | axial deformation suppressed | 28 / 28 (frequencies 7.3e-3 to 3.7, statics 4.2e-5 to 1.0) |
| `lumped_loads` | member loads as end forces without fixed-end moments | 27 / 28 (statics 9.8e-3 to 7.4 of scale) |
| `no_j0` | Wittrick-Williams without the member-local term | 21 / 28 (12 never reach `n_modes`, 9 misorder from 5.8e-2) |

### Tolerances

| Quantity | Tolerance | Method spread (oracle vs Reference A / referee) | Nearest wrong answer |
| --- | --- | --- | --- |
| natural frequencies | 1e-9 relative | 4.1e-13 / 4.1e-13 | 3.2e-5 (`fe4_consistent`) |
| static displacements | 1e-9 of the group scale | 1.9e-13 / 1.9e-13 | 4.2e-5 (`no_axial`) |
| harmonic amplitudes | 1e-9 of the group scale | 2.5e-13 / 1.9e-13 | 4.3e-8 (`fe4_consistent`, one query 1.3 % from a resonance) |

The tolerances sit more than three orders of magnitude above the spread of the independent
exact methods and at least an order below the closest wrong method.

### Coverage of the 28 frames

| Frame | nodes / members | n_modes | f_1 to f_n (Hz) | closest pair (rel) | count_below | member-local modes | member loads / masses | harmonic | structure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `held_01` | 4 / 3 | 12 | 4.859 to 777.5 | 4.6e-02 | 9 | - | 2 / 0 | 1 | cantilever beam |
| `held_02` | 5 / 4 | 4 | 17.26 to 147 | 6.2e-02 | 4 | - | 2 / 0 | 3 | simply supported beam with distributed load |
| `held_03` | 6 / 6 | 3 | 13.31 to 77.94 | 4.4e-01 | 1 | - | 4 / 0 | 4 | two-bay or two-storey portal frame |
| `held_04` | 9 / 10 | 9 | 6.368 to 80.09 | 2.8e-02 | 1 | - | 6 / 0 | 3 | multi-bay multi-storey frame |
| `held_05` | 12 / 14 | 9 | 0.5748 to 31.27 | 1.3e-02 | 4 | - | 7 / 3 | 3 | frame with lumped masses |
| `held_06` | 9 / 10 | 9 | 1.04 to 43.17 | 3.4e-02 | 6 | - | 7 / 3 | 1 | larger frame with lumped masses |
| `held_07` | 6 / 4 | 11 | 38.76 to 450.1 | 8.9e-03 | 5 | yes | 2 / 0 | 4 | member-local modes within the count |
| `held_08` | 6 / 4 | 7 | 19.94 to 142.3 | 8.7e-02 | 7 | yes | 3 / 0 | 1 | member-local modes |
| `held_09` | 4 / 3 | 6 | 34.4 to 256.9 | 8.9e-03 | 4 | - | 2 / 0 | 4 | close pair of frequencies |
| `held_10` | 4 / 3 | 8 | 20.9 to 347.6 | 7.7e-03 | 8 | - | 2 / 0 | 2 | close pair and distributed loads |
| `held_11` | 4 / 3 | 9 | 46.38 to 2732 | 2.0e-02 | 3 | - | 1 / 0 | 1 | stocky members |
| `held_12` | 6 / 5 | 11 | 3.223 to 330.4 | 8.8e-02 | 8 | - | 2 / 0 | 1 | slender beam, many modes below f_max |
| `held_13` | 8 / 7 | 11 | 2.403 to 79.61 | 2.7e-02 | 9 | - | 4 / 0 | 1 | polygonal arch |
| `held_14` | 7 / 6 | 10 | 41.48 to 448.1 | 5.5e-02 | 10 | - | 2 / 0 | 1 | loaded polygonal arch |
| `held_15` | 8 / 13 | 10 | 18.8 to 123.9 | 4.6e-02 | 4 | - | 6 / 0 | 2 | triangulated frame |
| `held_16` | 8 / 13 | 6 | 25.46 to 44.22 | 1.8e-02 | 6 | - | 8 / 0 | 1 | larger triangulated frame |
| `held_17` | 8 / 7 | 5 | 4.209 to 28.73 | 1.5e-01 | 4 | - | 5 / 0 | 2 | harmonic load below the first mode |
| `held_18` | 9 / 10 | 9 | 15.66 to 199.8 | 4.0e-02 | 6 | - | 6 / 0 | 3 | harmonic load above the first mode |
| `held_19` | 3 / 2 | 5 | 19.27 to 301.3 | 2.0e-01 | 4 | - | 1 / 0 | 2 | simply supported beam |
| `held_20` | 3 / 2 | 11 | 7.457 to 1048 | 9.8e-02 | 4 | - | 2 / 0 | 1 | cantilever with distributed load |
| `held_21` | 6 / 5 | 8 | 1.438 to 57.61 | 5.6e-03 | 6 | - | 1 / 3 | 3 | masses and a close pair |
| `held_22` | 12 / 15 | 4 | 2.875 to 17.67 | 9.9e-02 | 4 | - | 7 / 0 | 1 | large frame |
| `model_01` | 8 / 9 | 4 | 4.498 to 28.67 | 1.1e-01 | 3 | - | 7 / 0 | 4 | single-storey portal frame (base case) |
| `model_02` | 5 / 4 | 11 | 4.114 to 669.8 | 9.3e-02 | 9 | - | 1 / 0 | 2 | multi-member cantilever |
| `model_03` | 6 / 4 | 7 | 14.55 to 132.4 | 1.5e-01 | 7 | yes | 2 / 0 | 1 | member between two fixed nodes: member-local modes |
| `model_04` | 4 / 3 | 11 | 47.68 to 922.4 | 9.7e-03 | 6 | - | 1 / 0 | 2 | nearly symmetric frame with close frequencies |
| `model_05` | 9 / 10 | 3 | 7.85 to 40.75 | 2.8e-01 | 2 | - | 6 / 4 | 2 | frame with lumped masses, harmonic load above the first mode |
| `model_06` | 6 / 9 | 5 | 91.42 to 298.2 | 1.5e-01 | 5 | - | 2 / 0 | 1 | triangulated frame with rigid joints |

### Reproduction (dev folder `turing/tbScience/frame-vibration-audit-dev`)

`tools/gen_frames.py` (28-slot plan, guarantee screening including the verifier's domain check),
`tools/validate_oracle.py`, `tools/agree.py`, `controls/controls.py`, `tools/controls_study.py`,
`tools/docker_chain.sh`, `refA/` (Reference A with METHOD.md and tests), `refB/` (referee with
METHOD.md, tests and `run_set.sh`), `evidence/` (Docker logs, CTRF, rewards), `tools/build_zip.py`.
