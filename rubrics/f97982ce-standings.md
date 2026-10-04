# f97982ce-standings (2026 league final table with pending panel cases)

The full prompt and criteria 1 to 32 are on the platform. Only the 2026-10-04 additions are recorded here.

## Added 2026-10-04 (criteria 33 to 35, weight | text)

33 | 3 | standings_2026.txt states that if only ironside's appeal is allowed the finishing order is calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated.
34 | 3 | standings_2026.txt states that if only ironside's protest is upheld the finishing order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.
35 | 3 | standings_2026.txt states that if both the appeal and the protest succeed the finishing order is calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.

## Status

2026-10-04: difficulty passed (GPT-5.6 80%). The Quality Judge raised 2 majors: full order not checked for each panel outcome, and promoted club not checked for each outcome. Fixed with criteria 33 to 35, plus one full-order line per scenario in the golden standings_2026.txt note. standings.py, the README and the final table are byte-identical.
