# 2774bd40-trueup (meter read true-up statement)

The prompt and criteria live on the platform. Only the 2026-10-07 changes are recorded here.

## 2026-10-07 adjudication round

- Adjudication note: no criterion graded the prompt's line 7 requirement to leave reads.csv and tariff.csv unchanged. Added the adjudicator's own wording as a new criterion:
  new | 3 | reads.csv and tariff.csv are left byte-for-byte unchanged by running trueup.py; the script opens them read-only and writes nothing back to either file.
- The golden trueup.py opens both files read-only and writes only to stdout and stderr, so the golden is unchanged.
- Quality Judge: 0 Major and 4 Minor (optional), left as they are.
- Script: fill/2774bd40-trueup-fix.js
