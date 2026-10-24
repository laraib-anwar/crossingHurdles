Write `/root/results/lambert.py`, a program that computes exact two-body ephemerides and complete sets of Lambert transfer solutions for the systems shipped in `/root/data/systems/`: a central body, objects on elliptic or hyperbolic Keplerian orbits given by their orbital elements, ephemeris queries and transfer queries. Also diagnose the scientific defects of the inherited script `/root/data/legacy/porkchop.py`, which takes the same command line and writes the same kind of report.

The model, the prograde convention, the definition of the revolution count and of the two branches of each multi-revolution family, the units, the parameter domain, every input and output file schema, the tolerances, the diagnosis file and the exact conditions under which the verifier runs your program are defined in `/root/data/LAMBERT_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/lambert.py --system <system.json> --output <report.json>
```

and must report in `<report.json>`:

1. `ephemeris`: the position and velocity of each queried object at the queried time.
2. `transfers`: for each query (departure object and time, arrival object and time, maximum revolution count), the transfer angle, the minimum time of flight of every revolution count from 1 to `n_max`, every prograde solution with 0 to `n_max` revolutions (departure and arrival velocities, semi-major axis, eccentricity, total impulsive cost), and the index of the cheapest solution.

Save the report for `/root/data/systems/model_01.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find in the inherited script, each with a numerical witness consisting of a system inside the spec's domain, the quantity the script gets wrong on it, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are required but not graded.

The verifier runs your program on the 6 shipped systems and on 22 held-out systems that vary the central body, the orbits, the epochs, the queries and the revolution counts within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks each diagnosis witness by executing the pristine legacy script and an independent computation. The outcome is pass or fail as a whole: every quantity must be correct on every system, and every witness must hold.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
