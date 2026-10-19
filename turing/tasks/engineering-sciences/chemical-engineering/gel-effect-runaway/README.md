# gel-effect-runaway

Infer how propagation and termination become diffusion controlled in bulk MMA free-radical
polymerization (the gel and glass effects; their laws are stated, their seven constants are
not) from self-heating ampoule conversion and polystyrene-calibrated GPC data. Then predict
the mid-plane exotherms, conversion, molar masses and molar-mass distributions of thick PMMA
sheet castings through cure and post-cure, and design a fast cure program for a 20 mm sheet
that stays clear of thermal runaway and bubble formation.

| | |
|---|---|
| Domain | engineering-sciences / chemical-engineering / polymer-reaction-engineering |
| Agent budget | 18000 s; 2 CPUs, 2 GB RAM, open internet |
| Verifier | separate container, no network, binary reward |

[instruction.md](instruction.md) is the task as the agent receives it and [task.toml](task.toml)
the configuration. `tests/plant.py` is the data-generating model itself; its slab equations are
built by `slab_system()`, which `simulate_slab()` and the verifier's continuous-time cure run
share. The script that sampled the data and the author-side comparator fits are not part of the
package.

## Difficulty

PMMA sheet is made by casting bulk methyl methacrylate between cell walls in a water bath.
Past roughly 20-35 % conversion termination slows by orders of magnitude (the
Trommsdorff-Norrish gel effect). Near the glass transition, propagation and initiator
efficiency fall too, and above about 100 C the propagation equilibrium caps conversion. The
published rate constants are chemically controlled values; in the data-generating model `kt` is
already 5-20 % below its published value at a few percent conversion, and far below it in the
gel regime.

The instruction states the free volume of the mixture, the separately measured cage effect on
the initiator efficiency (as a table), and the gel-effect law for `kt` and the glass-effect law
for `kp` in closed form. It does not give the seven constants of those two laws. The agent has
to infer them from seven self-heating ampoule runs (50-70 C, three initiator loadings; 81
gravimetric conversion points and 28 GPC points, 137 residuals) and carry the fitted model into
a thick casting with a population balance, shrinkage and transient conduction. Several
realistic features break the usual shortcuts:

- The ampoules self-heat by 1.3-9.6 K; fitting them as isothermal fails the castings.
- The GPC averages are polystyrene-equivalent, 10-15 % below the absolute values, and were
  computed slice by slice; taking them as absolute fails every molar mass.
- The data are sparse where the gel effect is fastest.
- The castings are conduction-limited: the mid-plane runs 7.5-19.6 K above the bath, against
  1.4-3.3 K for a lumped model.
- The castings extrapolate beyond the calibration. C1 has a lower initiator loading than any
  ampoule, so its gel onset falls at a different cumulative Mw; a fit without the chain-length
  term of the gel onset misplaces C1's `t80_min` by 8-10 % against a 6 % band. C3 is post-cured
  at 120 C, where depropagation sets the residual monomer and the initiator left after 960 min
  at 45 C sets `Mn`. C1 and C4 (60 C) sit just below runaway: with the bath 1 K hotter their
  mid-plane excess already leaves its band (16.0 -> 20.6 K, 19.6 -> 33.7 K), 2-3 K hotter
  they run away to 70-90 K. A model slightly too reactive at 60 C predicts a runaway that does
  not happen.
- Each casting's molar-mass distribution is graded bin by bin and must be accumulated from
  instantaneous chain-length distributions; a Schulz-Zimm or log-normal shape with the exact
  `Mn` and `Mw` fails every casting (L1 0.067-0.298 against 0.05).

The agent must also design a bath program for a 20 mm sheet (D1) with at most four points that
finishes within 670 min, keeps every layer below 90 % conversion at or under 95 C, and ends at a
mass-average conversion of at least 0.975. Held at a constant bath temperature, the sheet runs
away above about 48.3 C: the mid-plane peaks at 72 C at 48.0 C but at 148 C at 49 C. The
fastest safe hold-and-ramp program holds within about 1.1 K below that boundary (a hold at
47.0 C already needs 682 min), and each kelvin of caution costs about 75 min. Four-point
warm-start programs that cool through the gel effect exist but end within 0.0023 of the target
and run away when shifted 0.4 K. The program is run in the data-generating model, so a design
pushed to the edge of the agent's own model fails if that model misplaces the boundary by the
0.3-0.8 K that fitted comparators typically do.

In platform runs of earlier revisions (one attempt per model), two frontier agents reached
reward 0 on the same physics: C1 `t80_min` +9.6 %, C1 peak time +14 to +17 %, C3 `Mn` x1.18
and x0.82, distributions at L1 0.06-0.25, and D1 programs that either ran away in the plant
(162.7 C) or needed seven points. Both had fitted gel laws without a chain-length dependence.

The data are synthetic. They come from a free-volume diffusion-control model (Marten-Hamielec
style chain-length-dependent gel onset, reaction-diffusion floor, glass and cage effects,
depropagation) with nine constants chosen to reproduce AIBN-initiated bulk MMA, plus gravimetric
and GPC-scale noise. Polymer reaction engineers do this when designing cure cycles for cast
acrylic sheet.

## Reference solution

`solution/solve.py` keeps every published constant and the free volume as instruction.md states
them. For the cage effect it fits the two-parameter logistic `f/f0 = 1/(1 + exp(B_f (1/V_f -
1/V_ff)))` to the published 100-node table by least squares; the residual is the table's
6-decimal rounding (below 5e-7 at every node) and every start gives `B_f` = 0.499999,
`V_ff` = 0.0350000. A smooth law is used instead of `np.interp` because the piecewise-linear
interpolant has a derivative kink at every node and costs LSODA about 3.6 times the steps per
slab run.

For `kp` and `kt` it implements the laws instruction.md states: a logistic switch in `kt` whose
onset depends on free volume, cumulative `Mw` and temperature, with a reaction-diffusion floor
proportional to `kp[M]`; a logistic critical-free-volume switch for `kp`; and net propagation
`kp([M] - [M]_eq)` with the published ceiling equilibrium. The seven constants are fitted by
weighted least squares to all conversion points (scale 0.01) and to log `Mn` and log `Mw`
(scale 0.05), each ampoule being a well-mixed vessel that loses heat through its stated `UA`.

The polystyrene-equivalent GPC averages are modelled the way the instruction says the GPC
computed them, slice by slice. With `M_PS = C M^b`, `b = (1 + a_PMMA)/(1 + a_PS)`, the slice
sums `sum(W M_PS)` and `sum(W / M_PS)` are fractional moments of order `+b` and `-b` of the
gamma-shaped instantaneous distributions, which are closed-form and are integrated over time
alongside the dead-polymer production. At the hidden constants this agrees with the fine-binned
slice calculation of `tests/plant.py` to within 0.1 % at every GPC point.

The fit starts from a 2 x 2 x 2 design over the gel-onset constants (`A_t` in {2, 5}, `V_ft` in
{0.155, 0.170}, `E_t` in {-2000, -8000} K) combined with each of two generic settings of the
other four (`m` 0.3 or 1.0, `C_rd` 300 or 50 L/mol, `B_p` 0.7 or 1.5, `V_fp` 0.025 or 0.020).
No start value is a data-generating value. The best start of each setting is refined by bounded
least squares (bounds `LOWER`/`UPPER`; none binds) and the first fit within 0.05 of the best
cost is kept, so the choice does not turn on trailing digits that vary between hosts (BLAS is
pinned to one thread for the same reason). Both settings reach `A_t` = 3.04, `V_ft` = 0.1638,
`m` = 0.524, `E_t` = -6140 K, `C_rd` = 106 L/mol, `B_p` = 4.49, `V_fp` = 0.0265 at cost 43.64
(45.29 at the data-generating constants: 3.0, 0.164, 0.5, -6000 K, 100 L/mol, 1.0, 0.028).
`B_p`, the steepness of the glass effect, is the loosely determined constant; a profile over it
(the other six refitted at each fixed `B_p`) passes every casting band down to `B_p` = 0.5 and
first fails C3's `Mn` at `B_p` = 0.45, where the cost is 1.91 above the best fit, at the edge of
the 95 % single-parameter interval.

Why the cage effect is published rather than fitted: with all nine constants free, the ampoules
cannot separate the glass switch on `kp` from the cage switch on `f`, because both act near the
limiting conversion at 50-70 C, and the nine-constant fit has several minima of similar cost
that disagree about C3, whose 120 C post-cure starts new chains from the remaining AIBN:

| Nine-constant fit | Cost | C3 `Mn` / truth | C3 distribution L1 | C3 verdict |
|---|---|---|---|---|
| lowest found | 41.01 | 0.54 | 0.090 | fail |
| another minimum | 42.52 | 1.03 | 0.021 | pass |
| glass effect off (`B_p` = -30, `V_fp` < 0) | 45.27 | 0.60 | 0.026 | fail |
| data-generating constants | 45.29 | 1.00 | 0.000 | pass |

With the cage effect published, every converged seven-constant fit from the starts above
reaches the same constants. The ampoules constrain every term of the stated laws; the same fit
with one term removed:

| `kp`/`kt` law | Fit cost (137 residuals) | Castings |
|---|---|---|
| reference: gel onset with chain length and temperature, reaction diffusion, glass effect | 43.6 | pass, worst quantity 0.73 of its band |
| no chain-length term in the gel onset | 113 | fail (C1 `t80_min` +8.5 %, `X_avg_t1` 0.016) |
| no temperature term in the gel onset | 327 | fail (3 checks) |
| neither (plain free-volume switch) | 327 | fail (4 checks) |
| no reaction-diffusion floor | 4868 | fail (35 checks) |
| plain switch and no reaction diffusion | 6554 | fail (C1 never reaches 80 % conversion) |

Each casting is a symmetric slab of 30 finite volumes in a mass coordinate (each volume keeps
its monomer mass and shrinks with its density), with composition-dependent conductivity and
convective walls to the programmed bath, integrated by LSODA at rtol 1e-7 on a 10 s grid. The
molar-mass distribution is accumulated from instantaneous chain-length distributions: geometric
live radicals with depropagation in the radical balance, weight ~ n q^n from disproportionation
and transfer, ~ n^2 q^n from combination.

For D1 the solution minimizes the cycle time over a hold, ramp at 1 K/min, post-cure family
(three parameters; at most the four points `design.json` allows) in its own model, coarse to
fine: Nelder-Mead on 10 volumes from two safe starts in parallel, then on 30 volumes the
earliest ramp start that keeps the margined bubble limit, by bisection to 1 min. Design runs
stop at the margined target and abort as a runaway when a layer below the bubble conversion is
10 K above the limit, so no candidate drags the stiff solver through a runaway. Two margins
protect the design on the true system: the program must also keep the bubble limit with the
bath 1 K hotter (an error of that size in the model's runaway boundary, about 10 % in its
gel-effect timing), and the target carries +0.005 (the model's late-conversion error; with
+0.002 the plant ended only 0.0004 above the target because the post-cure is still converting
about 0.001 per minute). Neither margin is tuned to the truth: two independent comparators pass
with the same 1 K margin and fail without it (Verification). No random seed is used.

| Oracle run (Harbor, `harbor run -a oracle`, agent image from `environment/` with 2 CPUs and 2 GB, verifier image from `tests/` with no network) | Result |
|---|---|
| Fit | `A_t` 3.04, `V_ft` 0.1638, `m` 0.524, `E_t` -6140 K, `C_rd` 106 L/mol, `B_p` 4.49, `V_fp` 0.0265; cost 43.64 |
| Castings, worst over C1-C4 | `t80_min` 1.5 % (band 6 %), peak time 1.2 % (12 %), `dT_mid_max_K` 0.38 of its band, `X_avg_t1` 0.0012 (0.010), `X_avg_end` 0.0032 (0.006), molar-mass factor 1.072 (1.10), distribution L1 0.017 (0.05) |
| D1 program | `[[0, 47.607], [584.72, 47.607], [648.33, 111.22]]`: hold 47.61 C, ramp at 1 K/min from 584.7 min, end on the ramp at 648.3 min |
| D1 in the plant | hottest under-converted layer 92.86 C (continuous time, 80 volumes), final mass-average conversion 0.9791, 21.7 min under the cycle limit |
| Harbor trial | reward 1, all four tests passed (CTRF: 4 passed, 0 failed, 0 skipped); 15 min 43 s end to end on an Intel Mac host (Colima VM, 3 vCPU, agent container capped at 2 CPUs and 2 GB), of which pytest in the verifier took 5.9 s |

## Verification

`tests/test.sh` runs with `set -euo pipefail` and is the only writer of
`/logs/verifier/reward.txt`. It writes `0` before anything else, so a crash at any later point
still leaves a valid binary result. It then checks that the verifier files exist and that
`truth/expected.json`, `truth/design.json` and `plant.py` match `truth/SHA256SUMS.txt`, runs
pytest with a CTRF report, and has `tests/decide.py` confirm that the report lists exactly the
four tests below, none skipped, consistent with the exit status. Only then does it write `1`.
An infrastructure error (missing file, hash mismatch, pytest exit other than 0 or 1, rejected
report) leaves the reward at 0 and exits 2. pytest 8.4.1, pytest-json-ctrf 0.3.5, numpy and
scipy are baked into `tests/Dockerfile` at the agent image's versions.

| Test | What it checks |
|---|---|
| `test_castings_conversion_and_exotherm` | exact schema of `/root/results/predictions.json` (prerequisite), then `t80_min`, `dT_mid_max_K`, `t_dT_mid_max_min`, `X_avg_t1`, `X_avg_end` of each casting against `tests/truth/expected.json` |
| `test_castings_molar_masses` | the schema prerequisite, then the four cumulative molar masses of each casting |
| `test_castings_mwd_fractions` | the schema prerequisite, then the binned distribution of each casting (L1) |
| `test_cure_program_in_plant` | exact schema of `/root/results/cure_program.json` and the program limits in `design.json` (prerequisite; an invalid program is never run), then the program run through `tests/plant.py`: bubble limit in continuous time, target conversion |

A well-formed file passes no test by itself: the schema checks are prerequisites of the physics
tests, so a malformed `predictions.json` fails three tests and a malformed program one. Extra or
missing keys, unknown or duplicate ids, non-finite or non-numeric values, a malformed
distribution and a missing or unreadable file all fail. Every inequality is evaluated exactly in
double precision, as instruction.md says: a value on a bound passes, one past it by any amount
fails. The reference solution therefore builds its 1 K/min ramp a fraction 1e-9 longer than
`|dT|/ramp` so its slope never depends on the last bit of the arithmetic.

| Casting quantity | Acceptance band |
|---|---|
| `t80_min` | within 6 % relative error of the reference |
| `t_dT_mid_max_min` | within 12 % relative error of the reference |
| `dT_mid_max_K` | absolute error at most max(1.5 K, 25 % of the reference) |
| `X_avg_t1` | absolute error at most 0.010 |
| `X_avg_end` | absolute error at most 0.006 |
| `Mn_avg_end_g_per_mol`, `Mw_avg_end_g_per_mol`, `Mw_inner_end_g_per_mol`, `Mw_outer_end_g_per_mol` | within a multiplicative factor of 1.10 |
| `mwd_weight_fractions` | sum over the 16 bins of the absolute difference at most 0.05 |

### The truth

`tests/truth/expected.json` is reproducible from the package with the pinned numpy and scipy
with zero deviation: for each casting in `castings.json`, run `plant.simulate_slab` with 40
volumes on the grid `t = linspace(0, 60 t_end_min, round(6 t_end_min) + 1)` s. `t80_min` is the
linear interpolation of `X_avg` between the two samples that bracket 0.80; `dT_mid_max_K` and
`t_dT_mid_max_min` come from the first maximum of `T_mid` minus the bath on that grid;
`X_avg_t1` is interpolated at `t1_min`; the end values are the last sample; the inner and outer
`Mw` use `outer_frac` = 0.10; the distribution is `plant.cumulative_mwd` over the run, divided
by its sum. Changing 40 volumes to 20 or the 10 s grid to 60 s moves the distributions by
L1 0.0035 and the scalars by far less than their bands.

### The plant run

The cure program runs in `tests/plant.py` with 80 finite volumes per half-thickness.
`run_plant()` in `tests/test_state.py` integrates it step by step with LSODA at rtol 1e-7 and
exactly the settings of `plant.simulate_slab` (steps of at most 10 s) and enforces the bubble
limit in continuous time on the integrator's dense output, not at output samples. For each
layer, `g(t) = min(T - 95 C, 100 K * (0.90 - X))` is positive exactly when the layer is below
the bubble conversion and hotter than the bubble temperature. Each step's dense output is
sampled at 17 equally spaced times; around every sampled local maximum of `g` within 2 K of
zero, a bounded Brent search (time resolution 1e-4 s) locates the maximum of `g`. Any `g > 0`
anywhere in `[0, cycle time]` fails the program, resolved to about 1e-5 K. Sampling 257 points
per step instead of 17 moves the located maximum by less than 0.001 K, and an independent
1025-point check agrees on 9 of 9 programs, one of them 0.0001 K below the limit.

The continuous check matters because the hottest under-converted temperature usually falls at
the instant a layer passes 0.90 conversion while still heating, between fixed samples; on the
programs tested it reads up to 0.25 K above the 10 s sampled maximum. The program
`[[0, 48.332656], [495.1, 48.332656], [554.5, 107.732656]]` passes a 10 s sampled check
(94.974 C) and fails the continuous one (layer 28 reaches 95.002 C at conversion 0.89993 at
500.04 min).

Spatial resolution is converged: hottest under-converted layer on 24, 40, 80 and 160 volumes
for the no-margin hold-and-ramp optimum is 94.353, 94.119, 94.019 and 93.994 C, and for the
reference solution's program 92.553, 92.564, 92.568 and 92.571 C. Coarser grids are not
one-sided (they overstate the mid-plane and understate the wall layers), which is why the
reference solution decides its ramp timing on 30 volumes rather than with a wider margin. A
670 min program runs in 5-9 s.

### How the bands were chosen

Each comparator reads only the agent-visible inputs, fits its own kinetics, predicts every
casting including the distribution, and is graded by the verifier's `score()`. Worst errors
over the four castings:

| Comparator | What differs | Fit cost | `t80` (6 %) | Peak time (12 %) | `dT` (fraction of band) | `X_avg_t1` (0.010) | `X_avg_end` (0.006) | Molar-mass factor (1.10) | L1 (0.05) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| `oracle` | `solution/solve.py` | 43.64 | 1.5 % | 1.2 % | 0.38 | 0.0012 | 0.0032 | 1.072 | 0.017 | pass |
| `fv_chain` | reference family, earlier nine-constant fit | 45 | 1.4 % | 1.2 % | 0.41 | 0.0019 | 0.0021 | 1.046 | 0.019 | pass |
| `marten_ham_pubf` | independent: Marten-Hamielec onset as a per-layer event (chain length and temperature), power-law and exponential post-onset termination, reaction-diffusion term, exponential glass effect, five constants fitted; published cage effect | 127.4 | 4.1 % | 7.8 % | 0.71 | 0.0029 | 0.0010 | 1.051 | 0.042 | pass |
| `marten_ham_pubf`, worse minimum | the same model at the lowest minimum a cold 54-start search reached | 187.1 | 8.0 % | 10.2 % | 1.47 | 0.0061 | 0.0122 | 1.348 | 0.075 | fail |
| `marten_ham` | as above with its own cage effect fitted (six constants) | 127.0 | 3.9 % | 7.8 % | 0.71 | 0.0028 | 0.0016 | 1.068 | 0.035 | pass |
| `coarse_grid` | `fv_chain` on 5 volumes | - | 0.9 % | 1.2 % | 0.34 | 0.0015 | 0.0021 | 1.040 | 0.018 | pass |
| `isothermal_amp` | ampoules fitted as isothermal | 210 | 9.4 % | 6.2 % | 1.27 | 0.0041 | 0.0023 | 5.079 | 0.131 | fail |
| `ps_as_absolute` | GPC values taken as absolute | 93 | 2.3 % | 1.4 % | 0.26 | 0.0070 | 0.0033 | 6.582 | 0.134 | fail |
| `no_deprop` | no depropagation | 45 | 1.3 % | 1.4 % | 0.39 | 0.0019 | 0.0146 | 1.220 | 0.032 | fail |
| `lumped_casting` | each casting one well-mixed lump | - | 19.1 % | 61.2 % | 3.45 | 0.0592 | 0.0102 | 1.612 | 0.263 | fail |
| `classical` | no diffusion control | 52426 | never 80 % | 92.1 % | 12.36 | 0.6099 | 0.5899 | 15.050 | 1.130 | fail |
| `no_chain` | `oracle` without the chain-length term in the gel onset | 113 | 8.5 % | 11.4 % | 0.36 | 0.0160 | 0.0028 | 1.053 | 0.031 | fail |
| `no_Et` | `oracle` without the temperature term in the gel onset | 327 | 10.2 % | 14.5 % | 0.998 | 0.0188 | 0.0028 | 1.131 | 0.043 | fail |
| `no_rd` | `oracle` without the reaction-diffusion floor | 4868 | 10.5 % | 29.2 % | 44.24 | 0.1116 | 0.0931 | 62.8 | 0.684 | fail |

The bands are set so that the correct models pass with margin and every wrong-physics model
fails on at least one quantity. The independent model `marten_ham_pubf` (a structurally
different diffusion-control law fitted to the same data, with none of the reference points of
the stated laws) is the binding case: distribution 0.042 against 0.05, `dT` at 0.71 of its band,
`t80` 4.1 % against 6 %, C3 peak time 7.8 % against 12 % (C3's 45 C bath lies below the
calibrated range, which is why that band is wider). A distribution band of 0.045 would leave it
at 0.93 and 0.04 would fail it. The `X_avg_t1` and molar-mass bands leave every correct model at
or below 0.29 and 0.73 of the band. Shape shortcuts fail on their own: a Schulz-Zimm
distribution with the exact `Mn` and `Mw` gives L1 0.067-0.121 and a log-normal 0.149-0.298;
ignoring depropagation only in the distribution costs at most 0.016.

### How the D1 limits were chosen

In the data-generating model a single hold followed by the fastest 1 K/min ramp, with the ramp
started at the earliest instant that keeps the bubble limit and no margin at all, needs 718 min
at 46.5 C, 682 at 47.0, 664 at 47.25, 645 at 47.5, 624 at 47.75 and 597 at 48.0 C, and holds
above 48.33 C run away. The 670 min limit therefore excludes holds at or below about 47.2 C and
leaves about 18 min above the slowest correct design on record; a model that places the runaway
boundary too low fails on time instead of passing with a cold hold. `max_points` = 4 removes
the seven-point warm-start-and-chill family, which looks conservative in a sampled check only
because the bubble criterion stops counting layers once they pass 0.90 conversion; of nine
neighbours of such a program, six ran away to 130-165 C. A scan of 358 four-point programs
outside the hold-and-ramp family found seven that pass, all using the whole 670 min, ending
0.0005-0.0023 above the target and running away when shifted 0.4 K. A shorter limit near
400 min was evaluated and rejected: it would force hot-start programs, which are safe only in a
two-sided window about 1 K wide that the constant-temperature ampoules cannot locate, so correct
fits fail from both sides.

Each comparator designed a program in its own fitted model with the same optimiser and margins
as the reference solution, graded by `program_errors()` and `plant_errors()` at full precision:

| Model (margins) | Program, rounded, [min, C] | Hottest under-converted layer in the plant | `X_avg` at the end | Verdict |
|---|---|---|---|---|
| reference solution (target +0.005, bath +1 K) | [0, 47.607], [584.72, 47.607], [648.33, 111.22] | 92.86 C | 0.9791 | pass |
| `marten_ham_pubf` (target +0.005, bath +1 K) | [0, 47.88], [561.4, 47.88], [620.6, 107.09], [626.3, 107.09] | 92.97 C | 0.9798 | pass |
| `marten_ham` (target +0.002, bath +1 K) | [0, 47.87], [559.4, 47.87], [621.5, 109.97] | 93.57 C | 0.9773 | pass |
| `fv_chain` (target +0.002, bath +1 K; two-slope ramp collapsed to one) | [0, 47.65], [588.22, 47.65], [651.2, 110.63], [651.67, 110.63] | 91.6 C | 0.9792 | pass |
| `fv_chain` (no bath margin) | [0, 48.6], [481.15, 48.6], [542.5, 109.95] | 134.11 C (runaway) | 0.9695 | fail |
| `marten_ham` (no bath margin) | [0, 48.73], [464.89, 48.73], [524.83, 108.67] | 150.04 C (runaway) | 0.9300 | fail |
| `isothermal_amp` | [0, 47.05], [615.43, 47.05], [673.97, 105.59], [682.33, 105.59] | 95.60 C (outer layer during the ramp) | 0.9789 | fail (also over the cycle limit) |
| `lumped_casting` | [0, 68.37], [137.66, 68.37], [178.67, 109.37] | 158.86 C (runaway) | 0.7358 | fail |

The correct models pass with the 1 K bath margin and fail without it; the two fitted
comparators put the runaway boundary 0.3 K and 0.4 K too high (no-margin holds at 48.6 and
48.73 C against 48.33 C).

### Nulls and self-test

| Trivial null | Result |
|---|---|
| nearest ampoule run as the casting, `dT` of 0 or 10 K, Schulz-Zimm distribution | fail 6-10 of the 10 checks on every casting |
| D1: C3's schedule cut at the cycle limit | `X_avg` 0.666 |
| D1: C3's schedule compressed to the cycle limit | runaway to 150 C, `X_avg` 0.933 |
| D1: 60 C hold | runaway to 164 C |
| D1: 130 C from the start | runaway to 164 C, `X_avg` 0.115 |
| D1: 40 C hold | `X_avg` 0.209 |

An author-side self-test of 80 cases gave the intended verdict in every case: the exact truth,
values at 0.95 and 1.05 of each band for every quantity, unit mistakes, malformed files and
schemas, malformed distributions, invalid programs (point count, first time, ordering, range,
ramp rate, cycle time), and plant runs of the hold-and-ramp optimum (pass), a 130 C hold and a
40 C hold (both fail), the reference optimum cut 1 min short, and the between-sample excursion
above. `solution/solve.py` does not read `tests/` and embeds no truth; its only constants beyond
`properties.json` are the two it fits to the published cage-effect table.

| Package checks | Result |
|---|---|
| `harbor run -a oracle` | reward 1, 4 of 4 tests passed, 15 min 43 s trial; two independent oracle runs gave byte-identical `predictions.json` and `cure_program.json` (SHA-256 a2919b6c... and 76d8de52...) |
| `harbor run -a nop` (no output files) | reward 0, all four tests fail on the contract prerequisite, `test.sh` exit 0; 50 s trial |
| `tests/truth/SHA256SUMS.txt` against `expected.json`, `design.json`, `plant.py` | all three match |
| `plant.py` or `expected.json` altered after the build | reward 0, `test.sh` exit 2 ("truth or plant model does not match its recorded hash") |
| valid predictions, 5-point program | the plant test fails on the program limits (not run in the plant), the three casting tests pass; reward 0 |
| `predictions.json` missing one key, valid program | the three casting tests fail on the contract prerequisite, the plant test passes; reward 0 |
