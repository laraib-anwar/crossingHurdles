# SwarmBench (Turing) project notes

Laraib Anwar builds multi-agent swarm benchmark tasks for Turing (Phase 2 MAS, client QA). Pod leads: Olusegun Olayinka (BT task), Asma (Marshmallow, Pyparsing). Team Q standup daily. Slack channels: hopefield-mas-phase2-team-q, hopefield-mas-q-n-a-trainers, hopefield-mas-cloud-run-quota-request, hopefield-mas-main-announcement, mas-phase2-onboarding.

Contents of this folder:
- `README.md` this file: rules, the gap method, lessons, meeting updates, current status
- `handbook.md` the trainer handbook (12 steps), as shared on 2026-10-01
- `rca/` the three RCAs for shipped tasks

## 1. What a task is

The same job runs twice under identical conditions: once by a team of agents (multi), once by one agent alone (single, the control). The gap is multi reward minus single reward and must be at least 0.18 (hard gate). The gap must come from the work, never from the scoring.

Three runs are required for delivery:
- `single`: one agent, no sub-agent spawning, never sees decomposition.yaml
- `multi`: the team, given decomposition.yaml as its plan
- `multi_noplan`: the team without the plan. No target score, but it must complete cleanly.

## 2. Package

| File | Purpose |
|---|---|
| instruction.md | The only thing the agent reads. Stands alone. Human voice; describes the problem, not functions or filenames. Under 86% on the similarity checker. |
| high_level_prompt.md | Short busy-requester ask. Not a copy of instruction.md. |
| environment/ | Dockerfile, documents, data. Platform builds with environment/ as the context. |
| tests/ | verify.py, test.sh, rubric_manifest.json. Grades against a held-out key the agent never sees. Tests in separate files the agent cannot modify. |
| decomposition.yaml | Team plan. Multi only. Nothing required may live only here. |
| task.toml | Exact metadata. name equals folder name. No agent timeout. Description under 500 characters. |
| execution_logs/ | single, multi, multi_noplan. All three required. |

No __pycache__, .bak, .pre-reverify backups, scratch notes or leftover AI commentary. No keys anywhere. No solution/ directory at task root.

## 3. Scoring rules

- Three buckets: static (format), reward_hacking (real work, not padding), partial_oracle (judgement against the key).
- Every check weight 1 inside its bucket. Bucket score = mean of its checks.
- reward = (static x 1 + reward_hacking x 2 + partial_oracle x 3) / 6. Equal thirds no longer accepted.
- Minimum 5 partial_oracle checks, build 6 or more.
- No single check above about 10% of reward (bucket weight / 6 / checks in bucket).
- reward.json holds exactly four fields: reward and the three total_*_check_score values.
- rubric_manifest.json matches verify.py exactly, updated in the same edit.
- No caps, clamps, gates, tiers, bonuses or minimums. A gap manufactured in the verifier is a permanent reject.
- Measure empty, lazy (right shape, no comprehension) and oracle submissions before any paid run. Lazy score is the floor.

## 4. Screening an idea

1. Could a script do one unit? Labelled fields, counting, text matching: idea is dead.
2. Would a strong model know the answers from memory? Use recent, obscure, messy sources.
3. Is the evidence spread across many places? The answer must be assembled from dozens of documents.

Size: about 60 units of real judgement (gather about 90 raw). Below about 40 the arms do not separate. A real professional must want the output.

## 5. How the gap is achieved (the method)

1. **Coverage, not cleverness.** Many independent units, each needing real reading. One agent degrades after about 20 units or runs out of clock; one worker per unit does not.
2. **Natural units, never greppable.** Pyparsing's first build seeded literal guards and single fixed 40 of 45 by grep. Natural condition inversions dropped single from about 0.49 to 0.18 with the team unchanged.
3. **A cross-unit join that compounds the shortfall.** BT contradiction pairs need both sites coded, so pair recall falls with the square of coverage. Code tasks: ledger, notes and summary must reconcile with patches that compose on one tree.
4. **Denominate over the key.** Recall over the key's units so omissions cost. Balanced recall for skewed labels (BT outcome: all "dismissed" earns 0.5, not 0.81). Per-item checks over the source's list, not the agent's.
5. **Decomposition preserves evidence.** Managers pass through, never reconcile or harmonise. The orchestrator only does the cross-lane join (BT: 0.4455 to 0.6364 after this one change).
6. **Decompose along the natural document.** One coder per decision letter, not per site. Read noplan's spawn tree before writing the plan.
7. **No leaks in the plan.** Group by id, never by module (module grouping leaks where the bug is). No verifier-aware coaching in decomposition.yaml.
8. **No format cliffs.** Marshmallow's exact-header gate created 0.153 of fake gap. Resolve columns by exact name, then case and underscore insensitive, then common aliases.

## 6. When stuck

- Single above 0.70: too easy. Widen coverage, not difficulty.
- Noplan above multi: plan lists work but nobody delegates, or waves serialise. Name who owns what.
- Noplan minus single under 0.18: plan tuning will not rescue it.
- Multi spent far more tokens and scored lower: work lost in aggregation. Compare /logs/agent/ outputs and the losing arm's verifier stdout.
- A zero may be a crash. Read the trajectory before believing it.
- Two rounds with no movement: drop the task.
- Run alive or dead: `mascloud pull-trajectory <run_id>` from an empty folder.

## 7. Shipped tasks

| Task | Pod lead | Single | Multi | Noplan | Gap | Single's failure |
|---|---|---|---|---|---|---|
| BT Street Hub Appeal Consistency Map | Olusegun | 0.4092 | 0.6142 | 0.6191 | 0.205 | 61 docs, 327,744 words. 0 on officer statuses, engagement, contradiction pairs |
| Marshmallow Regression Triage | Asma | 0.6496 | 0.8831 | 0.9349 | 0.2335 | Fixed 56 of 61 but dropped quoted_lines, causes and release-note shape |
| Pyparsing Fork Regression Sweep | Asma | 0.1778 | 0.8672 | 0.8765 | 0.689 | Timed out at 14,400 s after 13 of 44 fixes, no ledger, no summary |

Known weak points in these packages and RCAs:
- Noplan beat multi in all three.
- Marshmallow RCA Phase 10 lists multi as 0.9349 (that is noplan; multi is 0.8831). Phase 1 says "44 patches", Phases 8, 11 and Final Reflection are copied from Pyparsing, Phase 12 repeats paragraphs, several Phase 9 fields empty.
- Pyparsing check_rh_1 has a deliberate 0.25 tier; Marshmallow keeps a "repairs at least one target test" eligibility gate. Tiers and gates are listed as hard rejects.
- Keyword or regex scoring (template detection, eight-word restatement runs, verbatim quote matching) now at risk under the new LLM-judge direction.

## 8. Lessons from the RCAs

- Pilot 10 units through all three modes before building the full corpus.
- Read the gap on the mean of two multi runs, not one draw.
- After any scoring change, verify-only every arm. The Quality Gate E-01 reads stored rewards, not a fresh run. verify-only writes one filename, so downloads overwrite each other; it is refused at the daily quota, so keep slots in reserve.
- Test the Docker image with the same build context the platform uses (environment/ as context).
- Keep fixers' working copies out of /workspace and dispatch managers in waves (26 parallel fixers crashed the sandbox on opencode's workspace snapshot).
- Run the free Static + Exec check before spending a review.
- Answer Quality Gate findings with comments on the report; do not rerun it to go green.
- QD-07.10 (single-agent prompt wrapped in a stray double quote) is a harness artefact. Answer with evidence.
- Keep the labeling-tool form's instruction.md field identical to the packaged file.

## 9. Updates from meetings

**All Hands, Rework Stage MAS Overview (2026-09-30)**
- New client QA lead with stricter criteria; rejection rates up. Quality over speed (Mehedi Hasan).
- No hidden requirements: every verifier check must trace to instruction.md.
- rubric_manifest.json and metadata must match the code; no placeholders.
- Enum ambiguity: state exact allowed values or accept equivalents.
- Tests in separate files under tests/ so the agent cannot modify them.
- Instructions must not contradict the input files.
- API or judge failures must exit non-zero, never return a zero score.
- Replace keyword and regex scoring with LLM-judge checks (notes say "reject checks", almost certainly "regex"). Hybrid verifier direction.
- Remove network-mode settings from task.toml (notes garbled; confirm in channel).
- Validate with the Quality Gate and get pod lead approval before final delivery.
- Mehedi to share the client RCA document.

**Team Q standup (2026-09-30)**
- Automated cloud reviews remove the wait for manual reviews.
- Verifier-only fixes need only static checks, not a full Quality Gate run. Whether partial reworks need a full QG run was still open.
- Rework speed decides when phase 3 starts.

**Team Q standup (2026-10-01)**
- Instruction, corpus and verifier must align completely, including identifiers and uniqueness claims (Benaiah: instruction said each spec sheet ID was distinct, corpus had near-duplicate IDs, QG flagged ambiguity).
- Input context near 3M tokens made the harness exit non-zero and single score 0.0 or 0.27 (Vansh); the output token limit issue on mascloud was fixed.
- Quality Gate flagged implicit header rules as instruction ambiguity (Yousef). State headers explicitly.
- Quality Gate flagged part of a corpus as synthetic due to similarities (Benaiah removed it and reran three arms).

## 10. Current status (2026-10-02)

- Rejected tasks are listed in "Phase 2 MAS_Client_QA_Rejected_Tasks_Tracker" (shared by Yousef on 2026-10-01). Columns: Task ID, UUID, Trainer, Trainer Email, Batch, Task Name, Domain, Priority, Rejection Type (Content or Measurement), Task LT Link, Client's Stated Reason, Client Doc Link, Current Verdict, Main Reason of Rejection, Reviewer Name, Our QA Recheck Verdict (Partial Rework or Rework Needed), Justification, Claude Verdict.
- Laraib's rows were not in rows 2 to 130 of the screenshot. Next: filter Trainer Email for Laraib, download the tab as CSV, download each Client Doc as .docx, and fetch each rejected task's package zip into Downloads.
- Open question for the channel: does a partial rework need a full Quality Gate run or only the static check.

## 11. Rework workflow

1. Read the client doc and QA justification for the task.
2. Fix exactly what is named. Keep verified parts byte-identical.
3. Check every verifier check against instruction.md, and the manifest against verify.py.
4. Rerun empty, lazy and oracle locally.
5. If scoring changed, verify-only all three arms; new runs only if the task or plan changed.
6. Static + Exec check, then Quality Gate if required, pod lead approval.
7. Update the RCA so its numbers match the package.
8. Comment each finding with what changed and where.
