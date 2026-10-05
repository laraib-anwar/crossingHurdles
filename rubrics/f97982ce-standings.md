# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 32 are on the platform. Only the 2026-10-04 changes are recorded here.

## Changed 2026-10-04 (criteria 31 and 32 overwritten, weights unchanged)

31 | (weight unchanged) | standings_2026.txt gives the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for the both-succeed outcome as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
32 | (weight unchanged) | standings_2026.txt gives the full finishing order for the protest-only outcome as calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.

## Added 2026-10-05 (criteria 33 to 35, weight | text)

33 | 3 | standings_2026.txt states that if only ironside's appeal is allowed, berwick, ironside and fairmont finish level on 12 and level on points in their mini table, and goal difference in their mutual matches separates them, berwick +1, ironside 0 and fairmont -1, rather than ironside's head to head win over berwick.
34 | 3 | standings_2026.txt states that if only ironside's protest is upheld, the four club mini table at 13 points splits denton and ashford from eastvale and ironside, denton goes above ashford on season goal difference, and eastvale goes above ironside on season goals scored, 16 to 14, after the two finish level on season goal difference.
35 | 2 | standings_2026.txt states that if both cases succeed, ironside finishes alone on 15 with no tiebreak, and the three club tie at 13 breaks as in the published table, with the mini table dropping eastvale and season goal difference putting denton above ashford.

## Status

2026-10-04: difficulty passed (GPT-5.6 80%). The Quality Judge raised 2 majors: full order not checked for each panel outcome, and promoted club not checked for each outcome. Fixed by overwriting criteria 31 and 32 (no new criteria), plus one full-order line per scenario in the golden standings_2026.txt note. standings.py, the README and the final table are byte-identical.

2026-10-05: Quality Judge raised 1 major: the rubric did not check which tiebreak step settles the ties under each panel outcome. Fixed with criteria 33 to 35 (35 criteria total). The golden note's both-succeed paragraph now names the steps. standings.py, the README, the final table and the inputs are byte-identical.
