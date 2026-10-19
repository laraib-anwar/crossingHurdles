# anion-breakthrough-audit

Compute the exact effluent history of a fixed-bed anion exchanger (chloride, nitrate, sulfate,
bicarbonate; constant separation factors; local equilibrium; plug flow) for a run with one feed
or one feed change: every shock, every spreading wave, every plateau, the nitrate peak, the
first exceedance of the nitrate limit and sampled compositions. Then diagnose a legacy
breakthrough script by executable witnesses.

| | |
| --- | --- |
| Domain | engineering-sciences / chemical-engineering / separation-processes |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

A utility runs a chloride-form strong-base resin to remove nitrate from groundwater that also
carries sulfate and bicarbonate. Sulfate is held more strongly than nitrate, so late in the run
the sulfate front displaces nitrate already on the resin and the effluent nitrate rises above the
influent value, often two to three times (2.36 meq/L against a 0.7 meq/L feed in the base case).
This chromatographic peaking ("nitrate dumping") is a documented drinking-water hazard
(Clifford and Weber; Clifford's chapter in AWWA *Water Quality and Treatment*), and the safe run
length is set by when the peak arrives, not by when nitrate first appears. Process engineers
compute this with equilibrium theory, which for constant separation factors is exactly solvable:
the problem is a system of first-order hyperbolic conservation laws of Temple class, whose
entropy solution is a sequence of shocks and spreading waves with compositions fixed by Riemann
invariants (Helfferich-Klein h-transformation, equivalent to Rhee-Aris-Amundson for Langmuir
systems). The spec states the model and the required solution concept and no method.

What a competent solver gets right: the roots, the all-shock chloride-form base case, units,
schema. Where the difficulty is, each exercised by several of the 28 recipes:

1. **Exact event positions.** Front positions in bed volumes to 2e-4 relative. A finite-volume
   solver smears every front by numerical dispersion; the all-shock and legacy controls below
   miss by 7e-4 and more, and the two shocks of `held_09` are 0.24 BV (7.4e-4 relative) apart.
2. **Shock or spreading wave.** The kind is set by the direction of the wave's own invariant,
   not by which ion is "favourable"; pre-loaded resins (sulfate or bicarbonate from a previous
   cycle) and complete elution give mixed structures. Counts of shocks and transitions are graded
   exactly.
3. **Family is not ion.** Plateau compositions follow from the invariants; a component-wise
   material balance gives the right final state and wrong intermediate plateaus, and can never
   produce roll-up. The clamp control (exact history with effluent capped at influent) passes 1
   of 28 recipes.
4. **Zero-strength and pole-hugging roots.** Bicarbonate absent from feed and resin (`held_06`)
   puts a root exactly on its pole: that wave is absent. Bicarbonate at 0.2 % of the normality
   (`held_07`) puts the root 1e-3 from the pole: the wave is present, 0.1 BV wide, and graded.
5. **Interactions after a feed change.** The second feed's waves overtake the first feed's.
   Because the system is of Temple class the invariants pass through each other, but speeds
   change: a shock crossing a spreading wave of another family follows a curved path and
   refracts the wave; a same-family shock absorbs a spreading wave piece by piece, sometimes
   up to the outlet; two spreading waves cross. Superposing the two Riemann solutions (the
   superposition control) passes every single-feed recipe and fails all five recipes in which
   the waves interact before the outlet.
6. **Derived events inside spreading waves.** `nitrate_limit_bv` falls inside a spreading wave
   in `service_06` and `held_10` and must be found by inverting the wave; it falls at a shock, at
   BV 0, and never, in other recipes.
7. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `ixbreak.py` is a plausible plant script: run length = capacity / loading
per ion ("sharp fronts, component-wise stoichiometry"), fronts sorted by position, a feed change
handled by restarting and shifting. Its three defects are scientific (sharp-front assumption,
component-wise plateaus that cannot roll up, superposition after a feed change), and the
diagnosis is graded by executing it.

The data are synthetic, generated inside the stated domain with published type 1 strong-base
resin selectivities as the centre of the ranges. Recipe ids carry no information.

## Reference solution

`solution/ixfront.py` works in characteristic coordinates. For liquid equivalent fractions
`x_i` and separation factors `a_i`, the roots `h_k` of `sum_i a_i x_i prod_{j != i} (a_j - h) = 0`
interlace the `a_i` (a root sits exactly on `a_m` when ion `m` is absent). Across a wave of
family `k` only `h_k` changes; with `S = prod a / prod h`, a characteristic of family `k` moves
at `1 / (eps + Lambda h_k^2 prod_{j != k} h_j / prod a)` and a jump of family `k` between `h_k^-`
and `h_k^+` at the same expression with `h_k^- h_k^+` in place of `h_k^2`. A wave is a shock
when `h_k` is smaller on the feed side than on the bed side, a spreading wave when larger, absent
when equal. Compositions come back from the roots in closed form. For one feed the Riemann fan
evaluated at the outlet gives every quantity in closed form; the nitrate limit inside a spreading
wave is inverted with a bracketed root finder (every fraction is monotone along a wave).

For two feeds the solver tracks fronts. A spreading wave is discretised into jumps between
consecutive values of `h_k`; because jump loci coincide with characteristic paths, each jump
moves exactly on the characteristic of the geometric mean of its two values, and every crossing
of two jumps of different families is an instantaneous exchange of states. All crossings of two
waves are computed on a lattice whose points are intersections of straight segments; a same-
family catch-up is a chain of merges, with exact edge characteristics inserted where a shock
dies; each jump's arrival at the outlet is then read off. The convergence study below shows that
every event position is exact at any resolution; only the smooth composition inside a spreading
wave is interpolated (PCHIP of the characteristic value against bed volume), which converges at
second order and is Richardson-extrapolated from 400 and 800 pieces. The slowest recipe takes
5 s on one CPU.

`solution/diagnose.py` runs the legacy script and the program on the shipped recipes at run
time and selects witnesses on which they differ by more than the tolerance (five quantities on
`service_01` and `service_05` in the oracle run). Nothing is stored.

## Verification

Expected values come from `tests/reference/reference.py`, written by a separate agent from the
spec alone and forbidden from using the h-transformation or Riemann invariants: it works on the
reduced three-component system with an analytic Jacobian and `numpy.linalg.eig`, integrates
rarefaction curves as eigenvector ODEs (DOP853, rtol 1e-12), solves Rankine-Hugoniot conditions
by Newton with the Lax admissibility test, builds each Riemann solution by nested root finding
over the three wave strengths with wave-ordering validation, and tracks interactions in the
(position, bed volume) plane: shock-shock re-solves, a shock through a spreading wave as an ODE
with the unknown side free along all non-shock eigendirections (the reflected components come
out at 1e-14, which independently confirms the simple-wave structure the oracle assumes),
same-family absorption, and spreading-wave crossings as a Goursat problem by Chebyshev
collocation (N = 18, with an N = 13 solve as the error estimate). Its own evidence: rarefaction
curves straight to 1e-17 (emergent, not assumed), jump-condition residuals at most 4e-14,
integral mass balance closed to 7e-12 bed volumes, graded numbers insensitive to its ODE
tolerance between 1e-8 and 1e-13 (changes at most 9e-15), and a crude upwind finite-volume
solve agreeing on wave counts, kinds and plateaus. It takes 0.5 to 10.6 s per recipe on one CPU.
During development it caught one real defect in the oracle (a same-family absorption that was
skipped when the merged front sat at the leading end of its chain, on `held_14`); after the fix
the two codes agree on every recipe.

A third code, a conservative finite-volume solver (conserved variable `eps x + Lambda y`,
upwind flux, MUSCL with a cell-common minmod limiter, SSP-RK2, CFL 0.4 on the tracked maximum
characteristic speed, exact inversion of the conserved variable), run at 1000, 2000 and 4000
cells with Richardson extrapolation, served as a referee for the structure on the eight
development recipes (base case, pre-loaded resins, elution, absent ion, nitrate-selective
resin, and three feed changes with crossing and absorbing waves). It classifies fronts by how
their 10-90 % width scales with resolution (halving: shock; constant: spreading wave), and it
reproduces the exact solution's structure in every case: the same numbers of shocks and
spreading waves, plateau compositions equal to the invariant values to 1e-9 at 1000 cells,
shock positions within its own extrapolation error (519.944 +- 0.019 against the exact 519.9441
in the base case; 467.315 +- 0.017 and 561.591 +- 0.020 for the merged shocks after a feed
change; 492.373 +- 0.05 for a shock that absorbs a spreading wave right up to the outlet), the
same roll-ups (nitrate at 2.91 meq/L against a 0.7 meq/L feed after the feed change), and the
same composite "spreading wave ending in a shock". Its mass balance closes to 1e-9. Where it is
weak is instructive: the edges of spreading waves are located only to a few bed volumes, and
compositions inside them converge at first order (1e-4 to 5e-4 meq/L at 4000 cells, after
17 to 29 minutes per recipe), which is why a dispersive solver cannot meet the tolerances
within the 60 s call limit and why the exact solution is required.

Agreement of the two exact codes over the 28 recipes (every structure identical):

| Quantity | Largest difference |
| --- | --- |
| any bed volume (shocks, wave edges, plateau edges, peak, limit) | 1.8e-12 relative |
| any composition entry (meq/L) | 1.3e-11 |

Tests (`tests/test_outputs.py`, hardened runner from the project template: unprivileged uid,
fresh working directory as the only writable location, process-group kill at the 60 s limit,
regular-file and 1 MB guards before every copy or read, strict JSON):

| Node | Checks |
| --- | --- |
| `test_saved_base_case` | the three artifacts are regular files; `base_case_report.json` meets the contract and the tolerances for `service_01` |
| `test_fresh_case[<recipe>]` (28) | a fresh call on each shipped and held-out recipe: contract (exact key sets, finite numbers, orders, exact tiling of the window, every shock on a boundary), counts, then every value against the reference within the tolerances |
| `test_diagnosis` | 3 to 8 witnesses with at least three distinct quantities; each recipe validated against the domain; the pristine legacy script reproduces the legacy value; the independent reference reproduces the correct value; the two differ |

`finalize_reward.py` issues 1 only for a complete CTRF report listing exactly these 30 nodes
with every failure in the call phase; `conftest.py` preserves parametrised nodes in the report;
`test.sh` writes 0 first and locks the shared writable paths.

### Tolerances

| Graded quantity | Tolerance | Agreement of the two codes | Basis |
| --- | --- | --- | --- |
| bed volume of a shock, wave edge, plateau edge, peak or limit crossing | max(2e-4 relative, 1e-6) | 1.8e-12 | nearest wrong answer: the sharp-front control is off by at least 7.4e-4 on a shock it places (3.7 tolerances) and the superposition control by at least 8.7e-4; the closest pair of distinct events in any recipe is 7.4e-4 apart (`held_09`) |
| composition entry (meq/L) | 1e-4 absolute | 1.3e-11 | nearest wrong answer: the legacy script is off by at least 3.3e-4 on any plateau it gets wrong; the sharp-front control comes within 1.1e-4 on one sample inside a wave it misrepresents while failing that recipe elsewhere; roll-up plateaus differ from the clamped value by 0.3 to 2 meq/L |
| `nitrate_limit_bv` | as a bed volume; `null` exact | 1.8e-12 | crossings inside spreading waves are screened to have slope at least 5e-3 meq/L per BV, so a 1e-4 meq/L composition error moves the crossing by at most 0.02 BV |
| counts of shocks, transitions, plateaus | exact | identical | the sharp-front control reports no transitions; the legacy one front per ion |

### Wrong-method controls

Each control is a program with the task's CLI, graded with the verifier's own validate and
compare functions on all 28 recipes against the reference values:

| Control | What it does | Passes | Smallest error on a quantity it gets wrong |
| --- | --- | --- | --- |
| legacy script | sharp fronts, component-wise stoichiometry, superposition | 0 / 28 | 1.8e-3 relative (BV), 3.3e-4 meq/L |
| all-shock | the exact Riemann structure with every spreading wave collapsed to one front at its jump-condition position | 3 / 28 (the recipes with no spreading wave) | 7.4e-4 relative, 1.1e-4 meq/L |
| clamp | the exact history with every effluent concentration capped at the influent value | 1 / 28 (the recipe without roll-up) | 6.5e-2 relative on the limit crossing, 6.2e-4 meq/L |
| superposition | both feeds solved as independent Riemann problems, no interactions | 23 / 28 (all single-feed recipes, the late switch and the unseen switch) | 8.7e-4 relative, 1.15e-4 meq/L |

### Runs

| Check | Result |
| --- | --- |
| oracle, `docker run --network none --cpus=1 --memory=2048m` with `solve.sh` | all three artifacts written in 15 s |
| verifier image on the oracle's artifacts, `--cpus=1 --memory=2048m`, no network | 30 passed, reward 1, 61 s (two independent oracle runs gave identical reports) |
| verifier on an empty results directory | 30 failed, reward 0 |
| FIFOs planted at the three artifact paths | 30 failed in 3 s, reward 0, no hang (`not a regular file`) |
| Harbor 0.24 `oracle` / `nop` (local, Docker in a Colima VM on macOS) | the agent phase runs and all three artifacts are collected (oracle trial 1 min 19 s); the verifier then stops at `test.sh`'s lockdown self-check, because the VM's virtiofs and 9p bind mounts of `/logs/verifier` ignore `chmod`, so the check correctly refuses to grade in that environment (reward 0 for both). On a Linux Docker host the same bind mount honours `chmod 700` and the check passes, as it did for the two earlier tasks built on this template; the plain-Docker rows above are the grading evidence from this machine |
| OpenBLAS kernels `OPENBLAS_CORETYPE` = default, Prescott, SandyBridge, Zen on all 28 recipes | byte-identical reports under all four (the method uses no BLAS beyond scalar work; the SkylakeX kernel needs AVX-512, which the development machine lacks, so it could not be run) |

### Coverage of the 28 recipes

| recipe | covers | shocks | transitions | plateaus | nitrate peak (meq/L) | at BV | limit BV | samples | feeds |
|---|---|---|---|---|---|---|---|---|---|
| service_01 | chloride-form bed, four-ion feed (base case) | 2 | 1 | 4 | 2.359 | 355.0 | 355.01 | 6 | 1 |
| service_02 | sulfate-loaded bed | 1 | 2 | 4 | 1.439 | 391.4 | 311.40 | 8 | 1 |
| service_03 | complete elution with chloride | 1 | 2 | 4 | 1.306 | 65.4 | 0.00 | 5 | 1 |
| service_04 | nitrate-selective resin | 2 | 1 | 4 | 0.963 | 326.6 | 326.60 | 7 | 1 |
| service_05 | feed change, second waves cross first waves | 2 | 4 | 6 | 2.064 | 368.0 | 367.95 | 12 | 2 |
| service_06 | limit exceeded inside a spreading wave | 1 | 2 | 4 | 0.843 | 759.2 | 651.81 | 6 | 1 |
| held_01 | chloride-form bed, four-ion feed | 2 | 1 | 4 | 2.272 | 387.7 | 387.66 | 5 | 1 |
| held_02 | chloride-form bed, four-ion feed | 2 | 1 | 4 | 1.290 | 286.9 | 286.92 | 7 | 1 |
| held_03 | bicarbonate-loaded bed | 3 | 0 | 4 | 1.237 | 818.7 | 818.68 | 4 | 1 |
| held_04 | sulfate-loaded bed | 1 | 2 | 4 | 0.702 | 617.1 | null | 7 | 1 |
| held_05 | complete elution with chloride | 1 | 2 | 4 | 0.712 | 108.4 | null | 6 | 1 |
| held_06 | bicarbonate absent from feed and bed | 2 | 0 | 3 | 1.362 | 448.3 | 448.30 | 3 | 1 |
| held_07 | bicarbonate at trace level in the feed | 2 | 1 | 4 | 1.970 | 444.5 | 444.54 | 6 | 1 |
| held_08 | nitrate-selective resin | 2 | 1 | 4 | 0.583 | 447.6 | null | 6 | 1 |
| held_09 | nearly coincident outlet events | 2 | 1 | 4 | 2.960 | 322.9 | 322.93 | 5 | 1 |
| held_10 | limit exceeded inside a spreading wave | 0 | 3 | 4 | 0.966 | 204.1 | 191.62 | 6 | 1 |
| held_11 | limit never exceeded | 2 | 1 | 4 | 1.513 | 472.7 | null | 5 | 1 |
| held_12 | limit exceeded at BV = 0 | 2 | 1 | 4 | 3.176 | 174.3 | 0.00 | 5 | 1 |
| held_13 | limit exceeded at a shock | 2 | 1 | 4 | 2.848 | 246.7 | 246.73 | 6 | 1 |
| held_14 | feed change, crossing waves | 3 | 3 | 5 | 2.863 | 311.0 | 310.96 | 8 | 2 |
| held_15 | feed change, crossing waves | 2 | 2 | 5 | 2.599 | 443.5 | 443.50 | 10 | 2 |
| held_16 | feed change, a shock absorbs a spreading wave | 4 | 2 | 7 | 2.099 | 662.3 | 280.17 | 8 | 2 |
| held_17 | feed change, a shock absorbs a spreading wave | 3 | 2 | 6 | 1.257 | 539.6 | 501.40 | 9 | 2 |
| held_18 | feed change after every first wave has left | 2 | 4 | 7 | 2.186 | 249.9 | 249.88 | 7 | 2 |
| held_19 | feed change whose waves do not reach the outlet | 1 | 1 | 3 | 1.921 | 404.6 | 404.56 | 5 | 2 |
| held_20 | window ends before the first event | 0 | 0 | 1 | 0.000 | 0.0 | null | 1 | 1 |
| held_21 | selectivities at the domain bounds, no samples | 2 | 1 | 4 | 0.748 | 215.6 | 215.63 | 0 | 1 |
| held_22 | C_T at a domain bound | 2 | 1 | 4 | 0.510 | 1575.7 | null | 7 | 1 |

## Reproducing the reference values

Development tools live outside the task in the repository folder
`turing/tbScience/anion-breakthrough-audit-dev/` (nothing there is needed by grading):

- `tools/gen_recipes.py <ixfront.py> <out>`: builds the 28 recipes deterministically (one random
  stream per recipe) inside the spec's domain, screening each with the oracle for the spec's
  structural guarantees (event separations, plateau and wave lengths, bound margins, limit-crossing
  slope), placing the nitrate limit relative to the exact history where the recipe's purpose
  requires it, and finding the near-coincident recipe by bisection on `alpha_sulfate`.
- `refA/reference.py --recipe --output`: the independent exact solver shipped as
  `tests/reference/reference.py`; `expected.json` is its report for each recipe, keyed by id.
- `refB/fv_referee.py` and `refB/richardson.py`: the finite-volume referee.
- `controls/controls.py <control> --recipe --output` and `controls/grade.py`: the wrong-method
  controls and their grading with the verifier's functions.
- `tools/tolerance_study.py`: the two legs of the tolerance table.
- `tools/two_feed_check.py` and `tools/mass_balance_check.py`: integral mass balances of the
  oracle's histories (closed to 1e-8 relative) and the late-switch limit (exact).
- Convergence of the two-feed engine (dev recipes with crossing and absorbing waves, pieces
  150 to 2400): every shock position and wave edge changes by less than 1e-11 relative between
  resolutions; sampled compositions inside interaction regions converge with ratio 4.0 per
  doubling (second order) and are extrapolated.
