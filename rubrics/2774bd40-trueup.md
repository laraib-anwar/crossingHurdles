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

## 2026-10-08 full rubric rebuild for the 14-account data (fill/2774bd40-trueup-rebuild.js)

The close of the prompt from "Build/Write trueup.py" onward is replaced: it states the stderr format, month names from the read dates, the hand-worked account in README.md, the single deliverable, and that the inputs stay untouched. Every number below was checked against statement_2026_09.txt and README.md.

1 | 5 | Running trueup.py reads.csv tariff.csv writes this line to stderr: accounts=14 august=369115 trueup=70420 corrected=11 due=439535
2 | 1 | statement_2026_09.txt opens its batch with a line naming September as the statement month, directly followed by the summary line of batch totals and then the first account block.
3 | 2 | In statement_2026_09.txt, a-3117 shows August usage 53 units and charge 29910 cents, no corrected months and no true up line, and amount due 29910 cents.
4 | 3 | In statement_2026_09.txt, a-4501 shows corrected May 44 units 21470 cents against 30 units 12300 billed, June 42 units 20160 against 28 units 11480, July 43 units 20815 against 28 units 11480, true up 27185 and amount due 49895 after an August charge of 22710.
5 | 3 | In statement_2026_09.txt, a-2933 shows corrected May 31 units 12955 cents against 56 units 29330 billed, June 30 units 12300 against 62 units 33260, July 31 units 12955 against 66 units 35880, and a true up of -60260.
6 | 3 | In statement_2026_09.txt, a-2933 shows an August charge of 13350 cents for 30 units and an amount due of -46910 cents, printed as a negative credit.
7 | 3 | In statement_2026_09.txt, a-5169 corrects only July, 40 units 18850 cents against 23 units 9430 billed, with true up 9420, August 39 units 19830 and amount due 29250.
8 | 2 | In statement_2026_09.txt, a-1846 shows corrected May 97 units 56185 cents, June 93 units 53565 and July 96 units 55530, true up 43885, August 96 units 60870 and amount due 104755.
9 | 2 | In statement_2026_09.txt, a-6220 shows June corrected to 1 unit 410 cents against 2 units 820 billed and July corrected to 2 units 820 against 0 units 0, with true up 410 and amount due 855.
10 | 2 | In statement_2026_09.txt, a-8814 shows corrected May 94 units 54220 cents, June 91 units 52255 and July 94 units 54220, true up 81220, August 94 units 59430 and amount due 140650.
11 | 2 | In statement_2026_09.txt, a-2290 corrects only June and July, 53 units 27365 cents against 49 units 24745 billed and 54 units 28020 against 50 units 25400, with true up 5240 and amount due 35870.
12 | 2 | In statement_2026_09.txt, a-6618 shows a true up of -56985 cents and an amount due of -40035 cents, printed as a negative credit.
13 | 3 | In statement_2026_09.txt, a-9035 shows August usage 32 units and charge 14790 cents with no corrected months and no true up line, and amount due 14790 cents.
14 | 2 | In statement_2026_09.txt, a-4127 corrects only June and July, 42 units 20160 cents against 38 units 17540 billed and 44 units 21470 against 41 units 19505, with true up 4585 and amount due 27295.
15 | 2 | In statement_2026_09.txt, a-5583 corrects only July, 43 units 20815 cents against 47 units 23435 billed, with true up -2620 and amount due 20090.
16 | 2 | In statement_2026_09.txt, a-3364 shows corrected May 40 units 18850 cents, June 38 units 17540 and July 40 units 18850, each against 30 units 12300 billed, with true up 18340 and amount due 38890.
17 | 1 | In statement_2026_09.txt, a-7702 shows August usage 59 units and charge 34230 cents, no true up line, and amount due 34230 cents.
18 | 2 | README.md works a-4501 by hand from its 1180 and 1352 actual readings: 172 units over 123 days, 2 spare units, the first to June on its .95 and the second to May on the tie.
19 | 2 | README.md says the tie rule decides a spare unit in six of the eleven corrected spans: a-4501, a-2933, a-5169, a-1846, a-6220 and a-4127.
20 | 2 | trueup.py takes the statement month and the August label from the read dates in reads.csv instead of printing them as fixed text.
21 | 3 | reads.csv and tariff.csv are left byte-for-byte unchanged by running trueup.py; the script opens them read-only and writes nothing back to either file.
22 | 1 | The delivered files are named trueup.py, statement_2026_09.txt and README.md.
23 | -5 | statement_2026_09.txt shows a-2933 or a-6618 with an amount due of zero instead of its negative credit.
24 | -5 | statement_2026_09.txt prices a corrected May, June or July month at the August 2026 tariff instead of the tariff in force for that month.

2026-10-08 (11:16 results): the rebuild set criteria 1 to 24, but the deletes of 25 to 28 did not take (28 left). Penalty scope check failed: the credit-floor and August-tariff negatives count as ordinary calculation errors that mirror positives 6 and 12. fill/2774bd40-trueup-finish.js deletes everything after 23 (with confirm handling and checks that each delete took), turns #21 into "-5 reads.csv or tariff.csv is modified, renamed or deleted, whether by trueup.py when it runs or in the copies handed back with the submission." and #23 into "-5 statement_2026_09.txt includes an account block for an account that does not appear in reads.csv.", and removes #24. The final rubric has 23 criteria. Credit and per-month tariff mistakes are still caught by the exact-value positives (6, 12, and the corrected-month values).
