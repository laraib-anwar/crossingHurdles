# Proposal: An Original-Task SWE Benchmark from Open-Source Repositories (taskbot pipeline)

## 1. Summary

This document describes a DeepSWE-style task-annotation program (DeepSWE: Datacurve, arXiv:2607.07946) implemented as the **taskbot** pipeline: a GitHub-driven workflow in which software engineers mine curated open-source repositories for *new, unmerged features*, author each as a self-contained benchmark task, and admit a task only when a frontier agent cannot solve it in a single turn but reaches a verifier-passing patch across multiple turns with recorded hints.

The pipeline keeps DeepSWE's three load-bearing properties — original (never-merged) tasks, natural developer-register instructions, and functional verifiers that accept any correct implementation — and operationalizes them as a state machine of seven slash-commands, a battery of nine programmatic gates, a layer of agent-judge rubrics, and a hint gate that enforces difficulty. Every command runs identically from a PR comment or the local CLI, and the whole authoring loop runs on a laptop with no cloud dependencies.

## 2. Background and motivation

Most public agentic-coding benchmarks descend from SWE-bench and mine merged fixes from public repositories. DeepSWE documents two structural costs: the fixes and their discussion are plausibly in pretraining data, so a high score can reflect recall rather than problem-solving; and grading is inherited from the tests that shipped with each merged fix, which were written to confirm one specific fix and therefore reject valid alternatives or accept incomplete ones.

DeepSWE avoids both by authoring tasks from scratch across 91 active repositories in five languages, never contributing them upstream, and grading each with a hand-written functional verifier. On a matched audit an independent judge disagrees with DeepSWE's verifier about an order of magnitude less often than with an inherited-test scheme (1.4% vs 32.4%). The two directions of that disagreement — accepting incomplete work and rejecting valid alternatives — are exactly what the stub and breadth gates below are built to catch.

## 3. Objectives

- Produce a corpus of original, long-horizon feature-implementation tasks from real open-source repositories, decontaminated by construction.
- Grade every task with a hand-written functional verifier that accepts any correct implementation, proven by a nine-gate battery.
- Calibrate difficulty explicitly: reject tasks a frontier agent solves in one turn; accept tasks that require multiple turns and recorded hints, enforced by the hint gate.
- Enforce authoring norms for instructions, hints, and verifiers through programmatic checks and agent-judge rubrics, so the corpus measures problem-solving rather than recall, prompt-reading, or verifier-overfitting.

## 4. Scope

**In scope:** repository-scale feature additions expressed as a short natural-language request against an existing codebase, graded on observable functional behavior.

**Out of scope** (consistent with DeepSWE's limitations): partial-credit scoring, code-quality/style/performance grading, genuinely ambiguous requests, and non-coding uses such as planning, review, or debugging dialogue.

## 5. Task directory structure

Each task is a self-contained directory, scaffolded empty by /init and filled in over the pipeline. Structure follows the taskbot templates and fixtures.

```
<task-id>/
├── task.toml
├── instruction.md
├── hint.md
├── environment/
│   └── Dockerfile
├── tests/
│   └── test.sh
├── solution/
│   ├── solve.sh
│   └── patch.diff
└── variants/
    ├── alt0.diff
    └── alt1.diff
```

| File / dir | What it contains |
|---|---|
| task.toml | Metadata: repo, base commit, language, Docker image, resource/time limits |
| instruction.md | The actual task prompt shown to the coding agent |
| hint.md | The recorded hint ladder for a task that required multiple turns (Section 8) |
| environment/ | Reproducible Docker image; shallow clone at base commit, network_mode = no-network |
| tests/test.sh | The shipped verifier entry point; hidden tests are populated blind by /gen-tests |
| solution/solve.sh | The ground-truth solution build, hidden from the agent |
| solution/patch.diff | The reference patch, captured from the annotator's checkout |
| variants/alt*.diff | Alternative correct implementations, used by the breadth gate |

Repository-level configuration lives in `.taskbot/config.yaml` at the fork root. Every gate verdict is bound to an artifact hash over the task's tracked files (`taskbot hash --task <task> --files`); editing any tracked path changes the hash, while notes never do — so a verdict can never be silently reused against changed inputs.

**Note:**
- Annotators are expected to only edit the instruction.md file, where they will incorporate the required feature or change. The update should be clearly scoped, and only the instruction.md portion should be passed to the agent for execution.
- In parallel, annotators may update the hints.md file to include any guidance, intermediate steps, or hints they have provided during the process.
- No other files or folders should be modified, accessed, or passed to the model. This constraint ensures isolation, reproducibility, and prevents unintended leakage of task context or solutions.
- Annotators should use frontier models to execute tasks and generate hints.

## 6. The pipeline: a seven-command state machine

The pipeline is a state machine. Each slash-command in a PR comment (or the identical CLI call) advances the task from one state to the next only if its checks pass; anywhere the system flags complexity, spec, or hints, the author reworks against that feedback and re-runs the command.

```
NEW ─/bootstrap→ REPO_READY ─/init→ DRAFT ─/scope→ SCOPED
    ─/verify-spec→ SPEC_ALIGNED ─/gen-tests→ TESTS_DRAFTED
    ─/review→ REVIEWED ─/submit→ PUBLISHED
```

| Command | Precondition | Produces | Needs |
|---|---|---|---|
| /init <slug> | REPO_READY | DRAFT | git + API only |
| /scope | DRAFT | SCOPED | agent judge + GitHub MCP |
| /verify-spec | SCOPED | SPEC_ALIGNED | tier-1 checks, then an agent judge |
| /gen-tests | SPEC_ALIGNED | TESTS_DRAFTED | agent CLI, blind |
| /review [--fast] | TESTS_DRAFTED | REVIEWED | 3 judge models, unanimous |
| /analyse | BENCHMARKING AND FAILURE ANALYSIS | SCORES | 5 or any model runs |
| /submit | REVIEWED | PUBLISHED | nothing |

### /init <slug> — scaffold the task

Pins the default-branch HEAD (an immutable base commit), fetches the checkout, and writes the empty task directory of Section 5 plus `.taskbot/config.yaml`. Needs git and the API only. Locally this is `taskbot new --upstream <url> --slug <slug> --root <dir>`.

### /scope — is the task worth building at all

Before any code is written, the scope agent-judge rubric (GitHub MCP-backed) decides whether the proposed feature is worth building and complex enough by DeepSWE standards, so a doomed task dies cheaply. The annotator fills in instruction.md first. A fail returns feedback to rework.

### /verify-spec — spec, integrity, safety, and the hint gate

Runs tier-1 programmatic checks first (hint triage, gate H1, symbol coverage), then three independent agent-judge rubrics against the same workspace so a failure's cause stays legible:

- **spec-alignment** — instruction.md and the solution correspond: every behavior a test enforces is traceable to instruction text, and nothing tested is left unstated.
- **instruction-integrity** — the correspondence is honest: the instruction discloses the observable symptom, not the fix, and names only what a solver needs, not the reference solution's internal shape.
- **task-security** — solve.sh, patch.diff, and test.sh are safe to execute unsandboxed, because the local backend has no network isolation and a malicious script is a real risk to the annotator's laptop.

Gate H1 is the difficulty enforcement: a zero-hint pass is rejected. A task the agent could solve without hints does not belong in the corpus. This requires hint.md and the ground truth to exist before /verify-spec, so the solution and the hint record are authored between /scope and here.

### /gen-tests — author the verifier, blind

An agent CLI drafts the hidden tests, run blind: invariant I2 guarantees that no fragment of the reference solution reaches the test-authoring workspace, and a leak raises rather than proceeding. Authoring tests without sight of the solution is what forces them to assert observable behavior rather than the solution's internal shape.

### /review [--fast] — the nine gates, then the final quality pass

/review now does the work of what were previously two separate checks. It runs in two phases against the same task directory:

- **Phase 1** — the nine programmatic gates, run in sandboxes with zero LLM (Section 7). `--fast` runs only f2p_base, f2p_solution, and hygiene — the iterate-until-green loop — and deliberately does not advance state or invoke the judge phase, because the two gates that matter most, stub and breadth, have not run yet.
- **Phase 2** — the judge review, which only runs once all nine gates are green. It runs across three judge models and requires a unanimous verdict; a split verdict goes to a human and is never auto-passed on majority. It confirms F2P tests assert through public APIs only, with no private-helper imports, citing file and line for any violation.

Only a full /review — nine gates green, followed by a unanimous judge verdict — produces REVIEWED.

### /analyse — validating failures and measuring model performance

/analyse runs to focus on two core aspects: benchmarking and failure analysis. The goal is to determine whether a task is genuinely challenging for models (model-breaking) or failing due to other inconsistencies.

**1. Benchmarking — measuring task difficulty**

In this phase, the task is executed across a set of state-of-the-art models through multiple trials (e.g., 5 runs per model). The outcome is evaluated based on pass rates.

For example, if a model achieves 2/5 passes, it indicates partial success and signals potential model difficulty. Consistently low pass rates across strong models suggest that the task may be model-breaking, provided the failures are valid.

**2. Failure Analysis — validating the nature of failures**

For all failed trials (e.g., 3/5 failures), a deeper inspection is conducted to determine:

- Whether the failure is caused by the agent/model behavior
- Or due to issues in the task itself (e.g., ambiguity, environment flaws, incorrect expectations)

Only genuine model failures are considered valid signals. If failures are attributed to task design issues, the task is flagged for correction rather than being marked as model-breaking.

**Final Outcome**

A task is marked as model-breaking only when:

- Benchmarking shows low pass rates across strong models, and
- Failure analysis confirms that failures are authentic and model-driven, not task-induced

This step ensures that every model-breaking claim is both quantitatively supported and qualitatively validated.

### /submit — publish

Publishes the task into the corpus. Needs nothing further.

## 7. The nine gates (verifier battery)

The gates are programmatic and LLM-free; they are the part most likely to be subtly wrong, so they run against a real task directory and are themselves regression-tested against three fixtures (example-good, example-weak-verifier, example-overfit-verifier).

| Gate | Passes when |
|---|---|
| f2p_base | the new fail-to-pass tests fail at the base commit (they exercise the unbuilt feature) |
| f2p_solution | all F2P tests pass once the reference solution is applied |
| p2p_base | the selected pass-to-pass regression tests are green at base |
| p2p_solution | those P2P tests stay green with the solution applied (no regressions) |
| oracle | the reference solution earns a full verifier reward (1.0) |
| flake | repeated identical runs agree (no flaky verifier) |
| stub | an auto-generated no-op stub is rejected by the F2P tests |
| breadth | multiple correct alternative implementations (variants/alt*.diff) all pass |
| hygiene | the patch is clean and scoped (limited files, reasonable line delta) |

stub and breadth are the two gates a single reference solution cannot check, and the two directions SWE-Bench Pro's inherited tests failed in: stub catches a weak verifier that accepts incomplete work (a false positive), and breadth catches an overfit verifier that rejects a valid alternative (a false negative). The negative fixtures exist precisely to prove these gates still bite — example-weak-verifier must fail stub, example-overfit-verifier must fail breadth. This is the machinery behind DeepSWE's 1.4%-vs-32.4% verifier-reliability result.

These gates map to DeepSWE's verifier norms: assert through public APIs and observable outputs (enforced by /gen-tests blindness and the review rubric), accept any implementation (breadth), reject incomplete work (stub), screen flakiness (flake), and guard regressions (p2p_*).

## 8. Guideline — Instructions, hints, and verifier authoring

### Instructions (instruction.md)

- Natural developer register, focused on desired functionality, roughly DeepSWE's ~2,000-character scale; not a checklist and not a requirements-plus-interface block.
- No interface leakage: do not name the exact classes, functions, or signatures the verifier expects. instruction-integrity and the symbol-coverage / prompt-drift metrics (taskbot spec) enforce that the instruction names only what a solver needs.
- Prompt–verifier bijection: the instruction describes exactly what the tests enforce, no more and no less — checked by spec-alignment.
- Realism and a specification floor: reads naturally, is maintainer-plausible, and is under-specified enough to require exploration while still naming enough behavior for the verifier to have a surface to assert against.

### Hints (hint.md)

Hints are the difficulty instrument. Governing principle: **a hint narrows the search; it never moves the target.**

- **Required by construction:** gate H1 rejects any zero-hint pass, so a genuine, recorded hint ladder is mandatory for admission.
- **Strictly aligned:** every hint is entailed by, or consistent with, instruction.md and the ground truth; a hint may never introduce a new requirement, contradict the stated behavior, or point at a different feature. A misaligned hint can make a solvable task unsolvable.
- **Progressive and minimal:** tiered least-to-most specific; use the fewest, weakest hints that move the agent forward, so recorded difficulty reflects the task, not the hints.
- **Non-disclosing:** hints never reveal the verifier's assertions, fixture values, or the ground truth's internal structure, and remain implementation-agnostic to preserve breadth.

Hint triage runs as a tier-1 /verify-spec check (lib/hints.py), including rejecting a degenerate failure: note.

### Verifier (tests/)

Authored blind by /gen-tests, asserting public observable behavior, shipped with all fixtures, and proven by the nine gates of Section 7 — grounded so test.sh passes against solve.sh and fails against the unmodified baseline.

---

# The Annotator's Flow

1. **Access** — The annotator is invited by the team to join the organization where their designated repository will exist. (/bootstrap has already been run by an admin at this point, so the repo is REPO_READY.)
2. **The annotator runs /init** — The annotator would run the /init command in the open Pull request, this will automatically fork a branch for the annotator with a scaffolded task folder.
3. **Clone and work locally** — The annotator clones the repository normally and works on it locally, as they would any other codebase.
4. **Analyze the repo and identify the feature** — The annotator studies the codebase and identifies the correct feature to be worked upon. The annotator fills in instruction.md — the feature description the coding agent will read, following the authoring guidelines in Section 8 — and task.toml.
5. **The annotator pushes these changes to the branch and runs /scope** — This checks whether the task described in instruction.md is worth building, per Section 6.
6. **Difficulty-test locally, and record hints** — Only once /scope passes does the annotator interact with a coding agent locally, checking whether it can solve the task in one go. If it cannot, the annotator writes hints (frontier models to be used) — following the hint guidelines in Section 8 (narrows the search, never moves the target; progressive and minimal; non-disclosing) — to prompt the agent toward an accurate, verifier-passing patch, filling hint.md simultaneously with these exact prompts.
7. **The annotator runs /verify-spec** — This runs the hint gate (H1), spec-alignment, instruction-integrity, and task-security checks, per Section 6.
8. **The annotator runs /gen-tests** — This authors the hidden verifier tests blind, per Section 6.
9. **The annotator runs /review** — This runs the nine programmatic gates, then, once all nine pass, the three-judge unanimous review, per Section 6.
10. **The annotator runs /analyze** — This runs benchmarking across frontier agents and a failure-mode analysis, checking whether an agent that solves the task does so through genuine reasoning rather than a shortcut. If every trial passes — meaning the task is too easy — it is rejected immediately, and the annotator must rework the task to increase its complexity before re-running /analyze.
11. **The annotator runs /submit** — Only once /analyze passes is the annotator permitted to run this and submit the task.

**Notes:**

- A gate must pass before the annotator proceeds to the next one. No step above can be attempted out of sequence while an earlier gate is still failing.
- If a gate fails because the task's complexity is insufficient (most commonly at /scope or /analyze), the annotator must make the underlying feature more complex, update instruction.md accordingly, push these changes to the branch again, and run that same set of commands in sequence from the point of failure.
- More generally, for any rework triggered by a failing command at any step above, the annotator must push the updated changes to the branch and run the relevant command again before proceeding.

## Important

Please follow only the Taskbot workflow and the next action shown in the pinned Taskbot status comment.

**Normal flow:**

1. Trigger /init <task-slug> through the designated repository flow.
2. Wait for Taskbot to create the task branch, task PR, and pinned status comment.
3. Write instruction.md, then run /scope.
4. Complete the solution and record hints as instructed, then run /verify-spec.
5. Run /gen-tests and review the generated tests according to Taskbot's instructions.
6. Run /review.
7. After review passes, run /analyze.
8. Run /submit only when Taskbot shows it as the next action.

**Important restrictions:**

- Only the assigned annotator should trigger task commands.
- Do not manually create a task PR if /init stops partway.
- Do not rerun /init against a partially created task.
- Do not edit environment/Dockerfile.
- Do not install missing dependencies on the EC.
- If Taskbot says that no task is associated with the PR, stop and report it. Do not create another PR, rerun /init, or change the task branch to work around the error.
- Do not add guessed metadata to diffs or task.toml.
- Do not use local Taskbot CLI commands unless the official flow explicitly instructs you to.
- Do not skip ahead or substitute /review --fast for the normal full /review unless the platform team specifically requests it for diagnosis.
- Do not repeat commands while the previous job is queued or running.

**If any step fails or leaves incomplete state, stop and report:**

- Repository and PR URL.
- Command that was run.
- Approximate timestamp.
- Exact Taskbot response.
- Relevant error output.
- Last successful state shown in the pinned status comment.

The platform team will repair registration, environment, metadata, or worker problems. After recovery, you will be given the next normal Taskbot command to continue the same flow.
