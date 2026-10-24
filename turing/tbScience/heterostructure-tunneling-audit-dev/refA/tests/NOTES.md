# refA tests

This folder holds the Reference A test structures, their reports, and the scripts that check
them.

## Files

| file | content |
| --- | --- |
| `make_structures.py` | writes the 9 test structures to `structures/` (all inside the HETERO_SPEC domain) |
| `structures/*.json` | the test structures |
| `reports/*.json` | `../reference.py` reports for them (CLI output) |
| `hp.py` | independent high-precision checker in Python `decimal`: Taylor-series integration of psi'' = (m/C)(V - E) psi, with no Airy functions and no global matrix |
| `closed_form.py` | closed-form and limit checks; its output is `closed_form_results.json` |
| `run_checks.py` | internal and hp checks plus guarantee checks for any structure files (`--hp` for the decimal comparison); outputs `check_results_tests.json` (these 9) and `check_results_gen.json` (the 28 gen structures) |

## Commands

```
python make_structures.py
python run_checks.py --hp --out check_results_tests.json structures/*.json
python run_checks.py --hp --out check_results_gen.json ../../gen/structures/*.json
python closed_form.py > closed_form_results.json
```

## Structures and what each one checks

| id | build | purpose |
| --- | --- | --- |
| t1_single_well | barrier 6 nm / GaAs-like well 9.4 nm (m 0.0665) / barrier 6 nm, leads = barriers (0.32 eV, m 0.0919) | BDD finite-well even/odd equations; single-layer T formula above the barrier; maximum at q L = 3 pi with T = 1 |
| t2_sym_double_well | two 6.5 nm wells, 13 nm central barrier 0.28 eV | small splitting (ground pair 4.70e-6 eV) against the closed-form even/odd equations (central-barrier tanh/coth matching) |
| t3_triangular_bias | linear ramp 0 to 1.8 eV over 36 nm (two sloped layers, m 0.35) against a 1.95 eV wall | 35 bound states; the 13 lowest against the Airy equation (beta/m) Ai'(z0) = (kappa_L/m_L) Ai(z0); 8 maxima |
| t4_thick_double_barrier | 10 nm / 1.0 eV barriers (m 0.092) around a 5 nm well, leads at 0 | T down to 3.5e-29 off resonance; no bound state (well bottom = lead edge) |
| t5_superlattice | 6 x (2 nm barrier 0.3 eV, 4 nm well), leads 0.15 eV | 6 miniband bound states; 5 above-barrier maxima |
| t6_graded_leads | graded and sloped layers; left lead m 0.067 at 0 eV, right lead m 0.13 at 0.35 eV | different lead masses and band edges; conservation and reversal symmetry with unequal leads |
| t7_rect_barrier | 7 nm, 0.35 eV barrier (two identical halves) | sinh/sin T formula below and above the top; 3 maxima at E = V + C (n pi/d)^2/m_b, T = 1 |
| t8_thick_barrier | 7 nm, 1.6 eV, m 0.5 barrier | T down to 1.18e-26 against the sinh formula; 6 maxima |
| t9_large_airy | slope 1e-3 eV/nm layers with m 0.95 to 1.0: barriers near 1.9 eV and a well near -0.95 eV | Airy arguments up to ~900 (z ~ +850 in the barriers, z ~ -870 to -1050 in the well); 37 bound states; 9 maxima |

## Guarantee checks (`check_results_tests.json`, from `run_checks.py`)

Every test structure satisfies section 2:

- at most 40 states, spacing >= 1e-6 eV, top state >= 1e-4 eV below E_th;
- every query >= max(V_L, V_R) + 1e-3, T >= 1e-30, |d ln T/dE| <= 1e3;
- window >= max V + 0.01;
- window extrema (from a 1e-5 eV T scan) >= 2e-4 eV apart and from the ends, with maximum
  contrast >= 1e-3.

| id | states | maxima | min spacing (eV) | top gap (eV) | min T(query) | max \|dlnT/dE\| | min extremum spacing (eV) | min contrast | runtime (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1_single_well | 3 | 1 | 0.105 | 0.0239 | 0.14 | 70.9 | 0.139 | 0.196 | 0.45 |
| t2_sym_double_well | 4 | 3 | 4.7e-06 | 0.0627 | 0.000131 | 786 | 0.014 | 0.0938 | 0.28 |
| t3_triangular_bias | 35 | 8 | 0.0227 | 0.014 | 0.248 | 46.9 | 0.00051 | 0.0986 | 0.66 |
| t4_thick_double_barrier | 0 | 4 | - | - | 3.54e-29 | 141 | 0.0074 | 0.0348 | 0.28 |
| t5_superlattice | 6 | 5 | 0.00524 | 0.0093 | 4.18e-05 | 70.7 | 0.0145 | 0.243 | 1.77 |
| t6_graded_leads | 2 | 3 | 0.145 | 0.00257 | 0.00202 | 71.6 | 0.06 | 0.0671 | 2.12 |
| t7_rect_barrier | 0 | 3 | - | - | 1.63e-05 | 39.8 | 0.0735 | 0.0359 | 0.32 |
| t8_thick_barrier | 0 | 6 | - | - | 1.18e-26 | 37 | 0.0114 | 2.07 | 0.30 |
| t9_large_airy | 37 | 9 | 0.00116 | 0.00663 | 0.171 | 339 | 0.00181 | 0.00595 | 0.79 |

(The runtimes in this table are in-process and were taken while two hp runs shared the CPU.)

Two windows were narrowed while the structures were built, because the first versions violated
or nearly violated guarantee 3:

- t4 [1.02, 1.6] contained a maximum pair with contrast 8e-6, so it became [1.02, 1.3].
- t2 [0.29, 0.62] had a pair with contrast 1.34e-3, so it became [0.29, 0.52].

## Precision (maximum absolute or relative deviation)

**Columns:**

- **hp E bound:** bound-state energy difference from `hp.py`, in eV.
- **hp T:** relative difference of query T from `hp.py`.
- **hp E max:** maximum energy difference from `hp.py`, in eV.
- **hp T max:** relative difference of T at the maxima from `hp.py`.
- **hp dT/dE:** analytic derivative against an hp central difference, relative to
  max(|dT/dE|, T).
- **cons:** | |r|^2 + T - 1 |.
- **rev:** T for incidence from the right divided by T from the left, minus 1.
- **count ok:** Sturm count consistency at E_n -/+ 1e-9 and at E_top.
- **det vs count:** determinant root against bisection on the Sturm count alone.
- **scan:** maxima found by an independent 1e-5 eV T-value scan, and whether they agree.

| id | hp E bound | hp T | hp E max | hp T max | hp dT/dE | cons | rev | count ok | det vs count | scan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1_single_well | 9.0e-17 | 1.3e-15 | 1.1e-16 | 6.7e-16 | 6.3e-15 | 6.7e-16 | 0 | yes | 8.3e-17 | 1 agree |
| t2_sym_double_well | 5.6e-17 | 1.0e-15 | 5.6e-17 | 1.3e-15 | 7.2e-15 | 1.3e-15 | 0 | yes | 9.9e-15 | 3 agree |
| t3_triangular_bias | 4.4e-16 | 2.1e-14 | 1.3e-15 | 3.6e-15 | 7.2e-13 | 6.7e-16 | 1.7e-15 | yes | 4.4e-16 | 8 agree |
| t4_thick_double_barrier | - | 4.9e-15 | 2.2e-16 | 8.9e-16 | 1.5e-14 | 8.9e-16 | 0 | yes | - | 4 agree |
| t5_superlattice | 1.2e-16 | 1.6e-15 | 1.1e-16 | 1.8e-15 | 7.2e-15 | 1.8e-15 | 8.9e-16 | yes | 1.5e-16 | 5 agree |
| t6_graded_leads | 2.8e-17 | 7.3e-15 | 8.9e-16 | 8.9e-16 | 7.3e-15 | 1.3e-15 | 1.9e-14 | yes | 2.8e-17 | 3 agree |
| t7_rect_barrier | - | 1.7e-15 | 0 | 0 | 9.2e-16 | 4.4e-16 | 0 | yes | - | 3 agree |
| t8_thick_barrier | - | 1.2e-15 | 4.4e-16 | 0 | 6.1e-15 | 2.2e-16 | 0 | yes | - | 6 agree |
| t9_large_airy | 2.9e-15 | 3.0e-13 | 3.6e-15 | 6.4e-14 | 4.9e-13 | 8.9e-16 | 2.2e-15 | yes | 8.1e-14 | 9 agree |

**Closed forms** (`closed_form_results.json`):

- t1: bound states 9.0e-17 eV, T 8.9e-16, maximum energy 1.1e-16 eV, |T - 1| = 6.7e-16.
- t2: 8.3e-17 eV, including the 4.705e-6 eV splitting.
- t3: 13 lowest states 3.9e-16 eV. The finite wall lowers them by about 0.0141 eV relative to
  the infinite-wall Airy-zero formula.
- t7: T 2.0e-15, 3 maxima within 5.6e-17 eV.
- t8: T 1.1e-15 down to 1.18e-26, 6 maxima within 4.4e-16 eV.
- **Infinite-well limit** (out of domain on purpose, barrier height up to 1e6 eV): the relative
  deviation from C (n pi/L)^2/m_w approaches -4 m_b/(m_w kappa L) (ratio 0.94, 0.994, 0.9994).
- **Triangular infinite-wall limit:** the deviation from (C F^2/m)^{1/3} |a_n| falls as
  1/sqrt(V_wall).

## The 28 gen structures (`check_results_gen.json`; reports in `../out_gen/`)

**All checks pass:**

- Sturm count consistent.
- The maxima count agrees with an independent scan for all 28.

**Maximum deviations against hp:**

| quantity | max deviation | structure |
| --- | --- | --- |
| bound-state energies | 3.3e-16 eV | held_21 |
| query T | 1.5e-13 | held_07 |
| maximum energies | 4.8e-14 eV | held_17 |
| maximum T | 1.3e-14 | held_17 |
| analytic dT/dE | 1.4e-12 | model_02 |
| conservation | 1.3e-14 | |
| reversal | 1.4e-13 | |

**Contents:** 120 bound states (at most 12 in one structure), 90 maxima, and a minimum query T
of 9.3e-30.

**Runs and timing:**

- Each was a CLI run under the verifier environment (`env -i`, single-threaded BLAS, fresh
  working directory).
- Wall time ranged from 0.46 s to 1.15 s per call (maximum held_10), 16.4 s for all 28.
- Three runs produced byte-identical reports.
- held_03 was replaced by the coordinator at 23:11. `out_gen/held_03.json` and its checks come
  from the new file (6 states, lowest pair split by 1.759e-5 eV).

## Noise-pair filter

The maxima routine discards adjacent extremum pairs whose T values differ by less than 1e-7
relative. Instrumented with `maxima(..., stats=)`, it removed 0 pairs over all 37 structures.
