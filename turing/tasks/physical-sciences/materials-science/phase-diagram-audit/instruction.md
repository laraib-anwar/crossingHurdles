Write `/root/results/phasediagram.py`, a program that computes the exact equilibrium phase diagram of a binary system A-B from its Gibbs energy models: substitutional solution phases with Redlich-Kister excess terms and stoichiometric compounds, as in a CALPHAD assessment. The systems are shipped in `/root/data/systems/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/tangentdiag.py`, which takes the same command line and writes the same kind of report.

The thermodynamic model, the definition of equilibrium (the lower convex hull of all phases), the tie-lines, the event kinds and their classification, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/PHASE_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/phasediagram.py --system <system.json> --output <report.json>
```

and must report in `<report.json>`:

1. `isotherms`: for each temperature in the system's `isotherms_K`, the isothermal section: the single-phase regions and the tie-lines of the equilibrium hull in order of composition, with their phases and exact boundary compositions.
2. `invariants`: every three-phase equilibrium inside the system's temperature window, with its temperature, the three phases and their compositions, its class (eutectic or peritectic type, from the stability of the middle phase above or below the invariant) and its name (eutectic, peritectic, monotectic, syntectic, eutectoid, peritectoid, metatectic, inverse monotectic).
3. `congruent_points`: every congruent point (two phases stable at one composition: a congruent maximum or minimum of a two-phase lens, or a compound melting or forming congruently), with the phases above and below and the side of the lens.
4. `critical_points`: every consolute point of a miscibility gap on the equilibrium diagram, with the side of the gap.

Only equilibrium features count: metastable common tangents, metastable compounds and metastable critical points are not part of the diagram; transitions of the pure components are not reported.

Save the report for `/root/data/systems/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a system inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped systems and on 22 held-out systems that vary the phases, the end members, the excess parameters, the compounds, the window and the isotherms within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every system, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
