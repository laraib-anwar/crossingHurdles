# 6c39e6d4-flagcheck (feature flag support batch)

The prompt and criteria live on the platform. Only the 2026-10-07 changes are recorded here.

## 2026-10-07 adjudication round

- Adjudication note: the script broke same-day seat ties by each user's first readable row in file order, but flag_rules.txt section 4 says "the order their earliest readable rows appear in users.csv". The script now sorts by the position of the earliest readable row, and the README says the same. All 109 answers are unchanged, so flag_answers.txt is byte-identical. The unused `first` dict and the "s.4" comment (role check: coined term) are gone.
- Reference soundness: the golden was not one zip. The console fix changes the prompt's "one zip with everything in it" so the deliverable is the three files.
- Reference soundness Major said the CSVs have no date columns. The local inputs.zip has them (checks.asked, flags.effective, users.changed), so the platform may be holding an older inputs.zip. Re-upload inputs.zip.
- Rod (Slack): the rubric did not grade unchanged inputs. The console fix adds this criterion only when the prompt asks for it and no criterion already covers it:
  2 | flagcheck.py opens flags.csv, rules.csv, users.csv and checks.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.
- The console fix also renames "first readable row" to "earliest readable row" in any criterion.
- Script: fill/6c39e6d4-flagcheck-fix.js

## 2026-10-07 difficulty round (Easy, both models 5/5)

- Seats are now held, not re-dealt per date (flag_rules.txt section 4 rewritten): replay day by day, holders keep seats while eligible, a cut takes back the most recently seated first (same-day ties: further back in the line), open seats go down the enrolment line.
- Inputs: flags.csv gains `pilotui,active,no,,3,2026-07-27`; checks.csv gains zd-44612 (u-lars pilotinvite 06-22), zd-45207 (u-vero pilotui 08-06), zd-45231 (u-lars pilotui 08-13). rules.csv and users.csv unchanged.
- Answers that change: zd-44149 abel pilotui yes; zd-44326 lars pilotui seats full; zd-44547 lars pilotalerts prereq pilotui; zd-44568 devi pilotalerts yes. Totals checks=112 yes=42 no=70; rule 39, prereq 12, seats 13.
- Re-dealing per date instead of holding gets 7 lines wrong (the 4 above plus the 3 new checks).
- Golden note, README and flagcheck.py updated. Platform was likely still holding the pre-date-column inputs, so both zips must be re-uploaded.
- Script: fill/6c39e6d4-flagcheck-heldseats.js (swaps changed lines/counts in any criterion by text, adds 2 criteria).
