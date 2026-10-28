# Annotating a private DeepSWE task

Each task in this repository is already written as a complete Harbor task. Your job is to
take the one assigned to you, check it, improve it where needed, and carry it through the
review stages until it is submitted. All of it happens on GitHub, in one pull request.

---

## 1. Getting started

1. **Accept the invitation.** You get an email invitation to this repository. Until you
   accept it you cannot see the code or your pull request.
2. **Find your pull request.** It is titled `Task: <slug>` and assigned to you. It
   compares your task branch `task/<slug>` against `main`.
3. **Read the pinned status comment** at the top of the PR. It shows the stages, which ones
   have passed, and what to do next. Keep coming back to it.
4. **Check out only your branch.** You never need the others:

   ```bash
   git clone --single-branch -b task/<slug> https://github.com/deccan-taskbot-private/<repo>.git
   ```

## 2. What is in a task

Everything for your task lives in `tasks/<slug>/`:

| Path | What it is |
|---|---|
| `instruction.md` | What the agent is asked to do. Describe behaviour, not implementation. |
| `task.toml` | Metadata (title, difficulty, explanations) and container settings. |
| `environment/Dockerfile` | The container the agent works in. |
| `environment/app/` | The project code at the starting point. |
| `tests/Dockerfile` | The separate container the tests run in. |
| `tests/app/` | A second copy of the same starting code, for the test container. |
| `tests/test.patch` | The hidden tests, as a patch applied on top of the code. |
| `tests/config.json` | Which tests must go from failing to passing (`f2p_node_ids`) and which must keep passing (`p2p_node_ids`). |
| `tests/test.sh`, `tests/grader.py` | Runs the tests and grades the result. |
| `solution/fix.patch`, `solution/solve.sh` | The reference solution and the script that applies it. |

## 3. Rules for editing

- **Change files only inside `tasks/<slug>/`.** A change anywhere else fails review.
- **Keep the two app copies identical.** If you change something in `environment/app`,
  make the same change in `tests/app`. Review names the first file that differs.
- **Tests live in `tests/test.patch`.** To add or change a test, edit the patch, then keep
  `tests/config.json` in step: every new failing-then-passing test goes in `f2p_node_ids`,
  every test that must stay green goes in `p2p_node_ids`. A test may not be in both.
- **Keep the solution honest.** `solution/fix.patch` must make every F2P test pass and keep
  every P2P test passing, without editing the tests.
- **No network.** Tasks run with networking off. Anything the task needs must be in the
  Dockerfiles.
- **Do not merge, close or retarget the PR,** and do not push to `main`. The PR stays open
  for its whole life; changes to `main` are reverted automatically.
- **Work only on your own task.** You can read other tasks in this repository, but pushes
  to another person's branch are reverted, and commands on their PR are refused.

## 4. The stages

Drive the task by commenting a command on your PR. Run them in this order:

```
/scope → /verify-spec → (/gen-tests) → /review → /benchmark → /analyze → /submit
```

| Command | What it checks |
|---|---|
| `/scope` | The task is a real, well-scoped piece of work for this codebase. |
| `/verify-spec` | `instruction.md` asks for what the tests check and the solution implements: nothing missing, nothing extra, no hidden requirements. |
| `/gen-tests` | Optional. Only when the task needs more tests than it has. It will not overwrite existing tests unless asked. |
| `/review` | The full quality gate: the task builds; the F2P tests fail on the starting code and pass with the solution; the P2P tests pass both times; results are the same on every run; the solution has no leftover debug code; then a rubric review of the instruction, tests and solution. |
| `/benchmark` | Two AI agents attempt the task five times each. It must **run**, but its result does not block you: if agents solve it too often, the status comment shows a warning ("too easy"), and the result is recorded with the task. |
| `/analyze` | Explains every attempt: the agent's mistake, or a problem in the task. It must run too; what it concludes is recorded, not blocking. Read it: it is the best evidence of what to fix. |
| `/submit` | Submits the finished task once `/scope`, `/verify-spec` and `/review` have passed and `/benchmark` and `/analyze` have run, all on the current content. The PR is **not** merged; it stays open as the record. |

**When every agent attempt fails** (optional). A task no agent solves may be broken
rather than hard. After `/benchmark` shows every attempt failing and `/analyze` says the
agents, not the task, were at fault, you may show it is solvable with a few hints:

1. Write `hint.md` in the task folder, one hint per line:

   ```
   - [approach] The cache key has to include the locale, not only the path.
   - [spec] An empty input returns an empty list rather than raising.
   ```

   `[approach]` nudges toward the solution; `[spec]` is something the instruction should
   have said. At most five hints, a sentence or two each, no code, and an `[approach]`
   hint may not name what the reference solution adds.
2. Comment `/hint-run`. One agent gets five more tries with your hints added to the
   instruction. One pass shows the task is solvable. At most two rounds per version of
   the task, and never the same hints twice.
3. Before `/submit`, write every `[spec]` hint into `instruction.md` and remove it from
   `hint.md`: the instruction was incomplete.

Hinted attempts never count toward how hard the task is, and `hint.md` never ships.

## 5. After every push

When you push a change, the checks it affects are marked out of date, and the status
comment shows which stages to run again. Earlier stages that your change did not touch stay
passed.

## 6. Getting help

- A failed stage explains what went wrong and which file to look at, in the PR comment.
- If a result looks wrong, or you are stuck, comment on your PR and tag your coordinator.
