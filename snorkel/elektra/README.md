# Project Elektra (Deep SWE / taskbot)

Working notes for Laraib's Elektra tasks. The full project guidelines (proposal + annotator flow) are in `taskbot_guidelines.md` in this folder.

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
| 6 | `/analyze` | About 5 runs per frontier model; if every run passes, the task is too easy and is rejected; failures must come from the model, not the task |
| 7 | `/submit` | Only when the pinned status comment shows it as the next action |

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

## If a step fails, report

- Repository and PR URL
- Command run
- Approximate timestamp
- Exact taskbot response
- Relevant error output
- Last successful state in the pinned status comment

Log it in the Elektra Issues sheet, then wait for the platform team to give the next command.

## Lessons from the Elektra Issues sheet (read 2026-10-04)

- The sheet is only for reporting a taskbot failure. Columns: Date, Name, CH Email, PR, Issue Summary, Error SS, Status (Pending/Picked/Resolved), Deccan Response. Leave Status at Pending; Deccan sets it.
- Always give the full PR link. A report without one got "Need PR links to verify".
- /analyze (/benchmark) failed with "ssm command Failed" until task.toml set cpu 1 and memory 6gb, and the Dockerfile gained `RUN apt-get update && apt-get install -y --no-install-recommends tmux asciinema && rm -rf /var/lib/apt/lists/*` before benchmarking. Deccan says this is now in the guidelines doc. It conflicts with "don't edit environment/Dockerfile", so confirm with Deccan before touching the Dockerfile.
- /init fails on a repo whose language is outside the verifier scope (python/node/typescript/go/rust). Ask for a new repo on the sheet. Both my repos are JavaScript, so they're in scope.
- /review stuck "QUEUED" for 18h was a backend backfill bug, fixed by Deccan. Don't re-trigger; report it.
- "no task-contract verdict recorded for artifact ..." during /review: Deccan's first answer was that edits hadn't been pushed. Push everything and check that local and remote HEAD match before reporting.
- 2026-09-30 Slack: other annotators report /benchmark (the /analyze step) erroring 5/5 trials within minutes even after /review passes; Deccan treats it as harness-side. Gitoxide /scope passed but H1 environment validation failed on missing OpenSSL dev files, which the Dockerfile hid with `|| true`.
- Issue reports need your registered email, task/PR link or session ID, error details and screenshots. Deccan reviews the sheet on a rolling basis, so check your rows.
- After finishing a task, ask in the channel for the next repo assignment.
