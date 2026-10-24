Write `/root/results/hetero.py`, a program that computes the exact electronic properties of layered semiconductor heterostructures in the effective-mass approximation: flat and linearly graded or biased layers with their own effective masses between two contacts. The structures are shipped in `/root/data/structures/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/qwell.py`, which takes the same command line and writes the same kind of report.

The model (including the interface conditions and the constants), the definitions of the bound states, the transmission coefficient and the transmission maxima, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/HETERO_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/hetero.py --structure <structure.json> --output <report.json>
```

and must report in `<report.json>`:

1. `bound_states`: every bound state of the structure below the lower contact band edge, in increasing energy.
2. `transmission`: the transmission coefficient at each queried energy, including energies deep in the tunnelling regime.
3. `maxima`: every local maximum of the transmission coefficient inside the structure's energy window, with its energy and transmission.

Save the report for `/root/data/structures/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a structure inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped structures and on 22 held-out structures that vary the layers, the masses, the band profile, the bias, the contacts, the queried energies and the window within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every structure, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
