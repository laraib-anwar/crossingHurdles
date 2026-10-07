# f9657a53-swapcheck

The full prompt and earlier criteria are on the platform. Only changes from 2026-10-07 on are recorded here.

## Added 2026-10-07 (reviewer adjudication: run-name line ungraded)

new | 2 | swapcheck.py's stdout and the machine output in swap_report.txt each open with the line naming the run, swap queue worked against roster.csv, before the requests 28, applied 20, refused 8 summary line.

Golden checked: rotation_rules.txt line 66 requires "First a line naming the run"; swapcheck.py prints it first and swap_report.txt line 18 onward matches stdout byte for byte. Inputs and golden unchanged.
