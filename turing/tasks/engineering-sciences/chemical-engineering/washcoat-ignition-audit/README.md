# washcoat-ignition-audit

Locate every ignition, extinction and Hopf point of a porous catalytic washcoat layer with
external heat and mass transfer resistances, find every steady state at given Thiele moduli with
its stability, and diagnose a legacy light-off script by executable witnesses.

| | |
| --- | --- |
| Domain | engineering-sciences / chemical-engineering / reaction-engineering |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

The active layer of an automotive or industrial monolith converter is a thin porous washcoat.
An exothermic oxidation in it is a non-isothermal reaction-diffusion problem (Weisz and Hicks),
and with the external film resistances (mass and heat Biot numbers) the steady states fold back
on themselves: a cold, kinetically limited state and a hot, transport-limited state coexist over
a range of the Thiele modulus, and the converter lights off and extinguishes with hysteresis.
Emission engineers use exactly this model to place light-off. The spec states the model and the
stability concept and no method.

What a competent solver gets right: the textbook S-shaped curve of the infinite-Biot problem and
the slope rule for its stability. Where the difficulty is, each exercised by several of the 28
recipes:

1. **The film.** With finite and unequal Biot numbers the folds move by tens of percent and the
   ignited state can sit at a temperature rise set by the film, not the layer. Solving with the
   exposed face at bulk-gas conditions fails every recipe.
2. **Exact fold positions.** Folds are graded to 1e-6 relative in the Thiele modulus. Reading
   them off a sampled curve misses by 8.6e-5 or more (86 tolerances) even with the exact model.
3. **Up to five steady states.** Four recipes have four folds; three of them have five
   coexisting steady states at one Thiele modulus (1-3-5-3-1), one has two separate hysteresis
   loops (1-3-1-3-1). A solver that assumes at most three states, or stops at the first loop,
   fails them.
4. **Stability is not the slope rule.** With a Lewis number below one the ignited state loses
   stability through Hopf bifurcations; the stability class comes from the eigenvalues of the
   linearised two-field transient problem. The slope-rule control (exact steady states, middle
   state unstable, no Hopf analysis) fails exactly the 9 recipes whose physics has a Hopf point.
5. **Hopf points next to folds and real-complex mergers.** A real pair of eigenvalues merges into
   a complex pair near the ignition fold, and that pair can cross the imaginary axis within the
   same short stretch of the curve (`held_16`, Hopf point near a fold; `held_07`, `held_08`). A
   scan that ignores the merger misses the Hopf point, and a scan that takes the merger for a
   crossing reports a false one. Both errors occurred in development and were caught by the
   independent reference (below).
6. **Two Hopf points without any fold** (`lightoff_06`, `held_10`, `held_11`): an oscillatory
   window on a unique steady state, invisible to any analysis that looks only for multiplicity.
7. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `lightoff.py` is a plausible plant script: exposed face at bulk-gas conditions,
the curve sampled on a fixed grid of wall concentrations with turning points read off the grid,
states by linear interpolation, stability by the slope rule, no transient analysis. The
diagnosis is graded by executing it.

The data are synthetic, generated inside the stated domain. Recipe ids carry no information.

## Reference solution

`solution/lightoff_exact.py`. Adding beta times the reactant equation to the energy equation
gives `(theta + beta c)'' = 0`, so `theta + beta c = A` across the layer, and the two film
conditions fix `A` from the surface concentration `c_s`. The reactant equation then has a first
integral, and the layer thickness and the film condition give two expressions for the Thiele
modulus,
`phi = int_{c0}^{c_s} dc / sqrt(2 D(c)) = Bi_m (1 - c_s) / sqrt(2 D(c_s))`,
`D(c) = int_{c0}^{c} s R(A - beta s) ds`. For each `c_s` this is one equation in the wall
concentration `c0`; it has exactly one root on every recipe (and on 120 random parameter sets
over the whole domain), so the steady-state set is the single curve `c_s -> (phi, theta_c, eta)`
and isolated branches cannot occur. Folds are the zeros of `d phi / d c_s`, refined by Brent's
method; states at a query value are the crossings of the curve. Quadrature is Gauss-Legendre with
`c = c0 cosh t` near the wall (smooth integrand), `log c` above, and the closed-form frozen-
kinetics piece below `c = 1e-14`; dead cores down to `c0 = 1e-300` and the exact dead-core limit
beyond.

Stability: the linearised two-field problem with the Lewis number is discretised by Chebyshev
collocation (the steady profile is polished by collocation Newton from the first-integral
profile) at 48, 72, 108 and 162 points until the rightmost eigenvalue agrees to 1e-7. Hopf points
are sign changes of the real part of the rightmost complex pair along the curve, scanned at the
coarsest resolution, with every interval next to a real-complex merger subdivided, refined by
Brent's method on the converged spectrum and kept only if the root has `|Re| < 1e-6` and `omega >
1e-3`. The slowest recipe takes 32 s on one shared CPU.

`solution/diagnose.py` runs the legacy script and the program on the shipped recipes at run
time and keeps one witness per quantity on which they differ (five quantities in the oracle
run). Nothing is stored.

## Verification

Expected values come from `tests/reference/reference.py`, written by a separate agent from the
spec alone and forbidden from using the `theta + beta c` invariant, any first integral, quadrature
or collocation. It shoots the full two-field problem from the wall in `log c` (stable for wall
concentrations as small as `exp(-1e6)`), traces the steady-state curve by pseudo-arclength
continuation in `(theta0, c0, ln phi)` with the sensitivity equations, refines folds on the
determinant of the shooting Jacobian, and computes the spectrum by second-order finite
differences on surface-clustered grids with shift-invert refinement at 100, 200 and 400 intervals
and Richardson extrapolation (errors fall by 4 per doubling). It checks the parity of the number
of folds crossed against the sign of the real eigenvalue at every query state. Its own evidence:
shooting tolerance 1e-12 against 1e-13 moves phi by at most 2.3e-11 and values by 7.5e-10;
doubling the eigen grid moves Hopf points by 1.6e-12 and frequencies by 2.4e-11; an independent
finite-difference steady solve matches its centre temperatures to 3e-10. It takes 4 to 11 s per
recipe. During development it caught one defect in the oracle (a Hopf point 4.8e-4 from an
ignition fold, missed because the real-complex merger and the crossing fell in one scan
interval); after the fix the two codes agree on every recipe.

Agreement of the two codes over the 28 recipes (every count, fold kind and stability class
identical):

| Quantity | Largest difference |
| --- | --- |
| phi of folds and Hopf points | 1.5e-10 relative |
| theta_c and eta (folds, Hopf points, states) | 1.7e-9 relative to max(1, value) |
| omega | 1.1e-9 relative |

A third code, a method-of-lines transient solver (second-order finite volumes clustered at the
exposed face, stiff implicit integration with the analytic banded Jacobian), referees the
dynamics by direct time integration on seven development recipes, with no steady solver and no
eigenvalue computation. It finds the same ignition and extinction points within its 1e-4
resolution (0.367186 and 0.276380 against the exact 0.3672225 and 0.2763970), both hysteresis
loops of a four-fold recipe, no oscillation of the ignited state at Lewis numbers 1 and 5, and at
Lewis number 0.2 a supercritical Hopf bifurcation between phi 0.501 and 0.502 at frequency 22.2
(exact 0.5016669, 22.230), with the upper state at phi 0.3 unstable through two real positive
exponents (the oracle's `unstable_real`, against the slope rule's `stable`).

Tests (`tests/test_outputs.py`, hardened runner from the project template: unprivileged uid,
fresh working directory as the only writable location, process-group kill at the 120 s limit,
regular-file and 1 MB guards before every copy or read, strict JSON):

| Node | Checks |
| --- | --- |
| `test_saved_base_case` | the three artifacts are regular files; `base_case_report.json` meets the contract and the tolerances for `lightoff_01` |
| `test_fresh_case[<recipe>]` (28) | a fresh call per shipped and held-out recipe: contract (exact key sets, finite numbers, orders, query values exactly as given, closed vocabularies), counts of folds, Hopf points and states, then every value against the reference |
| `test_diagnosis` | 3 to 8 witnesses with at least three distinct quantities; each recipe validated against the domain; the pristine legacy script reproduces the legacy value; the independent reference reproduces the correct value; the two differ |

`finalize_reward.py` issues 1 only for a complete CTRF report listing exactly these 30 nodes with
every failure in the call phase; `conftest.py` preserves parametrised nodes; `test.sh` writes 0
first and locks the shared writable paths.

### Tolerances

| Graded quantity | Tolerance | Agreement of the two codes | Basis |
| --- | --- | --- | --- |
| phi of a fold or Hopf point | 1e-6 relative | 1.5e-10 | nearest wrong answer: the exact curve read off a 60-point grid misses a fold by at least 8.6e-5 (86 tolerances); ignoring the film or the legacy script by at least 6.1e-2 |
| theta_c, eta of a fold or a query state | 1e-6 max(1, value) | 1.7e-9 | nearest wrong answer: on the states it otherwise gets right, the sampled-curve control misses by at least 1.15e-5 (11 tolerances), the film-free control by at least 1.3e-4, the legacy script by at least 3.4e-4. At a fold phi is stationary, so the fold's theta_c and eta require the fold condition to be solved, not only phi to be maximised |
| theta_c, eta of a Hopf point | 5e-5 max(1, value) | 1.7e-9 | a Hopf point placed within the phi tolerance moves its theta_c and eta along the curve; the largest measured sensitivity over the 13 Hopf points is 19.6 (relative change of eta per relative change of phi, `held_09`), so twice that times 1e-6, rounded up, keeps every placement inside the phi tolerance acceptable |
| omega | 2.5e-4 relative | 1.1e-9 | same coupling for the frequency: the largest measured sensitivity is 110 (`held_09`, a Hopf point at low frequency), and 2.5e-4 is twice that times the phi tolerance, rounded up. No control reports a wrong omega; the slope-rule and legacy controls report no Hopf point at all |
| counts, kinds, stability classes | exact | identical | the spec guarantees that no query value has an ambiguous spectrum (rightmost eigenvalue at least 1e-4 from the imaginary axis, imaginary part 0 or at least 1e-3) and that events are at least 1e-3 apart |

### Wrong-method controls

Each control is a program with the task's CLI, graded with the verifier's own validate and
compare functions on all 28 recipes against the reference values:

| Control | What it does | Passes |
| --- | --- | --- |
| legacy script | film ignored, coarse grid, slope rule, no transient analysis | 0 / 28 |
| no film | exact method with the exposed face at bulk-gas conditions | 0 / 28 |
| coarse | exact curve sampled on 60 points, folds and states read off it, exact stability | 0 / 28 |
| slope rule | exact steady states and folds, middle of three states unstable, no Hopf analysis | 19 / 28 (fails all 9 recipes with a Hopf point) |

### Runs

| Check | Result |
| --- | --- |
| oracle, `docker run --network none --cpus=1 --memory=2048m` with `solve.sh` | all three artifacts written in 109 s (five witnesses: fold_phi, fold_count, state_count, stability, hopf_count) |
| verifier image on the oracle's artifacts, `--cpus=1 --memory=2048m`, no network | 30 passed, reward 1, 7 min 44 s (an earlier run with the pre-final tolerances also passed, 12 min 10 s on a more loaded host) |
| verifier on an empty results directory | 30 failed, reward 0, 5 s |
| FIFOs planted at the three artifact paths | 30 failed, reward 0, 5 s, no hang (`not a regular file`) |
| OpenBLAS kernels `OPENBLAS_CORETYPE` = default, Prescott, SandyBridge, Zen on all 28 recipes | Zen byte-identical to default on 28/28; Prescott and SandyBridge on 20/28, the other 8 differing in trailing digits of the eigenvalue solves only: every count, kind and class unchanged, and agreement with the reference stays within 1.7e-9 (values), 1.5e-10 (phi), 1.5e-9 (omega). The SkylakeX kernel needs AVX-512, which this machine lacks |
| Harbor 0.24 locally | as for the earlier tasks on this machine: the Colima VM's bind mounts ignore `chmod`, so `test.sh`'s lockdown self-check refuses to grade under local Harbor; the plain-Docker rows above are the grading evidence, and on a Linux Docker host the check passes |

### Coverage of the 28 recipes

| recipe | covers | Le | folds | Hopf points | steady states at the queries |
| --- | --- | --- | --- | --- | --- |
| lightoff_01 | two folds, Le = 1 (base case) | 1 | 2 | 0 | 1, 1, 3, 1, 1 |
| lightoff_02 | unique steady state | 2.5479 | 0 | 0 | 1, 1, 1 |
| lightoff_03 | two folds, one Hopf point, Le < 1 | 0.3376 | 2 | 1 | 1, 1, 3, 1, 1 |
| lightoff_04 | four folds (two hysteresis loops) | 1.1514 | 4 | 0 | 1, 1, 3, 5, 3, 1, 1 |
| lightoff_05 | two folds, Le > 1 | 2.4381 | 2 | 0 | 1, 1, 3, 1, 1 |
| lightoff_06 | two Hopf points, no fold | 0.1396 | 0 | 2 | 1, 1, 1, 1, 1 |
| held_01 | unique steady state | 14.5215 | 0 | 0 | 1, 1, 1 |
| held_02 | unique, Biot numbers at the domain bounds | 0.6145 | 0 | 0 | 1, 1, 1 |
| held_03 | two folds, Le = 1 | 1 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_04 | two folds | 1.4469 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_05 | two folds, Le > 1 | 5.6842 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_06 | two folds, large Le | 12.4658 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_07 | one Hopf point, Le < 1 | 0.4235 | 2 | 1 | 1, 1, 3, 3, 1, 1 |
| held_08 | one Hopf point, Le < 1 | 0.3263 | 2 | 1 | 1, 1, 3, 3, 1, 1 |
| held_09 | one Hopf point, small Le | 0.1215 | 2 | 1 | 1, 1, 3, 1, 1 |
| held_10 | two Hopf points | 0.103 | 0 | 2 | 1, 1, 1, 1, 1 |
| held_11 | two Hopf points | 0.1811 | 0 | 2 | 1, 1, 1, 1, 1 |
| held_12 | four folds | 0.8764 | 4 | 0 | 1, 1, 3, 5, 3, 1, 1 |
| held_13 | four folds | 0.9461 | 4 | 0 | 1, 1, 3, 1, 3, 1, 1 |
| held_14 | four folds, Le < 1 | 0.1555 | 4 | 0 | 1, 1, 3, 5, 3, 1, 1 |
| held_15 | two nearly coincident folds | 0.5776 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_16 | Hopf point close to a fold | 0.3871 | 2 | 1 | 1, 1, 3, 3, 1, 1 |
| held_17 | two folds, Biot numbers at the bounds | 0.6032 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_18 | two folds, Biot extreme, Le < 1 | 0.1434 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_19 | two folds, Le = 1 | 1 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_20 | two folds, Le near the Hopf onset | 0.2129 | 2 | 0 | 1, 1, 3, 1, 1 |
| held_21 | unique, small Le | 0.2212 | 0 | 0 | 1, 1, 1 |
| held_22 | two folds | 0.8909 | 2 | 0 | 1, 1, 3, 1, 1 |

## Reproducing the reference values

Development material lives outside the task in `turing/tbScience/washcoat-ignition-audit-dev/`:

- `tools/steady_core.py`, `tools/scan_mult.py`: the first-integral formulation and the scan of
  120 random parameter sets showing one wall root per surface value (no isolas), with 0, 2 or 4
  folds.
- `tools/hopf_probe.py`: the Hopf-point survey that set the Lewis-number floor at 0.1 (below it,
  resolution-dependent high-frequency candidates appear at large phi).
- `tools/gen_recipes.py`, `tools/run_indices.py`: deterministic recipe generation (one random
  stream per recipe) with screening for every guarantee of the spec, including a check that the
  sign of the rightmost complex pair's real part is the same at 72 and 162 collocation points
  along the whole window.
- `tools/final_gate.py`: Reference A agrees with the oracle on every structure, and the spec's
  guarantees hold on Reference A's report.
- `refA/reference.py` (shipped as `tests/reference/reference.py`): `expected.json` is its report
  for each recipe, keyed by id. `refB/mol_referee.py`: the transient referee.
- `controls/controls.py`: the wrong-method controls; `tools/agree.py`: the agreement table.
