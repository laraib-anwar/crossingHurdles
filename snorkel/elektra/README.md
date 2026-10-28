# Project Elektra (Deep SWE / taskbot)

Working notes for Laraib's Elektra tasks. The full project guidelines (proposal + annotator flow) are in `taskbot_guidelines.md` in this folder.

## NEW WORKFLOW (announced 2026-10-28): read this first

Zaheer (@channel): Elektra is moving to an "open-source style approach on existing private repository tasks". The IDE approach pauses once the current batch is done. The new guide is the Google Doc "Private Repository Tasking (Git approach)" (tabs: Context, Annotator Workflow). The Context tab is transcribed in `private_repo_git_approach.md`.

What changes:
- **Review and fix instead of authoring.** Tasks already exist in private repos and are assigned to you on GitHub. Your job is to judge whether each one is fair and reliable for coding agents: a clear instruction, a well-scoped change, tests that capture the intended behavior, a complete package. Fix the instruction and tests where needed, then run the quality checks.
- **No /init and no feature hunting.** The pipeline starts at /scope: /scope, /verify-spec, /gen-tests, /review, /benchmarking (Luna and Sol), /analyse, /submit.
- **solution/solution.patch is the golden truth.** The instruction must cover every part of the patch, and the tests (P2P + F2P) must cover it completely. Tests must not be overly broad or unrelated, and must separate a correct fix from a wrong one.
- **Two Dockerfiles may exist.** Only environment/Dockerfile is task-specific and checked; ignore the root one.
- So the repo picks below (swagger-client, OpenHands) are probably moot. Tasks get assigned directly.

To do: react ✅ to the announcement, post your preferred onboarding time (IST) in the thread, read the Annotator Workflow tab and save it here, attend the onboarding.

Ask at onboarding:
1. Do we still author any new tasks, or only review and fix the assigned private-repo tasks?
2. Is hint.md still required (gate H1), or only "if needed" as the new table says?
3. May we edit environment/Dockerfile now? The old rule said never.
4. Patch file names differ: the sample layout has solution/solution.patch and tests/test.patch, but the table has solution/patch.diff. Which is right?
5. What's the difference between /benchmarking and /analyse, and do we run both?
6. Do the 2026-10-09 rework rules (QC-only /rework) still apply?

## What the project is

Write original SWE benchmark tasks from curated open-source repos, DeepSWE-style (Datacurve, arXiv:2607.07946). Each task is a new feature that was never merged upstream. A task is accepted only if a frontier agent can't solve it in one turn but reaches a patch that passes the verifier over several turns with recorded hints.

## My setup

- GitHub: https://github.com/laraib-anwar
- Task repos: private org `Deep-SWE-Tasks-Annotation`, named `tasks-<owner>-<repo>` (e.g. `tasks-diesel-rs-diesel`)
- Repo assignments: "Deccan <> Crossinghurdles Annotator Details" sheet, Repos tab (annotator handles in columns C onward)
- Issue log: "Deep SWE - Elektra Issues" sheet (Date, Name, CH Email, PR, Issue Summary, Error SS, Status)
- Slack: int-experts-elektra channel

## Status

- 2026-09-23: added to the project. Not yet listed on the annotator sheet and no repo assigned.
- 2026-09-23: tasking paused while the pipeline is being changed. Wait for the resume announcement before running any command.
- 2026-10-02: on the annotator sheet. Details tab row 154 (Laraib Anwar, github.com/laraib-anwar). Repos tab rows 56-57, column D: https://github.com/cure53/DOMPurify (JavaScript, branch main) and https://github.com/NuSkooler/enigma-bbs (JavaScript, branch master), both shared with prathameshsonawane05-bit in column C. I entered my handle in column D myself; the green is the sheet's own formatting, so the assignment is not confirmed yet. Mathiraja S (Slack DM) asked me to put both repo links in Details!D154 and to check for the GitHub collaborator invite.
- 2026-09-28 (Zaheer, #int-experts-elektra-deccan): tasking RESUMED. Deccan shared "Updated Project Elektra Guidelines" (Google Doc "Deepswe task workflow (Annotation)") and ran an onboarding call that day at 1 pm (recording was requested in channel). Confirm taskbot_guidelines.md matches that doc.
- 2026-09-30 (Zaheer): Deccan processed repo requests. Check your allocation and any comments in the sheet. If a repo has an unsupported language or issues, update your preferences. Allocation shows as the "Repo assigned" column (F) on the Details tab (e.g. Mathiraja row 152).
- 2026-10-05: Issues sheet row 63 (my report: no allocation, no org invite) marked Resolved. Deccan replied: "The repos chosen are out of scope, pls choose another repos". DOMPurify and enigma-bbs are rejected, so I need to pick new repos.
- 2026-10-05: DOMPurify/enigma-bbs rows (56-57) are now removed from the Repos tab. Pick only from repos still listed there. Suggested picks: OpenHands/software-agent-sdk (Python, row 70, free col E) and swagger-api/swagger-client (JS, row 58, free col D, only 1 annotator). Backups: oceanbase/powercontext (Python, row 71), release-plz/release-plz (Rust, row 74). Avoid C#/Kotlin rows (verifier languages are python/node/typescript/go/rust).
- 2026-10-05: re-picked. Repos tab: swagger-api/swagger-client (row 58) and OpenHands/software-agent-sdk (row 70). My Details rows are now 157 (OpenHands, F157 says "choose another repo") and 174 (swagger-client, F174 says "Pls add another repo"). Those F comments were Deccan's replies to the old DOMPurify/enigma-bbs picks; I cleared F157 and F174 on 2026-10-05. Asked Deccan to re-review. Assignment is confirmed when F gets the repo link and the row turns green.
- 2026-10-06: raised the re-pick on Issues sheet row 64 (still no allocation, no invite) and pinged @Zaheer in #int-experts-elektra-deccan at 10:52 PM ("trying to get a task since 10 days"). He replied in the thread.
- 2026-10-27: first task repo invite: @deepswe-taskbot-private[bot] invited laraib-anwar (laraib.anwar919@gmail.com) to collaborate on https://github.com/deccan-taskbot-private/r065-laravel-php-tasks (PHP/Laravel). The invite expires 2026-11-03. Note the org is `deccan-taskbot-private`, not Deep-SWE-Tasks-Annotation.
- 2026-10-28: installed gh 2.103.3 at ~/.local/bin/gh (no brew). The keychain git credential is a token scoped to crossingHurdles only (403 on the task repo), so task repos use gh's login through a repo-local credential helper.
- 2026-10-28: invite accepted. My task is PR #2 "Task: recalculate-attendance-day" (branch task/recalculate-attendance-day), https://github.com/deccan-taskbot-private/r065-laravel-php-tasks/pull/2. PR #1 (process-sale-return) is Jatin's; don't touch it. The repo README (the real workflow) is copied to task_repo_README.md. Local clone: ~/elektra/r065, using a repo-local credential helper `!gh auth git-credential`. Docker is via Colima (see the tbscience-toolchain memory); run the verifier locally with the tests/ image.
- 2026-10-28: new workflow announced (see the top of this file). Allocation and invite status since 10-09 isn't recorded here; check with Laraib.
- 2026-10-08: Zaheer listed the GitHub IDs that have tasks at draft/scope with no progress and asked them to report status, or lose access. laraib-anwar is not on the list because I have no task yet.
- 2026-10-04: Gmail search for Deep-SWE-Tasks-Annotation finds only Slack digests, no GitHub invite. Org page github.com/Deep-SWE-Tasks-Annotation shows no repos and "must be a member", so I am not an org member yet (invite not received or not accepted). Note: Prathamesh logged "repo issue, req another repo" on enigma-bbs (Details row 129).

## To do before the first task

1. Accept the org invite: https://github.com/orgs/Deep-SWE-Tasks-Annotation/invitation
2. Add my details on the sheet's Details tab, then ask in Slack for a repo assignment.
3. Set up GitHub access on this Mac: `brew install gh`, then `gh auth login` (GitHub.com, HTTPS, web browser).
4. Once a repo is assigned: clone the public upstream, shortlist unmerged features complex enough for /scope, and draft instruction.md.

## Command order (PR comments)

| # | Command | What it checks / does |
|---|---------|-----------------------|
| 1 | `/init <slug>` | Pins the base commit, creates the task branch, PR, pinned status comment and empty task folder |
| 2 | `/scope` | Judge decides if the feature is worth building and complex enough (write instruction.md first) |
| - | local work | Run a frontier agent; if it fails in one turn, steer it with hints until it passes; record the exact prompts in hint.md; finish the solution |
| 3 | `/verify-spec` | Hint triage, gate H1 (a zero-hint pass is rejected), symbol coverage, then spec-alignment, instruction-integrity, task-security judges |
| 4 | `/gen-tests` | Hidden tests written blind (the test writer never sees the solution) |
| 5 | `/review` | 9 programmatic gates, then 3 judge models that must all agree (tests use public APIs only) |
| 6 | `/analyze` (shown as `/benchmark` in taskbot) | About 5 runs per frontier model; if every run passes, the task is too easy and is rejected; failures must come from the model, not the task |
| 7 | `/submit` | Only when the pinned status comment shows it as the next action |
| - | QC review | After submit, Deccan QC reviews. Only QC runs `/rework` to reopen a task (see Rework below) |

On any failure: rework, push, rerun the failing command, then continue in order.

### The 9 gates in /review

| Gate | Passes when |
|------|-------------|
| f2p_base | new fail-to-pass tests fail at the base commit |
| f2p_solution | all F2P tests pass with the reference solution |
| p2p_base | selected pass-to-pass tests are green at base |
| p2p_solution | those P2P tests stay green with the solution (no regressions) |
| oracle | reference solution gets full reward (1.0) |
| flake | repeated identical runs agree |
| stub | an auto-generated no-op stub is rejected |
| breadth | alternative correct implementations (variants/alt*.diff) all pass |
| hygiene | patch is clean and scoped |

## Authoring rules

**instruction.md**
- Sounds like a real developer request, about 2,000 characters. Not a checklist or a requirements-plus-interface block.
- Describes the behavior wanted (the observable symptom), not the fix.
- Doesn't name the classes, functions or signatures the tests expect.
- Covers exactly what the tests enforce, no more and no less.
- Leaves enough unsaid that the agent has to explore, but names enough behavior for the tests to check.

- Multi-feature tasks (Deccan, 2026-10-06): build a task from several related features with one clear purpose. Describe each feature's expected behaviour and how the features work together. Vary task scope, scenarios and instruction structure from task to task.
- Write it in plain human style. Deccan (2026-09-30) flagged submissions that read as LLM-generated: no em dashes, few colons, no heavy Markdown (headers, bullets, bold).

**hint.md**
- The exact prompts given to the agent during the multi-turn run.
- Least specific first, and as few and as weak as possible.
- A hint narrows the search and never moves the target: no new requirements, no contradictions, no pointing at a different feature.
- Never reveals test assertions, fixture values or the solution's internal structure.

**Files:** only instruction.md and hint.md are meant to be edited (plus task.toml and the solution, which the annotator flow also asks for). Only instruction.md goes to the agent. Any edit to a tracked file changes the task hash and invalidates earlier gate passes.

## Restrictions

- Only the assigned annotator triggers commands. One at a time; never while a job is queued or running.
- Don't hand-create a task PR if /init stops partway, and don't rerun /init on a partially created task.
- Don't edit environment/Dockerfile. Don't install missing dependencies on the EC.
- If taskbot says no task is linked to the PR: stop and report it.
- No guessed metadata in diffs or task.toml.
- No local taskbot CLI unless the official flow says so.
- Use the full /review, not --fast, unless the platform team asks.
- Any edit to instruction.md, even at the /review stage, means rerunning from /scope and going through every stage in order before /review or /benchmark (Deccan, 2026-10-07). Several tracker issues came from pushing changes without following this sequence.

## Rework after submit (Deccan, 2026-10-09)

- After /submit, wait for QC's review and comments. Don't change the task or run anything unless QC asks.
- Annotators never run `/rework`. Only QC uses it, to reopen a task.
- Once QC reopens the task, make the requested fixes and rerun the gates from the beginning in the normal order.
- If QC hasn't asked for rework, leave the submitted task alone.

## Repo rules (Deccan, 2026-10-05 to 10-07)

- Unassigned repo: read the comment on your row in the repo request sheet (unsupported language, GitHub ID problem, etc.) and update the request.
- Max 5 tasks per repo. After 5, request a different repo from the available list. Deccan wants repo and language diversity.
- When you finish an assigned repo, mark your entry "Completed" on the repo completion sheet.
- If you're inactive or leaving, say so. Deccan is pruning access for IDs with no progress.

## If a step fails, report

- Repository and PR URL
- Command run
- Approximate timestamp
- Exact taskbot response
- Relevant error output
- Last successful state in the pinned status comment

Log it in the Elektra Issues sheet, then wait for the platform team to give the next command.

## Taskbot behaviour learned on PR #2 (2026-10-28)

- Every push to the task branch automatically queues `/rehash`, and `/rehash` then auto-runs `/scope`. Don't comment `/scope` right after a push: it gets refused ("one job runs per task at a time") while the rehash holds the task.
- A `/scope` judge reads the files statically (no PHP or Docker), so it can misread a test runner. Our first Verifiable failure claimed PHPUnit only ran the first of three positional test files. A local run showed all 42 results. Fixed by passing the verify/ directory instead.
- `/scope` verdicts vary between runs on the same content ("Difficult" passed once, then failed). The failing reason was that the instruction named helpers and pointed at the stubs, so remove implementation pointers rather than just re-running.
- `/verify-spec` "a requirement stated in instruction.md" fails when (and it re-samples different claims every run, so sweep the WHOLE instruction at once: every default, threshold, casing rule, field list and envelope key needs a test or has to go) the instruction states something no test enforces. For each one, either drop it (when the endpoint makes it untestable, e.g. `updated_at` already stamped by the caller) or add a test through the public endpoints, then mutant-check the new test. To add a test, edit the new-file hunk in test.patch and recompute the `@@ -0,0 +1,N @@` count and the `index 0000000..<blob>` hash (`git hash-object`); add the node id to config.json f2p_node_ids.
- PR #2 log 2026-10-28: scope 13/14 (Verifiable misread) → fixed; scope 13/14 (Difficult) → removed helper/stub pointers → scope 14/14; verify-spec 7/8 (3 untested claims) → 2 tests added (30 F2P), updated_at dropped, extra-deduction break clarified; rerunning scope + verify-spec. 16:42Z scope 14/14 again; verify-spec 7/8 again (instruction promised "every threshold and policy fallback" of the per-session rules, untested: hourly payroll, overtime minimum, settings overtime_after_hours). 16:59Z pushed 503dda2: 9 more F2P tests (every policy knob, lateness defaults, exact-lowercase absent, largest stored figures, location fallback order) + 1 P2P (check-in ignores settings), and trimmed untested envelope/field-list claims. Now 39 F2P / 15 P2P; local base 0/39 + 15/15, solution reward 1. drive_taskbot.py running scope → verify-spec → review → benchmark → analyze; /submit by hand after reading /analyze. Deadline: Laraib needs it before 12 am IST Thu 2026-10-29 (= 18:30Z 10-28). 17:06Z scope 14/14 ✅, 17:12Z verify-spec 8/8 ✅, 17:14Z review stopped at the task contract (AUTHORED_ENVIRONMENT_ERROR: tmux and asciinema missing from environment/Dockerfile's final stage). Fixed in c750871 (one RUN layer appended); driver now running review → benchmark → analyze.
- Stage driver: `drive_taskbot.py` in this folder (working copy at ~/elektra/scratch/drive3.py). Usage: `python3 drive_taskbot.py [--attach] scope verify-spec review benchmark analyze`. It posts each stage in order and re-posts when the bot never picks a command up, when the bot refuses because another job holds the task, or when a stage runs past its normal time. It stops on a failed blocking stage or after the last stage. REPO and PR are hard-coded at the top; change them for the next task.
- `/review` starts with a task-contract check before any Harbor run. environment/Dockerfile's final stage must install `tmux` and `asciinema` (the benchmark harness needs them). Check this before the first /review on any task: `docker run --rm <env image> sh -c 'command -v tmux asciinema'`.
- Local verifier run: `docker build -t r065-verifier tasks/<slug>/tests`, then `docker run --rm --network none -v <dir with fix.patch>:/sol:ro -v <logs>:/logs/verifier r065-verifier bash -c 'cd /app && patch -p1 -s < /sol/fix.patch && bash /tests/test.sh'`. Leave out the patch step for the base run. The reward is in <logs>/reward.json.

## Lessons from the Elektra Issues sheet (read 2026-10-04)

- The sheet is only for reporting a taskbot failure. Columns: Date, Name, CH Email, PR, Issue Summary, Error SS, Status (Pending/Picked/Resolved), Deccan Response. Leave Status at Pending; Deccan sets it.
- Always give the full PR link. A report without one got "Need PR links to verify".
- /analyze (/benchmark) failed with "ssm command Failed" until task.toml set cpu 1 and memory 6gb, and the Dockerfile gained `RUN apt-get update && apt-get install -y --no-install-recommends tmux asciinema && rm -rf /var/lib/apt/lists/*` before benchmarking. Deccan says this is now in the guidelines doc. It conflicts with "don't edit environment/Dockerfile", so confirm with Deccan before touching the Dockerfile.
- /init fails on a repo whose language is outside the verifier scope (python/node/typescript/go/rust). Ask for a new repo on the sheet. (DOMPurify/enigma-bbs were later rejected as out of scope anyway because they were dropped from the curated Repos list.)
- /review stuck "QUEUED" for 18h was a backend backfill bug, fixed by Deccan. Don't re-trigger; report it.
- "no task-contract verdict recorded for artifact ..." during /review: Deccan's first answer was that edits hadn't been pushed. Push everything and check that local and remote HEAD match before reporting.
- 2026-09-30 Slack: other annotators report /benchmark (the /analyze step) erroring 5/5 trials within minutes even after /review passes; Deccan treats it as harness-side. Gitoxide /scope passed but H1 environment validation failed on missing OpenSSL dev files, which the Dockerfile hid with `|| true`.
- Issue reports need your registered email, task/PR link or session ID, error details and screenshots. Deccan reviews the sheet on a rolling basis, so check your rows.
- After finishing a task, ask in the channel for the next repo assignment.
- Issue tracker (2026-10-05): Deccan has added comments and resolutions to most rows. A row not marked "Resolved" is still under investigation. If a fix doesn't work, update your row with new details and screenshots.
- Blockers can also go in Zaheer's channel thread: PR link, latest command/run, exact error, screenshot.
- Open infra problems reported by others (2026-10-06 to 10-08): /benchmark "ssm command Failed" before any Luna trial ran, then a retry refused with "this task revision already has a benchmark cycle" (needs a Deccan reset). A GitHub Actions job never started because of a billing/spending-limit error on the org. Some annotators are asking for new repos because theirs keep failing on infra.
- Open question (Naveen, 2026-10-08, no answer seen yet): which model and effort level count as the unaided first attempt for gate H1 and the /scope difficulty check. Claude Opus 5.5 at high effort with a test runner solves most features in 15-30 minutes, so no failure can be recorded. He also asked whether a real hint ladder is required, or whether a zero-hint pass is acceptable when the benchmark models (Luna and Sol) score 0/5. Check the thread before starting a task.
- A "Project Nebula" reminder was posted in this channel on 2026-10-08 (Deccan Diff tab, env.patch/fix.patch, zero open changes before submit). It refers to a different project, so ignore it unless Elektra adopts the same flow.
