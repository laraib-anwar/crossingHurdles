# REGIMEN_SPEC: plasma concentration, exposure and steady state of multi-dose regimens

This document is authoritative for the model, the parameter domain, the input and output file
schemas, the diagnosis file, the tolerances and the conditions under which the verifier runs the
program.

## 1. Model

**Disposition.** A mammillary compartment model. The central compartment has volume `V1` (L) and
amount `A1` (mg); the plasma concentration is `C = A1 / V1` (mg/L). Up to two peripheral
compartments `k` with volumes `Vk` (L) and amounts `Ak` exchange with the central compartment at
intercompartmental clearances `Qk` (L/h). Elimination from the central compartment is the sum of a
linear clearance `CL` (L/h) and a saturable Michaelis-Menten pathway with capacity `Vmax` (mg/h)
and `Km` (mg/L):

```
dA1/dt = sum_f ka_f D_f + sum_k (Qk/Vk Ak - Qk/V1 A1) - CL C - Vmax C / (Km + C) + R(t)
dAk/dt = Qk/V1 A1 - Qk/Vk Ak
```

`R(t)` (mg/h) is the total infusion rate running at time `t`.

**Absorption.** Each oral formulation `f` has bioavailability `F_f`, lag time `tlag_f` (h), a
chain of `n_f` transit compartments (`n_f` from 0 to 5) with rate constant `ktr_f` (1/h) and an
absorption depot `D_f` with rate constant `ka_f` (1/h):

```
dT_{f,1}/dt = -ktr_f T_{f,1}
dT_{f,i}/dt = ktr_f (T_{f,i-1} - T_{f,i})        i = 2..n_f
dD_f/dt     = ktr_f T_{f,n_f} - ka_f D_f          (dD_f/dt = -ka_f D_f when n_f = 0)
```

An oral dose of `amount` mg of formulation `f` given at time `t_d` adds `F_f amount` to
`T_{f,1}` (to `D_f` when `n_f = 0`) at time `t_d + tlag_f`.

**Intravenous doses.** An IV bolus of `amount` mg at `t_d` adds `amount` to `A1` at `t_d`. An
IV infusion of `amount` mg over `duration` h starting at `t_d` adds the constant rate
`amount / duration` to `R(t)` for `t_d <= t < t_d + duration`. Infusions may overlap each other
and any other dose.

All amounts are zero at `t = 0` before any dose. `C(t)` is right-continuous: at an IV bolus time
`C(t_d)` is the post-dose value, and `C(t-)` denotes the pre-dose limit.

**Regimen.** The regimen consists of a finite list of loading doses and a maintenance cycle: a
list of doses with offsets in `[0, period)` given at `start + m period + offset` for every cycle
`m = 0, 1, 2, ...` without end. Cycle number `n` (`n >= 1`) spans
`[start + (n - 1) period, start + n period)`, and its trough is `C((start + n period)-)`.

**Reported quantities.**

- `concentrations`: `C(t)` at each query time.
- `auc`: the integral of `C(t)` from `0` to `horizon` (mg h/L).
- `cmax`, `t_cmax`: the largest value of `C(t)` on `[0, horizon]` and the time at which it is
  attained.
- `steady_state`: the maintenance regimen alone (loading doses removed, cycles continued
  indefinitely) has exactly one periodic solution of period `period`; it carries the lagged
  oral arrivals and the running infusions of earlier cycles into each period. Over one period
  of it, `cmax` is the largest concentration and `cmin` the smallest, where the limits from the
  left before IV boluses and at the end of the period count as values (so `cmin` is the
  infimum and may lie below `trough`); `trough` is the concentration at the end of the period
  (the limit from the left), and `time_in_window` is the total time (h) during which
  `low <= C <= high`.
- `n_cycles_to_steady`: the smallest cycle number `n` such that for every cycle `m >= n` of the
  actual regimen (loading doses included) `|trough_m - trough| <= 0.01 trough`, where `trough`
  is the steady-state value above.

## 2. Parameter domain

| Quantity | Domain |
| --- | --- |
| `V1` | `3` to `100` L; `CL` `0.1` to `50` L/h |
| peripheral compartments | `0` to `2`; `Qk` `0.1` to `100` L/h; `Vk` `1` to `500` L |
| `Vmax` | `0` (linear elimination) or `0.5` to `500` mg/h; `Km` `0.05` to `50` mg/L |
| formulations | `1` to `2`; `F` `0.1` to `1`; `ka` `0.1` to `5` 1/h; `tlag` `0` to `2` h; `n_transit` `0` to `5`; `ktr` `0.5` to `10` 1/h |
| doses | `amount` `1` to `5000` mg; infusion `duration` `0.1` to `24` h |
| loading doses | `0` to `4`; times in `[0, start]`; an infusion ends no later than `start` |
| maintenance | `start` `0` to `72` h; `period` `4` to `168` h; `1` to `6` doses per cycle |
| `horizon` | `start + period` to `360` h |
| query times | `3` to `10` values in `[0, horizon]` |
| window | `0 < low < high` mg/L |

Every regimen in the domain satisfies these guarantees:

1. Every query time and `horizon` differ from every IV bolus time (loading and maintenance) by
   at least `1e-3` h.
2. The maximum of `C` on `[0, horizon]` is attained at exactly one time; every other local
   maximum of `C` on `[0, horizon]` (including the post-bolus values at IV bolus times) is at
   most `(1 - 1e-4) cmax`; when the maximum is attained at a time that is not an event time
   (IV bolus, lagged oral arrival, infusion start or end) and not the horizon, `|d^2C/dt^2|`
   there is at least `1e-2 cmax` per h^2.
3. Over one period of the periodic solution, with `cmin` and `cmax` the steady-state values:
   `low` and `high` differ from `cmin` and `cmax` by at least `1e-3` of `cmin` and `cmax`
   respectively; at every time where `C` crosses `low` or `high` continuously,
   `|dC/dt| >= 1e-3 cmax` per h; every pre-bolus and post-bolus concentration differs from
   `low` and `high` by at least `1e-3` of the level.
4. For every cycle `m` from `1` to `60`, `| |trough_m - trough| - 0.01 trough | >= 1e-4 trough`,
   and the condition `|trough_m - trough| <= 0.01 trough` holds for every `m >= 60`.
5. All steady-state concentrations are positive, and `cmax >= 1e-3` mg/L.

## 3. Regimen file

A JSON object with exactly these keys:

- `regimen_id`: string, 1 to 64 characters, letters, digits, underscore, hyphen; carries no
  information about the answer.
- `model`: object with exactly the keys `V1`, `CL`, `Vmax`, `Km` (numbers) and `peripheral`
  (list of 0 to 2 objects with exactly the keys `Q`, `V`).
- `formulations`: list of 1 to 2 objects with exactly the keys `id` (integer, `1..` in order),
  `F`, `ka`, `tlag`, `n_transit` (integer), `ktr`.
- `loading_doses`: list of dose objects with exactly the keys `time`, `route`, `amount`,
  `duration`, `formulation`; `route` is `"iv_bolus"`, `"iv_infusion"` or `"oral"`; `duration`
  is a number for infusions and `null` otherwise; `formulation` is a formulation id for oral
  doses and `null` otherwise.
- `maintenance`: object with exactly the keys `start`, `period` (numbers) and `doses` (list of
  dose objects as above with `offset` in place of `time`).
- `horizon`: number.
- `query_times`: list of 3 to 10 numbers.
- `window`: object with exactly the keys `low`, `high`.

## 4. Report file

A JSON object with exactly these keys and no others. Numbers are finite JSON numbers at full
double precision.

- `regimen_id`: the regimen's id, exactly.
- `concentrations`: list with one number per query time, in order (mg/L).
- `auc`: number (mg h/L).
- `cmax`: number (mg/L); `t_cmax`: number (h).
- `steady_state`: object with exactly the keys `cmax`, `cmin`, `trough` (mg/L),
  `time_in_window` (h) and `n_cycles_to_steady` (integer).

**File conventions.** Every JSON file the verifier reads must be a regular file (not a symbolic
link or other special file), non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any
object.

## 5. Tolerances and grading

The outcome is pass or fail as a whole. A fresh call passes when, compared with the verifier's
reference values for that regimen:

1. The report meets section 4 exactly.
2. `n_cycles_to_steady` equals the reference.
3. Every concentration `v` (the `concentrations`, `cmax`, and the steady-state `cmax`, `cmin`
   and `trough`) satisfies `|v - v_ref| <= 1e-8 S` where `S` is the reference `cmax` of the
   report; `auc` is within `1e-8` relative of the reference.
4. `t_cmax` and `time_in_window` are within `1e-6` h of the reference.

A value exactly on a bound passes. No other tolerance applies. The rationale for each tolerance
is recorded in the task README and is not part of the contract.

## 6. Diagnosis file

`/root/data/legacy/regimencalc.py` is the inherited script (same command line, same report
keys). `/root/results/diagnosis.json` is a JSON object with exactly one key, `defects`, a list of
3 to 8 objects, each with exactly these keys:

- `description`: string, 1 to 500 characters. Required but not graded.
- `regimen`: a complete regimen object meeting sections 2 and 3 (a shipped regimen or one you
  construct inside the domain; it must satisfy the guarantees of section 2).
- `quantity`: one of exactly `"concentration"`, `"auc"`, `"cmax"`, `"t_cmax"`, `"ss_cmax"`,
  `"ss_cmin"`, `"ss_trough"`, `"time_in_window"`, `"n_cycles_to_steady"`.
- `index`: for `"concentration"`, the 0-based index into `query_times`; `null` otherwise.
- `legacy_value` and `correct_value`: the values of the quantity.

The verifier runs a pristine copy of the legacy script on the witness regimen and requires
`legacy_value` to match its report (the integer exactly, numbers under the section 5 rule of
their kind), computes the exact value independently and requires `correct_value` to match it
under the same rules, and requires the two values to differ (the integer by at least 1,
concentrations and `auc` by more than `1e-6` under the section 5 scale, times by more than
`1e-4` h). At least three distinct `quantity` values must appear. Every witness must pass.

## 7. Execution contract

The verifier evaluates `/root/results/regimen.py`, `/root/results/base_case_report.json` and
`/root/results/diagnosis.json`, and fresh runs of `/root/results/regimen.py` on the 6 regimens
shipped in `/root/data/regimens/` and on 22 held-out regimens of the same schema and domain, 28
fresh calls in total. The held-out regimens cover: one-, two- and three-compartment disposition,
linear and saturable elimination, IV bolus, infusion and oral dosing in the same regimen,
overlapping infusions, lag times and transit chains, two formulations, loading doses with and
without a gap before maintenance, cycles with unequal dose spacing, slow and fast accumulation,
and windows crossed several times per cycle. Their contents are not disclosed.

Each call is `python /root/results/regimen.py --regimen <regimen.json> --output <report.json>`
and must exit with status 0 within 120 seconds of wall-clock time measured by the verifier from
process start to exit; the legacy script runs on each diagnosis witness under the same contract.
The verifier as a whole has 7200 seconds of wall-clock time. All time limits are wall-clock
limits, not CPU-time limits. Calls run in a separate verifier container, offline, as an
unprivileged user in a fresh, empty, writable working directory that is the only writable
location, with Python 3.11, NumPy 1.26.4 and SciPy 1.11.4 and nothing else; the program may rely
only on its own source and its arguments, and must require neither other files nor state from
earlier calls. The verifier environment is allocated 1 CPU, 2048 MB of memory, 10240 MB of
storage and no GPU, and sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to
`1`; the environment passed to the program holds only `PATH`, `PYTHONHASHSEED=0`, those three
variables, and `HOME` and `TMPDIR` set to the working directory. The program must be a single
regular file of at most 1 MB, and every report it writes must follow the file conventions of
section 4. Anything the program writes to standard output or standard error is ignored.
