# Reference B: notes

This is an independent referee for REGIMEN_SPEC.md. I wrote it from the spec alone; I did not read
the oracle (`solution/`), `gen/expected/` or `refA/`.

Files:

- `referee.py`: `python referee.py --regimen in.json --output out.json [--check out.check.json]`.
  It writes exactly the section 4 report. Options: `--single` runs once with no halving check;
  `--theta`, `--order` change the step and the order.
- `run_all.sh [jobs]`: writes `out/<name>.json` and `out/<name>.check.json` for every file in
  `../gen/regimens/`.
- `out/`: 28 reports and 28 check files (model_01..06, held_01..22).

## Method

**Integrator.** A Taylor-series method of order K = 30 in numpy longdouble (x86-64 80-bit, eps
1.08e-19), restarted exactly at every event. The state is A1, the peripheral amounts, the transit
and depot amounts of every formulation that is dosed, and the AUC as an extra state with
dAUC/dt = A1/V1. Each step computes the coefficients of x(t0 + h tau), tau in [0, 1], from

    (k+1) c[k+1] = h (L c[k] + R e1 [k = 0] - Vmax y[k] e1),

The Michaelis-Menten series y = C/(Km + C) comes from the Cauchy-product recurrence
y[k] = (C[k] - sum_{j=1..k} C[j] y[k-j]) / (Km + C[0]). The method uses no matrix exponential,
no eigen-decomposition and no scipy integrator.

- **Linear models (Vmax = 0).** Equal fixed steps inside each event interval, with
  h <= min(2 theta, 4 theta / ||L||_1). The solution is entire, so at theta = 1/2 the
  truncation is below 2^31/31! ~ 3e-25.
- **Michaelis-Menten models.** The same cap, with Vmax/(V1 Km) added to the central column
  norm, plus a radius-of-convergence step control in the Jorba-Zou style:
  h <= f h_try min_{j=K-1,K} (1e-22 scale / |c_j|)^(1/j). Here f = 1 for theta = 1/2 and
  1/2 for the half-step run. A step that violates the bound is rejected and redone. The
  singularity of C/(Km+C) sits where C(t) = -Km, at a distance of about (Km + C)/|dC/dt|. That
  distance gets very short when a lagged oral dose arrives, or an infusion starts, while C is
  far below Km. In model_05 it is about 1.6e-3 h. See the development note below.

**Events.** Every time is an exact rational: the decimal value of the JSON number. So
`start + m period + offset`, the infusion ends and the lag arrivals merge exactly when they
coincide. Parameters are the double values. Infusion rates are exact rationals summed over the
infusions running in each interval. The rate is right-continuous on [t_d, t_d + duration).
Boluses go into A1 and oral doses go into T1, or into D when n_transit = 0, at t_d + tlag. Both
are applied at the start of the interval that begins at the event, so C is right-continuous and
the left limit is the state before the jumps.

**Periodic steady state.** One period [0, P) of the maintenance regimen continued in both
directions is built separately: infusions that wrap from earlier cycles, possibly several when
duration > period, and lagged arrivals from the previous cycle (offset + tlag >= P). The
period map acts on the left-limit state at the cycle start, excluding AUC. Its fixed point
comes from Newton's method with the exact Jacobian from the variational equations, which are
Taylor-integrated together with the trajectory; the Michaelis-Menten term contributes
-Vmax Km/(V1 (Km+C)^2) through a w = 1/(Km+C) recurrence. The linear solve is my own longdouble
Gaussian elimination with pivoting. Iteration stops when the update stagnates at roundoff.
A separate trajectory-only map then measures the final residual |Phi(x*) - x*| / |x*|: at most
3.7e-19 over the 28 regimens. Linear models converge in 2 to 3 iterations; Michaelis-Menten
models converge quadratically in 4 to 7 iterations.

**Extrema and crossings.** For each step I keep the C polynomial and sample it and its exact
polynomial derivative at 17 points. Sign changes of dC/dt bracket the critical points, and
sign changes of C - low and C - high bracket the window crossings. Each bracket is polished by
longdouble bisection on the polynomial. At every polished maximum and crossing, dC/dt is also
re-evaluated from the right-hand side at the dense state: it is about 1e-18 at every t_cmax.

The cmax candidates on [0, horizon] are:

- interior critical points;
- the right value at every step boundary (post-bolus values and infusion-end kinks);
- the left value at the closed end, the horizon.

The steady-state cmax and cmin also take left limits, so pre-bolus values and C(P-) count;
see ambiguity A1. time_in_window is the measure of {low <= C <= high} on [0, P), taken from the
crossing points and the bolus jump points. Each sub-interval is classified by the polynomial at
its midpoint.

**Troughs and n_cycles_to_steady.** The actual regimen, loading doses included, is simulated
directly with the actual-regimen schedule:

- first to t_{m_a} >= horizon, with dense output on [0, horizon];
- then one cycle per chunk, carrying the running infusion rate across chunks.

trough_m is the left limit at start + m period. Direct simulation stops at cycle m once the
tail bound ||e1/V1|| sup_j ||P^j||_2 ||x_m - x*||_2 <= 1e-7 trough holds, where P is the
period-map Jacobian at x*. That bound proves every later trough lies within 1e-7 relative of the
steady trough, so the condition holds for every later cycle with margin 0.01 - 1e-7. If cycle 61
is reached first, the run continues with the exact period map, nonlinear for Michaelis-Menten,
down to a 1e-6 deviation, then with the linearised recursion e <- P e checked cycle by cycle
until the bound reaches 0.999 x 1 %. Every regimen was certified this way (column
"cycles simulated" below; 61 means the extension was used). n_cycles_to_steady is one plus the
last cycle that violates |trough_m - trough| <= 0.01 trough.

**Cross-check of the two schedules.** After the direct simulation, one more cycle m -> m+1 is
integrated two ways: with the actual-regimen schedule, and with the periodic-window schedule
from the same state. They agree bitwise (difference 0) in all 28 regimens, so the periodic
window reproduces the actual cycles exactly, wrap-around included.

**Guarantee checks.** referee.py checks every section-2 guarantee itself; the results are in the
check file under `fine_run.guarantees` and in the table below.

- **G1.** Separation of the query times and the horizon from every bolus time, in exact rationals.
- **G2.** The list of local maxima on [0, horizon]: smooth maxima, maxima at step boundaries,
  post-bolus maxima, infusion-end kinks, and the horizon end when C is still rising. Also the
  largest other local maximum, all post-bolus values (counted as candidates even when C keeps
  rising), and |C''| at a smooth global maximum.
- **G3.** Window bounds against the steady-state cmin and cmax; |dC/dt| at every continuous
  crossing (RHS value) against the steady-state cmax, with the horizon-cmax version also in the
  file; pre-bolus and post-bolus values against low and high.
- **G4.** The margin ||trough_m - trough| - 0.01 trough| / trough for m = 1..60, and that every
  m >= 60 is inside the band (direct values plus the tail certificate).
- **G5.** Steady-state positivity and cmax >= 1e-3.

The check also verifies the section 2/3 domain and finds no violations.

## Error estimates: step halving

The whole pipeline runs twice: theta = 1/2 and theta = 1/4. The second run halves every fixed
step and every radius-limited step, and recomputes the Newton solve, the dense analysis, the
troughs and the guarantees. The theta = 1/4 run is the one reported. The differences are in
`out/<name>.check.json` under `error_estimates_half_step`.

Worst over the 28 regimens. S is the report's cmax, the section 5 scale:

| quantity | worst difference | regimen | tolerance |
|---|---|---|---|
| concentrations | 8.4e-19 S | held_08 | 1e-8 S |
| auc | 1.2e-18 relative | model_02 | 1e-8 relative |
| cmax | 3.9e-19 S | model_04 | 1e-8 S |
| t_cmax | 2.8e-17 h | model_02 | 1e-6 h |
| steady-state cmax / cmin / trough | 1.4e-18 S | model_04 | 1e-8 S |
| time_in_window | 5.3e-16 h | held_08 | 1e-6 h |
| troughs m = 1..60 | 1.0e-17 x trough | held_08 | - |
| n_cycles_to_steady | identical in both runs, all 28 | - | exact |
| Newton fixed-point residual | <= 3.7e-19 relative | held_03 | - |

**Disagreement above 1e-10 relative:** none. The largest relative difference between the two
internal runs on any reported value is 1.4e-18, and on any time 5.3e-16 h.

## Timing

Wall time for both runs together, with 3 regimens in parallel on a 4-core Intel Mac:

- median 2.0 s, range 0.4 s (model_01) to 26.5 s (held_15), 135 s for all 28;
- the slowest single run is 16.5 s (held_15, Michaelis-Menten, 168 h period).

Step counts are in the table, with rejected radius-controlled steps in parentheses.

## Results

Reported values (theta = 1/4 run), rounded here to 10 digits; full precision is in out/<name>.json:

| regimen | cmax | t_cmax (h) | where | auc | ss cmax | ss cmin | ss trough | time_in_window (h) | n_cycles |
|---|---|---|---|---|---|---|---|---|---|
| held_01 | 2.757944224 | 336 | event (bolus) | 323.5497727 | 2.758119625 | 0.1100911827 | 0.1100911827 | 15.32662468 | 2 |
| held_02 | 11.99450889 | 44.19907918 | smooth max | 293.1228243 | 22.56784542 | 20.05270571 | 20.7463963 | 3.559526078 | 38 |
| held_03 | 26.76240511 | 67 | horizon end | 1023.568125 | 36.29860207 | 23.26485747 | 23.26485747 | 5.857726355 | 44 |
| held_04 | 44.84975615 | 58.25 | event (bolus) | 1447.047154 | 48.89193108 | 30.15820001 | 44.63288111 | 7.927655159 | 10 |
| held_05 | 9.296766044 | 50.25 | event (inf_end) | 340.1440733 | 9.682420249 | 7.400343049 | 7.400343049 | 1.658388042 | 7 |
| held_06 | 0.6501578934 | 106.1012717 | smooth max | 50.13737869 | 0.6846065967 | 0.3206250721 | 0.3670769401 | 8.577825788 | 19 |
| held_07 | 51.1925156 | 228.714383 | smooth max | 10067.48695 | 51.29715725 | 33.32281345 | 40.3399317 | 29.78822787 | 4 |
| held_08 | 43.23317285 | 6.5 | event (bolus) | 6549.440728 | 11.236602 | 3.486273488 | 3.486273488 | 110.6857859 | 9 |
| held_09 | 65.59618607 | 0.7 | event (inf_end) | 359.5083701 | 3.079875585 | 1.465838779 | 1.465838779 | 16.79540942 | 2 |
| held_10 | 40.66102502 | 102 | event (bolus) | 2585.163316 | 41.30790569 | 20.70758337 | 23.80151023 | 5.750849408 | 6 |
| held_11 | 1.404897 | 99.65278906 | smooth max | 44.57249388 | 1.4070499 | 0.0882480989 | 0.09080334098 | 6.781272874 | 3 |
| held_12 | 34.64990891 | 80 | event (bolus) | 217.8374342 | 34.67797751 | 1.873464902 | 3.264508429 | 0.4477570183 | 4 |
| held_13 | 1.404346363 | 51 | event (inf_end) | 35.93401036 | 1.404401982 | 0.05882234376 | 0.05882234376 | 7.175395182 | 2 |
| held_14 | 36.61181954 | 8.5 | event (bolus) | 165.777555 | 36.18705475 | 4.39072147e-06 | 4.39072147e-06 | 0.4112953641 | 2 |
| held_15 | 16.40047445 | 312.9263506 | smooth max | 245.1874447 | 16.40490614 | 0.009553983814 | 0.042783238 | 4.059793572 | 3 |
| held_16 | 13.26788556 | 38.15 | event (inf_end) | 425.1471997 | 13.39552807 | 11.45537193 | 12.02642581 | 1.989154216 | 5 |
| held_17 | 118.707118 | 3.4 | event (inf_end) | 933.0301537 | 77.14325196 | 1.718329219e-05 | 1.719717313e-05 | 0.6578177672 | 2 |
| held_18 | 9.988078141 | 54 | event (bolus) | 374.3279587 | 10.55618012 | 6.144587612 | 6.603404278 | 8.828287909 | 9 |
| held_19 | 15.31302821 | 29 | horizon end | 248.6307449 | 17.05013608 | 9.144589723 | 10.48873875 | 3.549624075 | 6 |
| held_20 | 25.34417703 | 28.75 | event (bolus) | 523.7829017 | 25.35942515 | 12.58763954 | 12.58763954 | 3.603201182 | 2 |
| held_21 | 35.07999267 | 29.55 | event (inf_end) | 584.7186435 | 0.8170974673 | 0.007343366306 | 0.007343366306 | 8.429680171 | 2 |
| held_22 | 13.99559354 | 54 | event (bolus) | 548.9212653 | 13.99576465 | 5.835624804 | 6.688142084 | 6.885853873 | 3 |
| model_01 | 67.66896015 | 3 | event (bolus) | 1575.204542 | 35.07248962 | 31.88470386 | 31.88470386 | 1.482486771 | 49 |
| model_02 | 4.5373087 | 339.0334969 | smooth max | 84.16676133 | 4.539523592 | 0.01443503801 | 0.01453146931 | 2.241003911 | 5 |
| model_03 | 5.668704629 | 110.15 | event (inf_end) | 285.0579493 | 6.323936747 | 2.058127289 | 2.674175548 | 14.26092109 | 19 |
| model_04 | 31.17715172 | 14.87074198 | smooth max | 234.635955 | 39.08821465 | 22.4837891 | 35.69097985 | 1.539241031 | 5 |
| model_05 | 46.42939385 | 33.96174488 | smooth max | 536.9014834 | 46.41214637 | 0.007054724079 | 0.01498104792 | 3.482437556 | 2 |
| model_06 | 25.67312014 | 96 | event (inf_end+inf_start) | 1798.964871 | 25.71652973 | 19.48225456 | 25.71652973 | 27.70089951 | 2 |

Internal error estimates (|theta=1/2 - theta=1/4|), the Newton residual, the cycles simulated directly, and timing:

| regimen | conc / S | auc rel | cmax / S | t_cmax (h) | ss conc / S | tiw (h) | troughs / trough | n_cycles | fixed-point residual | cycles simulated | steps fine (rejected) | wall s, both runs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| held_01 | 2.0e-19 | 1.7e-19 | 0.0e+00 | 0.0e+00 | 1.2e-20 | 8.7e-19 | 6.2e-19 | same | 0.0e+00 | 6 | 4036 (0) | 2.0 |
| held_02 | 2.2e-19 | 6.6e-19 | 2.2e-19 | 0.0e+00 | 2.9e-19 | 8.0e-18 | 5.0e-19 | same | 1.2e-19 | 61 | 5647 (0) | 2.8 |
| held_03 | 1.3e-19 | 1.6e-19 | 1.9e-19 | 0.0e+00 | 1.3e-19 | 0.0e+00 | 3.7e-19 | same | 3.7e-19 | 61 | 3671 (6) | 5.4 |
| held_04 | 3.5e-19 | 2.3e-19 | 7.7e-20 | 0.0e+00 | 4.6e-19 | 3.9e-18 | 3.1e-19 | same | 0.0e+00 | 33 | 1120 (0) | 1.8 |
| held_05 | 3.3e-19 | 8.2e-20 | 9.3e-20 | 0.0e+00 | 9.3e-20 | 3.3e-19 | 2.9e-19 | same | 6.0e-20 | 29 | 3989 (0) | 1.7 |
| held_06 | 2.5e-19 | 2.1e-19 | 1.7e-19 | 0.0e+00 | 2.5e-19 | 8.7e-18 | 6.6e-19 | same | 4.4e-20 | 61 | 7665 (96) | 11.3 |
| held_07 | 1.7e-19 | 6.2e-19 | 0.0e+00 | 1.4e-17 | 1.4e-19 | 1.7e-18 | 3.4e-19 | same | 7.1e-20 | 13 | 3025 (0) | 2.1 |
| held_08 | 8.4e-19 | 6.1e-19 | 8.0e-20 | 0.0e+00 | 1.1e-19 | 5.3e-16 | 1.0e-17 | same | 9.7e-20 | 25 | 47555 (0) | 21.4 |
| held_09 | 3.3e-21 | 9.3e-19 | 1.1e-19 | 0.0e+00 | 6.6e-21 | 3.5e-18 | 3.0e-19 | same | 0.0e+00 | 4 | 2860 (47) | 5.5 |
| held_10 | 2.6e-19 | 1.7e-19 | 1.7e-19 | 0.0e+00 | 8.5e-20 | 1.3e-18 | 3.6e-19 | same | 0.0e+00 | 20 | 1252 (0) | 0.7 |
| held_11 | 2.4e-20 | 0.0e+00 | 0.0e+00 | 6.9e-18 | 7.7e-20 | 2.2e-18 | 4.5e-19 | same | 0.0e+00 | 9 | 1562 (0) | 1.1 |
| held_12 | 1.3e-20 | 6.4e-19 | 0.0e+00 | 0.0e+00 | 1.9e-20 | 2.7e-20 | 4.0e-19 | same | 4.8e-20 | 14 | 4120 (71) | 8.4 |
| held_13 | 2.9e-20 | 7.7e-19 | 0.0e+00 | 0.0e+00 | 2.4e-21 | 1.7e-18 | 3.5e-19 | same | 0.0e+00 | 5 | 643 (13) | 1.3 |
| held_14 | 5.9e-21 | 6.7e-19 | 0.0e+00 | 0.0e+00 | 4.5e-26 | 2.7e-20 | 5.7e-19 | same | 0.0e+00 | 6 | 1217 (0) | 0.8 |
| held_15 | 2.3e-21 | 4.5e-19 | 3.2e-19 | 0.0e+00 | 1.1e-19 | 4.3e-19 | 6.3e-19 | same | 7.9e-20 | 10 | 13439 (396) | 26.5 |
| held_16 | 6.5e-20 | 2.0e-19 | 0.0e+00 | 0.0e+00 | 2.6e-19 | 2.4e-18 | 1.4e-19 | same | 9.0e-20 | 17 | 735 (0) | 0.6 |
| held_17 | 1.3e-20 | 1.2e-19 | 1.2e-19 | 0.0e+00 | 2.3e-19 | 1.1e-19 | 1.5e-18 | same | 0.0e+00 | 6 | 2701 (0) | 2.0 |
| held_18 | 4.3e-20 | 1.5e-19 | 8.7e-20 | 0.0e+00 | 8.7e-20 | 8.7e-19 | 2.6e-19 | same | 6.2e-20 | 32 | 1011 (0) | 2.1 |
| held_19 | 2.3e-19 | 1.7e-19 | 1.7e-19 | 0.0e+00 | 1.7e-19 | 1.1e-18 | 3.3e-19 | same | 1.0e-19 | 20 | 1096 (59) | 2.9 |
| held_20 | 6.8e-20 | 3.2e-19 | 6.8e-20 | 0.0e+00 | 3.4e-20 | 2.2e-19 | 2.8e-19 | same | 0.0e+00 | 6 | 761 (0) | 0.7 |
| held_21 | 4.9e-20 | 2.8e-19 | 9.9e-20 | 0.0e+00 | 2.4e-23 | 0.0e+00 | 2.3e-19 | same | 0.0e+00 | 3 | 963 (0) | 0.8 |
| held_22 | 1.9e-19 | 1.0e-19 | 6.2e-20 | 0.0e+00 | 6.2e-20 | 0.0e+00 | 2.6e-19 | same | 0.0e+00 | 7 | 721 (60) | 1.6 |
| model_01 | 1.0e-19 | 7.0e-20 | 0.0e+00 | 0.0e+00 | 6.7e-19 | 4.3e-18 | 1.1e-18 | same | 0.0e+00 | 61 | 812 (0) | 0.4 |
| model_02 | 2.1e-21 | 1.2e-18 | 0.0e+00 | 2.8e-17 | 3.7e-21 | 2.2e-19 | 1.1e-18 | same | 9.8e-20 | 22 | 9439 (0) | 4.0 |
| model_03 | 7.7e-20 | 9.7e-20 | 3.1e-19 | 0.0e+00 | 3.1e-19 | 3.5e-18 | 4.9e-19 | same | 6.9e-20 | 61 | 3352 (0) | 1.6 |
| model_04 | 3.3e-19 | 1.8e-19 | 3.9e-19 | 8.7e-19 | 1.4e-18 | 4.1e-18 | 1.6e-18 | same | 0.0e+00 | 16 | 3747 (0) | 6.8 |
| model_05 | 2.3e-21 | 9.3e-19 | 7.5e-20 | 3.5e-18 | 1.1e-22 | 4.3e-19 | 9.0e-19 | same | 0.0e+00 | 10 | 12711 (398) | 16.8 |
| model_06 | 6.1e-19 | 6.2e-19 | 3.4e-19 | 0.0e+00 | 3.4e-19 | 3.6e-17 | 3.4e-19 | same | 0.0e+00 | 6 | 4323 (0) | 1.7 |

Guarantee checks (values; thresholds G1 1e-3 h, G2 1e-4 and 1e-2, G3 1e-3, G4 1e-4):

| regimen | G1 min sep (h) | G2 1 - 2nd max/cmax | G2 1 - other post-bolus/cmax | G2 abs C''/cmax | G3 window vs ss cmin/cmax | G3 min abs dC/dt at crossing / ss cmax | G3 bolus pre/post vs window | G4 min margin m=1..60 | G4 all m>=60 inside | G5 ss cmin | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| held_01 | 0.9 | 1.53e-03 | 1.53e-03 | - | 6.96e-01 | 8.43e-03 | 6.96e-01 | 8.41e-03 (m=2) | yes | 0.11 | ok |
| held_02 | - | 1.14e-01 | - | 0.0997 | 1.99e-02 | 1.48e-02 | - | 2.16e-04 (m=38) | yes | 20.1 | ok |
| held_03 | - | 3.81e-02 | - | - | 8.12e-02 | 3.82e-02 | - | 1.75e-04 (m=43) | yes | 23.3 | ok |
| held_04 | 0.75 | 1.25e-03 | 1.25e-03 | - | 3.91e-02 | 3.61e-02 | 3.16e-02 | 8.74e-04 (m=9) | yes | 30.2 | ok |
| held_05 | - | 3.93e-02 | - | - | 1.65e-02 | 2.25e-02 | - | 1.99e-03 (m=7) | yes | 7.4 | ok |
| held_06 | - | 1.03e-02 | - | 0.0177 | 1.34e-01 | 3.18e-02 | - | 5.98e-04 (m=18) | yes | 0.321 | ok |
| held_07 | - | 5.09e-03 | - | 0.0129 | 7.45e-02 | 1.86e-02 | - | 3.25e-03 (m=4) | yes | 33.3 | ok |
| held_08 | 17.5 | 9.63e-02 | 4.63e-01 | - | 2.22e-01 | 1.80e-03 | 2.22e-01 | 1.94e-03 (m=9) | yes | 3.49 | ok |
| held_09 | - | 9.29e-01 | - | - | 5.91e-02 | 1.83e-02 | - | 9.69e-03 (m=2) | yes | 1.47 | ok |
| held_10 | 0.45 | 2.12e-02 | 2.12e-02 | - | 1.52e-01 | 2.65e-02 | 1.44e-02 | 3.84e-03 (m=6) | yes | 20.7 | ok |
| held_11 | - | 1.09e-02 | - | 0.287 | 2.18e-01 | 2.20e-02 | - | 6.58e-03 (m=3) | yes | 0.0882 | ok |
| held_12 | 0.5 | 2.33e-03 | 2.33e-03 | - | 1.67e-01 | 4.60e-01 | 1.67e-01 | 3.53e-03 (m=3) | yes | 1.87 | ok |
| held_13 | - | 1.03e-03 | - | - | 5.39e-01 | 4.12e-02 | - | 8.63e-03 (m=2) | yes | 0.0588 | ok |
| held_14 | 0.35 | 1.16e-02 | 1.16e-02 | - | 2.41e-01 | 6.12e-01 | 2.41e-01 | 1.00e-02 (m=2) | yes | 4.39e-06 | ok |
| held_15 | - | 2.12e-03 | - | 0.273 | 4.29e-01 | 1.49e-01 | - | 3.22e-03 (m=2) | yes | 0.00955 | ok |
| held_16 | - | 1.79e-02 | - | - | 3.52e-02 | 2.37e-02 | - | 1.67e-03 (m=5) | yes | 11.5 | ok |
| held_17 | - | 3.50e-01 | - | - | 1.59e-01 | 7.47e-01 | - | 9.20e-03 (m=1) | yes | 1.72e-05 | ok |
| held_18 | 0.2 | 3.77e-02 | 3.77e-02 | - | 5.76e-02 | 4.79e-02 | 2.78e-02 | 9.87e-04 (m=9) | yes | 6.14 | ok |
| held_19 | - | 7.65e-02 | - | - | 8.39e-02 | 6.83e-02 | - | 3.30e-03 (m=6) | yes | 9.14 | ok |
| held_20 | 0.1 | 9.32e-03 | 9.32e-03 | - | 1.23e-01 | 1.55e-01 | 2.01e-03 | 6.33e-03 (m=2) | yes | 12.6 | ok |
| held_21 | 4.85 | 4.31e-01 | 4.31e-01 | - | 6.89e-02 | 3.35e-02 | - | 9.91e-03 (m=2) | yes | 0.00734 | ok |
| held_22 | 1.5 | 1.51e-04 | 1.51e-04 | - | 4.84e-02 | 3.60e-02 | 1.76e-02 | 5.11e-03 (m=2) | yes | 5.84 | ok |
| model_01 | 0.6 | 3.95e-02 | 4.38e-02 | - | 3.31e-02 | 1.50e-02 | 3.31e-02 | 4.11e-04 (m=49) | yes | 31.9 | ok |
| model_02 | - | 7.52e-04 | - | 0.269 | 5.14e-01 | 1.11e-01 | - | 5.40e-04 (m=5) | yes | 0.0144 | ok |
| model_03 | - | 3.12e-02 | - | - | 6.48e-02 | 2.66e-02 | - | 2.37e-04 (m=18) | yes | 2.06 | ok |
| model_04 | - | 4.27e-01 | - | 0.116 | 1.41e-01 | 1.43e-01 | - | 3.52e-03 (m=5) | yes | 22.5 | ok |
| model_05 | 2.4 | 3.34e-04 | 8.37e-02 | 1.05 | 4.55e-01 | 1.58e-01 | 2.19e-01 | 5.53e-03 (m=2) | yes | 0.00705 | ok |
| model_06 | - | 3.93e-02 | - | - | 4.16e-02 | 6.71e-03 | - | 8.31e-03 (m=2) | yes | 19.5 | ok |

## Guarantee violations

None. All 28 regimens satisfy G1 to G5 under my checks, and none violates the section 2/3 domain.

Tightest margins, as values against thresholds:

- **G2, second local maximum.** held_22: the post-bolus value at t = 42 is 1.51e-4 below the
  global maximum, the post-bolus value at t = 54 (threshold 1e-4).
- **G2, curvature at a smooth maximum.** held_07 0.0129, held_06 0.0177 (threshold 0.01).
- **G3, slope at a crossing.** held_08 1.80e-3 x ss cmax (threshold 1e-3).
- **G3, bolus values against the window.** held_20 2.0e-3 (threshold 1e-3).
- **G4, trough margin.** held_03 1.75e-4 at m = 43; held_02 2.16e-4 at m = 38; model_03 2.37e-4
  at m = 18 (threshold 1e-4).

## Spec ambiguities and the interpretations used

- **A1. Steady-state cmin with IV boluses.** On [0, P) the smallest concentration just before a
  bolus is a left limit and is never attained, so "smallest concentration" has no minimum. I
  report the infimum, including pre-bolus left limits and C(P-). With a bolus at offset 0,
  the trough C(P-) is one of the candidates. cmin is lower only where another pre-bolus value
  or an interior minimum is lower: held_10, held_18 and model_05 have cmin < trough. cmax is
  attained, post-bolus values included.
- **A2. "Strictly inside a dose-free interval" (G2 curvature).** I read it as an open interval
  that contains no dose event at all: no bolus, oral arrival, or infusion start or end. A smooth
  maximum while an infusion is running counts as inside. For every smooth global maximum I
  report |C''| / cmax; all are >= 0.0129.
- **A3. G2 "post-bolus values".** I count every post-bolus value as a local maximum, even when C
  keeps rising after the bolus (infusion or absorption running). That is the stricter reading,
  and no regimen fails it.
- **A4. G3 "1e-3 relative" and "1e-3 cmax".** The spec does not say what the relative differences
  are relative to. I take |low - c| / low and |high - c| / high, for c the steady-state cmin and
  cmax and for the pre-bolus and post-bolus values. In the slope condition, "cmax" could be the
  report cmax or the steady-state cmax. I use the steady-state cmax, which is the G3 context;
  the horizon-cmax version is also in the check files. No regimen comes near either reading's
  threshold.
- **A5. Lag arrivals in the periodic solution.** A maintenance oral dose with
  offset + tlag >= period arrives in the next cycle's window. In the periodic solution, with
  maintenance continued indefinitely, the window [0, P) therefore receives the arrival from the
  previous cycle. In the actual regimen, cycle 0's arrival falls in cycle 1. Infusions that
  outlast the period overlap later cycles in the same way. The spec implies this but does not
  say it.
- **A6. Numbers.** Times are taken as their decimal values (exact rationals) and parameters as
  doubles. The difference is about 1e-16 h and does not affect any value at tolerance level.
- **A7. Window endpoints.** Whether the window is closed or open does not change
  time_in_window; crossings are transversal by G3.
- **A8. Steady-state trough equal to the steady-state cmax.** model_06 has two back-to-back 24 h
  infusions per 48 h period. Its period ends exactly at the kink where the larger infusion stops
  and the smaller one starts. So the "trough" C(P-) equals the steady-state cmax, 25.7165 mg/L.
  That is correct under the spec's definition but counter-intuitive; worth knowing when
  reading solver disagreements.

Two regimens attain cmax at the closed end of the horizon, with C still rising: held_03 at
t = 67 and held_19 at t = 29. A solver that ignores the closed end would get them wrong.

## Development note: Michaelis-Menten series radius

My first version used a fixed Michaelis-Menten step h <= 0.5 V1 Km / Vmax. That bound is valid
only for pure elimination, where the singularity sits at distance >= pi V1 Km / Vmax. It
diverged or lost accuracy as soon as a large lagged oral dose, or an infusion, arrived while
C << Km. The step-halving comparison caught it: differences of 4e7 in held_09, 5e-8 in held_22
and 2e-13 in held_19, a singular Newton matrix in model_05, and an overflow in held_15. Every
other regimen already agreed to 1e-17. The radius-controlled version above fixes all of them.
Any fixed-step high-order or series-based solver of this model, legacy script or candidate
solution, is exposed to the same failure.

## External QA (outside Reference B)

As a sanity check of my own reading of the model, I wrote a throwaway script in the scratchpad.
It is not part of refB and is not a reference.

- It uses scipy DOP853 at rtol 1e-13 with restarts at events, written straight from the spec
  equations.
- The steady state comes from brute-force simulation of the maintenance regimen alone until the
  cycle-start state converges to 1e-14; no fixed-point solve.
- Extrema are polished with brentq on the RHS-derived dC/dt, and crossings with brentq on C.

Result over all 28: n_cycles_to_steady identical in all 28. Worst QA-versus-refB differences:

- concentrations 1.1e-11 S (model_06)
- auc 2.0e-14 relative (held_15)
- cmax 1.1e-13 S (held_11)
- t_cmax 5.5e-13 h (held_11)
- steady-state cmax / cmin / trough 1.3e-13 S (held_02)
- time_in_window 6.3e-10 h (model_06)

These are the QA's own DOP853 global errors over long infusion pieces and slowly converging
cycles; refB's half-step estimates there are 1e-18. The value of the QA is semantic: an
independent reading of the equations, the lag and transit chain, the infusion overlap, the
periodic carry-over, the left-limit troughs and the n_cycles definition agrees with refB on
every quantity of every regimen. That reading includes a brute-force steady state from up to
315 cycles of plain simulation.
