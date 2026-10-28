Write `/root/results/framedyn.py`, a program that computes the exact structural response of plane frames of straight prismatic members rigidly joined at nodes, with supports, lumped nodal masses, nodal and uniform member loads: the static nodal displacements, the natural frequencies of free vibration with the mass of every member distributed along it, and the undamped steady-state response to a harmonic nodal load. The frames are shipped in `/root/data/frames/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/framefreq.py`, which takes the same command line and writes the same kind of report.

The model (Euler-Bernoulli members with axial deformation), the definitions of the quantities, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/FRAME_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/framedyn.py --frame <frame.json> --output <report.json>
```

and must report in `<report.json>`:

1. `static`: the displacements and rotation of each queried node under the nodal and member loads.
2. `frequencies_Hz`: the lowest `n_modes` natural frequencies of the frame, every mode counted, including modes in which the nodes do not move.
3. `count_below`: how many natural frequencies lie at or below `f_max_Hz`.
4. `harmonic`: the signed steady-state amplitude at the queried node and degree of freedom for each harmonic nodal load.

Save the report for `/root/data/frames/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a frame inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped frames and on 22 held-out frames that vary the geometry, the members, the supports, the masses, the loads and the queries within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every frame, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
