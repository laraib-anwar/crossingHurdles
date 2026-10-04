# Project Geranium notes

User (Laraib) writes tasks for Snorkel AI's Project Geranium (GDPVal++) on experts.snorkel-ai.com. Docs: expertdocs.snorkel-ai.com/geranium-production-1. As of 2026-09-23, 14 tasks were in "needs revision" status (due ~Oct 11-12, 2026).

Each task = (1) prompt + input files, (2) golden solution file, (3) rubric. US-based professional workflow, 3+ hours by hand (aim 5+).

**Prompt:** natural colleague voice, not "You are a..." opener; who/why/now stakes; messy real constraints; names input files exactly and a concrete output file name; not step-by-step (tell what, not how); not solvable by frontier LLM in one pass.

**Input files:** 1 min, 2+ preferred, max 30MB/20 files; substantial, realistic (off-round numbers, real-sounding names, sector terminology); no answer leakage (no totals/conclusions/hidden tabs/comments/metadata); no project/eval/rubric references anywhere; no AI-blue #1C3557 family colors; spreadsheets multi-tab with formulas; single .zip, no subfolders, no spaces, no double extensions. Depth floors: prose doc 500 words, SOP/technical 600, contracts 800, correspondence 200, forms 5 sections x 3 fields; workbook 100 populated cells, 10 per tab; decks 5+ slides with master/theme. Optional standalone tell log only if tells found.

**Golden solution:** answers everything, fact-checked, human-edited, client-ready, scores 100 on own rubric; dynamic formulas; charts where data exists; practitioner file name (not "golden_solution"); no LLM prose tells (em dashes, hedging, buzzwords, generic headers, meta-sentences).

**Rubric:** 15-60 criteria (sweet spot 16-25); atomic, explicit values; weights only in numeric field (+4/+5 core, +2/+3 key, +1 minor, -3 to -5 penalties); at least 2 negative criteria worded affirmatively ("The deliverable has X issue"); style criteria < half and <= 25% of weight; criterion checking the exact output file name; reasoning criteria where wrong method could hit right answer; no stacked-adjective LLM pattern; don't restate prompt; don't paste platform-generated rubric.

**Auto-eval (60-120 min after submit):** Golden Solution, Dataset Quality, LLM Generated Files must PASS; Difficulty needs at least one agent accuracy <= 80%; Rubric Quality good/excellent. Rebuttals go as threaded reply in Slack #ec-geranium-project daily Eval & Review post with task ID.

**User's own workflow notes:** pick a fresh genre each time (corpus check catches lookalikes); build structural difficulty (ordering, chains, cycles) since plain rule-following gets solved 5/5; rules doc >600 words with worked boundary examples; hand-derive expected values plus a checker script; committed output should be a prose write-up, not raw dumps/JSON; enter prompt + O*NET first and run uniqueness before other work; pin rubric criteria to actual output file, 3 negatives, nothing needing the judge to run code; final sweep for consistent counts across prompt/rules/README/rubric and trailing whitespace; on feedback fix exactly what's named, keep verified parts byte-identical, recheck everything.

## Working location
All Geranium task work goes in /Users/hussain/Desktop/laraib/snorkel/geranium/, one subfolder per task. Each task folder holds ONLY inputs.zip and the golden zip. Do scratch work in the session scratchpad and overwrite those two zips; never add extra folders, copies or txt files there.

## GitHub
The laraib folder is the git repo for github.com/laraib-anwar/crossingHurdles (private, branch main). After every task fix or new task, run git add -A, commit with the task ID in the message, and push. Do not ask first. Keep each task's current prompt, O*NET picks and rubric in rubrics/<taskid8>-<slug>.md (outside the task folders) and update it whenever they change.

## Working style
Do not ask for permission or confirmation. Proceed with the task end to end and report at the end.

## Rubric negatives (learned 2026-09-23)
Negative criteria must be critical failures only: safety, privacy, fabrication, or an inverted prohibited decision. Never mirror a positive criterion and never penalize an ordinary wrong total. No trailing whitespace in criterion text.

## Revisions
Edit as little as possible. The user sends the current rubric; output a keep / edit / delete / add list and give paste-ready text only for criteria that change. Aim for 15-25 criteria.

## SwarmBench (Turing) project
All SwarmBench notes live in "/Users/hussain/Desktop/laraib/swarmbench turing project/": README.md (rules, gap method, lessons, meeting updates, status), handbook.md (trainer handbook), rca/ (shipped-task RCAs). Read README.md first for any SwarmBench work and keep its status section current.
