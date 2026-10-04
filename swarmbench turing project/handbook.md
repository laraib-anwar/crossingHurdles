# Building a task, start to finish

What the project is, how to think about it, the twelve steps you follow, the rules that get tasks accepted or rejected, and what to do when you are stuck. The handbook is the map; the Trainer Guidelines document is the rulebook. Pinned channel messages carry the links.

## 1. What this project actually is

A research client wants to know when a team of AI agents is genuinely better than one agent working alone, as a measured result. The same job is given twice under identical conditions: once to a team, once to a single agent (the control group). The team's result only counts when it provably does better where the individual failed.

A task is an experiment you design: the job, the conditions and the grading. The product is the measured difference between the two scores, the gap: team score minus single score, at least 0.18.

Guidelines: Section 1 'Why Phase 2 Matters'; Section 3.9 for the 0.18 gate.

## 2. How to think about a task

**Capacity, not ability.** One clerk with sixty case files reads properly until about file twenty, then skims. Twenty clerks with three files each read everything, and a supervisor stitches it together. Accepted example: 47 procurement files; single found 139 events but submitted 21 and scored 0.35; team submitted 132 and scored 0.60. Gap 0.25, from coverage.

**The single agent owns a photocopier.** If the job can be done by pattern (copying, counting, matching text), it writes one script, applies it to all units and wins alone. Every unit must need a real judgement a script cannot make.

**Build stocktakes, not riddles.** Wide work made of many independent units, where missing part of it is visibly worse.

Ask, in order:
1. Could a script do one unit, and therefore all of them? If yes, the idea is dead however big the corpus.
2. Would a strong model already know the answers from memory? Use recent, obscure, messy sources.
3. Is the evidence spread across many places? The answer must be assembled from dozens of places.

Size: around 60 units of real judgement (one case, one filing, one incident). Below about 40, one agent gets through nearly everything. About a third of raw material fails your own checks, so collect about 90. A real professional must want the output, or it reads as a puzzle and is rejected.

Guidelines: Section 3.6 'Task Scope and Diversity'; Section 5 worked examples.

## 3. What you hand in

| File | What it is |
|---|---|
| instruction.md | The exam paper. The only thing the agent reads. Must stand alone. |
| high_level_prompt.md | A busy requester's short ask. Not a second instruction or a copy. |
| environment/ | Dockerfile, documents, data. |
| tests/ | verify.py, test.sh, rubric_manifest.json. Grades against a held-out key. |
| decomposition.yaml | The team plan. Only the team run sees it. |
| task.toml | Metadata. Exact values; name matches folder name character for character. |
| execution_logs/ | single, multi, multi_noplan. All three required. |

Three runs: single (one agent, no spawning, never given decomposition.yaml), multi (team with your plan), multi_noplan (team without the plan; no target score but must complete cleanly). Gap = multi minus single.

The trap: anything the agent needs must live in instruction.md. A required detail only in decomposition.yaml makes the task unfair and the gap an artifact.

Guidelines: Section 6.2 'Standard Package Structure'; onboarding Section 4.7 for the three modes.

## 4. The twelve steps

1. **Task idea on the sheet, wait for the verdict.** Fill one row before building. Key columns: why one agent would fail (a mechanism) and what a no-comprehension script would score. Verdicts: APPROVE, IMPROVE, REJECT. After the first submitted task the sheet is no longer required. (Sections 3.6, 5.)
2. **Start the RCA the same day.** Update phase by phase; never reconstruct at the end. (RCA Format tab.)
3. **Write the files.** Claim a task in the unclaimed tab (view, then claim). instruction.md first, through the similarity checker (under 86%). Then decomposition.yaml, environment, verifier from the sample-pack template. Mistake: machine-written instruction, or naming exact functions and filenames instead of describing the problem. (Sections 6.1, 6.2; writing tab Section 5; Labeling Tool tab.)
4. **Local verification.** Read every file. Run qd_skills: QD-01, QD-02, QD-06 once instruction and decomposition exist; QD-11 once the verifier exists. Score a hollow submission; that is your floor.
5. **Draft review, once.** Before any agent run. Fix locally and move on. Quota: 4 reviews per day, draft and final combined, across all tasks.
6. **Run the agents.** One run at a time. Download every result zip immediately; the server deletes them after 24 hours. Leave agent timeout absent in task.toml. Harness per Section 2.3; `mascloud run --help` must list all three modes. ('How to run SA&MA' tab.)
7. **Check the gap.** Multi minus single at least 0.18. If short, read the three scores first. Fix decomposition first, one change per rerun, then instruction. Never touch the verifier to move the number. (Sections 3.9, 3.4.)
8. **Static and exec check, repeat until it passes.** Upload the zip in the labeling tool, copy the link (or a viewable Turing drive link), paste into the check. Only after all three logs exist. Free and unlimited. (Section 6.6, S-01 to S-07.)
9. **Final review, once.** Fix everything; write a comment beside each finding saying what changed and where. No rerun. (Labeling Tool tab 'Quality Gate Report'.)
10. **Verify-only, if scoring changed.** Re-score existing runs so shipped numbers come from shipped code. ('How to run SA&MA' Section 8.)
11. **Package clean and submit.** No __pycache__, scratch files, notes or AI commentary. Folder and zip name checked. RCA matches final numbers. Submit: Submit All Evaluation Forms, then Complete on the task page (starts auto review). (Section 8; Task Submission tab.)
12. **Auto review, then watch.** Fix what is valid; for findings you disagree with, explain in the response field. Monitor until approved. (Labeling Tool tab 'How to Find Rework Feedback'.)

## 5. How scoring must work

Buckets: static (format, structure, paths), reward_hacking (real work, not padding or fabrication), partial_oracle (judgement against the held-out key; where the gap lives).

- Average each bucket on its own, every check weight 1.
- Combine with (static x 1 + reward_hacking x 2 + partial_oracle x 3) / 6. Equal thirds no longer accepted.
- Minimum 5 partial_oracle checks; build 6 or more.
- No single check above about 10% of reward.
- reward.json: exactly reward and the three total_*_check_score values.
- rubric_manifest.json matches verify.py exactly, updated in the same edit.
- No caps, clamps, gates, tiers, bonuses or minimums. A gap manufactured in the verifier is a permanent reject.

Guidelines: Section 3.9 formula; Section 3.4 hard rejects.

## 6. What gets a task rejected

1. Convergence: both arms score about the same. Widen the work, do not make it harder.
2. A manufactured gap in scoring.
3. An arm that never really ran (crash and genuine zero look identical; read the trajectory).
4. A verifier that does not measure the work (hollow submission scores well).
5. Files you did not read: leftover model commentary, placeholders, instruction/decomposition contradictions.
6. Machine-written instruction, or one that gives the solution instead of the problem.
7. Similarity to your own or someone else's earlier task.
8. Dead noplan arm, self-imposed timeout, or reachable answers (key in environment, leaking git history).

Guidelines: Sections 3.4, 3.1, 7.

## 7. When you are stuck

- Single above 0.70: too easy. Needs coverage pressure, not clearer wording.
- Noplan beats multi: plan lists work without telling any stage to delegate. Name who owns what and who hands work down.
- Noplan minus single: roughly what coordination alone is worth. Under 0.18, plan tuning will not rescue it.
- Inverted gap with multi burning far more tokens: work lost between workers and deliverable. Compare /logs/agent/ outputs and read the losing arm's verifier stdout. Causes: orchestrator ran out of room, nothing gathered output, workers overwrote each other.
- Two rounds with no real movement: drop the task.
- Alive or dead: from an empty folder run `mascloud pull-trajectory <run_id>`. Session files inside means alive; API 500 with no files means dead, report to pod lead with the run id. Never Ctrl-C a streaming run.
- Ask in the channel, not DM, with numbers.

Guidelines: 'Managing Time' tab strategy 7; Section 3.2.

## 8. Practical notes

- Windows cannot open task zips (260-character paths). Use `tar -xf file.zip` or unzip_longpath.py.
- First run: reinstall the harness per Section 2.3 and confirm all three modes.
- Use AI for labour, not judgement. Read every line you ship.
- Never put a key in any file. The runner provides the judge key.
- The sample-pack verifier template does judge plumbing correctly (User-Agent, response body on failure, no retries on 400/401/403/404, status file). Its two partial_oracle examples are placeholders; expand them.
- A task is payable when Delivered and accepted by the client.
- Standup is daily and attendance is assessed.

## 9. FAQ

- Gap 0.12 is not close enough; 0.18 is a hard gate.
- Noplan needs no target score but must complete cleanly.
- Draft and final review cannot be rerun.
- Only the weighted formula is accepted.
- Minimum 5 partial_oracle checks; build 6 or more.
- Corpus about 60 units; gather about 90.
- A single score of 0 from a JSON wrapper is a container mismatch, not a result. Make the shape unambiguous or accept an equivalent container.
- Idea sheet only until the first task is submitted.

## 10. Where everything lives

| Need | Where |
|---|---|
| Rules | Trainer Guidelines: Onboarding tab, then Phase 2 tab |
| Twelve steps, all links | Pinned channel messages |
| Finished examples | trainer-samples.zip (four accepted tasks, verifier template); read its README |
| Local review | qd_skills.zip, QD-01 to QD-11 |
| Ideas | Task idea sheet (guidance tab) |
| RCA format | RCA Format tab |
| Running agents | 'How to run SA&MA' tab; Section 2.3 reinstall |
| Submitting, rework | Labeling Tool tab; Section 8 |
| Help | Daily standup and the channel |
