Write `/root/results/ixfront.py`, a program that computes the exact effluent history of a fixed-bed anion exchanger treating water that contains chloride, nitrate, sulfate and bicarbonate, under local equilibrium with constant separation factors and plug flow, for a run with one feed composition or with one change of feed composition. The column, resin and feed recipes are shipped in `/root/data/recipes/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/ixbreak.py`, which takes the same command line and writes the same kind of report.

The model, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/IX_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/ixfront.py --recipe <recipe.json> --output <report.json>
```

and must report in `<report.json>`, for the window from 0 to the recipe's `run_bv` bed volumes:

1. `shocks`: every discontinuity of the effluent composition, with its bed volume and the compositions immediately before and after it.
2. `transitions`: every maximal interval of positive length on which the effluent composition varies continuously, with its two bed volumes and the compositions at its two ends.
3. `plateaus`: every maximal interval of positive length on which the effluent composition is constant, with its two bed volumes and its composition.
4. `nitrate_peak`: the maximum effluent nitrate concentration in the window and the smallest bed volume at which it is attained.
5. `nitrate_limit_bv`: the smallest bed volume at which the effluent nitrate concentration strictly exceeds the recipe's limit, or `null` if it never does within the window.
6. `samples`: the effluent composition at each bed volume listed in the recipe's `sample_bv`.

All compositions are in meq/L in the fixed ion order `["chloride", "nitrate", "sulfate", "bicarbonate"]`. The spec defines each quantity for the exact solution of the model, including the conventions for plateaus and transitions that meet at a shock, for the edges of the window, and for ties.

Save the report for `/root/data/recipes/service_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a recipe inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped recipes and on 22 held-out recipes that vary the selectivities, the column, the initial resin loading, the feed program and the window within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every recipe, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
