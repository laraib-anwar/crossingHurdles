# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 30 are on the platform. Changes made in this repo's sessions are recorded here.

## Prompt edit 2026-10-05

In the paragraph about the disciplinary panel, "Two cases are still with the league's disciplinary panel" becomes "Three cases are still with the league's disciplinary panel".

## Criteria changed 2026-10-05 (weight | text). One criterion added, total 34.

31 | (weight unchanged) | standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
32 | (weight unchanged) | With denton's appeal dismissed, the protest-only order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated, and the note says ironside's secretary is wrong that beating berwick 1 to 0 puts ironside above berwick if the appeal is allowed, since fairmont is also on 12 and the three-club mini table puts berwick above on goal difference.
34 | 4 | With denton's appeal allowed, every order starts calder, granger, denton (calder promoted, bottom two relegated), then: denton alone eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook; with the protest eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook; with ironside's appeal eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook; all three ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook.

## Criterion added 2026-10-07 (weight | text). Total 35.

35 | 4 | With denton's appeal allowed, standings_2026.txt names each deciding tiebreak step: alone, berwick, ashford and fairmont on 12 split on mini table points; with the protest, eastvale above ironside on season goals scored, 16 to 14, and berwick above ashford on their 1 to 0 meeting; with ironside's appeal, the four-club mini table splits berwick and ashford (6) from fairmont and ironside (3), each pair settled by its own meeting; all three, denton above ironside on its 3 to 0 win at ironside.

Criterion 33 (on the platform, weight 4) covers the same for the three denton-dismissed outcomes.

Console autofill: fill/f97982ce-standings.js, built from tools/specs/f97982ce-standings.json by tools/make_fill.py.

## Status

2026-10-04: Quality Judge 2 majors (full order and promoted club per outcome). Fixed by overwriting criteria 31 and 32, plus a full-order line per outcome in the golden note.
2026-10-05: Difficulty came back Easy (both agents 5/5). Rubric Quality needs_improvement: no criterion on the secretary's claim, and criterion 19 has inverted polarity (text not on file). Added a third pending case, DP-26-021 (denton appeal against the March 7 abandonment; if allowed, the 2 to 0 stands and the April 8 replay counts for nothing), giving 8 outcomes, each verified by running standings.py on copies. Golden note and README updated. standings.py, the four record files and the final table are byte-identical.
2026-10-05 (17:31): the bcf343ab autofill script was pasted on this page by mistake. It overwrote criteria 3, 13, 16, 17, 18 and 19 with bcf343ab text, added 34 to 36, and removed the input zip. The originals of 3, 13, 16, 17, 18 and 19 are not on file, so they were rewritten from the golden: deduction 3 (ironside 10 points, fairmont overturned), eastvale_rovers mapping, abandoned row ignored, forfeit 3 to 0, publication summary line, and a -4 negative for applying a pending case. The bogus 35 and 36 are deleted and 34 holds the denton outcomes. Also restored the other session's both-succeed paragraph (names the tiebreak steps for criterion 33), which my 17:17 rebuild had dropped. All of this is in tools/specs/f97982ce-standings.json.
2026-10-05 (18:00): the v4 console fix applied cleanly (34 criteria). Rubric checks then flagged 3, 17 and 18 as overlapping existing 7, 8 and 20. They were replaced by v5: 3 = fairmont's overturned sanction, 12 points (weight 2); 17 = the withdrawn holbrook complaint changes nothing (weight 1); 18 = the denton appeal mechanics, 2 to 0 stands, replay drops out, denton +2, ashford -1 (weight 2). The golden note's denton sentence was reworded so it no longer calls March 7 a draw.
2026-10-07: Quality Judge 1 major (rubric coverage): the four denton-allowed outcomes had orders (34) but no criterion on the deciding tiebreak step. Added criterion 35. Each step was checked by running standings.py on copies for all four outcomes; the golden note already states every one, so both zips are unchanged. Autofill: fill/f97982ce-standings.js (adds one criterion, no uploads).
