# Reference A: method

`reference.py` is a single file (Python 3.11, NumPy 1.26.4, SciPy 1.11.4). Run it as
`python reference.py --recipe R --output O`. It writes the section-4 report and nothing else.
Options for development only: `--debug D` writes diagnostics (eigenvalues, error estimates,
timings, warnings), `--rtol` sets the shooting tolerance (default 1e-12), and `--n0` sets the base
finite-difference grid (default 100 intervals).

It does not use the invariant `theta + beta c = const`, any first integral, Gauss-Legendre
quadrature, or spectral/Chebyshev collocation. The steady problem is always integrated as two
coupled second-order equations.

## 1. Steady states: two-field shooting from the wall

The unknowns are `theta(0)` and `c(0)`. Writing `u = ln c` and `w = u'` turns the steady equations
into four first-order ODEs:

```
theta' = p,   p' = -beta phi^2 R(theta) e^u,   u' = w,   w' = phi^2 R(theta) - w^2
```

with `theta(0) = theta0, p(0) = 0, u(0) = u0, w(0) = 0`. There are two film residuals at `x = 1`:

```
F1 = p(1) + Bi_h theta(1)
F2 = e^{u(1)} (w(1) + Bi_m) - Bi_m
```

Why this form: integrated forward, the Riccati equation for `w` is contracting. The perturbation
of `w` decays like `exp(-2 w x)`, so the steep concentration boundary layer at the face and the
`c(0) ~ exp(-phi sqrt(R))` depletion of ignited layers cause no exponential error growth. There is
no parasitic growing mode, and `c(0)` can be as small as `exp(-10^6)` without underflow, because only
`u` is carried. The problem is still very stiff (rate `2w`, up to about 1e6 in the domain), so it is
integrated with `scipy.integrate.odeint` (LSODA, which switches to BDF when the problem turns stiff)
with an analytic Jacobian, `rtol = 1e-12` and `atol = 1e-15`. The 12 variational equations for
`d(theta, p, u, w)/d(theta0, u0, phi)` are integrated with the state (16 ODEs, block-diagonal
Jacobian), which gives the exact shooting Jacobian. The reported quantities are `theta_c = theta0`
and `eta = e^{u(1)} w(1) / phi^2`.

## 2. Pseudo-arclength continuation of the steady set

The steady set is a curve in `z = (theta0, q, ln phi)`, where `q = -ln(1 - u0)`. This keeps the
very negative `u0` of ignited layers in a range of about 0 to -14. Arclength is measured in
`(theta0 / Theta, q, ln phi)` with `Theta = beta Bi_m / Bi_h`. The trace:

* starts at `phi_s = min(0.02, phi_min / 2)` on the cold branch (Newton from `theta0 = 0, c0 = 1`);
* takes a tangent predictor (the cross product of the two Jacobian rows), then a Newton corrector
  on `[F; t.(z - z_prev) - ds]` with the variational Jacobian;
* adapts the step: `ds <= 0.6`, `|d ln phi| <= 0.2` per step, tangent turn `<= 0.12 rad`, change of
  `d(ln phi)/ds` `<= 0.08` per step (this resolves nearly coincident folds: a test pair 2.4e-4 apart
  in phi is found, while the spec guarantees at least 1e-3), and the step is halved when the
  corrector fails. The Newton noise floor scales with the ODE tolerance, because the 2x2 shooting
  Jacobian is ill-conditioned on ignited branches (its rows are nearly parallel);
* stops once `phi > phi_max` (with `d phi/ds > 0`).

Trace points are computed at `rtol = 1e-9`, because they only bracket events. Every reported
number is recomputed at `rtol = 1e-12`.

**Folds.** A sign change of `d(ln phi)/ds` between consecutive points brackets a fold. The fold is
refined by Brent's method on `det(dF/d(theta0, q))` along the curve. Each evaluation is a curve point
solved with the arclength constraint `t_a.(z - z_a) = s`. Because the tangent's phi component is
this determinant, this is equivalent to solving residuals plus det = 0. Kind: `ignition` when
`phi` increases before the turn (a local maximum of phi), `extinction` otherwise.

**Query states.** Every crossing of `ln phi = ln phi_q` by the traced curve is refined by Newton
at fixed phi. The crossings are de-duplicated and sorted by `theta_c`.

## 3. Spectrum: finite differences, mapped grid, shift-invert iteration, Richardson

**Linearisation.** The linearisation about a steady state is
`Le lambda T = T'' + beta(a T + b C)`, `lambda C = C'' - (a T + b C)`, with
`a = phi^2 R'(theta) c` and `b = phi^2 R(theta)`, and with the homogeneous wall and film conditions.

**Discretisation.** The operator is discretised with the second-order conservative three-point
formula on a mapped grid `x = g(xi)`, `xi` uniform. Ghost points enforce the Neumann and Robin
conditions with central differences. The mapping is analytic: with `zeta = 1 - xi`, the distance
from the face is `eta(zeta) = (S/A) ln((S + delta e^{A zeta})/(S + delta))`. The cell density grows
geometrically from `delta = 6 / k` at the face (`k = phi sqrt(R(theta0))`, the largest local Thiele
number) and saturates at `S` (about 2 to 3) in the interior, with 60 % of the cells in the graded
zone. The grid is uniform when `k <= 12`.

The interior spacing is bounded. This matters: a sinh map tried first had interior cells 15 times
too wide at `k ~ 1e5` and lost the thermal modes. Because the scheme and the map are symmetric in
`h`, the error has an expansion in `h^2, h^4, ...`.

**Coefficients.** The coefficients come from the shooting profile, evaluated by LSODA at the grid
nodes. The FD steady problem is also solved by Newton on the same grids. Its Richardson-extrapolated
`theta_c` agrees with the shooting value to 1e-16 to 2e-10, which is an independent check of the
steady states.

**Candidates.** All eigenvalues on a 50-interval grid come from QZ on the weighted generalized
form `(W A) v = lambda (W B) v`, where `W` holds the trapezoidal weights and `B = diag(Le, 1)`.
`W D2` is symmetric, which keeps QZ accurate. QZ on the plain matrix `B^-1 A` produced spurious
positive eigenvalues on strongly graded grids.

**Refinement.** Each candidate (the 3 rightmost in the upper half plane) is refined on the grids
`n0, 2 n0, 4 n0` (`n0 = 100`) by sparse-LU shift-invert iteration. That is 3 fixed-shift steps,
then Rayleigh-quotient updates. The three values are Richardson-extrapolated (`h^2` and then
`h^4`). The difference between the two-level and three-level values is the error estimate.

**Parity check.** Each fold flips the sign of the shooting determinant. A state whose determinant
sign differs from the cold start must have a positive real eigenvalue. If none is found, the
candidate search widens to 8 candidates with 8 fixed-shift steps. A remaining failure is recorded
in the warnings of the debug file. There were none on any recipe.

**Classification.** This follows spec section 1. The eigenvalue counts as real when
`|Im| <= 1e-6 max(1, |lambda|)`.

## 4. Hopf points

**Scan.** Every continuation point inside the window (plus one point on each side) gets QZ
candidates on the 50-interval grid. Each relevant complex eigenvalue, meaning one in the upper half
plane with `Re > -(1 + |lambda|/2)`, is improved by one shift-invert solve on the 100-interval grid
and `h^2` extrapolation. Between consecutive points:

* if a relevant complex eigenvalue matches a complex eigenvalue at the other end (distance
  `<= 0.25 |lambda|`) and the sign of Re differs, that is a Hopf bracket;
* if a relevant complex eigenvalue is unmatched or poorly matched, and the other end has an
  eigenvalue of opposite Re sign nearby, the step is bisected along the curve (up to 6 levels).
  This covers a pair that crosses zero and then merges into two real eigenvalues inside one step;
  merging alone, without a sign change, does not create a bracket.

**Refinement.** Brent's method is applied to the Richardson-extrapolated Re of the tracked
eigenvalue along the curve (tolerance 1e-11 in arclength). If the accurate function has no sign
change on the coarse bracket, the bracket is widened outward. The pass is repeated with
`n0 = 200` and then 400 in a narrow bracket until the estimates give `|dphi|/phi < 1e-8` and
`|domega|/omega < 1e-7`. Only roots with `phi` in the window and `omega > 1e-3` are kept.

## 5. Accuracy evidence (dev_01 to dev_07, plus three stress recipes at domain extremes)

* Steady shooting at `rtol` 1e-12 against 1e-13: phi agrees to 2.3e-11 at worst, and theta_c and
  eta to 7.5e-10 (dev) or 3.3e-8 (stress: gamma 40, phi up to 30, k ~ 7e5).
* Eigen grids `n0 = 100` against 200: all counts, kinds and stabilities are equal. Hopf phi agrees
  to 1.6e-12 (dev_05) and 3.8e-11 (stress), and omega to 2.4e-11 (dev_05) and 5e-9 (stress).
* The FD steady problem (extrapolated) against shooting: theta_c agrees to 1e-16 to 3e-10.
* Richardson ratios are about 4.0 per grid doubling. For example, dev_05 at the Hopf point gives
  Re = 9.8e-4, 2.5e-4, 6.1e-5 on N = 100, 200, 400.
* Against the solver's outputs (`out_oracle`, compared only after the fact): every count, kind and
  stability matches. phi agrees to <= 2.5e-11, values to <= 5e-10 and omega to 5.5e-11.
* Timings (`out/timings.json`): 3.8 to 14.8 s CPU per dev recipe on a 1.6 GHz i5-8210Y. The stress
  recipes (Le 0.05, gamma 40, four folds and three Hopf points) take 41 to 57 s CPU.

## 6. Limits

* Only the steady-state component that is connected to the cold branch is traced. Isolas would be
  missed. An independent check (a theta0 march at fixed phi, solving F2 = 0 for c0 and counting the
  sign changes of F1) reproduces the state counts at every dev_01 and dev_07 query value, and at
  dev_02 phi = 0.01 and 0.1. The march cannot follow strongly ignited states (large k), and it
  cannot resolve ignited states whose theta_c lies at the bound beta Bi_m / Bi_h.
* Two Hopf crossings inside one continuation step, with the coarse spectrum giving no hint, would
  be missed.
