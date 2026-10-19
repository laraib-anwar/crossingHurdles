# refB: finite-volume referee for the four-anion fixed-bed model

Files: `fv_referee.py` (solver + effluent analysis), `richardson.py` (multi-resolution driver,
front classification, Richardson extrapolation), `out/dev_XX/N{1000,2000,4000}/{effluent.npz,
summary.json}` and `out/dev_XX/extrapolated.json`. Python: `/Users/adnananwar/.venvs/tbs/bin/python`
(numpy 1.26.4, scipy 1.11.4). The solver never reads `solution/` or `tests/`.

## 1. Scheme

Conserved variable per ion `w_i = eps x_i + Lambda y_i(x)`, `y_i = alpha_i x_i / S`, `S = sum_j alpha_j x_j`,
`Lambda = 1000 Q / C_T` (233.33 for every dev recipe). Conservation form
`d w_i / dBV + d x_i / dxi = 0`, flux = liquid composition, velocity positive, so the face flux is
the upwind (left-cell) reconstructed composition. N uniform cells on `0 < xi < 1`.

* **Reconstruction (default `--order 2`)**: MUSCL on `x`. One limiter value per cell:
  `phi = min_k phi_k(r_k)`, `r_k = dL_k / dR_k`, with minmod `phi(r) = max(0, min(1, r))` (default)
  or van Leer `(r+|r|)/(1+|r|)`. Face value `x_face = x_j + 0.5 phi dR`. Because one scalar
  multiplies every ion's forward difference and the forward differences sum to zero, the face
  compositions sum to one exactly, so `sum_i w_i = eps + Lambda` is preserved to roundoff and the
  inversion below is consistent. Ions whose `|dR| <= 1e-12` do not constrain `phi`; a cell in which
  no ion varies beyond 1e-12 gets `phi = 0` (first version used `phi = 2` there, which is a
  downwind reconstruction of roundoff noise and was unstable; fixed).
* **Boundaries**: inlet ghost = feed composition (the inlet flux is exactly the feed);
  outlet ghost = linear extrapolation, so the outlet face value is second order.
* **Time**: SSP-RK2 (Heun) by default, SSP-RK3 optional; `--order 1` is upwind + forward Euler.
* **CFL**: `dt = 0.4 dx / lambda_max`. `lambda_max` is the largest characteristic speed actually
  present in the bed, `1/(eps + Lambda omega_min/S)`, with `omega_min` the smallest root of the
  h-transform equation `sum_i alpha_i x_i/(alpha_i - omega) = 0` (eigenvalue of `dy/dx` on the
  simplex; verified against brute-force Jacobian eigenvalues to 1e-15). `omega_min` lies in
  `[a_(1), a_(2)]` (two smallest separation factors; equals `a_(1)` exactly where the least-preferred
  ion is absent). It is solved as the root of `G = (a_(1)-om)(a_(2)-om) sum_i a_i x_i/(a_i-om)`,
  which is smooth on the closed bracket, positive left of the root, negative right of it. To keep the
  cost down: all cells are solved to convergence every 20 steps; in between, `G` is evaluated at the
  stored root; where `G >= 0` the stored value is a rigorous lower bound on `omega` (upper bound on
  the speed) and is kept; where `G < 0` the stored value is halved toward `a_(1)` until `G >= 0`;
  then the cell that attains the maximum speed is solved exactly (scalar Newton) whenever its bound
  is not already exact, repeated until the argmax cell is exact. So `dt` is always rigorous and
  equals the exact-speed `dt` (same step counts as solving every cell exactly every step).
  The bound `1/eps` suggested in the brief would be 70x too conservative here: the fastest wave is
  the family-1 (bicarbonate/chloride) characteristic at the feed state, ~0.036 xi/BV for dev_01.
* **Inversion w -> x**: `x_i = w_i /(eps + Lambda alpha_i / S)`; `h(S) = sum_i x_i(S) - 1 = 0` is
  increasing and concave in `S`, so unsafeguarded Newton (warm start from the previous `S`) converges
  globally; iterate until `|h| <= 1e-14` for every cell (typically 2 iterations); bisection fallback
  on `[alpha_min, alpha_max]` for any cell not converged in 60 steps (never triggered:
  `inversion_failures = 0` in every run).
* **Events**: feed switches and snapshot/sample times are hit exactly by clipping `dt`. Early exit
  when the whole bed is within 1e-12 of the current feed and no switch is pending (effluent is then
  constant to `run_bv`); recorded as `steady_state_exit_bv`.
* **Recorded**: at every step the outlet face value (`c_meq_per_L`, primary history) and the last
  cell average (`c_cell_meq_per_L`). The face history is second order but, being an extrapolation,
  over/undershoots by up to ~0.1 of a jump just *ahead* of an arriving shock (e.g. nitrate -0.10 at
  N=1000 in dev_01); the cell history is monotone wherever the scheme is but leads the outlet by half
  a cell transit (exactly first order in 1/N, removed by Richardson: both histories extrapolate to the
  same crossing BV to <1e-4 relative in every case). Plateau compositions, crossings and samples come
  from the face history; extrema, roll-up and the nitrate peak *value* from the cell history; the
  nitrate limit BV and shock BVs are reported from both.
* **Mass balance**: `W(end) - W(0) = inflow - outflow` per ion with the RK-weighted stage fluxes;
  error 1e-10 .. 5e-9 (relative ~1e-11 .. 1e-10) in all runs, i.e. roundoff accumulation.

Limiter choice. With van Leer, ion-by-ion limiting of this system emits small family-1 waves each
time a discrete shock crosses a cell; they travel downstream and leave 1e-4 .. 1e-3 noise on the
plateau behind every shock (feed region and shock-free binary tests are clean, so it is a system
effect at shocks, not a bug in the limiter). Minmod gives monotone discrete shocks and plateaus flat
to 1e-13 and equal to the h-root (Riemann-invariant) values to 1e-9 already at N=1000. Minmod is the
default and all results below use it. `fv_referee.py --limiter vanleer` is kept for comparison only.

## 2. Event detection (`analyze` in fv_referee.py)

Resample the face history on a uniform BV grid (50k .. 400k points). Flatness: windowed
max-min over `+-W`, `W = max(1e-3 run_bv, 10 run_bv/N)`, below `tol_flat = 1e-6 meq/L` for all
ions. Plateaus = flat runs longer than `4W`; composition = mean of the central half, with the spread
reported (1e-13 .. 1e-9). Fronts = the gaps. For each front: `before`/`after` = neighbouring plateau
compositions (or the window ends), jump, and for every ion with `|jump| > 1e-3` the first crossings
of 10/50/90 % of the jump (linear interpolation on the raw history; also `bv50` on the cell history);
width = `bv90 - bv10`; the normalised slope above `1/(20 cells-worth of BV)` marks steep sub-intervals,
whose share of the jump is `steep_fraction`. Single-resolution guess: shock-like if steep fraction
> 0.95 and 10-90 width < 15 cells, spreading if steep fraction < 0.05, mixed otherwise. The decisive
classification is in `richardson.py`: ratio of the leading ion's 10-90 width between successive N
(`>= 1.6` shock, `<= 1.3` spreading). Nitrate peak: max of the cell history; its BV is the preceding
shock's midpoint crossing when the maximum sits on a plateau that starts with a shock-like front, 0
when it is the initial plateau, else the first BV within 1e-7 of the maximum. Nitrate limit BV: first
strict exceedance on the raw history (interpolated), `null` if never, 0 if at BV = 0.
Plateau `bv_start/bv_end` are where the windowed spread crosses `tol_flat`, so they sit inside the
neighbouring fronts' smeared zones; use the crossings for positions.

## 3. Richardson extrapolation (`richardson.py`)

Three finest levels f1, f2, f3 (N, 2N, 4N), d1 = f2-f1, d2 = f3-f2. If both |d| below 1e-12:
converged (value f3, error max|d|). If d1 d2 > 0 and |d2| < |d1|: observed order p = log2(d1/d2),
clipped to [0.5, 3] for the extrapolation `f3 + d2/(2^p-1)`, reported error = |correction| (|d2|
is also stored and bounds the fine-level error when p >= 1). Otherwise value f3, error max|d|,
flagged. Plateaus/fronts of coarser levels are matched to the finest by interval overlap.

Observed orders: shock midpoint crossings p = 1.00 (face and cell), spreading-wave crossings and
10/90 points p = 0.9 .. 1.3, compositions inside spreading waves p ~ 0.9 .. 1.0 (minmod reduces to
first order at the fan edges), plateau compositions converged to 1e-12 .. 1e-9 at every level
(reported "converged" or flagged non-monotone with errors ~1e-12, which is roundoff, not a
convergence problem). dev_02 sample at BV 500 sits on the foot of the last spreading wave and shows
p = 3.6 with changes of 1e-6, i.e. essentially converged.

Levels run: N = 1000, 2000, 4000 for every recipe (the three used for extrapolation). N = 8000 was
not run: the machine (2-core 1.6 GHz i5, shared with other jobs during this session) needs ~3.5 ms
per step at N = 1000 and the step count grows like N, giving 17-20 min per recipe at N = 4000 and
an estimated 1.5-2 h per recipe at N = 8000. Extrapolated shock BVs carry 2e-3 .. 2e-2 BV error
(3e-5 relative), sample compositions <= 2.4e-4 meq/L before and ~1e-5 after extrapolation, so the
three levels suffice for the referee's purpose (TOL_BV = 2e-4 relative, TOL_C = 1e-4 meq/L).

## 4. Timings (minmod, RK2, CFL 0.4; wall-clock under 2-3 concurrent jobs)

| recipe | run_bv | N=1000 steps / s | N=2000 steps / s | N=4000 steps / s | early exit |
| --- | --- | --- | --- | --- | --- |
| dev_01 | 600 | 60875 / 172 | 122037 / 449 | 244365 / 1067 | no (sulfate front after 600) |
| dev_02 | 700 | 54230 / 145 | 109058 / 406 | 218721 / 959 | no |
| dev_03 | 1500 | 93557 / 239 | 187153 / 589 | 374347 / 1230 | no |
| dev_04 | 600 | 79004 / 110 | 158056 / 352 | 316159 / 1041 | no |
| dev_05 | 600 | 72150 / 142 | 144500 / 425 | 310718 / 1102 | 565 / 564 / none |
| dev_06 | 800 | 40950 / 77 | 82050 / 228 | 187739 / 835 | 701 / 700 / none |
| dev_07 | 900 | 106100 / 175 | 212650 / 1038 | 453028 / 1734 | 850 / 850 / none |
| dev_08 | 1600 | 71091 / 122 | 142861 / 772 | 286341 / 1661 | no |

(the N=4000 runs of dev_05/06 did not reach the 1e-12 uniformity test before run_bv because the
precursor tails decay more slowly on the finer grid; irrelevant for the results.)

## 5. Results per recipe (extrapolated; errors are the Richardson correction)

Sanity anchor: for dev_01 the h-root (Riemann-invariant) values of the two intermediate plateaus are
(3.96483007, 0, 0, 2.03516993) and (2.32459982, 1.81091697, 0, 1.86448321) meq/L; the FV plateaus
agree to 1e-9 at N=1000 and 1e-12 extrapolated, and the jump-condition shock BV
`Delta w / Delta x` = 519.95 agrees with the extrapolated crossing 519.944.

### dev_01 (chloride resin, 4-ion feed, run 600)
Structure: plateau (6,0,0,0) 0-61 | **spreading wave** (bicarbonate/chloride, 10-90 width 38.1 BV,
N-independent; onset 66.64, mid 82.46, end 104.71) | plateau (3.9648301, 0, 0, 2.0351699) |
**shock** at 519.944 +- 0.019 (width 0.71/0.36/0.18 BV at N=1k/2k/4k) | plateau
(2.3245998, 1.8109170, 0, 1.8644832) to 600. The sulfate front (feed state) has not arrived by 600.
Nitrate peak 1.8109170 (plateau, attained at the shock, 519.944); nitrate limit 0.714 first exceeded
at the shock, 519.944 +- 0.04. Samples: 50 -> (6,0,0,0); 150, 250, 350, 450 -> plateau 1 values
(converged to 1e-12). Roll-up: nitrate (1.811 vs feed 0.7) and bicarbonate (2.035 vs 1.8); no
roll-down.

### dev_02 (50/50 Cl/SO4 resin, run 700)
Structure: plateau (5.4059406, 0, 0.5940594, 0) 0-33 | **spreading** (bicarbonate; 36.77 -> 51.96,
mid 43.38, width 15.2 N-independent) | plateau (3.953127, 0, 0.4739514, 1.5729216) | **shock**
324.587 +- 0.011 | plateau (2.8927916, 0.7144989, 0.9053198, 1.4873896) | **spreading** (sulfate
family; onset 527.15 +- 0.44, mid 595.04 +- 0.3, still in progress at 700, width ~150 BV). Nitrate
peak is at run_bv inside the last spreading wave: 0.89356 +- 5e-4 at BV 700 (not converged better
than 5e-4 at N=4000: the wave is cut by the window); nitrate limit first exceeded at the shock
324.587 (plateau nitrate 0.7144989 > 0.714 by 5e-4, then rising in the last wave). Samples 20 ->
initial plateau, 120 and 300 -> plateau 1, 500 -> (2.892790, 0.714497, 0.905323, 1.48739) +- 4e-6.
Roll-up: sulfate (0.905 vs feed 0.6 / initial 0.594), bicarbonate (1.573 vs 1.5); roll-down:
chloride (2.893 below feed 3.0 and initial 5.41), sulfate (0.474 below both). Note the N=1000 level
missed the short initial plateau (33 BV, smeared onset), so plateau[0] has no error estimate.

### dev_03 (loaded resin eluted with 6 meq/L chloride, run 1500)
Structure: plateau (1.6947323, 0.7944058, 0.3724686, 3.1383932) 0-41 | **shock** 45.0089 +- 0.002
(bicarbonate leaves completely, 0.078/0.039/0.020 BV wide) | plateau (3.9039499, 1.4474512,
0.6485989, 0) | **spreading** (nitrate eluted; 200.03 -> 459.18, mid 290.29 +- 0.01, width 259)
| plateau (5.685654, 0, 0.314346, 0) 539-1026 | **spreading** (sulfate eluted; onset 1082.3 +- 1.5,
mid 1243.1 +- 0.5, cut at 1500: effluent (5.8593, 0, 0.1407, 0) at 1500). Nitrate peak 1.4474512
on plateau 1, attained at the shock (45.0089); nitrate limit exceeded at BV 0 (initial effluent
0.794 > 0.714). Samples: 100 -> plateau 1 (1e-15); 400 -> (5.310026, 0.305159, 0.384815, 0)
+- 1.4e-4 (p = 0.92, inside the nitrate wave); 800 -> plateau 2; 1200 -> (5.755247, 0, 0.244753,
0) +- 2.4e-4 (inside the sulfate wave). Roll-up: nitrate (1.447 vs initial 0.794) and sulfate
(0.649 vs 0.372). Interesting: bicarbonate is removed by a shock even though it is the least
preferred ion, because the displacing front is the chloride-for-bicarbonate exchange in the
favourable direction.

### dev_04 (chloride resin, Cl/NO3/SO4 feed without bicarbonate, run 600)
Structure: plateau (6,0,0,0) 0-425 | **shock** 427.517 +- 0.015 (0.66/0.33/0.165 BV) | plateau
(3.9595744, 2.0404256, 0, 0) to 600; the sulfate front is after 600. One front only in the window.
Nitrate peak 2.0404256 at the shock (427.517); limit exceeded at the shock. Samples 100, 300 ->
(6,0,0,0). Roll-up: nitrate (2.04 vs feed 1.0).

### dev_05 (dev_01 feed to 200 BV, then more sulfate / less chloride, run 600)
Identical to dev_01 until BV 278.97 (first divergence > 1e-6). Structure: plateau (6,0,0,0) |
spreading bicarbonate wave (as dev_01) | plateau (3.9648301, 0, 0, 2.0351699) 116-277 | **small
spreading wave** of family 1 from the feed switch (jump 0.148 in Cl/HCO3; 277.5-287.8, mid 282.41
+- 0.05, width 4.06/3.44/3.17 BV, ratio 1.18/1.09: converging to a finite width, so spreading, but
narrow; flagged "mixed" at N=1000 only) | plateau (3.8171087, 0, 0, 2.1828913) | **shock**
467.315 +- 0.017 (nitrate 0 -> 2.9104691) | plateau (1.2090108, 2.9104691, 0, 1.8805201) |
**shock** 561.591 +- 0.020 (sulfate 0 -> 2.5) | plateau = feed 2 (1, 0.7, 2.5, 1.8) from 563.6.
What happens after the switch: the feed-2 sulfate shock is faster than the feed-1 sulfate and nitrate
shocks (bed snapshots: at BV 250 there are five active fronts between xi = 0.22 and 0.73; by BV 350
only two remain, at 0.56 (feed 2 -> roll-up plateau) and 0.71 (roll-up plateau -> bicarbonate
plateau)). The feed-1 nitrate shock that dev_01 shows at 519.9 and the feed-1 sulfate shock (beyond
600 in dev_01) are both overtaken inside the bed and never reach the outlet; the merged structure
is one nitrate shock at 467.3 with a much stronger roll-up (2.910 vs 1.811 in dev_01) followed by
the merged sulfate shock at 561.6. Only the family-1 part of the switch reaches the outlet as a
separate (spreading) wave. Nitrate peak 2.9104691 (plateau 3, attained at the shock, 467.315); limit
exceeded at that shock (467.315 +- 0.04). Samples: 100 -> (4.317676, 0, 0, 1.682324) inside the
first wave (p = 0.99, extrapolated); 250 -> plateau 1; 350, 450 -> plateau 2; 550 -> plateau 3.
Roll-up: nitrate (2.91 vs 0.7) and bicarbonate (2.18 vs 1.8). The face-history nitrate max is 3.15
(the pre-shock extrapolation artefact); the cell history gives the plateau value, which is why the
peak value is taken from the cell history.

### dev_06 (nitrate-selective resin, alpha_NO3 = 5 > alpha_SO4 = 3, run 800)
Structure: plateau (6,0,0,0) | spreading bicarbonate wave (mid 82.15, width 37.4) | plateau
(3.9921726, 0, 0, 2.0078274) | **shock** 475.651 +- 0.018 (sulfate breaks through: 0 -> 2.0828,
roll-up) | plateau (2.0978336, 0, 2.0827932, 1.8193732) | **shock** 667.957 +- 0.022 (nitrate
0 -> 0.7 displaces sulfate down to 1.5) | plateau = feed (2, 0.7, 1.5, 1.8). The last front is
flagged "mixed" by the single-resolution test (steep fraction 0.90) but its 10-90 width halves with
N (2.37/1.18/0.59 BV) and the trailing deviation from the feed at BV 670 is 1.8e-2 / 1.0e-3 / 2.9e-6
for N = 1k/2k/4k: a shock with a one-sided discrete tail, not a composite wave. Nitrate peak 0.7
(= feed, reached after the last shock at 667.96); nitrate limit never exceeded (null). Samples:
100 -> (4.317675, 0, 0, 1.682325) in the first wave; 300 -> plateau 1; 500 -> plateau 2; 700 ->
feed. Roll-up: sulfate (2.083 vs 1.5) and bicarbonate (2.008 vs 1.8); no nitrate roll-up on a
nitrate-selective resin.

### dev_07 (dev_02 feed to 150 BV, then more sulfate / less chloride, run 900)
Identical to dev_02 until the switch waves arrive. Structure: plateau (5.4059406, 0, 0.5940594, 0)
0-34 | spreading bicarbonate wave (mid 43.38, width 15.2) | plateau (3.953127, 0, 0.4739514,
1.5729216) | **small spreading wave** from the switch (family 1; jump 0.15 in Cl/HCO3; mid 196.67
+- 0.004, width 2.37/2.03/1.87 BV, ratios 1.17/1.09, so converging to a finite width ~1.7 BV) |
plateau (3.8138967, 0, 0.4624408, 1.7236625) | **shock** 315.590 +- 0.009 (nitrate 0 -> 1.5114,
sulfate 0.462 -> 1.377, chloride 3.81 -> 1.59) | plateau (1.5919219, 1.5113635, 1.376635, 1.5200796)
317-422 | **composite**: a spreading wave 421.6 -> 492.4 (nitrate 1.511 -> 1.709 rising, sulfate
1.377 -> 1.143 falling, N-independent extent ~72 BV) that ends directly in a **shock** at
492.373 +- 0.05 (to feed 2) with no intermediate plateau | plateau = feed 2 (1.5, 0.9, 2.1, 1.5)
from 494. dev_02's shock at 324.6 and its long sulfate wave never reach the outlet: the feed-2 sulfate
wave overtakes them (merged shock at 315.6, earlier and stronger), and the family-2 fan it leaves
behind is cut off by the final shock. Nitrate peak 1.7212 +- 0.0016 (p = 0.86) at the pre-shock end
of the composite wave, BV 492.37 (the shock position); nitrate limit first exceeded at the shock
315.590 +- 0.01. Samples: 100 -> plateau 1; 250 -> plateau 2; 400 -> plateau 3 (all to 1e-9 or
better); 550, 700, 850 -> feed 2. Roll-up: nitrate (1.72 vs feeds 0.9) and bicarbonate (1.72 vs
1.5); roll-down: sulfate (0.462 below feed 1's 0.6 and initial 0.594).

### dev_08 (dev_03 elution to 100 BV, then 4 Cl / 2 HCO3 feed, run 1600)
Identical to dev_03 until the switch waves arrive. Structure: plateau (1.6947323, 0.7944058,
0.3724686, 3.1383932) 0-43 | **shock** 45.0089 +- 0.002 (bicarbonate out) | plateau (3.9039499,
1.4474512, 0.6485989, 0) 47-132 | **spreading wave** (bicarbonate returns 0 -> 1.849; 136.5 ->
158.0, width 21.5 N-independent) | **short plateau** (2.6026332, 1.0627816, 0.4859472, 1.8486379)
165-193 (27 BV; detected at N = 2000 and 4000 only, so no error estimate; values flat to 1e-9) |
**spreading wave** (nitrate eluted 1.063 -> 0, sulfate 0.486 -> 0.236, chloride 2.60 -> 3.79;
onset 220.8, end 569.4, N-independent) | plateau (3.790436, 0, 0.2355162, 1.9740478) 672-1320 |
**spreading wave** (sulfate eluted, onset 1371 +- 1, mid 1466.6 +- 1, cut at 1600; effluent
(3.8468, 0, 0.1722, 1.9810) at 1600). dev_03's long nitrate fan (177-539) is replaced: the feed-2
bicarbonate wave interacts with it, producing the short plateau and a steeper fan that ends at 569
instead of 539; the final sulfate fan is also shifted (onset 1371 vs 1082 in dev_03). Nitrate peak
1.4474512 on plateau 1, attained at the shock 45.0089; nitrate limit exceeded at BV 0. Samples:
150 -> (3.041312, 1.192455, 0.540778, 1.225456) +- 8e-6 (inside the bicarbonate wave); 300 ->
(3.056422, 0.656757, 0.390273, 1.896548) +- 2.4e-4 (p = 0.75, inside the nitrate fan); 450 ->
(3.46108, 0.294688, 0.304956, 1.939276) +- 6e-5; 700 and 1100 -> plateau 3; 1400 -> (3.803035,
0, 0.221357, 1.975608) +- 5e-4 (inside the cut sulfate fan, p = 0.94). Roll-up: nitrate (1.447 vs
initial 0.794), sulfate (0.649 vs 0.372); no roll-down.

## 6. Suspicious or notable

* Van Leer common limiter: plateau noise downstream of shocks (section 1). Not used.
* First version of the "excluded ions" rule (phi = 2 when no ion constrains) was unstable; fixed.
* Outlet extrapolation over/undershoots ahead of shocks (up to 0.35 meq/L in dev_05): expected for an
  unlimited boundary extrapolation; harmless for crossings and plateaus, handled by using the cell
  history for extrema.
* The nitrate peak BV on a plateau is a property of the exact solution (the plateau's first point);
  the FV argmax inside a flat plateau is roundoff-random, so `nitrate_peak.bv` is the preceding
  shock's crossing. For dev_05 the location label says `front[3]` because the roundoff argmax of
  the cell history fell just past the detected plateau end; the value and the shock-based BV are right.
* dev_02 initial plateau is only 33 BV long and was merged into the first wave at N = 1000 with the
  first flatness window; the window was then tightened to `W = max(5e-4 run_bv, 4 run_bv/N)` and
  all summaries re-analysed (`--analyze-only`), after which every plateau of dev_01..07 is found at
  all three levels; dev_08's 27-BV plateau is still missed at N = 1000.
* Composite fronts (dev_07): a spreading wave that ends in a shock has no plateau between them, so
  the detector reports one front; `richardson.py` labels it composite when the part of the leading
  ion's change outside the steep sub-interval exceeds 2 % and its extent does not shrink with N, and
  extrapolates the shock part's own midpoint (`steep_parts_extrapolated`). Samples inside spreading
  waves converge at first order (p 0.75 .. 1.0) and carry 1e-4 .. 5e-4 before extrapolation.
* dev_02 nitrate peak is at run_bv inside an unfinished spreading wave, so it converges only at
  first order (+-5e-4 after extrapolation); an exact solver's value should lie within that.
* Precursor tails: ions that have not yet broken through carry positive values down to 1e-300 in the
  effluent (exponentially small numerical precursors of the discrete shock profile), never negative
  with minmod. Treat anything below ~1e-10 as zero.
