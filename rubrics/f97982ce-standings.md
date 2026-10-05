# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 30 are on the platform. Changes made in this repo's sessions are recorded here.

## Prompt edit 2026-10-05

In the paragraph about the disciplinary panel, "Two cases are still with the league's disciplinary panel" becomes "Three cases are still with the league's disciplinary panel".

## Criteria changed 2026-10-05 (weight | text). One criterion added, total 34.

31 | (weight unchanged) | standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
32 | (weight unchanged) | With denton's appeal dismissed, the protest-only order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated, and the note says ironside's secretary is wrong that beating berwick 1 to 0 puts ironside above berwick if the appeal is allowed, since fairmont is also on 12 and the three-club mini table puts berwick above on goal difference.
34 | 4 | With denton's appeal allowed, every order starts calder, granger, denton (calder promoted, bottom two relegated), then: denton alone eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook; with the protest eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook; with ironside's appeal eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook; all three ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook.

Console autofill: fill/f97982ce-standings.js, built from tools/specs/f97982ce-standings.json by tools/make_fill.py.

## Status

2026-10-04: Quality Judge 2 majors (full order and promoted club per outcome). Fixed by overwriting criteria 31 and 32, plus a full-order line per outcome in the golden note.
2026-10-05: Difficulty came back Easy (both agents 5/5). Rubric Quality needs_improvement: no criterion on the secretary's claim, and criterion 19 has inverted polarity (text not on file). Added a third pending case, DP-26-021 (denton appeal against the March 7 abandonment; if allowed, the 2 to 0 stands and the April 8 replay counts for nothing), giving 8 outcomes, each verified by running standings.py on copies. Golden note and README updated. standings.py, the four record files and the final table are byte-identical.
2026-10-05 (17:31): the bcf343ab autofill script was pasted on this page by mistake. It overwrote criteria 3, 13, 16, 17, 18 and 19 with bcf343ab text, added 34 to 36, and removed the input zip. The originals of 3, 13, 16, 17, 18 and 19 are not on file, so they were rewritten from the golden: deduction 3 (ironside 10 points, fairmont overturned), eastvale_rovers mapping, abandoned row ignored, forfeit 3 to 0, publication summary line, and a -4 negative for applying a pending case. The bogus 35 and 36 are deleted and 34 holds the denton outcomes. Also restored the other session's both-succeed paragraph (names the tiebreak steps for criterion 33), which my 17:17 rebuild had dropped. All of this is in tools/specs/f97982ce-standings.json.
