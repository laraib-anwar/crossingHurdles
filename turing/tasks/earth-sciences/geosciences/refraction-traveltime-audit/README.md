# refraction-traveltime-audit

Compute every ray-theoretical P-wave arrival recorded at the surface over a flat layered crust
whose velocity varies linearly with depth inside each layer and jumps at interfaces: turning
waves, pre- and post-critical reflections, head waves and the direct wave, every caustic, and the
first-arrival traveltime curve with its exact crossovers. Then diagnose a legacy refraction
traveltime script by executable witnesses.

| | |
| --- | --- |
| Domain | earth-sciences / geosciences / seismology |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Wide-angle refraction surveys image the crust by fitting the traveltimes of every observed phase
to a layered velocity model (the workflow of ray-tracing inversion codes such as RAYINVR). For
layers with linear velocity gradients ray theory is exactly solvable: every branch `X(p)`,
`T(p)` is closed form, so every arrival, caustic and crossover has an exact value. The spec
states the model and the arrival definitions and no method.

What a competent solver gets right: constant-velocity layers, the direct wave, head waves and
their crossover distances (`model_01` reproduces the textbook crossover `2h sqrt((v2+v1)/(v2-v1))`
exactly). Where the difficulty is, each exercised by several of the 28 models:

1. **Post-critical reflections.** A reflection exists for every ray parameter below the slowness
   of the fastest layer above the interface, not only up to the critical angle. Wide-angle
   reflections are often the latest but sometimes the first arrival. Cutting reflections at the
   critical angle (the pre-critical control) fails 26 of 28 models.
2. **Turning waves and triplications.** Gradient layers produce turning branches; where a strong
   gradient lies below a weak one the branch folds (a caustic) and up to 11 arrivals reach one
   offset (`held_22`; 8 in `held_15` and `held_16`). Every arrival is graded with its kind,
   index, ray parameter and time.
3. **Caustics on turning branches only.** A reflection branch cannot fold: every layer it
   crosses adds `p h (v1 + v2)/(eta1 + eta2)` to `X`, which increases with `p`. A turning branch
   folds where the decreasing turning-layer term `eta1/(p b)` balances the increasing ones.
   Caustics are graded to `5e-7` in offset.
4. **Head waves only where they exist.** A head wave travels along the top of a constant-velocity
   layer that is faster than everything above it, and only beyond its critical offset; a
   gradient layer has turning waves instead, a slower layer has neither. The legacy script puts
   a head wave below every velocity increase of its averaged model.
5. **Low-velocity zones and shadow zones.** Negative gradients and velocity drops end the
   turning branches; beyond, the first arrival is a wide-angle reflection until a deeper branch
   takes over (`model_03`, `model_05`, `held_08` to `held_11`). Building the first arrival from
   refracted phases only fails all six of them (the no-reflection control passes the other 22).
6. **Exact first-arrival structure.** The first-arrival curve is split wherever the arrival that
   gives the minimum changes (crossovers, branch ends, a head wave leaving its critical
   reflection tangentially). Two branches meeting at a cusp are tangent there, so their times
   agree to many digits near the cusp; comparing tabulated times produces spurious slivers, and
   the boundaries must be computed exactly.
7. **Grazing singularities.** At branch ends `p` approaches `1/v` of an interface or layer top,
   where `X` has square-root behaviour or diverges; the exact branch-end offsets (for example the
   critical offset where a turning wave emerges) must be evaluated at the limit, not near it.
8. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `ttcurve.py` is a plausible field-processing script: each layer replaced by its
mean velocity, head waves below every velocity increase, reflections up to the critical angle,
the first arrival as the envelope of the direct and head-wave lines, no caustics.

The models are synthetic, generated inside the stated domain. Model ids carry no information.

## Reference solution

`solution/raytimes.py`. With `eta = sqrt(1 - p^2 v^2)`, a layer with top and bottom velocities
`v1`, `v2` contributes `X = p h (v1 + v2)/(eta1 + eta2)` (a cancellation-free form valid for every
gradient, zero included) and `T = [log1p(b h / v1) + log1p(p^2 b h (v1 + v2)/((eta1 + eta2)(1 +
eta2)))]/b` (`h/(v eta)` for `b = 0`); a ray turning in layer `k` adds `eta1/(p b)` and
`ln((1 + eta1)/(p v1))/b`. `dX/dp` is differentiated analytically. Each branch (turning in a layer,
reflection from an interface) is an interval of `p`; it is split at its caustics (zeros of
`dX/dp`, by Brent's method) into monotone segments, with branch ends evaluated exactly at their
limits wherever `X` is finite there. An arrival at an offset is the unique root of `X(p) = X` on
each segment covering it; direct and head waves are closed form. The first arrival is located
on a 6000-point offset grid from tabulated segments, every short run is re-decided exactly at its
centre (removing tangency artefacts near cusps), and every boundary is computed exactly: a
segment end, a segment start, or a crossover root of `T_a(X) - T_b(X)`. The slowest model takes
3 s.

`solution/diagnose.py` runs the legacy script and the program on the shipped models at run time
and keeps one witness per quantity on which they differ (four quantities in the oracle run).
Nothing is stored.

## Verification

Expected values come from `tests/reference/reference.py`, written by a separate agent from the
spec alone and forbidden from using the closed-form layer formulas. It evaluates `X(p)` and
`T(p)` by Gauss-Legendre quadrature of the ray integrals, layer by layer, with a depth
substitution anchored at the fast end of each layer that removes the `1/sqrt(1 - p v)`
singularity exactly (156 nodes per layer on graded panels), gets `dX/dp` by complex-step
differentiation of the same quadrature, evaluates times as `tau(p) + p X` for conditioning near
grazing ends, solves arrivals by safeguarded Newton on monotone segments, and resolves every
first-arrival boundary exactly, with an explicit rule for pairs of segments that meet with equal
`p` (cusps, tangential head-wave onsets). Its own evidence: quadrature refinement on 150 random
models changes `X`, `T` and `dX/dp` by at most 2.6e-15; a ray-ODE (Hamiltonian, DOP853) shooting
check agrees to 6.5e-12, limited by the ODE tolerance; a brute-force 200,000-point offset scan
without segment logic agrees on every model it was run on. During development the two codes
caught one defect each: the reference showed that the oracle evaluated the critical offset where
a turning wave emerges one grid step short of its limit (3.9 um off, `dev_04`), and the oracle's
comparison showed a spurious zero-length first interval in the reference near `X = 0`
(`held_09`). Both were fixed; the two codes then agree on every model.

Agreement of the two codes over the 28 models (every count, kind and index identical):

| Quantity | Largest difference |
| --- | --- |
| traveltimes and ray parameters | 6.0e-12 relative |
| caustic offsets and first-arrival boundaries | 1.8e-12 relative |

A third code, a second-order fast-sweeping eikonal solver on nested grids with Richardson
extrapolation, referees the first-arrival times and crossovers on five development models. Where
ray theory and the eikonal must agree (direct, head and turning first arrivals) it reproduces the
oracle within its error bars: crossovers 6.92821 +- 1.7e-5 and 24.20348 +- 8.2e-5 km against the
exact 6.9282032 and 24.2034870; 9.2497 +- 0.003 and 129.265 +- 0.021 against 9.2500 and 129.2601;
4.5967 and 31.81099 against 4.5968 and 31.8110. Where they must differ it shows why the spec's
arrival definitions matter: the eikonal first arrival includes diffracted waves creeping along
the top of a negative-gradient layer and along the bottom of a layer above a velocity drop, which
ray theory (and the spec) does not count as arrivals.

Tests (`tests/test_outputs.py`, hardened runner from the project template: unprivileged uid,
fresh working directory as the only writable location, process-group kill at the 60 s limit,
regular-file and 1 MB guards before every copy or read, strict JSON):

| Node | Checks |
| --- | --- |
| `test_saved_base_case` | the three artifacts are regular files; `base_case_report.json` meets the contract and the tolerances for `model_01` |
| `test_fresh_case[<model>]` (28) | a fresh call per shipped and held-out model: contract (exact key sets, finite numbers, closed kinds, integer indices, offsets exactly as given, times increasing, caustics in increasing offset, first-arrival intervals tiling `[0, x_max]` exactly), counts of arrivals per offset, caustics and intervals, then every value against the reference |
| `test_diagnosis` | 3 to 8 witnesses with at least three distinct quantities; each model validated against the domain; the pristine legacy script reproduces the legacy value; the independent reference reproduces the correct value; the two differ |

`finalize_reward.py` issues 1 only for a complete CTRF report listing exactly these 30 nodes with
every failure in the call phase; `conftest.py` preserves parametrised nodes; `test.sh` writes 0
first and locks the shared writable paths.

### Tolerances

| Graded quantity | Tolerance | Agreement of the two codes | Basis |
| --- | --- | --- | --- |
| traveltime, ray parameter (arrivals and caustics) | 1e-9 relative | 6.0e-12 | nearest wrong answer: the legacy script's smallest error on an arrival it gets wrong is 3.5e-6 (3500 tolerances); the eikonal referee's error bars are 1e-6 to 4e-3 s |
| caustic offset, first-arrival boundary | 5e-7 relative | 1.8e-12 | a crossover is the root of `T_a - T_b`, so a time error at the 1e-9 tolerance moves it by `dT / dp`; the largest measured coupling over all crossovers is 1.4e-7 (`model_05`, branches differing by `dp = 1.8e-3`), and 5e-7 is three times that, rounded up. Boundaries where a head wave leaves its critical reflection or a branch ends are fixed analytically and do not couple. Nearest wrong answer: the legacy script misplaces a boundary by at least 8e-5 and the 600-point coarse control by at least 9.6e-5 |
| counts, kinds, indices | exact | identical | the spec guarantees that queried offsets lie at least `1e-4 X` from every event that changes the count and that arrivals at an offset are distinct |

### Wrong-method controls

Each control is a program with the task's CLI, graded with the verifier's own validate and
compare functions on all 28 models against the reference values:

| Control | What it does | Passes |
| --- | --- | --- |
| legacy script | mean-velocity layers, head waves below every increase, pre-critical reflections, head-wave envelope | 1 / 28 |
| pre-critical | exact method, reflections only up to the critical angle | 2 / 28 |
| no reflections in the first arrival | exact arrivals, first-arrival curve from refracted phases only | 22 / 28 |
| coarse | exact arrivals, caustics and boundaries read off a 600-point offset grid | 1 / 28 |

### Runs

| Check | Result |
| --- | --- |
| oracle, `docker run --network none --cpus=1 --memory=2048m` with `solve.sh` | all three artifacts written in 8 s (four witnesses: first_arrival_time, arrival_count, first_arrival_count, caustic_count) |
| verifier image on the oracle's artifacts, `--cpus=1 --memory=2048m`, no network | 30 passed, reward 1, 38 s |
| verifier on an empty results directory | 30 failed, reward 0, 6 s |
| FIFOs planted at the three artifact paths | 30 failed, reward 0, 6 s, no hang (`not a regular file`) |
| OpenBLAS kernels `OPENBLAS_CORETYPE` = default, Prescott, SandyBridge, Zen on all 28 models | byte-identical reports under all four (the computation is scalar NumPy and SciPy root finding). The SkylakeX kernel needs AVX-512, which this machine lacks |
| Harbor 0.24 locally | as for the earlier tasks on this machine: the Colima VM's bind mounts ignore `chmod`, so `test.sh`'s lockdown self-check refuses to grade under local Harbor; the plain-Docker rows above are the grading evidence, and on a Linux Docker host the check passes |

### Coverage of the 28 models

| model | covers | layers | most arrivals at one offset | caustics | first-arrival intervals |
| --- | --- | --- | --- | --- | --- |
| model_01 | constant layers: direct and head waves (base case) | 5 | 9 | 0 | 4 |
| model_02 | gradient crust over a gradient half-space | 3 | 4 | 0 | 3 |
| model_03 | low-velocity zone: reflection fills the shadow | 5 | 5 | 0 | 4 |
| model_04 | strong-gradient zone with a caustic | 4 | 6 | 1 | 3 |
| model_05 | velocity drop: shadow zone | 6 | 7 | 0 | 4 |
| model_06 | head wave with critical offset beyond the window | 2 | 2 | 0 | 1 |
| held_01 | constant layers | 5 | 9 | 0 | 3 |
| held_02 | constant layers, three head waves | 4 | 7 | 0 | 4 |
| held_03 | mixed layers with head waves | 4 | 6 | 0 | 4 |
| held_04 | gradient layers | 3 | 5 | 0 | 2 |
| held_05 | gradient layers, three turning branches | 3 | 5 | 0 | 3 |
| held_06 | first arrival with several crossovers | 6 | 7 | 0 | 5 |
| held_07 | first arrival with several crossovers | 5 | 9 | 0 | 4 |
| held_08 | negative-gradient low-velocity zone | 4 | 5 | 0 | 3 |
| held_09 | low-velocity zone: reflection fills the shadow | 4 | 4 | 1 | 4 |
| held_10 | velocity drop: reflection first | 3 | 3 | 1 | 3 |
| held_11 | velocity drop: shadow zone | 3 | 3 | 0 | 3 |
| held_12 | caustic on a turning branch | 3 | 5 | 1 | 2 |
| held_13 | two caustics | 4 | 6 | 2 | 4 |
| held_14 | caustic and several first-arrival intervals | 4 | 6 | 2 | 3 |
| held_15 | triplication: five or more arrivals at one offset | 5 | 8 | 1 | 2 |
| held_16 | steep gradients, four or more arrivals | 3 | 8 | 4 | 2 |
| held_17 | head wave with critical offset beyond the window | 3 | 4 | 0 | 2 |
| held_18 | constant half-space below gradient layers | 2 | 3 | 0 | 2 |
| held_19 | gradient half-space | 2 | 3 | 0 | 2 |
| held_20 | direct wave and gradient layers | 4 | 6 | 0 | 3 |
| held_21 | mixed layers, long window | 5 | 7 | 0 | 5 |
| held_22 | head waves and post-critical reflections | 6 | 11 | 0 | 3 |

## Reproducing the reference values

Development material lives outside the task in `turing/tbScience/refraction-traveltime-audit-dev/`:

- `tools/gen_models.py`: deterministic model generation (one random stream per model) with
  screening for every guarantee of the spec (offsets away from caustics, critical offsets, branch
  ends and crossovers; events separated; distinct arrivals; no grazing arrivals; no gap in the
  window; runtime).
- `tools/final_pipeline.sh`: reruns the oracle, the reference and the controls on every model and
  installs the cases and `expected.json` (the reference's report for each model).
- `tools/agree.py`: the agreement table. `refA/reference.py` (shipped as
  `tests/reference/reference.py`), `refB/eikonal_referee.py`: the referee.
- `controls/controls.py`: the wrong-method controls.
