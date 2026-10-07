# d995a284-points

The full prompt and earlier criteria are on the platform. Only changes from 2026-10-07 on are recorded here.

## Added 2026-10-07 (reviewer adjudication: inputs must stay read-only)

new | 3 | points_run.py opens members.csv and activity.csv only for reading and never writes to, renames or replaces either file; its output goes to stdout and stderr.

Golden checked: points_run.py opens both inputs with plain open() for reading and writes only to stdout and stderr. Inputs and golden unchanged. The Quality Judge's 3 minors are non-blocking and were left alone.
