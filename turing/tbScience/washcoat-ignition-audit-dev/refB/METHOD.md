# Reference B: transient method-of-lines referee

`mol_referee.py` integrates the time-dependent model of WASHCOAT_SPEC.md section 1 and reports
only what direct time integration shows: which states are attractors, where the attractor
followed by a slow parameter sweep jumps, and whether an attractor is a steady state or a
limit cycle. It never solves the steady equations and never forms or diagonalises the
linearised operator, so it is independent of the two steady-state codes it referees. Unstable steady states are invisible
to it by construction; it confirms them only indirectly (no attractor near them, or a growing
departure when it starts on them).

Python: `/Users/adnananwar/.venvs/tbs/bin/python` (NumPy 1.26.4, SciPy 1.11.4).

## Discretisation

* Space: cell-centred finite volumes, N cells. Faces at `x(s) = 1 - sinh(a(1-s))/sinh(a)`,
  `s` uniform, which clusters cells towards the exposed face `x = 1` where the reaction zone
  is thinnest on the ignited branch. `a` is chosen automatically so that the face cell is
  about 1/20 of `delta = 1/(phi_max sqrt(R(theta_ad)))`, `theta_ad = beta Bi_m/Bi_h`, capped at
  `a = 7` (`--cluster` overrides; 0 is uniform).
* Interior face fluxes: centred differences between cell centres. Wall face: zero flux.
* Robin face (flux form): the quadratic through the last two cell centres and the face value
  gives `u_x(1) = w0 u_{N-2} + w1 u_{N-1} + w2 u_b`; eliminating `u_b` with
  `-u_x(1) = Bi (u_b - u_inf)` gives the face flux
  `F = Bi/(w2+Bi) (w0 u_{N-2} + w1 u_{N-1} + w2 u_inf)`, second order and exactly zero when
  the layer is at the bulk-gas state.
* Observables: `theta_c` is the zero-slope quadratic extrapolation of the first two cells to
  `x = 0`; `eta` is the Robin face flux of `c` divided by `phi^2`.
* Time: `scipy.integrate.solve_ivp`, BDF by default (Radau and LSODA selectable). Unknowns are
  interleaved `(theta_0, c_0, theta_1, c_1, ...)`, so the analytic Jacobian is banded with
  half bandwidth 2. It is passed as a sparse CSC matrix built from the band pattern (BDF,
  Radau) or in LAPACK packed band form with `lband = uband = 2` (LSODA, 7-row storage; checked on dev_03, same steady values as BDF and Radau). The Jacobian was
  checked against central differences (relative error 6e-10).

## Relaxation (`relax`)

Integration proceeds in windows (first window `max(1, Le)`, doubling up to `40 max(1, Le)`;
once oscillations are visible a window is capped at about 30 periods). `theta_c` is sampled
from the dense output at every integrator step subdivided 8 times (2 times in a window of
more than 2000 steps). After each window:

* **steady** when `max|dy/dt|` (theta rows multiplied back by `Le`), divided by
  `max(1, phi^2)`, is below `1e-9`; or, when that residual sits at its round-off floor
  (below `1e-6`), the state moved by less than `1e-11` over a window of at least
  `10 max(1, Le)`. The round-off floor is about `1e-8`: the clustered grid puts terms of
  size `1/h^2 ~ 1e7` in the residual.
* **cycle** when the last 7 maxima of `theta_c` (parabolic refinement) give 6 periods whose
  spread is below 0.2 % and 6 peak-to-trough amplitudes whose spread is below 0.2 %, with
  amplitude above `1e-7`. A decaying focus fails the amplitude test. The cycle is then
  integrated over 3 more periods with 6001 output points for the period, `omega = 2 pi/P`,
  mean, min and max of `theta_c` and of `eta`.
* **unresolved_oscillating** when oscillations of amplitude above `1e-6` are still unsettled
  at `300 max(1, Le)` (slow amplitude drift next to a Hopf point); the result carries the
  current amplitude and its exponential growth rate, and a growing oscillation is counted as
  the cycle side, a decaying one as the steady side.
* **unresolved** at `tmax` (default `3000 max(1, Le)`).

Extrema of `theta_c` are found with a zigzag filter (a swing below `1e-9` does not count), so
round-off wiggles of a settled state are never taken for oscillations. For the cycle test each
extremum is re-located on the dense output of the current window (201 points around it):
ignition spikes of relaxation cycles are too sharp for the step samples. An oscillation counts
as current only if an extremum occurred within the last three periods.

`relax --state NPZ --branch up|down` starts from a state saved by a sweep (same grid), which
is how an unstable steady state of one Lewis number is used as the initial condition for
another (steady states do not depend on `Le`). `--perturb` adds a uniform temperature kick
and `--trace T` integrates the kicked and the unkicked state side by side and fits the
exponents of the difference in `theta_c` (matrix pencil, as in `kick` below).

## Sweep (`sweep`)

Quasi-static continuation by relaxation. The `phi` grid is geometric from `phi_min` to
`phi_max` (at least 60 steps per decade and 150 steps per pass, or `--per-decade`) with every
`phi_query` value inserted. The up-pass starts cold (`theta = 0`, `c = 1`) at `phi_min` and
relaxes at each step from the previous end state; the down-pass starts from the up-pass end
state at `phi_max` (hot start).

An event is flagged between two steps when the attractor key (`theta_c` for a steady state,
time-mean `theta_c` for a cycle) changes by more than `0.01 theta_ad` and by more than 4 times
the neighbouring step changes, or when the attractor type changes. Each event is bisected in
`ln phi` down to `5e-5`, every trial restarting from the last state still on the old
attractor; a trial counts as jumped when its key is nearer the post-event key (or, for a type
change, when it has the post-event type). A steady/cycle type change without a jump of the key (a Hopf point) is bracketed only to
`1e-3` with `tmax = 400 max(1, Le)` per trial, because the amplitude settles at a rate that
vanishes at the Hopf point; the `kick` command locates Hopf points more precisely. After
bisection an event whose key gap is still
above `0.01 theta_ad` is a jump: an **ignition** when `theta_c` rises, an **extinction** when it
falls; otherwise it is a steep but continuous change. Type changes are reported as
onset or end of oscillation. The reported jump position is the geometric mean of the final
bracket, which contains the fold (or the Hopf point, when the old attractor dies there) of
the discretised model up to relaxation-time effects close to the fold.

## Kick (`kick`)

Steady states do not depend on `Le`, so a steady state that is an attractor at one Lewis
number (here dev_01, `Le = 1`) is an exact steady state of a recipe with the same `beta`,
`gamma`, `Bi_m`, `Bi_h` and another `Le`. `kick` relaxes the companion recipe at the exact
`phi` (residual below `1e-10`), adds `1e-8` to `theta` everywhere, integrates the kicked and
the unkicked state under the target `Le` (`rtol = 1e-11`), and fits the difference of
`theta_c` with a matrix pencil (2 to 4 exponentials) while it is still below `1e3` times the
kick. The exponent of largest amplitude is the leading mode excited by the kick; its real part
is the growth rate and its imaginary part the frequency. A Hopf point is the `phi` where the
real part of the dominant complex exponent changes sign. `--follow` then relaxes the kicked
state to its attractor (with a larger kick, `1e-4`, for the cycle runs). This is a direct
time integration of the nonlinear model; it never forms or diagonalises a matrix.

## Probe (`probe`)

Relaxes from uniform initial states, `theta0` in 7 values over `[0, theta_ad]` times `c0` in
5 values over `[0, 1]` (35 runs), plus the up- and down-sweep states nearest the probed
`phi` (2 runs), and clusters the end states: steady states equal within `1e-4 max(1,|v|)` in
both `theta_c` and `eta`; cycles equal within `2e-3` in mean `theta_c` and 1 % in period.
Probes use `rtol = 1e-6` (classification only; steady values do not depend on `rtol` because
they are fixed points of the integrator).

## Summary (`summary`)

Sweep plus probe at every `phi_query`, writing `sweep_N<N>.json`, `states_N<N>.npz`,
`probe_N<N>.json` and `summary_N<N>.json` in `out/<recipe>/`. Settings used for every dev
recipe: N = 200, BDF, `rtol = 1e-7` (sweep), `1e-6` (probe), `atol = 1e-11`; dev_07 with
400 steps per decade; dev_01 repeated with N = 400 (same mapping, every cell halved) as the
grid-convergence check, plus a dev_07 sweep at N = 400.

**Integrator for Le < 1.** dev_05 (`Le = 0.2`) is run with Radau. Its ignited branch has
weakly damped oscillatory modes (frequency about 22 near `phi = 0.5`, about 400 near
`phi = 2`); variable-order BDF at `rtol = 1e-7` rings on them at an amplitude of about `1e-6`
in `theta_c` without decaying (orders 3 to 5 are not A-stable), which a BDF sweep reported as
a Hopf bracket shifted to 0.5174. Radau (L-stable) settles the same states to steady. The
other recipes never met an oscillatory state and were run with BDF, by the script version
before its last three changes (dense-output refinement of cycle extrema, a history-length fix
and the stale-oscillation test); those changes touch only oscillation detection, and none of
those runs had a cycle or an unsettled oscillation in any sweep step or probe run.

## Results (N = 200 unless stated)

Jump positions are the geometric mean of the final bisection bracket (relative width
3.7e-5 to 4.5e-5; Hopf brackets 6e-4). "Basin" counts the 37 probe runs ending on an
attractor. No sweep step and no probe run of any recipe ended unresolved.

| recipe | Le | sweep events (phi) | attractors at phi_query |
| --- | --- | --- | --- |
| dev_01 | 1 | ignition 0.367186, extinction 0.276380 | 0.3: cold 0.0268624 / hot 0.3651894 (18/19); 1 elsewhere |
| dev_02 | 1 | ignition 0.285384, extinction 0.0435466 | 0.1: cold 0.0021030 / hot 0.9476283 (12/25); 1 elsewhere |
| dev_03 | 1 | none (no jump, no steep change) | 1 at every query |
| dev_04 | 5 | ignition 0.367186, extinction 0.276380 | as dev_01 (0.3: 16/21) |
| dev_05 | 0.2 | cold to cycle at 0.367186; cycle to hot steady (Hopf) in [0.501626, 0.501925]; down: hot to cycle in the same bracket, cycle to cold at 0.366939 | 1 at every query; 0.3: cold only |
| dev_06 | 3 | ignitions 0.343944, 0.485422; extinctions 0.446368, 0.225921 | 1 at every query (none lies in a loop) |
| dev_07 | 0.5 | ignitions 0.444429, 0.460156; extinctions 0.431157, 0.451265 | 0.43791: 0.0407900 / 0.1286383 (9/28); 0.44576: 0.1409025; 0.45567: 0.1576431 / 0.2569332 (15/22); 1.0: 1 |

All steady attractors at the queries agree between the up and down sweeps and the probes;
every attractor at a query is a steady state (no limit cycle at any query value of any
recipe). The full `(theta_c, eta)` of each attractor is in `out/<recipe>/summary_N200.json`.

**Lewis number (dev_01, dev_04, dev_05: identical steady parameters).** The fold positions do
not move with `Le` (ignition 0.367186 and extinction 0.276380 in all three sweeps, identical
steady values at every query), as the spec states. Le = 1 and Le = 5: the ignited branch is
stable down to the extinction fold; kicks of its states at phi 0.28, 0.3, 0.6, 1 decay (leading
excited exponents -0.09, -0.20, -0.42, -0.47 at Le = 5; -1.6, -2.4, -2.4, -2.4 at Le = 1, all
real), no oscillation anywhere in either sweep. Le = 0.2: the ignited branch is unstable below a
Hopf point and the extinction fold plays no role:

* Hopf point: the dominant complex exponent of a kicked upper state changes sign between
  phi 0.501 (+0.0349 + 22.17i) and 0.502 (-0.0219 + 22.27i); linear interpolation gives
  phi_H = 0.50161, omega = 22.23. The Radau sweep brackets the end of oscillation in
  [0.501626, 0.501925]; the squared cycle amplitude extrapolates to zero at 0.50144.
  Supercritical: the cycle amplitude grows from zero (peak-to-peak theta_c 0.042 at 0.500,
  0.086 at 0.495, 0.116 at 0.49).
* Cycle periods (from the kicked upper state): 0.2845 (phi 0.500, omega 22.09), 0.2902
  (0.495), 0.2963 (0.49), 0.3249 (0.47), 0.3650 (0.45), 0.5777 (0.42). Sweep values: 0.29189
  (0.4936), 0.31675 (0.4751), 0.34820 (0.4573), 0.39398 (0.4402), 0.50353 (0.4237).
* Near 0.41428 the cycle changes steeply but continuously (at 3.7e-5 resolution) from this
  small cycle into a large relaxation oscillation (period 1.53 at 0.4079, 1.77 at 0.3926,
  2.25 at 0.3779, 5.13 at 0.3671; theta_c swings from about 0.04 to 1.5, above theta_ad).
* Upper state at phi 0.3 (the Le = 1 hot steady state, theta_c 0.3651894, eta 16.1376276,
  used as the initial state at Le = 0.2): unstable, with two real positive exponents
  +11.15 and +5.48 (no oscillation in the departure); the kicked state falls to the cold state
  0.0268624. The probe at 0.3 finds only the cold state (37/37). So "unstable as predicted" is
  confirmed, and the leading eigenvalue there is real.
* Up-sweep: the cold state ignites at the fold 0.367186 into the relaxation cycle. Down-sweep:
  the cycle survives slightly below the fold and collapses to the cold state at 0.366939; a
  cold state relaxed at 0.3671 from phi 0.36375 also ends on the cycle (period 5.13), at 0.3670
  it stays cold. So cold state and cycle coexist in a narrow window of relative width about
  7e-4 below the fold.

**dev_07 (two separate hysteresis loops).** Confirmed. Up-sweep: lower to middle stable branch
at 0.444429, middle to upper at 0.460156. Down-sweep: upper to middle at 0.451265, middle to
lower at 0.431157. The loops [0.431157, 0.444429] and [0.451265, 0.460156] are disjoint; the
middle branch is stable in between (0.44576 has a single attractor, theta_c 0.1409025). The
predicted folds 0.4311 / 0.4444 and 0.4512 / 0.4601 match to the four digits given.

**dev_06** also shows two disjoint hysteresis loops, [0.225921, 0.343944] and
[0.446368, 0.485422]; its queries all lie outside them.

**Grid convergence.** dev_01 at N = 400 (every cell halved): ignition 0.367213 (+7.5e-5
relative), extinction 0.276390 (+3.7e-5, one bracket width); attractor values differ by at most
1.9e-5 in theta_c and 7.2e-5 relative in eta (`out/dev_01/convergence_N200_N400.json`, which
also lists Richardson values). dev_07 at N = 400: the four jumps move by 0 to 4.5e-5 relative
(one bracket width), `out/dev_07/convergence_N200_N400.json`. The N = 200 referee is therefore
good to about 1e-4 relative in phi and in the attractor values, far from the spec's 1e-6
tolerances; it settles counts, classes and positions, not the 1e-6 digits.

**Timings** (wall clock on a shared, heavily loaded 4-core machine; sweep + probe): dev_01
172 + 355 s, dev_02 337 + 261 s, dev_03 144 + 159 s, dev_04 259 + 347 s, dev_05 (Radau)
2223 + 770 s, dev_06 362 + 360 s, dev_07 (400 steps/decade) 464 + 242 s; dev_01 N = 400
256 + 318 s; dev_07 N = 400 sweep 332 s. Steady steps take 0.2 to 1 s; a cycle step at
Le = 0.2 takes 5 to 40 s (about 1000 steps per unit time on the relaxation cycles).

## Limits

* Time integration sees attractors only. Unstable steady states (middle branches, the dev_05
  upper branch between 0.2764 and 0.5016) are never reported by sweep or probe; their
  existence comes from the steady codes, and `kick` confirms instability only for states that
  are steady states at another Lewis number.
* The `kick` exponents are those excited by a uniform temperature kick and fitted from
  theta_c; small-amplitude exponents in the fit are not reliable, and the method is not an
  eigenvalue solver.
* Probes start from uniform states and the two sweep states; an attractor with a basin
  missed by all 37 starts would not be found.
* Jump positions near a fold carry a slow-passage bias. One bisection trial reached `tmax`
  without settling: dev_07 at phi 0.4601459 (upper end of the second ignition bracket), still
  on the old branch after 3000 time units; it was counted as not jumped, so the N = 200
  bracket [0.4601459, 0.4601666] may sit one bracket width too high (the N = 400 sweep puts
  this ignition in [0.4601252, 0.4601459]). In dev_05 two Hopf-bracket trials ended as
  decaying oscillations at the 400 time-unit budget and were counted as steady. Every other
  bisection trial settled.
