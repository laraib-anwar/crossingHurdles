# dosing-regimen-audit

Compute the exact plasma concentration-time course of multi-dose regimens in mammillary
compartment models with linear and Michaelis-Menten elimination, oral absorption through lag
times and transit chains, IV boluses and overlapping IV infusions: concentrations at query times,
AUC and peak over the horizon, the periodic steady state of the maintenance cycle (peak, minimum,
trough, time inside a therapeutic window) and the number of cycles until every later trough is
within 1 % of the steady-state trough. Then diagnose a legacy superposition regimen calculator by
executable witnesses.

| | |
| --- | --- |
| Domain | life-sciences / pharmacology / pharmacokinetics |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Regimen design is daily clinical-pharmacology work, and the model is the standard one: a
mammillary compartment system with a saturable elimination term, first-order absorption behind a
lag and a transit chain, bolus, infusion and oral inputs. The spec states the model and the
definitions and no method.

What a competent solver gets right: a time course by `solve_ivp` with the doses added as jumps,
and the peak by inspection. Where the difficulty is, each exercised by several of the 28
regimens:

1. **Exactness through hundreds of events.** Concentrations are graded to `1e-8` of the peak,
   AUC to `1e-8` relative. A regimen has up to six doses per cycle, loading doses, lag arrivals
   and infusion ends, all of which are kinks or jumps of the right-hand side; an integrator that
   steps across them, or one at default tolerance (`loose_rtol` control, `rtol = 1e-6`), fails
   13 of the 28 regimens. The integration must restart exactly at every event and run at near
   machine precision over up to 60 cycles, and reported values must come from the integrator's
   accepted steps, not from a dense-output interpolant (that alone costs `1e-9` of the peak).
2. **The periodic steady state is not "cycle 20".** With saturable elimination there is no
   accumulation factor, and with slow accumulation (`model_01`, `held_02`, `held_03`:
   `n_cycles_to_steady` 38 to 49) the 20th cycle is still percent-level away from the periodic
   solution (`ss_iterate20` control). The steady state is the fixed point of the period map,
   with infusions and lagged arrivals that wrap across the period boundary (`held_05`,
   `held_11`, `held_16`).
3. **Extrema and crossings are roots, not grid points.** `t_cmax` and `time_in_window` are
   graded to `1e-6` h. Reading them off a 0.01 h grid (`grid_001` control) fails every regimen
   on `time_in_window`; the peak may be a smooth interior maximum, the post-bolus value, the end
   of an infusion (a kink) or the horizon itself, and the window is crossed up to twelve times
   per cycle (`held_20`).
4. **`n_cycles_to_steady` is a statement about every later cycle.** With loading doses the
   trough sequence can overshoot and re-enter the 1 % band (`nc_single` control, which takes the
   first cycle inside the band, is wrong on those), and the accumulation-factor formula of the
   legacy script (`nc_formula` control) ignores loading doses and saturation altogether.
5. **The physics of the inputs.** Infusions placed as boluses (`bolus_infusion` control) fail
   all 13 infusion regimens; dropping lag and transit (`no_lag`) fails every oral regimen with
   them; linearising the saturable pathway as `CL + Vmax/Km` (`linear_mm`) fails every
   Michaelis-Menten regimen.
6. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `regimencalc.py` is a plausible office script: superposition of exponential
impulse responses of the linearised model, short-infusion approximation, no lag or transit, grid
peak, trapezoidal AUC, 20th cycle as steady state, `ln(100)/(k_term period)` cycles to steady
state.

## Reference solution

`solution/regimen.py`:

- **Event-exact integration**: the ODE (dynamic states plus the AUC as an extra state) is
  integrated between consecutive events with `DOP853` at `rtol = 2.5e-14`; impulses and
  infusion-rate changes are applied exactly at their times, including events that coincide with
  the start of an interval. Dense output is used only to bracket extrema and crossings; every
  reported value is re-integrated exactly from the nearest accepted step node, because the
  `DOP853` interpolant is `1e-9` of the peak off at this tolerance.
- **Periodic steady state**: the maintenance cycle's events are folded into one period (oral
  arrivals and infusion ends modulo the period; the rate running at the period start from
  earlier cycles' infusions is accumulated); Newton shooting on the period map with the monodromy
  matrix from the variational equations, started from three map iterations, converges to
  `1e-14`.
- **Extrema and crossings**: within each dose-free piece `dC/dt` is evaluated from the
  right-hand side on a 0.005 h grid, sign changes are polished with Brent's method to `1e-14` h;
  post-bolus values, infusion-end kinks and the closed horizon end are candidates for the peak;
  `time_in_window` is the exact measure of the crossing intervals.
- **Cycles to steady state**: troughs of successive cycles as left limits of the trajectory; the
  answer is one more than the last cycle outside the band. The program stops extending cycles
  once `|x_m - x*|_1 / V1 <= 0.009 trough`: compartmental systems are `L1`-contractive
  (cooperative, non-positive column sums), so every later trough is inside the band. Guarantee 4
  of the spec makes 60 cycles sufficient in any case.
- **Runtime**: 1 to 10 s per regimen (`model_05` is the slowest).

`solution/diagnose.py` runs the legacy script and the program on the shipped regimens and emits
one witness per defect quantity; `solution/solve.sh` is the oracle entry point.

## Verification

**Independent references.** Reference A (`tests/reference/reference.py`, the answer key; written
from the spec alone, without sight of the oracle) uses exact matrix exponentials of the augmented
linear system between events for the linear regimens and an order-28 Taylor-series integrator with
automatically differentiated coefficients for the saturable ones, Newton on the period map with an
analytic Jacobian, Brent plus Newton polish for all extrema and crossings, and an explicit 60-cycle
trough sequence. Reference B (referee, dev material) is a third implementation: an order-30
Taylor-series method in 80-bit `longdouble` with no matrix exponential and no scipy integrator,
restarted at every event, with a step-halving check and a check of every spec guarantee on every
regimen. Worst differences over the 28 regimens, in the units of the
tolerance rule (`S` = cmax of the report):

| pair | concentrations and ss values | AUC (rel) | t_cmax (h) | time_in_window (h) | n_cycles |
| --- | --- | --- | --- | --- | --- |
| oracle vs A | 3.7e-12 S | 5.0e-15 | 2.8e-14 | 2.5e-12 | identical |
| oracle vs B | 3.7e-12 S | 5.1e-15 | 2.8e-14 | 2.4e-12 | identical |
| A vs B | 9.5e-15 S | 2.9e-15 | 0 | 1.2e-12 | identical |

The referee's closest guarantee margins: G2 second peak 1.51e-4 below cmax (`held_22`),
curvature at the peak 0.0129 cmax (`held_07`); G3 slope at a crossing 1.8e-3 ss cmax per hour
(`held_08`); G4 trough margin 1.75e-4 (`held_03`). Peaks at the horizon end occur in `held_03`
and `held_19`; in `model_06` the steady-state trough equals the steady-state peak (an infusion
ends at the cycle boundary).

**Tolerances.** Concentrations and AUC within `1e-8` (relative to the peak and to the AUC), times
within `1e-6` h, `n_cycles_to_steady` exact. The method spread is four orders of magnitude below
the tolerance. The time tolerance is the binding one: at `held_08` the window is crossed on a
slope of 1.8e-3 ss cmax per hour, so a concentration error of `1e-8 S` moves `time_in_window`
by about 2e-5 h; a correct method therefore needs a few `1e-9 S` of concentration accuracy where
the curve crosses the window, which `solve_ivp` reaches only when restarted at every event and
run far below its default tolerance. Wrong-method controls, graded with the verifier's own
comparison against the oracle outputs (`controls/controls.py`, dev material):

| control | what it does | fails / 28 | closest miss |
| --- | --- | --- | --- |
| `loose_rtol` | oracle at `rtol = 1e-6` | 13 | 1.02x tolerance (`held_17`, cmax) |
| `grid_001` | extrema and window on a 0.01 h grid | 28 | 376x (`held_19`, time_in_window) |
| `grid_01` | 0.1 h grid, as the legacy script | 28 | 900x (`model_06`) |
| `bolus_infusion` | infusions as boluses at their start | 13 (all infusion regimens) | 3e6x |
| `no_lag` | lag and transit dropped | 11 (all regimens using them) | 1e6x |
| `linear_mm` | `CL + Vmax/Km` instead of saturable term | 12 (all MM regimens) | 8e5x |
| `ss_iterate20` | 20th maintenance cycle as steady state | 13 | 2.0x (`held_10`, ss cmax) |
| `nc_formula` | `ln(100)/(k_term period)` cycles | 12 | integer |
| `nc_single` | first trough inside the band | 2 (`held_14`, `held_21`) | integer |
| `legacy` | `regimencalc.py` unchanged | 28 | 8e4x |

`loose_rtol` and `ss_iterate20` sit closest to the tolerance, which is why it cannot be relaxed
by more than a factor of about 2 without letting a default-tolerance integrator through on some
regimen; `nc_single` fails only on the two regimens whose loading dose puts the first trough
inside the band before later troughs leave it again (`held_14` 18 cycles, `held_21` 22 cycles).

**Verifier in Docker** (Colima, `linux/amd64`, 1 CPU, 2 GB, offline): oracle `solve.sh` 30 s,
then `test.sh` 30 passed in 109 s, reward 1; empty `/root/results` 30 failed, reward 0; FIFO in
place of `regimen.py` 30 failed, reward 0. The oracle diagnosis found eight witnesses
(`n_cycles_to_steady` at `model_03`, `concentration`, `ss_trough`, `cmax`, `time_in_window`,
`auc`, `ss_cmax` at `model_01`, `t_cmax` at `model_02`), each reproduced by the verifier against
the pristine legacy script and Reference A.
