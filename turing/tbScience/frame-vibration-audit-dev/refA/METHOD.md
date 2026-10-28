# Reference A: method, independence and measured precision

`reference.py` is one file that needs only NumPy 1.26.4 and SciPy 1.11.4 (plus the standard
`fractions` module):

```
python reference.py --frame <frame.json> --output <report.json> [--diag <diag.json>]
```

It writes the section-4 report of FRAME_SPEC: `frame_id`, `static`, `frequencies_Hz`,
`count_below`, `harmonic`. Every number goes through an explicit finiteness check, then
`json.dumps(..., allow_nan=False)`. Query fields (`node`, `load_node`, `amplitude`, `f_Hz` and
so on) are echoed as parsed. The input is read with a duplicate-key check. The optional
`--diag` file holds the certification data and the cross-checks described below. The program
is deterministic: two runs of every test frame, each in a fresh directory with the verifier's
environment, gave byte-identical reports, and so did two complete passes over the 28 gen frames.
Runtime is 0.9 to 7.3 s per test frame across runs on this machine (one BLAS thread). The slowest
is t9: 16 members, with 55 roots located for the count_below cross-check. The 28 gen frames take at
most 2.5 s each.

## 1. Model and sign conventions

The member local axis x' runs from node i to node j, with c = (xj - xi)/L and s = (yj - yi)/L.
Local end displacements are u = c ux + s uy, v = -s ux + c uy and theta = rz. Along xi = s'/L
in [0, 1] each member carries:

| block | state | equations (omega = 2 pi f) |
| --- | --- | --- |
| axial | u, N (tension +) | u' = N/EA, N' = -rho A omega^2 u - q_a |
| bending | v, theta = v', M = EI v'', Q = M' | v' = theta, theta' = M/EI, M' = Q, Q' = rho A omega^2 v + q_t |

Here q_a = wx c + wy s and q_t = -wx s + wy c are the uniform member loads, taken per unit
member length. The loads enter the statics only. The force that a member exerts on its node,
in local axes, is (N, -Q, M) at end i and (-N, Q, -M) at end j. This follows from the internal
moment M = EI v'' acting counterclockwise on the left part, with shear S = -M'. The node
equation is sum(member forces) + m omega^2 (ux, uy) + P = 0.

**Scaled states.** Let lambda = L (rho A omega^2/EI)^(1/4), alpha = omega L sqrt(rho/E),
sigma = max(lambda, 1) and sigma_a = max(alpha, 1). The scaled states are
z = (v, L theta/sigma, M L^2/(EI sigma^2), Q L^3/(EI sigma^3)) and w = (u, N L/(EA sigma_a)).
With them, dz/dxi = sigma C_mu z, where C_mu is the cyclic shift with mu = (lambda/sigma)^4 in
the corner. Likewise dw/dxi = sigma_a [[0, 1], [-(alpha/sigma_a)^2, 0]] w. For lambda >= 1,
C_mu is a permutation matrix (normal, eigenvalues +-1, +-i). The scaled propagators therefore
have singular values exp(+-sigma h) and 1, with no extra non-normal growth.

## 2. Natural frequencies: one global system in the member end states

**Member subspace.** The admissible bending end-state pairs [z(0); z(1)] form a
4-dimensional subspace of R^8, which is the graph of the transfer T = exp(sigma C_mu). Forming T
directly fails for large lambda. Its entries are about e^lambda / 2, so the decaying and
oscillatory parts drop below rounding: with a single exponential per member, roots were lost
for lambda above about 20 (table below). The subspace is propagated over n_s =
ceil(max sigma) equal segments instead, so the growth per segment is at most e. Each segment
applies the propagator Phi = exp(sigma C_mu / n_s) to the bottom half of the basis. The basis
is then re-orthonormalised by a batched QR whose R is forced to have a positive diagonal.

Because a product of upper-triangular matrices with positive diagonals is again such a matrix,
the final basis W is exactly the unique positive-R QR factor of [I; T]. So W does not depend on
the number of segments and is continuous in omega. Phi is a Taylor series summed until the next
term is below 1e-18, using ||sigma C_mu / n_s|| <= 1. `scipy.linalg.expm` is the cross-check.
The axial exponential is a rotation, so it is computed by Taylor series with scaling and
squaring, and [I; T_a] is orthonormalised the same way.

**Global matrix G(omega).** The unknowns are the 6 basis coordinates of every member, which
are its 12 end states through [y(0); y(1)] = W a, and the 3 displacements D of every node. The
rows are:

- at every member end, 3 compatibility rows (local to global): c u - s v = Dx, s u + c v = Dy,
  L theta = L Dr;
- at every node dof, either the support row D = 0 or the equilibrium row (section 1) with
  m omega^2 D for the translations.

This is the end-state system of the brief with the 6 member relations (y(1) = T y(0)) already
built into the basis: det G equals the 12-unknowns-per-member determinant times a positive
factor. Natural frequencies are the zeros of det G(omega). det G is computed by LU with
partial pivoting, after positive row scaling, as sign times log |det|. Every change of
representation contributes a positive factor:

- the QR R factors;
- the sigma scalings, which are continuous in omega;
- the row scaling.

So the sign of det G changes exactly at roots of odd multiplicity. A member vibrating between
two nodes that do not move gives a zero of det G like any other mode. For example, a member
between two fully fixed supports makes the 6 x 6 block of its displacement rows singular at
its clamped-clamped frequencies.

**Counting: an independent FE model.** Wittrick-Williams is not used, and neither is any
closed-form member function. The count of natural frequencies below omega comes from a
conforming finite element model of the same frame:

- one element per member;
- cubic Hermite (bending) and linear (axial) nodal shape functions;
- hierarchical bubbles: twice-integrated Legendre polynomials for bending, once-integrated for
  axial;
- consistent mass, exact Gauss quadrature, lumped nodal masses added.

The bubbles are orthogonal in energy to each other and to the nodal functions. So the
member-interior stiffness is diagonal and K_ib = 0, and the interior generalized eigenproblem
reduces to a standard symmetric eigenproblem of the interior mass matrix.

The number of FE eigenvalues below omega^2 is the inertia of K - omega^2 M. It is evaluated by
a block LDL^T that eliminates every member interior first, using Sylvester's law and Haynsworth
additivity. The count is the number of interior eigenvalues below omega^2 plus the number of
negative eigenvalues of the node-dof Schur complement:

S = K_bb - w M_bb - w^2 P^T diag(1/(lam - w)) P,   with w = omega^2 and P = Phi^T M_ib.

The Schur complement is diagonally scaled (a congruence) before `eigvalsh`. The static part has
no cancellation, because K_ib = 0. In the tests, this block count equals the inertia of a dense
Bunch-Kaufman LDL^T (`scipy.linalg.ldl`) of the assembled FE matrix at all 33 points tried
(t3, t5, t6).

The two refinements are the polynomial degrees ceil(lambda_top) + 18 (fine) and
ceil(lambda_top) + 10 (coarse) per member, and likewise with alpha for axial. Here lambda_top is
the member's lambda at 1.02 max(f_(n_modes+1), f_max, f_h). The two spaces are nested, so both
models give Rayleigh-Ritz upper bounds.

**Isolation and refinement.**

1. Pre-passes at low degree converge the (n_modes+1)-th FE eigenvalue, which fixes the
   frequency range.
2. The fine and coarse FE eigenvalues are found by bisection on the count to 1e-13.
3. Exact root k is searched in [e_k (1 - tau), e_k (1 + min(tau, 1e-9))], with tau starting
   at max(4 |e_coarse - e_fine|/e, 1e-11). The window widens by 10x until det G changes sign,
   and it never reaches below root k-1. brentq then refines the root (rtol 8.9e-16).
4. Certification: at the midpoints between consecutive roots (and at r_1/2), the FE count at
   both degrees must equal the index. The FE count must step by exactly one between consecutive
   roots, and |r_k/e_k - 1| must be at most 1e-8. If the certification fails, the degree rises
   by 12 and the run repeats, up to 4 times. If it still fails, the program raises an error
   rather than write an uncertified report. It never needed a retry on the 38 frames.
5. This is done for the lowest n_modes + 1 roots.

**count_below.** At both degrees, the FE count must be the same at f_max (1 - 1e-8), f_max and
f_max (1 + 1e-8). The FE error is at most about 1e-12 (measured below), and f_max is at least
1e-6 relative away from every frequency (guarantee 2). So no FE eigenvalue can lie on the other
side of f_max from its exact frequency.

As a diagnostic, every root up to the first one above f_max is also located by det G and
certified the same way (when count_below >= n_modes + 1). The program checks that the number of
those roots at or below f_max equals the FE count. It did on all 38 frames (up to 54 roots in
t9).

## 3. Statics and harmonic response

**Statics** use the same end-state formulation at omega = 0, with 12 end-state unknowns per
member plus the node displacements. The member relation is y(1) = T y(0) + p in the
dimensionless states (u, N L/EA, v, L theta, M L^2/EI, Q L^3/EI). T and the particular
solution p of the uniform load come from the exponential of the augmented nilpotent 7 x 7
matrix. Its Taylor series terminates, so the polynomials are exact. The system is solved by LU,
then refined with residuals evaluated exactly in rationals (`fractions`) from the double
entries, so the double system is solved to the last bit. The result is cross-checked against
the classical stiffness method with fixed-end actions (q_a L/2, q_t L/2, +-q_t L^2/12) in the
diagnostics.

**Harmonic response.** G(omega_h) is solved with -P on the load dof's equilibrium row, using
the same refinement. U is the node unknown. The cross-check is the p-version FE dynamic
condensation S(omega_h) D = P.

## 4. Independence

I read only FRAME_SPEC.md and, as inputs, the gen frame files. I did not open anything under
`solution/`, `refB/`, `tools/`, `controls/` or `fin/`. There is no
sin/cos/sinh/cosh member function, no dynamic stiffness matrix of the closed form and no J0 or
s{K} count anywhere in reference.py. The member transfer is numerical (Taylor series of
exp(hA)), the determinant is that of an end-state system, and the count comes from a
discretised FE inertia. Closed-form frequency equations (cos b cosh b = +-1, n pi) appear only
in `tests/run_checks.py`, for validation.

**Deviation from the brief, and why.** The brief suggested an h-version cubic-Hermite/linear
FE with many elements per member. I measured that model on the cantilever (L = 4.3 m):

| elements | eigh | dense LDL^T count | expected discretisation error |
| --- | --- | --- | --- |
| 78 | -5.3e-8 | -1.2e-9 | +2.3e-10 |
| 160 | +7.2e-7 | -3.1e-9 | +1.3e-11 |

The FE eigenvalue error reaches a rounding floor of 1e-9 to 1e-6, because the condition number
grows like n^4. Linear axial elements converge only as h^2 ((k h)^2/24 in frequency). Such a
model cannot certify counts and separate pairs 1e-6 apart at lambda = 40 within the time limit.

The p-version uses the same nodal functions plus bubbles. It converges exponentially and has no
such floor:

| frame | degree margin | max relative error vs the exact roots |
| --- | --- | --- |
| t3 | -6 | 0.49 |
| t3 | -2 | 2e-2 |
| t3 | +2 | 5e-7 |
| t3 | +6 | 1.4e-13 |
| t3 | +10 | 1.9e-14 |
| t3 | +18 | 7e-15 |
| t8 (lambda up to 33) | +2 | 3.5e-12 |
| t8 (lambda up to 33) | +6 | 6.7e-15 |

The h-version is kept in the tests to show the requested h^4 convergence toward the exact
roots. The observed orders, from 2 to 4 to 8 to 16 elements per member, are 3.9 to 4.0 for t3,
t6 and t1. At 16 elements the error is down to the 1e-8 rounding floor.

## 5. Measured precision

"hp60" is `tests/hp_check.py`. It re-evaluates the same end-state system in 60-digit decimal
arithmetic, with the plain (unstabilised) transfer T = exp(A) and Gaussian elimination. Every
reported frequency is re-solved by secant iteration on det, and every harmonic amplitude and
static displacement is re-solved directly. Static errors are relative to the largest magnitude
of the same component among the query nodes.

| check | result |
| --- | --- |
| cantilever, 3 collinear members at 30 deg, 8 modes (beta L = 1.8751041, 4.6940911, 7.8547574, ... and axial (2n-1) pi/2) | max rel 9.9e-16; count_below exact |
| simply supported beam, 2 members (n pi, axial fixed-free) | max rel 3.3e-16; count_below exact |
| member between fixed supports inside a frame (t4): 10 clamped-clamped local modes (beta L = 4.7300408, 7.8532046, ...) interleaved with frame modes | all found, max rel 6.0e-16 |
| t8: only member-local modes up to f_max (lambda = 39.35 at f_max, pairs 4.0e-6 apart) | max rel 5.9e-16; count_below 17 exact; roots 13 to 18 (lambda 35 to 42.4) vs hp60 at most 4.3e-16 |
| static closed forms (cantilever tip and intermediate nodes, axial, uniform load; SS beam with point and uniform load) | at most 6.0e-16 |
| cantilever tip receptance (sin cosh - cos sinh)/(EI k^3 (1 + cos cosh)) and the axial bar L tan(alpha)/(EA alpha) at 23.7 Hz | 5.8e-16, 5.0e-16 |
| hp60, frequencies, 10 test frames and 28 gen frames | at most 1.0e-15 and 6.8e-16 |
| hp60, harmonic U | at most 4.3e-14 (test frames) and 5.3e-14 (gen frames); the largest values are 1 to 2 % from a resonance |
| hp60, statics (relative to the kind maximum) | at most 1.1e-15 (test frames) and 2.9e-14 (gen frames, held_17) |
| det G roots vs fine p-FE eigenvalues | at most 2.8e-13 (tests) and 3.5e-13 (gen) |
| reciprocity U(a <- b) = U(b <- a), 9 pairs (force-force, force-moment) | at most 1.05e-15 |
| Taylor propagator vs `scipy.linalg.expm` | at most 4.3e-16; det roots with either propagator agree to at most 1.6e-15 |
| statics vs the classical stiffness method (double, no refinement) | at most 5.5e-14 (tests) and 1.8e-13 (gen, model_01); where they differ, hp60 agrees with reference.py (model_01 8e-16, t10 1.1e-16), so the difference is the classical double solve's |
| harmonic vs p-FE condensation | at most 1.2e-13 (tests) and 2.7e-13 (gen) |

**Marching segment size** (`step_sigma`, the growth exponent per segment). The table gives the
error of roots 1, 6, 10, 11 and 12 against hp60:

| step_sigma | t8 (lambda up to 33) | t4 (lambda up to 30) |
| --- | --- | --- |
| 0.25 to 4 | at most 1.3e-15 | at most 7.5e-16 |
| 8 | at most 1.5e-14 | at most 2.0e-14 |
| one exponential per member | 5.7e-15 for mode 1; no sign change within +-1e-6 for modes 6 to 12 | 5.0e-10, then lost |

The program uses step_sigma = 1.

The stiff/soft corner of the domain is covered by t10: a 19.7 m member with A = 5e-2 and
I = 1e-7, so L/r is about 14000 and the axial-to-bending stiffness ratio is about 1e7. It needs
nothing special. Frequencies agree with hp60 to 4.0e-16, harmonic to 1.6e-16 and statics to
1.1e-16.

## 6. Gen frames (refA/out_gen/)

Results for all 28 frames are summarised in `tests/check_results_gen.json`:

- all exit with status 0, in at most 2.5 s each;
- all certified on the first attempt, with no warnings;
- count_below is confirmed by det roots on every frame.

My values for the section-2 guarantees on these frames:

| guarantee | value |
| --- | --- |
| max lambda | 12.1 |
| max alpha | 5.8 |
| min gap among the first n_modes + 1 frequencies | 5.7e-3 (held_21) |
| f_max distance from the nearest frequency | at least 1.3e-4 (held_16) |
| harmonic distance from the nearest frequency | at least 1.31e-2 (held_21) |

Guarantee 4 holds for every static and harmonic value. Note that the gen set does not come
near lambda = 40 or 1e-6 gaps. The test frames t8 and t9 do.

## 7. Spec sentences that admit more than one reading (and the reading used here)

1. Guarantee 4 and section 5: "(`ux`, `uy` and harmonic translations in m; `rz` and harmonic
   rotations in rad, each group compared within itself)". It is not clear whether static `ux`
   and `uy` form one group or two, and whether harmonic translations share a group with the
   static translations, since both are in m. The "kind" scale S of section 5 inherits this. It
   does not affect the values computed here, but it does change the tolerance and the
   guarantee-4 check.
2. Section 1: "a uniform member load `wx`, `wy` (N/m, global directions) acts along a member".
   This could be per unit member length or per unit horizontal (or vertical) projection. I used
   per unit member length, which matches "fixed-end actions ... axial and transverse components
   in the member's local axes". For an inclined member under gravity given per horizontal metre,
   the two readings differ by a factor cos(theta).
3. Section 1: "end moments `+-q_t L^2 / 12`". The sign convention is not stated. The displacements
   do not depend on it if the moments are applied consistently. Here the equivalent nodal
   moments are +q_t L^2/12 at end i and -q_t L^2/12 at end j, counterclockwise.
4. The spec does not say what happens to a nodal load on a constrained dof, a harmonic load on a
   constrained dof, or repeated `nodal_loads` / `member_loads` entries for the same node or
   member. Here the load goes into the reaction (no displacement), the response is 0, and
   repeated entries are summed.
5. Harmonic: "A harmonic nodal force ... of amplitude `P` ... produces the steady-state motion
   `U cos(2 pi f_h t)`". This implies, without saying so, that the force is P cos(2 pi f_h t)
   in phase, so U is signed relative to P. Below the first frequency, U has the sign of the
   static response.
