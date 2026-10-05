# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 30 are on the platform. Changes made in this repo's sessions are recorded here.

## Prompt edit 2026-10-05

In the paragraph about the disciplinary panel, "Two cases are still with the league's disciplinary panel" becomes "Three cases are still with the league's disciplinary panel".

## Criteria changed 2026-10-05 (weight | text)

31 | (weight unchanged) | standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
32 | (weight unchanged) | standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the protest-only outcome as calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
34 | 3 | standings_2026.txt gives the full order if only denton's appeal is allowed as calder, granger, denton, eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook, with calder promoted and ironside and holbrook relegated, and if denton's appeal and ironside's protest are upheld as calder, granger, denton, eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
35 | 3 | standings_2026.txt gives the full order if denton's and ironside's appeals are allowed and the protest dismissed as calder, granger, denton, eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and if all three cases succeed as calder, granger, denton, ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
36 | 2 | The note says ironside's secretary is wrong that the 1 to 0 win over berwick puts ironside above berwick if the appeal is allowed, because fairmont is also on 12 and the three-club mini table puts berwick above ironside on goal difference, +1 to 0.

## Status

2026-10-04: Quality Judge 2 majors (full order and promoted club per outcome). Fixed by overwriting criteria 31 and 32, plus a full-order line per outcome in the golden note.
2026-10-05: Difficulty came back Easy (both agents 5/5). Rubric Quality needs_improvement: no criterion on the secretary's claim, and criterion 19 has inverted polarity (text not on file). Added a third pending case, DP-26-021 (denton appeal against the March 7 abandonment; if allowed, the 2 to 0 stands and the April 8 replay counts for nothing), giving 8 outcomes, each verified by running standings.py on copies. Golden note and README updated. standings.py, the four record files and the final table are byte-identical.
