# Reference A: method

`reference.py` (numpy + scipy only, one file) implements PHASE_SPEC.md by a route that shares no
step with the grid-hull / fixed-step-scan / bisection oracle. Everything is written in the logit
variable `u = ln(x/(1-x))`, with `x = 1/(1+e^-u)` and `1-x = 1/(1+e^u)` carried separately, so
`x ln x` is never formed at `x = 0` and compositions down to `1e-17` keep full relative precision.
All derivatives of `G` in `x` (to fourth order) and in `T` are analytic.

## Isotherm (exact common tangents, no composition grid)

1. **Convex branches.** `x(1-x) G'' = RT + x(1-x) E''(x)` is a quintic in `x`; its real roots in
   (0,1) are the spinodal points (companion-matrix roots, Newton-polished). The convex branches
   are the sub-intervals where `G'' > 0`; on each branch `G'` is monotone, so `G' = m` has exactly
   one root (safeguarded Newton/bisection in `u`).
2. **Candidate tie-lines.** For two branches (of different phases or of the same phase), the
   intercept difference `f(m) = [G_P(x_1(m)) - m x_1(m)] - [G_Q(x_2(m)) - m x_2(m)]` has
   `f'(m) = x_2(m) - x_1(m)`, which vanishes only where `G_P'(x) = G_Q'(x)` at the same `x`: a
   quartic polynomial (the `RT ln` terms cancel). Splitting the common slope range at those exact
   roots makes `f` monotone on every piece, so each sign change holds exactly one common tangent,
   found with `brentq` and polished by a 2x2 Newton in `(u_1, u_2)`. Compound-to-branch tangents
   are the roots of `G_P(x) - G_P'(x)(x - x_theta) - G_theta`, monotone on each side of `x_theta`.
   Compound-compound lines are explicit.
3. **Stability filter (supporting-line test).** A candidate line `m x + c` is kept iff for every
   solution phase `min_x [G_R(x) - m x - c] >= -1e-6 J/mol` (the minimum is attained at a root of
   `G_R' = m` on a convex branch or at a pure end, so it is evaluated exactly, without a grid) and
   every compound point lies on or above the line.
4. **Assembly.** Stable lines are sorted; single-phase regions fill the gaps; a compound shared by
   two neighbouring lines is a vertex and gets no region; the first/last region phases are checked
   against `min GA`/`min GB`; overlaps or inconsistent neighbours raise a warning.

## Temperature events (no topology scan)

* **Exact candidates.** Congruent points of two solution phases: `G_P - G_Q = U(x) + T V(x)` is a
  degree-5 polynomial linear in `T`, so tangency is `U V' - U' V = 0` (degree 9) and `T = -U/V`.
  Critical points: `G'' = 0` and `G''' = 0` are both linear in `T`; eliminating `T` gives a
  degree-9 polynomial. Compound congruent points and pure-end crossings are linear in `T`. Every
  candidate is Newton-polished in `(u, T)` and accepted only if the touching point lies on the
  exact hull at `T_c` (`hull(x_c) = G(x_c)` within 1e-6 J/mol); metastable candidates are dropped.
* **Three-phase equilibria by continuation.** Starting from the exact hull at `T_lo`, the stable
  tie-lines are continued in `T` (Newton predictor-corrector in `(u_1, u_2)`, sub-stepping on
  trouble) in steps of 0.25 K (events are >= 0.5 K apart), and smooth indicator functions are
  evaluated on the continued topology: for every tie-line and phase `R`,
  `min_{x in [x_1,x_2]} [G_R(x) - line(x)]` excluding `R`'s own end states (a phase touching the
  tie-line: eutectic class); `G_theta - hull(x_theta)` for every compound; the length of every
  single-phase region between two tie-lines (a region vanishing: peritectic class); the slope
  difference of the two tie-lines meeting at a compound vertex (compound decomposing: peritectic
  class). A sign change is bracketed with `brentq` (1e-12 K), the earliest root wins, and the
  full three-state system (`G_P' = m`, `G_P = m x + c` for solution states, `G_theta = m x_theta + c`
  for compounds, unknowns `T, m, c, u_i`) is polished by Newton to machine precision. The class
  follows from the sweep direction and is cross-checked against from-scratch hulls at `T +- 0.02 K`
  (the middle composition must lie strictly inside the outer-phase tie-line on exactly one side).
  After every real event the sweep restarts from the exact hull at `T_e + 0.1 K`; every 20 steps
  the continued topology is compared with a from-scratch hull (a mismatch is reported on stderr).
* Names follow the spec table; sides (`two_phase_side`, `gap_side`, `phase_above/below`) are read
  from exact hulls at `T_c +- 0.1 K`.

## Verification and measured precision

* `tests/check_report.py` re-implements only the spec formula with plain numpy and checks each
  report: chemical-potential residuals of every tie-line, every reported line below every curve on
  a dense grid with log-spaced ends, every region phase lowest on a grid, collinearity of each
  invariant, the congruent/critical defining equations, name table, exact outer bounds/compound x,
  and coverage of [0,1]. Over the 9 test systems: `|mu_A^L - mu_A^R|, |mu_B^L - mu_B^R| <= 3.0e-10`
  J/mol (that is `delta x ~ 1e-16` for ends near `x ~ 1e-3`), invariant collinearity residual
  `<= 5.5e-12` J/mol (`delta T ~ 1e-12` K), congruent residual `<= 9.1e-13` J/mol, critical
  residuals 0, no point of any phase below a reported line by more than `1.8e-12` J/mol.
* Textbook checks (`tests/NOTES.md`): ideal lens liquidus/solidus agree with the closed form to
  `<= 2.2e-15` in `x`; regular-solution consolute point `T_c = L0/(2R)`, `x_c = 0.5` reproduced to
  0 ulp; compound congruent temperature equals the closed form to 0 ulp; the metastable-compound
  system gives a report byte-identical (apart from `system_id`) to the compound-free control.
* Completeness: a brute-force topology scan of the exact hull (step 0.2 K, test harness only)
  finds exactly the reported events plus the unreported pure-end crossings on all test systems,
  on 10 random in-domain systems (step 0.4 K) and on the 29 dev/generated systems (step 0.25 K;
  the only four scan intervals without a listed event are the pure-end melting points of
  dev_01..dev_04 at exactly 1000, 1200, 1500 and 1000 K, where the scan grid landed on the event
  and the half-open interval test of the harness missed it; hulls at T +- 0.1 K confirm them).
* Dev and generated systems: `reference.py` ran end to end (exit 0, no warning) on the 7 systems
  in `models/dev_0*.json` (reports in `refA/out/`) and the 22 systems in `gen/systems/` (reports in
  `refA/out_gen/`); `check_report.py` passes on all 29 (tie-line mu residuals `<= 1.9e-9` J/mol,
  invariant collinearity `<= 9.6e-12` J/mol, congruent residuals `<= 2.6e-9` J/mol on `G ~ 1e4`,
  critical residuals `<= 5.5e-15`, no curve below a reported line by more than `7.3e-12` J/mol).
* Runtime on one core (Intel Mac, Python 3.11): 1 to 5 s for the test systems; 2 to 15 s on the
  generated systems (worst: held_18, 4 phases + 1 compound, 1180 K window, 14.8 s); 3 to 20 s on
  the dev systems (worst dev_01, 20.3 s); 3 to 21 s for random systems with 4 solution phases,
  3 compounds and 1000 K windows (about 200 exact hulls plus 4000 continuation steps). No
  non-finite number can be written (`json.dump(..., allow_nan=False)` and an explicit finiteness
  check on every value).
