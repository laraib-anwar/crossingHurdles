Write `/root/results/cabletree.py`, a program that computes the exact passive electrotonic properties of a reconstructed neuron: an isopotential soma with a tree of cylindrical dendritic segments, each with its own membrane resistance, axial resistivity and capacitance, with sealed, killed or shunted terminals and an optional somatic shunt. The neurons are shipped in `/root/data/neurons/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/cableprop.py`, which takes the same command line and writes the same kind of report.

The model, the quantities, the units, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/CABLE_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/cabletree.py --neuron <neuron.json> --output <report.json>
```

and must report in `<report.json>`:

1. `input_resistance`: the steady-state input resistance at each queried location (soma, or a point along a segment).
2. `attenuation`: for each queried ordered pair of locations, the steady-state attenuation factor from source to target (the factors depend on the direction).
3. `impedance`: for each queried (source, target, frequency), the modulus and phase of the complex transfer impedance.
4. `modes`: every equalization time constant of the neuron not smaller than the neuron's `tau_min_ms`, in decreasing order, each with the coefficient of its mode in the somatic voltage response to a current step at the soma.

Save the report for `/root/data/neurons/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a neuron inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped neurons and on 22 held-out neurons that vary the morphology, the passive parameters, the boundary conditions, the queries and `tau_min_ms` within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every neuron, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
