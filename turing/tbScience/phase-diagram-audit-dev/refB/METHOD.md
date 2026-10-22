# Reference B: independent referee for phase-diagram reports

`referee.py` checks a report file against PHASE_SPEC.md with machinery of its own. It was written
from the spec alone; it has not read the task solution or Reference A and shares no code with
them. It also contains a small solver (`--solve`) that gives a third opinion on any system.

```
python referee.py --system S.json --report R.json [--out verdict.json] [--quiet] [--no-scan] [--scan-step K]
python referee.py --solve --system S.json --output R.json
```

Exit status 0 means `pass: true`. Python 3.11, NumPy 1.26.4, SciPy 1.11.4; no mpmath. All
equilibrium conditions are evaluated and refined in 80-bit `numpy.longdouble` (eps 1.1e-19).

## What is checked

**Schema.** Exact key sets of section 4, isotherm temperatures equal to the system file, compound
tie ends exactly at `x_theta`, events strictly increasing in T and strictly inside the window.

**Isotherm certificates** (one block per isotherm):

- (a) Sequence: pieces sorted by x must alternate region / tie-line, start with a region at
  `x_lo = 0`, end with a region at `x_hi = 1`; consecutive region/tie pairs must share the boundary
  (gap reported, failure above 1e-12) and name the same phase; two consecutive ties must share a
  compound vertex exactly at `x_theta`.
- (b) Tangency: for solution-solution ties the residuals of `mu_A = G - x G'` and
  `mu_B = G + (1-x) G'` between the two ends; for solution-compound ties the residual of the
  solution tangent line at the compound point. Each tie is also re-solved by Newton (long double)
  from the reported compositions and the shift `|x_newton - x_report|` is recorded.
- (c) Global stability: the reported hull (region curves plus straight tie segments) is evaluated
  on a 200,601-point grid (200,001 uniform plus 50 points per decade from 1e-9 to 1e-3 at both
  ends) and compared with every solution phase at every grid point and with every compound; the
  worst `hull - G_phase` is reported (positive means something lies below the reported hull).
- (d) Each region is convex (`min G''` over the grid points inside it) and is the lowest phase
  there (minimum margin to every other phase and compound). The slope sequence along the whole
  hull (tangent slopes at region ends, tie slopes) must be non-decreasing.
- Independent construction: a pointwise envelope `min_phi G_phi(x)` plus compound points on a
  50,241-point grid, lower convex hull by Andrew's monotone chain (C helper compiled on first use,
  pure-Python fallback), edges classified as region edges (adjacent grid points of one phase) or
  tie edges (different phases, compounds, or same-phase edges that skip grid points lying more than
  1e-7 J/mol above the chord), then every tie end refined by Newton on the common-tangent
  equations. Counts, phase names and the maximum composition difference to the report are recorded.

**Event certificates.**

- Invariant: line through the outer two states; collinearity residual of the middle state;
  `mu_A`/`mu_B` residuals of each solution state against the line (intercepts `c` and `m + c`) and
  the on-line residual of each compound; global stability of the extended line on the fine grid;
  Newton on the full system (compositions of the solution states, T, slope, intercept) started
  from the reported values, reporting `|dT|`, `dT/T` and `max |dx|`; class by evaluating the hull
  at `T +- 0.1 K` and asking whether the middle phase is stable within half the distance to its
  neighbours of `x2`, cross-checked by asking on which side the `P1-P3` tie-line covers `x2`; name
  from the spec table using which states are `liquid`.
- Congruent point: `G_P - G_Q` and `G'_P - G'_Q` at `(x_c, T_c)` (or `G_P(x_theta) - G_theta`),
  stability of the tangent line, Newton refinement of `(x, T)` (closed form in T for a compound,
  since G is linear in T), `two_phase_side` and `phase_above`/`phase_below` from the hull at
  `T +- 0.1 K`: the lens side is the side where `x_c` lies in a region (or compound vertex) whose
  two neighbours are tie-lines between the two phases.
- Critical point: `G''` and `G'''` residuals, stability of the tangent, Newton on `(x, T)` with
  `G''''` in the Jacobian, `gap_side` from the hull at `T +- 0.1 K`.

**Completeness.** The window is scanned every 0.1 K (20,121-point grid; the step is widened to
at most 0.25 K only without the C helper). At every scan temperature two things are recorded: the
label sequence of the hull, and for every solution phase the minimum of `G''` over the grid points
of its stable support (its regions plus its own-phase gap intervals). That minimum is negative
exactly when the phase has a stable miscibility gap, so its sign flips at the consolute temperature
itself; `G''` is linear in T, so bisection on the sign (to 1e-9 K relative) locates `T_c` without
the lag that sampled-hull detection of a shallow gap has (depth of the curve above the chord grows
like the fourth power of the gap width; 2.3 mK lag on held_10, 4.4 mK on the consolute test). A
zero crossing is accepted as a critical point when `|min G''|` is tiny at both bracket ends (a jump
to a finite negative value is a gap created by an invariant, recorded under `spinodal_jumps`), and
the Newton-polished critical point must lie within 1e-3 K of the bracket. The lagging label change
of the same gap is attributed to that critical point instead of being counted separately.

Each change of the label sequence
(`R:phase`, `T:left|right`, `V:compound`) is bisected to 1e-9 K relative on the 50k grid, then
interpreted from the pieces on the richer side: a collapsing region or compound vertex between two
ties is an invariant (or a congruent point when both ties shrink with it and join the same phase),
a collapsing same-phase tie is a critical point, a collapsing first or last region is a pure-end
transition (compared with the analytic crossing of the two end-member lines). Each interpretation
is polished with the Newton routines above and must land inside the bracket and be globally
stable. Every change must match a reported event of the same kind within 0.25 K (the matched
event's `dT` and `dx` against the independent values are recorded) or a pure-end transition, and
every reported event and analytic pure-end transition must have a change.

**Verdict thresholds** (`pass` requires all): tangency/line residuals < 1e-6 J/mol, stability
violations < 1e-6 J/mol, refined T within 1e-7 relative, compositions within 1e-9 absolute (both
Newton-from-report and the independent construction), class/name/sides equal, no unmatched
topology change, no reported event without a change, no schema or sequence error. Note that the
residual thresholds are stricter than the composition thresholds: a composition error of 1e-9
already gives a `mu` residual of roughly `x G'' dx ~ 1e-5 J/mol`, so the residual check is the one
that catches sub-1e-9 errors (see the negative test with a 5e-10 shift below).

**Newton convergence.** All refiners stop when the step is below 1e-15 in x and 1e-13 relative in
T, or when two successive steps are below 1e-12 / 1e-10 but no longer shrink: that is the rounding
floor of the residual. The second rule matters at critical points, where `G''' = 0` makes the x
step `noise(G''') / G''''`, about 4e-18 for held_10 (`G'''' ~ 270 J/mol`), which a fixed 1e-18
criterion never met and which produced a false "did not converge" on an exact report.

## Independence

Different hull algorithm (monotone chain on a pointwise envelope, not a tangent construction),
different unknowns in the Newton systems (slope and intercept carried explicitly for invariants),
different class logic (two hull evaluations at `T +- 0.1 K` instead of any curvature argument),
analytic pure-end transitions, and a label-sequence scan with bisection for completeness. The
only shared inputs are the spec and the system file.

## Measured precision and runtime

Reports of the seven dev systems (`models/dev_01..07`, produced by the oracle) all pass:

| system | max residual (J/mol) | worst stability (J/mol) | max dx isotherms | max dT/T events | max dx events | time |
| --- | --- | --- | --- | --- | --- | --- |
| dev_01 | 9.9e-12 | 0 | 2.2e-16 | 0 | 6.9e-18 | 8.2 s |
| dev_02 | 3.6e-12 | 0 | 4.4e-16 | 0 | 0 | 7.4 s |
| dev_03 | 7.9e-12 | 0 | 1.7e-16 | 0 | 3.3e-16 | 28.9 s |
| dev_04 | 3.7e-11 | 0 | 4.4e-16 | 1.4e-16 | 0 | 51.2 s |
| dev_05 | 1.9e-09 | 0 | 1.1e-16 | 1.5e-16 | 1.1e-16 | 35.2 s |
| dev_06 | 1.4e-10 | 0 | 6.7e-16 | 0 | 1.1e-16 | 35.7 s |
| dev_07 | 2.2e-11 | 1.1e-16 | 2.2e-16 | 3.8e-16 | 1.2e-15 | 40.4 s |

The independent event finder agreed with the reported dev_05 invariants to 1.1e-13 K and 1e-16 in
x. Residuals of 1e-11..1e-9 J/mol are the double-precision rounding of the reported numbers
themselves (G ~ 1e4 J/mol, eps 2e-16); the referee's own arithmetic is at the 1e-15 level.

Runtime is dominated by the completeness scan (about 4.4 ms per hull at 0.1 K, 12,001 hulls for
a 1200 K window, so about 55 s plus 2-3 s of certificates). Worst case observed: 51 s for the
1100 K window of dev_04. Without the C helper the scan uses a step of up to 0.25 K and the
monotone chain in Python (about 40 ms per hull), which stays under 5 minutes.

### Own test systems (`tests/`), each with an independent verification (`tests/verify_tests.py`)

`verify_tests.py` solves the textbook equations with `scipy.optimize.fsolve`/`brentq` from the
model written out again by hand (no import of `referee.py`) and brute-force checks each tie-line
for global stability on a 400k grid.

- `eutectic.json`: liquid with `L0 = -3000`, terminal alpha and beta (`L0 = 14000`), A melts at
  1000 K and B at 1050 K (pure-end transitions, not reported). Eutectic alpha-liquid-beta at
  608.843171419341 K, x = 0.0211704608561392 / 0.480958628410851 / 0.978829539143861; the
  `--solve` report agrees to 0 in T and 0..7e-18 in x; isotherm tie-lines agree to <= 1.1e-16.
- `congruent_compound.json`: compound AB at x = 0.5 melting congruently; closed-form
  `T_c = (h - A_L(0.5)) / (B_L(0.5) + s) = 950.00125463375 K`; report agrees to 1.1e-13 K with
  `phase_above = liquid`, `phase_below = AB`, `two_phase_side = below`. Two eutectics
  (alpha-liquid-AB at 794.802174317833 K, AB-liquid-beta at 727.183857707856 K) agree to
  1.1e-13 K and <= 1.7e-18 in x.
- `consolute.json`: regular solution alpha with `L0 = 20000`; `T_c = L0/(2R) = 1202.72355044943 K`
  at x = 0.5, `gap_side = below`; report agrees to 0 in T and x. Binodal tie-lines from
  `ln(x/(1-x)) = (L0/RT)(2x-1)` agree to <= 9.4e-16.

All three reports pass the referee (24, 24 and 19 s).

### Negative tests (corrupted copies of the dev_01 oracle report)

| corruption | caught by |
| --- | --- |
| tie end and region bound shifted by 2e-9 | residual 2.5e-5 J/mol; Newton-from-report dx 2e-9; independent dx 2e-9 |
| class flipped to peritectic | class and name checks |
| invariant T scaled by (1 + 3e-7) | line residual 5e-3 J/mol; liquid 2.4e-3 J/mol below the line; dT/T = 3e-7 |
| tie end shifted by 1e-4 | residual 8.4 J/mol; stability violation 4.6e-4 J/mol; dx 1e-4 |
| middle composition of the invariant shifted by 5e-10 | line residual 7e-6 J/mol (dx itself is below 1e-9) |
| invariant deleted | completeness: topology change at 539.384761 K with no reported event |

## Limits

- Critical points are located from the spinodal sign (exact in T); the other events are detected
  on sampled hulls and then bisected and Newton-polished, which removes the sampling lag.
- A feature narrower than the 20k scan grid
  (5e-5 in x) for its whole life would be missed by the scan (it would still be seen at the
  isotherms by the 50k construction and the 200k stability check). The bisection and Newton
  polishing remove the sampling lag before matching, so the 0.25 K matching tolerance is only a
  safety margin.
- Two events inside one 0.1 K scan interval whose combined effect leaves the label sequence
  unchanged would be missed; the spec guarantees events at least 0.5 K apart.
- The class and side tests evaluate the hull 0.1 K away from the event and rely on the same
  guarantee.
