# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 32 are on the platform. Only the 2026-10-04 changes are recorded here.

## Changed 2026-10-04 (criteria 31 and 32 overwritten, weights unchanged)

31 | (weight unchanged) | standings_2026.txt gives the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for the both-succeed outcome as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
32 | (weight unchanged) | standings_2026.txt gives the full finishing order for the protest-only outcome as calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.

## Added 2026-10-05 (one criterion, weight | text)

33 | 4 | standings_2026.txt names the deciding tiebreak step for each panel outcome: appeal only, berwick, ironside and fairmont are level on mini table points and split on mini table goal difference, +1, 0 and -1; protest only, the four club mini table splits off denton and ashford, season goal difference puts denton above ashford, and season goals scored, 16 to 14, put eastvale above ironside; both succeed, ironside is alone on 15 and the 13 point tie breaks as in the published table.

## Status

2026-10-04: difficulty passed (GPT-5.6 80%). The Quality Judge raised 2 majors: full order not checked for each panel outcome, and promoted club not checked for each outcome. Fixed by overwriting criteria 31 and 32 (no new criteria), plus one full-order line per scenario in the golden standings_2026.txt note. standings.py, the README and the final table are byte-identical.

2026-10-05: Quality Judge raised 1 major: the rubric did not check which tiebreak step settles the ties under each panel outcome. Fixed with criterion 33 (33 criteria total), one criterion covering all three outcomes at the user's request. The golden note's both-succeed paragraph now names the steps. standings.py, the README, the final table and the inputs are byte-identical.
