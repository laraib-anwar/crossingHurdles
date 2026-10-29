Write `/root/results/regimen.py`, a program that computes the exact plasma concentration-time course of multi-dose regimens in mammillary compartment models with linear and saturable (Michaelis-Menten) elimination, oral absorption through lag times and transit chains, IV boluses and overlapping IV infusions: the concentrations at query times, the exposure and peak over the horizon, the periodic steady state of the maintenance cycle (peak, minimum, trough, time inside a therapeutic window) and the number of cycles until the trough has settled. The regimens are shipped in `/root/data/regimens/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/regimencalc.py`, which takes the same command line and writes the same kind of report.

The model, the definitions of the quantities, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/REGIMEN_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/regimen.py --regimen <regimen.json> --output <report.json>
```

and must report in `<report.json>`:

1. `concentrations`: the plasma concentration at each query time.
2. `auc`: the area under the concentration curve from time zero to the horizon.
3. `cmax` and `t_cmax`: the largest concentration over the horizon and when it occurs.
4. `steady_state`: for the periodic steady state of the maintenance cycle, its `cmax`, `cmin`, end-of-cycle `trough`, the `time_in_window` per cycle, and `n_cycles_to_steady`, the first cycle from which every trough stays within 1 % of the steady-state trough.

Save the report for `/root/data/regimens/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a regimen inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped regimens and on 22 held-out regimens that vary the compartments, the elimination, the formulations, the routes, the dose schedule, the horizon, the queries and the window within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every regimen, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
