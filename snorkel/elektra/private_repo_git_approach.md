# Private Repository Tasking (Git approach): Context tab

Transcribed from the Google Doc "Private Repository Tasking (Git approach)", Context tab, shared by Zaheer on 2026-10-28. The doc has a second tab, "Annotator Workflow", that isn't transcribed here yet; it covers the tasking process, the purpose of each gate, how runs work and how tasks should be executed.

## Objective

This workflow defines how annotators should verify the quality of coding tasks prepared in the DeepSWE format. The annotator's role is not to solve the task but to judge whether it is fair and reliable to give to coding agents. Check that:

- the instructions are clear
- the expected change is well-scoped
- the tests correctly capture the intended behavior
- the full task package is complete and usable for evaluation

If the instructions or test cases need changes, make the corrections and run the quality checks provided.

## Task structure

Every task is based on a unique codebase that resembles production-level code, with multiple files in different languages (Python, Java, JS, etc.). Tasks appear on GitHub once they are assigned to you.

Example public tasks: https://github.com/datacurve-ai/deep-swe

Sample repo layout (the task-specific files are listed first):

```
workspace/
├── instruction.md
├── environment/
│   └── Dockerfile
├── tests/
│   ├── test.sh
│   ├── test.patch
│   └── repo based test files
├── solution/
│   ├── solve.sh
│   └── solution.patch
├── task.toml
├── repo folder1/
│   ├── file1
│   └── file2
└── repo folder2/
    └── ...
```

Extra files or folders may be present if edits, updates or hints were added to the task.

- **instruction.md**: the task or issue description the agent is expected to solve.
- **tests/**: the verifier files (P2P tests and F2P tests, with the patch) that check whether the expected behavior is captured.
  - **P2P (pass to pass)**: tests of existing functionality on the base repo, not the task. They must pass both before and after the solution patch is applied, so they protect backward compatibility.
  - **F2P (fail to pass)**: tests of the task itself. They must fail before the solution patch is applied and pass after.
- **solution/**: the reference solution, which you can use for the quality review.
- **task.toml**: task metadata (repo, base commit, language, Docker image, resource/time limits).
- **environment/Dockerfile**: the environment setup used to build the task. A repo can contain two Dockerfiles, one at the root and one under environment/. Only the one under environment/ is task-specific, and only that one is checked during annotation.
- **All remaining files and folders** belong to the base repository.
- **Check the tests:** they must match the behavior the instruction asks for, must not be overly broad or unrelated, and must fairly separate a correct fix from an incorrect one.
- **Align the instruction and tests with the solution patch:** treat solution/solution.patch as the golden truth. The instruction must cover every aspect of the patch, and the tests must cover it completely.

| File / dir | What it contains |
|---|---|
| task.toml | Metadata: repo, base commit, language, Docker image, resource/time limits |
| instruction.md | The task prompt shown to the coding agent |
| hint.md (if needed) | The recorded hint ladder for a task that needed multiple turns |
| environment/ | Reproducible Docker image; shallow clone at base commit, network_mode = no-network |
| tests/test.sh | The verifier entry point; hidden tests are populated blind by /gen-tests |
| solution/solve.sh | The ground-truth solution build, hidden from the agent |
| solution/patch.diff | The reference patch, captured from the annotator's checkout |
| variants/alt*.diff | Alternative correct implementations, used by the breadth gate |

Repo-level configuration is in `.taskbot/config.yaml` at the fork root. Every gate verdict is bound to an artifact hash over the task's tracked files (`taskbot hash --task <task> --files`). Editing any tracked path changes the hash; notes never do.

## Pipeline (no /init: the tasks already exist)

| Command | Precondition | Produces | Needs |
|---|---|---|---|
| /scope | DRAFT | SCOPED | agent judge + GitHub MCP |
| /verify-spec | SCOPED | SPEC_ALIGNED | tier-1 checks, then an agent judge |
| /gen-tests | SPEC_ALIGNED | TESTS_DRAFTED | agent CLI, blind |
| /review [--fast] | TESTS_DRAFTED | REVIEWED | 3 judge models, unanimous |
| /benchmarking | benchmarking against Luna and Sol | SCORES | 5 or any model runs |
| /analyse | benchmarking and failure analysis | SCORES | 5 or any model runs |
| /submit | REVIEWED | PUBLISHED | nothing |

The nine gates (f2p_base, f2p_solution, p2p_base, p2p_solution, oracle, flake, stub, breadth, hygiene) are unchanged; see README.md.
