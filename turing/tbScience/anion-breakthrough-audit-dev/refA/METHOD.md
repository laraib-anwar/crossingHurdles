# refA: independent reference for IX_SPEC by generic hyperbolic machinery

`reference.py` (single file, numpy 1.26.4 + scipy 1.11.4) implements
`python reference.py --recipe <recipe.json> --output <report.json>` and writes a report per
IX_SPEC section 4. It never uses the Helfferich-Klein h-transformation, omega/h roots or
Riemann invariants; every quantity comes from eigen-decomposition of the equilibrium Jacobian,
ODE integration, Newton/root-finding and (for fan-fan interactions) spectral collocation.

## 1. Model as treated

The n present ions (an ion absent from the bed and from every feed is dropped, which reduces
the system size, so dev_04 is a 3-ion, 2-wave problem) give m = n-1 unknowns x (the last
fraction is 1 - sum). The balance is d/dBV [eps x + Lambda y(x)] + d/dxi x = 0 with
y_i = alpha_i x_i / D(x). The Jacobian J = dy/dx and its derivative tensor dJ/dx are analytic.
Characteristic speed of family k: dxi/dBV = 1/(eps + Lambda lambda_k), lambda_k an eigenvalue
of J (numpy.linalg.eig, sorted decreasing: family 0 = slowest, nearest the inlet).

## 2. Waves

* Rarefaction curve of family k from x_from: dx/ds = r_k(x) (unit eigenvector, oriented so
  lambda_k decreases; followed by continuity, i.e. at each state the eigenvector most parallel
  to the running direction is taken), DOP853, rtol 1e-12, atol 1e-14, dense output.
* Shock of family k from x_from: Rankine-Hugoniot y(x_to) - y(x_from) = mu (x_to - x_from),
  sigma = 1/(eps + Lambda mu), solved by Newton in the scaled unknowns u = (x_to - x_from)/s,
  mu with the normalisation r_k . u = 1 (well conditioned down to s -> 0). For |s| < 1e-5 the
  divided difference loses digits and mu is taken as lambda_k at the midpoint (exact to
  O(s^2) for any genuinely nonlinear system). Lax (lambda_k(L) <= mu <= lambda_k(R)) is
  checked on every reported shock.
* Composite wave curve W_k(x_from; s): s > 0 rarefaction, s < 0 shock. Riemann problem
  (left = inlet state, right = bed state): Newton with central-difference Jacobian on the three
  strengths s_0, s_1, s_2 so that W_2(W_1(W_0(x_L))) = x_R, convergence 1e-13 in composition.
  The solution is accepted only if the waves are ordered by speed (every speed of wave k <=
  every speed of wave k+1); otherwise the physical branch is reached by continuation in the
  right state from the trivial solution (needed on recipes whose intermediate states lie on a
  face where an ion with an intermediate alpha is absent: there the eigenvalue ranks of two
  families cross and the midpoint guess converges to a non-admissible root; held_01, held_09,
  held_13, held_14 of gen2 did this). Waves with |s| < 1e-9 are zero-strength and dropped.

## 3. Front tracking for two feeds

Waves live in the (xi, BV) plane: straight shocks and fans (one-parameter families of straight
characteristics with origin, state and derivatives). The second Riemann problem is centred at
(0, start_bv) inside the first-feed plateau. Adjacent waves are tested pairwise for the next
meeting (straight-line intersections) and the earliest one inside the bed and the window is
processed:

* shock-shock (any families, including same-family merges): Riemann re-solve between the outer
  states at the meeting point; the generic solver finds the third-family strength to be
  ~1e-16 (no new waves), as the theory predicts, without that being assumed;
* shock through a fan (other family, either side; same family): ODE in the fan parameter p for
  (BV, unknown-side state, mu): dBV/dp from the characteristic geometry, and the differentiated
  RH conditions with the unknown-side state allowed to move along every eigen-direction except
  the shock's own family. The components along families other than the fan's are "reflected
  waves"; they come out <= 4e-15, which confirms the transmitted fan is a simple wave. For the
  same-family case the unknown-side state stays constant and no refracted fan is created (the
  shock absorbs the fan). The passage ends at the far edge of the fan, at the outlet
  (terminal event xi = 1), or is truncated where another wave would reach the shock or the fan
  first (then the loop resumes from the truncation point);
* fan-fan (a faster family overtaking a slower one): the interaction region is a rectangle in
  the two fan parameters (p, q). Node states are intersections of the k-rarefaction curve from
  the A state with the backward j-rarefaction curve from the B state (Gauss-Newton on two arc
  lengths; residual <= 1e-15, which again confirms the two-wave structure generically). The
  geometry solves the linear hyperbolic system xi_q = s_j BV_q, xi_p = s_k BV_p on a Chebyshev
  tensor grid (N = 18 per direction) by collocation, with boundary data from two
  characteristic-through-fan ODEs (the leading A characteristic through B and the trailing B
  characteristic through A). The transmitted fans are read off the two exit sides as barycentric
  Chebyshev interpolants (state, origin and their derivatives). If the outlet cuts the region,
  the contour xi(p,q) = 1 provides the effluent inside the region (Newton on the 2-D
  interpolants) and only the parts of the transmitted fans that originate inside the bed
  continue. Spectral convergence (ff test case): N = 12/16/24 versus 32 give exit-BV
  differences 2e-7 / 6e-11 / 1e-11; the corner state agrees with an independent Riemann solve
  to 4e-16 and the PDE residual at off-grid points is 6e-15. Each production region is solved
  at N = 13 and N = 18 and the difference is recorded as an error estimate.

## 4. Outlet history

Every surviving shock gives a point event at its exit BV; every surviving fan range gives a
transition piece (head characteristic first); region contours give pieces too. Pieces are
sorted, gaps become plateaus, adjacent continuous transitions merge, and consistency of the
state on both sides of every junction is asserted (1e-7). Nitrate peak: every plateau value and
every transition (grid scan of 400 points plus bounded minimisation; no monotonicity assumed),
earliest BV among equal maxima. nitrate_limit_bv: first strict exceedance (plateau start, or
root bracketing inside a transition). Samples: state at the given BV (root-find for the
characteristic exiting at that BV).

## 5. Accuracy evidence

* Rarefaction curves computed by the eigenvector ODE come out straight to 1e-17 (deviation from
  the chord) on all dev recipes, consistent with the classical theory but not assumed.
* RH residuals of all shocks <= 1.2e-14; Lax satisfied; third-family strengths at every
  interaction <= 3e-16; reflected components in passages <= 4e-15.
* Integral mass balance (scratch script `mass_balance.py`, window extended to 4000 BV so every
  wave leaves; plateaus exact, transitions by 96-point Gauss-Legendre): residual <= 7e-12 BV
  (relative to Lambda: <= 3e-14) for every ion on dev_01..dev_06, including the two-feed
  cascade of dev_05.
* Tolerance refinement: rtol/atol = 1e-8/1e-10, 1e-10/1e-12, 1e-12/1e-14 versus 1e-13/1e-15
  change every graded number of dev_01..dev_06 by <= 9e-15 relative (BV) and <= 1.4e-14 meq/L.
  The ODE error is therefore not the limiting term; the Newton thresholds (1e-13 in composition)
  and roundoff (1e-16/|s| in the RH divided difference) are, giving ~1e-13 relative on event
  BVs for single feeds.
* Passage ODE cross-check (dev_05, bicarbonate fan crossing the first sulfate shock): the
  unknown-side state along the shock agrees with the intermediate state of the Riemann problem
  [fan state | plateau ahead] (algebraic route, no ODE in p) to 1.4e-14, mu to 1.7e-13, and the
  exit BV recomputed from the algebraic mu agrees to the last digit.
* Crude first-order upwind finite-volume solve (scratch `fv.py`, 600-1000 cells, CFL 0.45,
  w -> x inversion by Newton) on all six dev recipes: same wave count and kinds, plateau values
  agree to 4 digits (dev_04 to 1e-13 since it has no fans), shock half-jump BVs within 0.03 BV
  of the exact shocks, maximum deviation 0.07 meq/L located at fan edges (numerical diffusion).
* Independent solver (gen2 oracle, 28 production recipes): see section 7.

## 6. Timings

Wall-clock per fresh call, one CPU, OPENBLAS_NUM_THREADS=1 (refA/out/timings.json):
* dev_01: 1.6 s
* dev_02: 1.1 s
* dev_03: 1.1 s
* dev_04: 0.5 s
* dev_05: 3.4 s
* dev_06: 1.1 s
* dev_07: 3.8 s
* dev_08: 3.2 s
* gen2 production set (28 recipes, refA/out/gen2/): 0.5 to 10.6 s each (held_09 10.6 s, held_14 9.2 s, all others <= 4.9 s). All far below the 60 s limit.

## 7. Results on the recipe sets

* dev_01..dev_08: reports in refA/out/. dev_07 (second-feed shock crossing a first-feed spreading wave of
  another family, then a same-family shock absorbing part of a spreading wave up to the outlet) and
  dev_08 (second-feed spreading wave crossing two first-feed spreading waves, last wave cut by
  run_bv = 1600) exercise the fan-fan machinery; both close consistency checks at every junction.
* gen2 (28 production recipes, compared with the independent oracle in gen2/out_oracle): 27 agree in
  every count, every BV to <= 4.6e-13 relative, every composition to <= 1.3e-11 meq/L and in
  nitrate_limit_bv. The four earlier failures (held_01, held_09, held_13: spurious Riemann root with
  unordered waves; held_14: non-terminating loop of concurrent passages) are fixed by the ordering
  check with sign-pattern search / continuation and by the concurrent-passage handling.
* held_14 disagrees with the oracle in structure (refA: 2 shocks, 1 transition, 4 plateaus; oracle: 3,
  3, 5). In the oracle's report the transition 485.2-660.3 ends at the second feed's composition
  (3.502, 0.777, 0.969, 0.752 meq/L), a plateau at that composition follows, and a shock at 708.24
  then changes the effluent to (3.195, 0.218, 1.857, 0.730). Once the feed composition has reached the
  outlet the whole bed is at the feed state and nothing can follow, so that history cannot be the
  exact solution; it looks like the oracle lets the second-feed family-0 spreading wave pass through
  the first-feed family-0 shock as if they were different families. In refA the family-0 shock absorbs
  the family-0 spreading wave (its states and the shock's far state differ only in the family-0 wave,
  confirmed by the far-side state staying constant to 7e-15 in every same-family passage), slows from
  mu = 2.84 to 4.34 and leaves the window; the family-1 shock exits at 607.89. refA's held_14 history
  closes the integral mass balance (window extended to 4000 BV) to 6.6e-10 BV, 2.5e-12 relative to
  Lambda. I recommend checking the oracle's same-family fan-shock interaction.


## 8. Open issues

* Loss of strict hyperbolicity on faces where an ion with an intermediate alpha is absent is
  handled by eigenvector continuity (rarefaction ODE, fan speeds) and by the ordering check with
  continuation in the Riemann solver. Shock-passage ODEs and characteristic-through-fan ODEs
  still identify families by eigenvalue rank at the unknown-side state; a crossing exactly there
  would be mishandled (none observed on the 36 recipes).
* Interactions not implemented: another wave reaching a fan-fan region while it forms, a shock
  simultaneously inside two fans, a shock entering a fan-fan region. These raise
  NotImplementedError instead of producing a report.
* dev_03 is not all-rarefaction as the task brief said: the bicarbonate elution wave (family 2)
  is a Lax-admissible shock at BV 45.009 (chloride displacing the less-preferred bicarbonate is
  self-sharpening); the finite-volume check confirms the jump and the plateau after it.
* Weak shocks between 1e-9 and 1e-5 in strength use the midpoint eigenvalue for mu (error
  O(s^2) <= 1e-10); shocks weaker than 1e-9 are dropped as zero-strength waves.
