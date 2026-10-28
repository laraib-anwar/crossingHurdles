# Reference A test frames

Files:

- `frames/` holds the 10 frames, written by `make_frames.py`. All are inside the FRAME_SPEC
  domain and satisfy the section-2 guarantees.
- `reports/` holds the reference.py reports.
- `run_checks.py` runs all internal checks and writes `check_results.json`.
- `hp_check.py` re-solves a report in 60-digit decimal arithmetic.
- `check_results_gen.json` summarises the 28 gen frames, whose reports are in `../out_gen/`.

Rerun with:

```
/Users/adnananwar/.venvs/tbs/bin/python make_frames.py
/Users/adnananwar/.venvs/tbs/bin/python run_checks.py      # about 75 s, rewrites reports/
```

| frame | what it exercises | key results |
| --- | --- | --- |
| t1_cantilever3 | 3 collinear members along a 30 deg line, clamped at node 1; tip force, axial pull, uniform transverse load; harmonic tip receptance | the 8 frequencies equal the closed-form cantilever bending values (beta L = 1.8751041, 4.6940911, 7.8547574, ...) and axial fixed-free values to at most 9.9e-16; statics at all 3 free nodes to at most 6.0e-16 of the kind maximum; tip receptance (sin cosh - cos sinh)/(EI k^3 (1 + cos cosh)) and L tan(alpha)/(EA alpha) to at most 5.8e-16 |
| t2_ssbeam | pin and roller, 2 members, node at a = 2.9 of 6.3 m; point and uniform loads and an end axial load | frequencies = (n pi)^2 bending and (2n-1) pi/2 axial to 3.3e-16; static ux, uy, rz to 1.2e-16, 1.9e-16, 4.3e-16 |
| t3_portal | fixed portal with different column and beam sections; lateral, vertical and moment loads; uniform loads on beam and column; 4 harmonic queries in 2 reciprocal pairs, one 1.8 % from a resonance | hp60 frequencies 5.4e-16, harmonic 3.2e-14; reciprocity 3e-16 |
| t4_fixedfixed | member 1 joins two fully fixed supports (member-local modes), interleaved with the modes of a stocky column and strut carrying an 850 kg mass | all 10 clamped-clamped local modes below the 12th frequency (beta L = 4.7300408, 7.8532046, ...) appear, to at most 6.0e-16 |
| t5_closepair | nearly symmetric two-bay frame, stocky columns, slender beams, bays differ by 0.03 mm | pairs 1.7e-4 to 3.6e-4 apart, certified; hp60 3.8e-16 |
| t6_masses | two-storey frame with four lumped floor masses; harmonic queries below (1.21 Hz) and above (7.93 Hz) the first frequency, in reciprocal pairs | reciprocity at most 7.6e-16; hp60 4.3e-16 |
| t7_slender_stocky | inclined slender tie (L/r about 970), stocky concrete post, roller, lumped mass | count_below 10; hp60 3.5e-16; statics 7.5e-16 |
| t8_local40 | only member-local modes up to f_max: a 14.2 m member between fixed supports (lambda = 39.35 at f_max) and two short fixed-fixed members 2e-6 apart in length (pairs 4.0e-6 apart) | the 12 frequencies and count_below (17) equal the closed form (max 5.9e-16); located roots up to lambda = 42.4 agree with hp60 to at most 4.3e-16 |
| t9_stress16 | domain maximum: 12 nodes, 16 members (3 bays x 2 storeys, two slender braces), lambda = 39.5 at f_max, 4 harmonic queries | count_below 54, confirmed by 55 located roots; 5 s; hp60 5.8e-16 |
| t10_extreme | domain corner: 19.7 m member with A = 5e-2 and I = 1e-7 (L/r about 14000) on a stocky column | hp60 frequencies 4.0e-16, harmonic 1.6e-16, statics 1.1e-16 |

Cross-cutting checks in `check_results.json`:

- **Determinism.** All 10 frames, run twice in fresh directories with the verifier's
  environment, gave byte-identical reports.
- **Report format.** Every report has exactly the section-4 keys, the query fields echoed, and
  finite numbers.
- **h-version cubic Hermite FE.** The error against the exact roots falls with observed order
  3.9 to 4.0 (2, 4, 8, 16 elements per member; t1, t3, t6). At 16 elements per member it
  reaches the 1e-8 rounding floor of that model, which is why reference.py uses the p-version
  for counting.
- **Block LDL^T count.** It equals the dense Bunch-Kaufman LDL^T inertia of the assembled
  p-version FE matrix at all 33 points (t3, t5, t6).
- **Taylor propagator vs `scipy.linalg.expm`.** They agree to at most 4.3e-16, and the det
  roots computed with either agree to at most 1.6e-15.
- **Diagnostics from `--diag`.** Statics vs the classical stiffness method at most 5.5e-14.
  Harmonic vs the p-version FE condensation at most 1.2e-13. det roots vs the fine p-FE
  eigenvalues at most 2.8e-13.

Gen frames (`check_results_gen.json`):

- all 28 exit with status 0, in at most 2.5 s each;
- all are certified, and count_below matches the det roots on every frame;
- hp60 agrees to at most 6.8e-16 (frequencies), 5.3e-14 (harmonic) and 2.9e-14 (statics);
- by my values, all 28 satisfy guarantees 2 to 4. Max lambda is 12.1, the smallest gap is
  5.7e-3, f_max is at least 1.3e-4 from every frequency, and every harmonic frequency is at
  least 1.31e-2 from every natural frequency.
