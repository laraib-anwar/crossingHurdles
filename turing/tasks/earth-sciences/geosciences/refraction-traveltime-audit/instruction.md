Write `/root/results/raytimes.py`, a program that computes, for a flat layered crust whose P-wave velocity varies linearly with depth inside each layer and may jump at the interfaces, every ray-theoretical arrival recorded by surface receivers from a surface source, every caustic of the traveltime branches, and the first-arrival traveltime curve with its exact crossovers. The velocity models are shipped in `/root/data/models/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/ttcurve.py`, which takes the same command line and writes the same kind of report.

The model, the arrival kinds, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/TRAVELTIME_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/raytimes.py --model <model.json> --output <report.json>
```

and must report in `<report.json>`:

1. `arrivals`: for each offset in the model's `offsets_km`, every arrival (direct, turning, reflected or head wave) with its kind, layer or interface index, ray parameter and traveltime, in increasing traveltime.
2. `caustics`: every caustic of the turning and reflection branches up to the model's `x_max_km`, with its kind, index, ray parameter, offset and traveltime.
3. `first_arrival`: the intervals of offset from 0 to `x_max_km` on which the first arrival comes from one part of one branch, with their kind, index and boundaries.

The spec defines every arrival kind, the indices, the branch segments and the orders.

Save the report for `/root/data/models/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a model inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped models and on 22 held-out models that vary the number of layers, the velocities, the gradients, the interfaces, the window and the offsets within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every model, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
