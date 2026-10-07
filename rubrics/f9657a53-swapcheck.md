# f9657a53-swapcheck (October rota swap queue)

The prompt and criteria live on the platform. Only the 2026-10-07 changes are recorded here.

## 2026-10-07 reviewer round

- Reviewer: section 6 requires one line per request in queue order after the summary, and only the part before the summary was graded. Added:
  new | 2 | In stdout and swap_report.txt, the 28 request lines run in swaps.csv order, s-201 through s-228, between the summary line and the night counts.
- Reviewer: the opening note explained seven of the eight refusals. The golden note now says s-213 names arden_pike on both sides and is refused as same person. The report body below the note is byte-identical, and a rerun of swapcheck.py matches it.
- Quality Judge minor 2 and Rod's unchanged-inputs point: the script-only preservation penalty (criterion 24) was widened, weight unchanged:
  24 | (weight unchanged) | roster.csv or swaps.csv is modified, renamed or deleted, whether by swapcheck.py when it runs or in the copies handed back with the submission.
- Script: fill/f9657a53-swapcheck-fix.js
