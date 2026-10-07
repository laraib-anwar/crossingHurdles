# 2774bd40-trueup (meter read true-up statement)

The prompt and criteria live on the platform. Only the 2026-10-07 changes are recorded here.

## 2026-10-07 adjudication round

- Adjudication note: no criterion graded the prompt's line 7 requirement to leave reads.csv and tariff.csv unchanged. Added the adjudicator's own wording as a new criterion:
  new | 3 | reads.csv and tariff.csv are left byte-for-byte unchanged by running trueup.py; the script opens them read-only and writes nothing back to either file.
- The golden trueup.py opens both files read-only and writes only to stdout and stderr, so the golden is unchanged.
- Quality Judge: 0 Major and 4 Minor (optional), left as they are.
- Script: fill/2774bd40-trueup-fix.js

## 2026-10-07 reviewer round (11:42)

- Criteria 4, 7, 8 and 21 quoted exact statement lines, but the rules only ask for the values. The console fix rewrites them to values only (for example "2026-05 corrected to 44 units and 21470 cents against 30 units and 12300 cents billed"), weights kept. The old and new text are printed in the console.
- Section 6 opening lines were ungraded. Added:
  new | 2 | Below the opening note, the statement in stdout and statement_2026_09.txt starts with a line naming September as the statement month, followed by the summary line giving 6 accounts, 147115 cents for August, 20640 cents of true up and 5 accounts corrected.
- README tie sentence fixed: a-4501 has one unit left after June, which the tie gives to May; a-2933 has two, which the tie gives to May and July (hand-checked from the day spread).
- Template overlap with swapcheck: the prompt from "Build trueup.py" on is replaced with trueup's own wording (the console fix prints the old tail). billing_rules.txt gets its own intro sentence, a section 1 heading and section 6 wording, with no rule content changed; the CSVs are byte-identical. The README is rewritten in its own structure with the same facts. A rerun of trueup.py still matches statement_2026_09.txt exactly.
- O*NET: add a third task by hand, "Store, retrieve, and manipulate data for analysis of system capabilities and requirements."
- Script: fill/2774bd40-trueup-fix2.js
- Near-identical check: criterion 29 repeated criterion 2's four totals. 29 now checks only the month line and its placement: "Below the opening note, the statement in stdout and statement_2026_09.txt starts with a line naming September as the statement month, with the summary line of batch totals directly after it and before the first account block." (weight 2). Criterion 2 keeps the values.

## 2026-10-07 reviewer round (14:09), files done, rubric pending

- Data: added 8 accounts (a-7702, a-8814, a-2290, a-6618, a-9035, a-4127, a-5583, a-3364) and 2 tariff history rows (2024, 2025). The six original accounts are untouched. New totals: accounts=14 august=369115 trueup=70420 corrected=11 due=439535. Credits a-2933 -46910 and a-6618 -40035. a-9035 has earlier estimates but an August 1 actual, so nothing is reopened.
- trueup.py takes its month labels from the read dates (statement month from the closing read, the "august" label from the last billing month). On the old data the output is byte-identical.
- README: adds a worked account (a-4501 by hand: 172 units over 123 days, 44/42/43/43, true up 27185, due 49895). Tie, estimate-spread (+33855 cents on the batch) and current-tariff (+61900 cents on the true up) claims recomputed; the method reproduces the old README's 17285 and 26660 on the old data.
- billing_rules.txt: section 6 is policy voice (no script name, stdout, stderr or file name), and the section 4 hint sentence about wrong methods is removed. The stderr format and file name move to the prompt.
- Rubric rebuild waits on a dump of the live criteria: fill/dump-rubric.js. Planned: re-value every criterion for the new data, split bundled ones (the README row), replace the password and network negatives with "credit floored at zero" and "corrected months priced at the August tariff", add a worked-account criterion, and rewrite the prompt close.
