# Inputs-unchanged criteria (drafts, 2026-10-07)

Adjudication (Rod, Slack) found that three of the five reopened tasks have no criterion grading the prompt's requirement that the input files stay unchanged. Add one only to a task whose Section 2 feedback names this gap. Every golden script below opens its inputs read-only and writes only to stdout and stderr (checked 2026-10-07).

6c39e6d4 flagcheck | 2 | flagcheck.py opens flags.csv, rules.csv, users.csv and checks.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
2774bd40 trueup | 2 | trueup.py opens reads.csv and tariff.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
70445e96 recall | 2 | trace_recall.py opens batches.csv, blends.csv and shipments.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
f9657a53 swapcheck | 2 | swapcheck.py opens roster.csv and swaps.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
d995a284 points | 2 | points_run.py opens members.csv and activity.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
e129acca access | 2 | access_check.py opens catalog.csv, transactions.csv, subscriptions.csv and queries.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
