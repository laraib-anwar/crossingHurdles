# Reference B: finite-element referee for FRAME_SPEC

Independent referee for the frame-vibration-audit task. It checks a report (section 4 of
FRAME_SPEC.md) against values it computes itself with a convergent finite element model and
Richardson extrapolation. It shares nothing with closed-form dynamic stiffness: no transcendental
member functions, no Wittrick-Williams count, no root finding on a determinant. Inputs used while
building it: FRAME_SPEC.md, the frames, and the oracle reports as data. Nothing under `solution/`,
`refA/`, `tools/` or `controls/` was read.

## Usage

```
python refB/referee.py --frame F.json --report R.json [--out verdict.json] [--quiet] [--verbose]
python refB/referee.py --solve --frame F.json --output R.json [--out diagnostics.json]
sh refB/run_set.sh FRAMEDIR REPDIR OUTDIR [PAR]      # OUTDIR/<id>.json + <id>.log + summary.txt
python refB/tests/run_tests.py [--pair FRAME REPORT ...]
```

Exit status: 0 pass, 1 fail, 2 referee cannot certify (uncertainty above 1e-7, invalid frame,
internal error). The stdout summary line is
`<id> pass=<bool> freq=<worst rel residual> static=<worst residual/scale> harmonic=<worst residual/scale> count=<report>/<reference> t=<s>`.
`--solve` writes a full section-4 report from the referee's own extrapolated values (third opinion).
Python 3.11, NumPy 1.26.4, SciPy 1.11.4; needs 80-bit `numpy.longdouble` (x86-64).

## Discretisation

* Each member k is split into n_k equal elements. Element = cubic Hermite bending (v, theta at both
  ends) + cubic Lagrange axial (end nodes plus two internal nodes at h/3 and 2h/3), consistent mass
  rho A from the same interpolations (no rotary inertia), rotated to global axes. Interior FE nodes
  carry global (ux, uy, rz); internal axial DOFs are element-owned. Lumped masses go on ux, uy of the
  frame node. Supports delete DOFs. Element matrices are built in exact rational arithmetic.
* The model is conforming (H2 bending, H1 axial, rigid joints), so it is a Rayleigh-Ritz method:
  every FE eigenvalue is an upper bound of the exact one, and the meshes n_k 2^l are nested, so the
  k-th FE eigenvalue decreases monotonically with l. Member-local modes (a member between two fixed
  nodes) appear naturally.
* Mesh design: a preliminary FE run gives an upper bound of the (n_modes+1)-th frequency; the design
  frequency is omega_T = max(that, omega_max, every omega_h). Base count
  n0_k = max(4, ceil(lambda_k(omega_T)/2), ceil(alpha_k(omega_T)/2)), i.e. beta h <= 2 and
  omega h sqrt(rho/E) <= 2 on the coarsest mesh. Levels l = 0..4 use n0_k 2^l elements (4, 8, 16,
  32, 64 for a member with small lambda). If the worst uncertainty exceeds 1e-10, up to two more
  levels are added (DOF cap 200000, time budget 150 s). On the 28 frames the finest mesh has 960 to
  4782 DOF; the domain-edge stress frame (16 members, lambda 39.8) has 12616. Sparse solvers make
  the suggested ~6000 DOF cap unnecessary, so the cap is set higher. It was never reached.

## Precision engineering (why longdouble)

In double precision, rounding of the stiffness entries breaks the exact rigid-body null space of
each element (12EI/h^3 times h is not exactly 2 times 6EI/h^2, and inclined members add rotation
rounding). Each element then injects an energy error of order eps (beta h)^-4. Measured: the lowest
eigenvalue of a simply supported beam at n = 128 is off by 2.4e-10. On model_01 and model_02 the
double eigsh values differ from the converged ones by 2e-8 and 1e-7 at the finest levels. The
referee therefore:

1. computes eigenvectors with double shift-invert Lanczos (`eigsh`, sigma = 0, tol 1e-12);
2. applies two subspace-iteration steps Y <- K^-1 M Y, each solve iteratively refined with residuals
   in longdouble (`K_apply`, `M_apply`): element forces come from deformation quantities only
   (natural rotations theta_i - (v2 - v1)/h and axial differences), so rigid motion contributes
   exactly zero;
3. performs Rayleigh-Ritz in longdouble: A = G^T G with G the per-element strain coordinates
   (Cholesky factors of the element deformation stiffness), B = Y^T M Y, then Cholesky and cyclic
   Jacobi in longdouble.

Static and harmonic solves use double sparse LU with 5 to 6 longdouble-residual refinement steps.
With this, level values carry about 1e-17 relative error, and the extrapolation error controls the
result.

## Richardson extrapolation and uncertainty

Romberg table in the mesh parameter t = 2^-l with exponents 4, 6, 8, 10 (at most 4 elimination
columns). The exponents were verified, not assumed. In the last triple of every sequence, bending
eigenvalues show observed order 3.99 to 4.00, cubic-axial eigenvalues 6.00, and harmonic nodal
amplitudes 3.99 to 4.00. No odd powers appear: on the 28 frames, 221 of 243 frequency sequences
are order 4 and 22 are order 6. The uncertainty is built from the last two extrapolants in the final
row: u = max(10 |T[L][L] - T[L][L-1]|, 1e-15 relative). The bare difference was below the true error
in some cases: at roundoff level (true errors 1.2e-16 to 4.9e-16), and twice in the portal test
against its fine-mesh truth (ratios 3.8 and 6.9). The factor 10 and the floor bound every error
observed. The diagonal difference |T[L][L] - T[L-1][L-1]| is also recorded. It is 3 to 5 orders more
pessimistic, and it replaces u when the last observed order is outside [3.5, 4.6] and [5.4, 6.6]
(irregular convergence; never happened on the 28 frames).

| test, 12 modes, production design (5 levels) | true error of extrapolant | u (final definition) |
| -------------------------------------------- | ------------------------- | -------------------- |
| SS beam, one member (closed form)             | <= 3.8e-15                | <= 1.0e-12           |
| 3-member cantilever (closed form)             | <= 1.8e-14                | <= 2.1e-12           |
| asymmetric portal, close pairs (fine truth)   | <= 2.7e-13                | <= 4.3e-12           |
| tip receptance, inclined cantilever (closed)  | 3.6e-15                   | 6.0e-13              |

Close pairs: for consecutive eigenvalues with gap < 1e-3 relative on the finest mesh, the sum and
the squared difference (smooth even through FE mode mixing) are extrapolated as well. If the pair
values disagree with the per-index values by more than 3u, u is widened to the disagreement. Pairs
down to a 4e-4 gap in asymmetric portals behaved like isolated modes (errors <= 2.7e-13). No pair in
the 28 frames is closer than 1e-3.

## Checks

1. **Section 4** exactly: key sets, list lengths, finite numbers (int and float, no bool), echoed
   fields equal to the frame (node ids must be JSON integers), file conventions (regular file, not a
   symlink, non-empty, at most 10^6 bytes, UTF-8, no duplicate keys, no NaN or Infinity).
2. **Statics**: classical 2-node element (linear axial + Hermite), exact fixed-end actions
   (q_a L/2, q_t L/2, +-q_t L^2/12 in member axes; wx, wy per unit member length). Repeated
   nodal-load or member-load entries are summed. Cross-checked by splitting every member into 8
   and 32 elements with consistent loads, and by the cubic-axial dynamic mesh at omega = 0 (n = 8).
   All are nodally exact, and they agree to <= 1.3e-16 of S on all 28 frames. Rule: |v - v_ref| <=
   max(1e-9, 3 u) max(|v_ref|, S).
3. **Frequencies**: n_modes + 1 extrapolated frequencies (the extra one completes the ordering
   check), and |f - f_ref| / f_ref <= max(1e-9, 3 u). Completeness: Sylvester inertia of
   K - sigma M at the midpoint between the (n_modes+1)-th and (n_modes+2)-th FE eigenvalue must equal
   n_modes + 1 on every level, so Lanczos cannot have skipped a mode.
4. **count_below**: inertia of K - omega_max^2 M on the finest mesh by LDL^T with diagonal pivots
   (SuperLU symmetric mode). The MMD and reverse Cuthill-McKee orderings must give the same count,
   and the pivot order is checked to be symmetric. FE eigenvalues are upper bounds, so the count can
   only be too low, and only through eigenvalues just above f_max. Those (global index from the
   inertia) are extrapolated across the last three levels, and any whose limit falls at or below
   f_max is added. Crossings found on the 28 frames: none. The smallest f_max separation is 1.3e-4
   relative.
5. **Harmonic**: (K - omega_h^2 M) U = F on every level, refined, Romberg, same section 5 rule.
6. **Self-certification**: if any frequency, harmonic or static uncertainty exceeds 1e-7, the
   verdict is a refusal (exit 2), never a pass.
7. **Domain warnings** (not failures): guarantee 1 (Cholesky and eigenvalues of the supported static
   stiffness), guarantee 2 (consecutive separations up to n_modes + 1, f_max against the
   extrapolated neighbours, f_h against the nearest FE eigenvalues), guarantee 3 (lambda, alpha at
   max of f_{n_modes}, f_max, f_h), guarantee 4 (both groupings, see ambiguities), and section 2 and 3
   ranges.

## Measured results

* Closed-form tests (`tests/run_tests.py`, 118 checks, 0 failed, log in `tests/out/run_tests.log`):
  cantilever frequencies (bending roots of 1 + cos x cosh x = 0, i.e. beta L = 1.875104, 4.694091,
  7.854757, ..., merged with axial modes) to 1.6e-16, tip statics to 1.7e-16 of S, three tip
  receptances to 5.1e-16. SS beam (beta L = n pi plus axial fixed-free) to 8.6e-17, statics to
  9.5e-17, midspan and axial receptances to 9.7e-17. Portal frame tie clamped at both ends: its
  clamped-clamped frequencies (beta L = 4.730041, 7.853205, 10.995608) appear among the natural
  frequencies to 7e-16. Every negative test fails as required: frequency shifted by +-3e-9,
  dropped frequency, count_below +-1, static displacement and harmonic amplitude shifted by 3e-9
  (relative, or of the section-5 scale when another value sets the scale), extra key, reversed list.
  The 3e-10 controls pass.
* Oracle reports, 28 frames: **28/28 pass** (`out/summary.txt`). Worst residuals: frequency 1.1e-10
  (model_02, next worst 3.3e-13), static 1.9e-13, harmonic 1.9e-13. Referee uncertainty: frequency
  <= 1.1e-11 relative (held_07), harmonic <= 1.1e-16 absolute, static <= 1.3e-16 of S. Tolerances
  are therefore exactly the verifier's 1e-9. All frames use 5 levels; the finest mesh has 960 to
  4782 DOF. Runtime 0.6 to 3.7 s per frame (i5-8210Y, two in parallel). The domain-edge stress frame
  runs in 4.6 s.
* model_02 frequency 9 (319.39672509 Hz): the oracle is 1.09e-10 relative away from the referee.
  Three FE designs (base counts 7, 13 and 18 per member, 5 and 6 levels) agree to 3e-15. A
  longdouble transfer-matrix solution (cancellation-limited to about 1e-11 at this beta L) puts the
  oracle 1.22e-10 off. Modes 6 and 8 show the same signature at 5.6e-12 and 6.6e-12. The report
  side is off. It still passes (1.09e-10 < 1e-9), but this is the only residual above 4e-13 in the
  set, and it grows with frequency on a 2-member cantilever (member lambda about 12).

## Spec sentences found ambiguous

1. Guarantee 4: "(`ux`, `uy` and harmonic translations in m; `rz` and harmonic rotations in rad,
   each group compared within itself)", used by section 5: "`S` is the largest magnitude of the
   reference values of its kind in the report". This can mean two groups by unit or five groups
   (static ux, static uy, static rz, harmonic translations, harmonic rotations). The referee grades
   with the two unit groups. It records the per-quantity residual too and lists any value that
   would fail under five groups (`per_quantity_grouping_failures`, empty on all 28 frames).
2. Guarantee 4: "Every reported static displacement and harmonic amplitude has magnitude at least
   `1e-9` times the largest magnitude of its kind". This does not hold for 7 queries in 5 frames,
   which are exactly zero in both the oracle and the referee. Five apply the harmonic load to a
   supported DOF (held_16 q1, held_19 q0, model_05 q0, q1, q2); the spec ("A harmonic nodal force or
   moment of amplitude `P` at node `n`, degree of freedom `d`") does not forbid that. Two are
   axial-bending decoupling on a straight beam (held_20 q0, model_02 q0). Grading is unaffected,
   because the S floor makes 0 against 0 pass.
3. "a uniform member load `wx`, `wy` (N/m, global directions) acts along a member": per unit member
   length or per unit projected length. Per member length is assumed, which matches the fixed-end
   moment q_t L^2/12 with L the member length. The oracle agrees to 1e-13.
4. Section 3 does not say that `nodal_loads` (or `member_loads`) entries for the same node or
   member add up. model_01 has two entries on node 2. They are summed, and the oracle agrees.
5. "as given" (echoed report fields): whether 5.0 for node 5, or 49264.0 for amplitude 49264, counts
   as given. The referee requires JSON integers for node ids and numeric equality for amplitude and
   f_Hz.
6. "at most 1 MB": 10^6 or 2^20 bytes. The referee uses 10^6.
7. "Numbers are finite JSON numbers at full double precision": "full double precision" cannot be
   checked and is not enforced.

## Files

* `referee.py`: referee and solver (single file).
* `run_set.sh`: batch runner.
* `tests/`: `tb_cantilever.json`, `tb_ssbeam.json`, `tb_fixedmember.json` (hand-verified),
  `tb_stress16.json` (domain edge), `run_tests.py`, and `out/` (solver reports, diagnostics, test
  log).
* `out/`: verdicts and logs for the 28 oracle reports.
