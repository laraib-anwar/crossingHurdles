# heterostructure-tunneling-audit

Compute the exact electronic properties of layered semiconductor heterostructures in the
effective-mass approximation (flat and linearly graded or biased layers, each with its own
effective mass, between two contacts): every bound state below the lower contact band edge, the
transmission coefficient at queried energies down to `1e-30`, and every local maximum of the
transmission in an energy window. Then diagnose a legacy quantum-well script by executable
witnesses.

| | |
| --- | --- |
| Domain | physical-sciences / physics / semiconductor-quantum-transport |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Envelope-function calculations of quantum wells, superlattices and resonant-tunnelling diodes are
the daily design tool of semiconductor device physics (nextnano, Silvaco ATLAS QW modules, and
countless group codes). For piecewise-flat and piecewise-linear band profiles the solution is
exact in every layer (exponentials, sines, Airy functions), so every answer has a definite value.
The spec states the model and the definitions and no method.

What a competent solver gets right: a finite square well (`dev` checks reproduce the
transcendental equations to `2e-16` eV), a rectangular barrier (closed form to `7e-16`). Where the
difficulty is, each exercised by several of the 28 structures:

1. **BenDaniel-Duke interface conditions.** `psi'/m`, not `psi'`, is continuous, and the leads
   have their own masses. A single mass everywhere (the `one_mass` control, and the legacy
   script) shifts levels by tens of meV.
2. **Transmission is a current ratio.** `T = (k_R/m_R)/(k_L/m_L)|t|^2`; with different contact
   band edges or masses (biased structures, `model_06`) `|t|^2` alone is wrong (`no_velocity`
   control).
3. **Biased and graded layers are Airy problems.** A staircase of flat steps converges only at
   second order; twenty steps per layer (`staircase` control) are `1e-5` to `6e-3` off in `T`
   and up to `6e-4` eV off in the levels.
4. **Opacity without overflow.** Thick barriers give `T` down to `1e-30`, and Airy arguments of
   magnitude several hundred appear in gently sloped layers; transfer matrices with unscaled
   hyperbolic or Airy functions overflow or lose the physical solution. The exponents have to be
   carried separately.
5. **Every bound state, certified.** Double wells have pairs split by as little as `1.8e-5` eV
   (`held_03`) and wells hold up to 12 levels (`held_09`); an energy scan misses half of a pair. Counting nodes
   (oscillation theorem) isolates every level; finite differences in a box (`box_fd` control)
   are `2e-4` to `5e-3` eV off.
6. **Every transmission maximum, exactly.** Superlattice windows hold up to 9 maxima, at
   least `2e-4` eV apart (guarantee 3); a 1 meV scan (`coarse_scan`) misses and shifts them, and
   each maximum must be refined to `1e-8` eV.
7. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `qwell.py` is a plausible group script: one effective mass, finite differences
on a 0.1 nm grid with hard walls 10 nm into the contacts, five-step staircases for graded layers,
`|t|^2` from plane-wave transfer matrices written in absolute positions, maxima from a 1 meV scan.

## Reference solution

`solution/hetero.py`:

- **Exact layer matrices, scaled.** The state `(psi, psi'/m)` is continuous at every interface;
  each layer maps it with a unit-determinant transfer matrix built from trigonometric or
  hyperbolic functions (flat layers) or Airy functions (sloped layers). Hyperbolic functions are
  written with decaying exponentials and Airy functions of positive argument through their scaled
  forms (`airye`), the large exponent kept as a separate log scale, so no product overflows and
  the dominant solution is never lost.
- **Bound states by node counting.** The number of bound states below `E` equals the number of
  nodes of the solution decaying at `-infinity`. Nodes are counted exactly: inside a layer by
  sampling `psi` more finely than the minimum node spacing `pi / k_max` (Sturm comparison), in the
  right lead from the decomposition into growing and decaying exponentials. Bisection on the
  count isolates each level, which is then the unique root of the direction mismatch with the
  decaying right-lead solution.
- **Transmission** by carrying the outgoing right-lead wave leftwards (the stable direction for
  the physical solution) and splitting it into incident and reflected waves in the left lead.
- **Maxima** from a `1e-5` eV scan of `T`, each refined as the root of a fourth-order central
  difference of `T` whose step is set from the local curvature.
- **Checks in the dev pipeline** (`tools/validate_oracle.py`): closed-form well and barrier,
  Richardson-extrapolated fine staircases reproduce the Airy layers to `1e-12` in `T` and `1e-9`
  eV in the levels.

`solution/diagnose.py` runs the legacy script and the program on the shipped structures and
writes witnesses for the diagnosis quantities; nothing is stored.

## Verification

Every expected value in `tests/expected.json` comes from Reference A (`tests/reference/reference.py`),
an independent implementation built without access to the oracle: one global linear system for
the whole structure with basis functions normalised at the layer ends (scaled exponentials,
scaled Airy functions with its own asymptotic modulus/phase series for large arguments), the
sign of its determinant tracked consistently so bound states are its roots, an independent node
count (Prufer phase in flat layers, Airy phase in sloped layers) to certify and isolate every
level, transmission from the same linear system, and maxima from the sign of the analytic
`dT/dE` (differentiated linear system) refined by Brent. Reference B (`refB/referee.py` in the
dev folder) shares nothing with special functions or closed-form layer matrices: a high-order
Taylor-series integrator inside every layer (with the energy derivative), rescaled every 32
steps, Prufer-angle node counts, a self-precision rerun at half step, and a long-double mode.

| Check | Result |
| --- | --- |
| Oracle vs Reference A, 28 structures | every count equal; worst bound-state energy 1.9e-15 eV, transmission 1.3e-13 relative, maximum energy 9.9e-11 eV, transmission at maxima 3.9e-14 relative |
| Reference A vs a decimal-arithmetic Taylor checker and closed forms | bound states 3.3e-16 eV (finite well 9e-17, double well with a 4.7e-6 eV splitting 8e-17), `T` 1.5e-13 (rectangular barrier down to 1.2e-26: 2e-15), maxima 4.8e-14 eV |
| Reference B referee, 28 structures | 28 pass with no domain warning: bound states 5e-15 eV, `T` 1.6e-13, maximum energies 4.2e-11 eV, current conservation 1e-13; its own half-step and long-double reruns agree to 5e-14; negative tests (3e-9 eV, 3e-9 relative, 3e-8 eV shifts, dropped or added states and maxima) all fail |
| Totals graded | 118 bound states (up to 12 per structure, closest pair 1.8e-5 eV, 9 structures with none), 142 transmission values (down to 9.3e-30), 89 maxima (up to 9 per window, one window with none); 9 structures with sloped layers, 10 with different contacts |
| Oracle in the environment image (`solve.sh`) | base case + diagnosis in 16 s; witnesses for all five quantities: `bound_count` (model_03), `transmission`, `bound_energy`, `maxima_count`, `maximum_energy` (model_01) |
| Verifier on the oracle artifacts | 30 passed, reward 1, 51 s; fresh calls 0.8 to 3.2 s |
| Verifier on empty `/root/results` | 30 failed, reward 0 |
| Verifier with a FIFO as `hetero.py` | 30 failed, reward 0 |
| Domain | all 28 structures pass the verifier's `validate_structure`; guarantees 1 to 3 screened by the generator at two scan resolutions and re-checked by the referee |

### Controls (wrong methods, graded with the verifier's comparison against Reference A)

| Control | Shortcut | Fails |
| --- | --- | --- |
| `legacy` | the shipped script | 28 / 28 |
| `one_mass` | left-contact mass everywhere | 28 / 28 (levels off by 8.5e-3 to 0.23 eV) |
| `coarse_scan` | maxima at 1 meV grid points | 27 / 28 (every window with a maximum; 1.4e-4 to 5e-4 eV off) |
| `box_fd` | finite differences, 0.05 nm grid, walls 10 nm into the contacts | 19 / 28 (every structure with a bound state; 2.3e-4 to 4.5e-3 eV off) |
| `no_velocity` | `T = |t|^2` | 10 / 28 (every structure with different contacts; 9e-2 to 2.3 relative) |
| `staircase` | 20 flat steps per sloped layer | 9 / 28 (every structure with a sloped layer; levels 7.8e-7 to 6.1e-4 eV, `T` 1.5e-5 to 6.3e-3) |

### Tolerances

| Quantity | Tolerance | Method spread (oracle vs Reference A / referee) | Nearest wrong answer |
| --- | --- | --- | --- |
| bound-state energies | 1e-9 eV | 1.9e-15 / 5e-15 eV | 7.8e-7 eV (`staircase`) |
| transmission `T` | 1e-9 relative | 1.3e-13 / 1.6e-13 | 1.5e-5 (`staircase`) |
| maximum energies | 1e-8 eV | 9.9e-11 / 4.2e-11 eV | 8.5e-7 eV (`staircase`) |
| `T` at maxima | 1e-9 relative | 3.9e-14 | as `T` |

The tolerances sit two to six orders of magnitude above the spread between independent exact
methods and two or more orders below the closest wrong method. The maximum-energy tolerance is
ten times looser than the level tolerance because a maximum is a stationary point: a
derivative-free refinement reaches it only to about `sqrt(eps)` times the peak width.

### Coverage of the 28 structures

| Structure | layers | contact masses; band edges | bound states | closest pair (eV) | smallest queried `T` | maxima | structure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `held_01` | 5 (0 sloped) | 0.118 / 0.118; 0.575 / 0.575 eV | 6 | 2.8e-02 | 3.9e-01 | 1 | single confined well |
| `held_02` | 7 (0 sloped) | 0.0953 / 0.0953; 0.206 / 0.206 eV | 8 | 2.0e-03 | 9.8e-02 | 4 | multiple confined wells |
| `held_03` | 5 (0 sloped) | 0.0962 / 0.0962; 0.508 / 0.508 eV | 6 | 1.8e-05 | 2.8e-01 | 2 | double well, pair split by less than 2e-5 eV |
| `held_04` | 5 (0 sloped) | 0.087 / 0.087; 0.872 / 0.872 eV | 4 | 5.0e-03 | 6.6e-01 | 1 | double well, several pairs |
| `held_05` | 2 (1 sloped) | 0.0857 / 0.0857; 0.842 / 0.798 eV | 8 | 9.5e-02 | 4.8e-01 | 2 | triangular well, eight or more levels |
| `held_06` | 2 (1 sloped) | 0.0879 / 0.0879; 0.412 / 0.302 eV | 3 | 7.4e-02 | 8.9e-01 | 1 | shallow triangular well |
| `held_07` | 5 (5 sloped) | 0.0614 / 0.0614; 0 / -0.155 eV | 0 | - | 4.8e-08 | 2 | biased RTD, tunnelling queries |
| `held_08` | 5 (5 sloped) | 0.0708 / 0.0708; 0 / -0.148 eV | 1 | - | 4.7e-05 | 1 | RTD with a well below the leads |
| `held_09` | 13 (0 sloped) | 0.108 / 0.108; 0.596 / 0.596 eV | 12 | 4.4e-04 | 1.7e-08 | 7 | superlattice, four or more maxima |
| `held_10` | 11 (0 sloped) | 0.0687 / 0.0687; 0 / 0 eV | 0 | - | 7.0e-15 | 9 | superlattice, eight or more maxima |
| `held_11` | 3 (0 sloped) | 0.0617 / 0.0617; 0 / 0 eV | 0 | - | 2.3e-05 | 3 | barriers only: no bound state |
| `held_12` | 3 (0 sloped) | 0.0727 / 0.0727; 0 / 0 eV | 0 | - | 1.3e-04 | 0 | no bound state, window with no maximum |
| `held_13` | 5 (0 sloped) | 0.0702 / 0.0702; 0 / 0 eV | 0 | - | 2.0e-26 | 8 | thick barriers, transmission below 1e-22 |
| `held_14` | 5 (0 sloped) | 0.0698 / 0.0698; 0 / 0 eV | 0 | - | 8.1e-17 | 3 | thick barriers |
| `held_15` | 3 (0 sloped) | 0.0689 / 0.286; 0.0479 / 0.0772 eV | 2 | 1.3e-01 | 9.2e-03 | 7 | lead contrast with a bound state |
| `held_16` | 3 (0 sloped) | 0.071 / 0.366; 0.00638 / 0.0455 eV | 1 | - | 2.2e-09 | 2 | lead contrast |
| `held_17` | 3 (2 sloped) | 0.0839 / 0.0839; 0.996 / 0.996 eV | 10 | 7.8e-02 | 9.9e-01 | 2 | graded barriers around a well |
| `held_18` | 3 (2 sloped) | 0.109 / 0.109; 0.564 / 0.564 eV | 9 | 4.7e-02 | 7.3e-01 | 3 | graded barriers, several maxima |
| `held_19` | 5 (5 sloped) | 0.0605 / 0.0605; 0 / -0.0236 eV | 0 | - | 1.2e-03 | 3 | RTD, several maxima |
| `held_20` | 7 (0 sloped) | 0.141 / 0.141; 0.94 / 0.94 eV | 10 | 1.4e-03 | 2.7e-03 | 4 | confined wells with maxima above |
| `held_21` | 13 (0 sloped) | 0.138 / 0.138; 0.96 / 0.96 eV | 12 | 2.5e-04 | 7.2e-06 | 3 | superlattice with bound miniband |
| `held_22` | 5 (0 sloped) | 0.115 / 0.115; 0.847 / 0.847 eV | 8 | 4.4e-04 | 3.7e-03 | 2 | double well, close pair and maxima |
| `model_01` | 3 (0 sloped) | 0.0831 / 0.0831; 0.443 / 0.443 eV | 4 | 1.1e-01 | 4.7e-01 | 1 | quantum wells confined by the lead band edge (base case) |
| `model_02` | 5 (5 sloped) | 0.0604 / 0.0604; 0 / -0.163 eV | 0 | - | 2.5e-06 | 1 | resonant-tunnelling diode under bias |
| `model_03` | 5 (0 sloped) | 0.115 / 0.115; 0.912 / 0.912 eV | 8 | 7.0e-04 | 1.4e-03 | 3 | double well with closely spaced levels |
| `model_04` | 2 (1 sloped) | 0.138 / 0.138; 1.08 / 0.982 eV | 6 | 1.3e-01 | 3.9e-01 | 1 | triangular well with many levels |
| `model_05` | 5 (0 sloped) | 0.0707 / 0.0707; 0 / 0 eV | 0 | - | 9.3e-30 | 7 | thick double barrier, tiny transmission |
| `model_06` | 3 (0 sloped) | 0.0652 / 0.522; 0.0249 / 0.0608 eV | 2 | 1.2e-01 | 9.5e-26 | 7 | different lead masses and band edges |

### Reproduction (dev folder `turing/tbScience/heterostructure-tunneling-audit-dev`)

`tools/gen_structures.py` (28-slot plan, guarantee screening at two scan resolutions including
the verifier's domain check), `tools/validate_oracle.py`, `tools/agree.py`, `controls/controls.py`,
`tools/controls_study.py`, `tools/docker_chain.sh`, `refA/` (Reference A with METHOD.md and tests),
`refB/` (referee with METHOD.md, tests and `run_set.sh`), `evidence/` (Docker logs, CTRF, rewards),
`tools/build_zip.py`.
