Write `/root/results/lightoff_exact.py`, a program that finds every ignition, extinction and Hopf point of a porous catalytic washcoat layer with external heat and mass transfer resistances over a given range of the Thiele modulus, and every steady state at given values of the Thiele modulus with its stability. The layer recipes are shipped in `/root/data/recipes/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/lightoff.py`, which takes the same command line and writes the same kind of report.

The model, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/WASHCOAT_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/lightoff_exact.py --recipe <recipe.json> --output <report.json>
```

and must report in `<report.json>`, for the window from the recipe's `phi_min` to its `phi_max`:

1. `folds`: every ignition and extinction point of the steady-state set, with its Thiele modulus, centre temperature rise, effectiveness factor and kind.
2. `hopf_points`: every Hopf point of the steady states, with its Thiele modulus, centre temperature rise, effectiveness factor and oscillation frequency.
3. `states`: for each Thiele modulus in the recipe's `phi_query`, every steady state, in increasing centre temperature rise, with its centre temperature rise, effectiveness factor and stability class.

The spec defines every quantity, the stability classes and the orders.

Save the report for `/root/data/recipes/lightoff_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a recipe inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped recipes and on 22 held-out recipes that vary the Prater, Arrhenius, Biot and Lewis numbers and the window within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every recipe, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
