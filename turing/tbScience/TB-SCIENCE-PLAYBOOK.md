# TB-Science task playbook (Turing project)

Prepared 18 October 2026 from the full working history of two tasks built for Gourav Kumar:
`heteroazeotrope-audit` and `cstr-bifurcation-audit`. Both passed every platform node, and in
both GPT-6 Sol (max) and Claude Opus 5.5 (low) failed at pass@1 for scientific reasons.

Give this whole file to the next AI assistant before it starts a new task. Sections 0, 4, 6 and
7 matter most.

---

## 0. Rules for the assistant (read first)

1. **The goal of every task** is to pass every platform node: package checks, oracle check, auto
   review, trials, trial-based review and manual review. Both GPT-6 Sol (max) and Claude Opus 5.5
   (low) must also fail at pass@1, and the reviewer's reading of their transcripts must confirm
   that the failures are scientific.
2. **The platform's own checks override the guideline document.** For example, the V2.2 guideline
   says `field`/`subfield`, but the platform's qualityChecks require `category`/`subcategory`. When
   a platform check asks for X, do X. Never revert a change the platform asked for.
3. **The user uploads and submits.** Never submit, upload or publish anything yourself.
4. **No paid API calls, purchases or frontier-model trials** without explicit permission. You
   cannot run the Sol or Opus trials; the platform does. Never claim that the models fail until
   the platform's trials show it.
5. **No tricks.** No hidden ambiguity, tolerance gaming or formatting traps. The trial reviewer
   reads the transcripts and fails the task if a model failed because of the instruction. The
   difficulty must come from the science. The user once suggested tricks; the answer was no, and
   the honest route worked twice.
6. **Never put credentials, tokens or auth files** in a task, a ZIP or a message.
7. **Evidence logs, backups and notes stay outside the task ZIP.**
8. **Before the first upload, list every constraint the verifier enforces** and confirm that
   each one is written in the instruction or the named spec. Every limit, bound, length,
   file rule, environment variable, count and comparison counts. This habit alone would have
   prevented most of our failed review rounds. Each auto review costs the user about $1.2 to
   $2.2, and he said "we can't afford this".

---

## 1. Working with Gourav

- He writes short, casual messages, sometimes in Hinglish ("bhai", "kya pta", "man"). Answer in
  plain English and keep it short.
- He wants speed. Silence frustrates him, and so do long verification runs he didn't ask for.
  While you work, post a one-line status every few minutes. Before anything that takes more
  than about 10 minutes, say what it is and why it's needed.
- Every time you deliver a build, send the ZIP file itself and state its **file name, version
  (from task.toml) and SHA256**. The file name stays the same across builds, so the version and
  hash are how he tells builds apart. He often asks "which zip do I upload": answer with exactly
  one file.
- When he pastes a review result, say in 2 to 4 bullets what failed and why, then fix it,
  re-verify only what the change could affect, and send the ZIP.
- If a platform message looks wrong to you, check where it came from before arguing. In task 1 I
  reverted a correct platform request because the guideline document disagreed. The upload was
  rejected and he was rightly angry.
- He logs time in the platform's "Complete Conversation" dialog at the end of each platform
  session (section 13).

**Author facts** (fixed; use exactly as written):

| Field | Value |
| --- | --- |
| Author name | Gourav Kumar |
| Author email | gouravantalvines20@gmail.com |
| Author profile | https://www.linkedin.com/in/gourav-kumar-193b651b5 |
| Author organization | Independent Researcher |
| Conflicts of interest | Engaged as a paid contractor by Turing to author this task. |
| Relevant experience | B.Tech in Computer Science and Engineering; research-engineer contractor on scientific computing benchmark tasks (Python data analysis, numerical simulation, Docker-based validation). No industrial refinery employment. |
| Research advisor | (blank) |
| Referred by | (blank) |
| AI disclosure | Prose and code are AI-drafted and AI-revised under the author's direction. Never claim unaided human authorship, a qualified endorsement or a publication. |

---

## 2. The two submitted tasks

| | heteroazeotrope-audit | cstr-bifurcation-audit |
| --- | --- | --- |
| Domain / category / subcategory | engineering-sciences / chemical-engineering / separation-thermodynamics | engineering-sciences / chemical-engineering / reaction-engineering |
| Science | NRTL calibration for water/1-butanol, global phase stability, exact temperatures where miscibility gaps appear or vanish (critical vs three-phase, metastable changes excluded), calorimetry-constrained uncertainty, legacy-script diagnosis | jacket-cooled CSTR with propylene oxide hydrolysis (Furusawa 1969, via Fogler): every fold and Hopf point to 0.002 K, Hopf criticality from the first Lyapunov coefficient, stable oscillation windows with each endpoint classified, attractors at operating points, legacy-script diagnosis |
| What the agent delivers | a program that the verifier reruns on held-out inputs, plus saved reports and `diagnosis.json` | same pattern |
| Graded calls | 28 nominal (60 s each) and 9 uncertainty (600 s each) | 28 (120 s each) |
| Limits | agent 10800 s; verifier 7200 s at 1 CPU / 2048 MB | same |
| Final version | 10.1.5 | 1.3.1 (after manual-review rework) |
| Trials: reward (nodes passed) | Sol 0.0 (29/42); Opus 0.0 (39/42) | Sol 0.0 (26/30); Opus 0.0 (27/30) |
| Failed rounds before passing | 2 auto reviews (3.9, 4.6), 1 trial review (4.5), 2 package-check rejections | 2 auto reviews (3.2, 4.6), 1 oracle check, 1 trial review (4.5), then 1 manual rework (4.7) |

How the models failed:

- **Task 1.** Sol mixed up the two event kinds (three-phase vs critical) and reported spurious or
  missed gap events. Opus got the concept right, but its numerics lost miscibility gaps pressed
  against a pure-component edge (x1 from about 1e-41 to 6e-6), so it declared a gap closed that
  was not. It also divided by zero when a composition reached 1.0.
- **Task 2.** Sol missed a bifurcation in one residence-time case and mislabelled
  oscillation-window ends (it reported a fold of cycles where the spec's convention gives a
  saddle connection). Opus claimed a saddle connection in a recipe with only one steady state,
  where no saddle exists: the orbit really dies in a fold of cycles 4e-5 K from a near-Bautin
  Hopf point. It also placed a fold of cycles 0.026 K off, against a 0.01 K tolerance.

Both models got all the "standard" parts right: steady states, stability classes, fold
locations, schemas and the CLI.

---

## 3. The platform pipeline, node by node

These are the nodes in the order we met them after an upload:

1. **Script validation: qualityChecks (the "Task Package" check).** A static package check
   (see section 6 for what it rejects).
2. **oracleValidation ("Oracle Check").** The platform runs your oracle on its own hardware.
   Every oracle trial must score 1. It can fail even when everything passes locally (section 14,
   floating point).
3. **Auto review.** An LLM reviewer scores about 11 dimensions. You get a score (we saw 3.2 to
   4.7) and a cost. The review fails if any one dimension is below threshold. Section 5 lists
   the checks.
4. **Trials (pass5Eval / pass5RewardValidation).** The roster is `openai/gpt-6-sol` (reasoning
   max) and `anthropic/claude-opus-5-5` (reasoning low), each run once with the terminus-2
   agent. Every model in the roster must produce a harbor_trial. If one is missing ("configured
   model 2 has no harbor_trial evaluation"), the platform runner failed, not the package: retry
   the evaluation run.
5. **Trial-based review.** Dimensions: Task Clarity, Test Failure Attribution, Error Message
   Actionability, Test Accuracy, False Positive Risk, Requirement Coverage, Environment Adequacy,
   Trajectory Integrity.
6. **Evaluation comment.** A free-text box that appears after all nodes pass. Template in
   section 13.
7. **Complete Conversation dialog.** Duration and Notes. Details in section 13.
8. **Manual review by a human.** Can return the task as "rework" for any dimension, including
   ones the auto review never showed: tests - Structure, tests - Trust boundary, environment -
   Cleanliness, instruction.md - Contested conventions resolved, instruction.md - Scoring
   transparency.

Quirks to know:

- **A redisplayed old review** shows the same score, cost and token count as before. If two
  "new" results match exactly, the new build has probably not been reviewed yet. Check which
  version the platform says it reviewed.
- **Wrapping folder.** When you download a package from the platform, its files sit inside a
  `<submission-id>/` folder. Our upload ZIPs put the six entries directly at the ZIP root. The
  platform accepted both.
- **Trial results** come as `root-folder_N.zip`, containing `agent/trajectory.json`,
  `agent/terminus_2.pane`, `verifier/ctrf.json`, `verifier/test-stdout.txt`,
  `verifier/reward.txt`, `artifacts/root/results/...`, `result.json` and `trial.log`. Ask the
  user for these before writing the evaluation comment. Read the failed nodes in `ctrf.json`,
  rerun the model's submitted program locally to confirm the verdicts, and check every disputed
  value against the independent reference.
- **Similarity-check problems.** An HTTP 429 or a blocked search during the similarity check is
  an infrastructure fault, not plagiarism.
- **Trial validity after changes.** Changes made after the trials that are documentation or
  packaging only (no verifier, oracle or answer-key change) keep the trial outcomes valid. Say so
  in the evaluation comment.

---

## 4. Every finding we received and its fix (do not regress)

### Package and script validation

| Finding | Fix |
| --- | --- |
| Run 27883 (earlier project): root `.gitignore` and `harbor-canary` markers rejected | No canary strings anywhere, and nothing at the root except the six entries |
| A friend's task on the same platform: `tests/.dockerignore` and `tests/truth/SHA256SUMS` rejected | `tests/` may hold only Dockerfile, test.sh, test_*.py and code or data files with whitelisted extensions (section 6). No .md, .log, dotfiles or extensionless files |
| Task 1: tests/reference/README.md and regeneration.log rejected | renamed to .txt at the time. Better: keep non-grading files out of `tests/` entirely (see manual review) |
| `task.toml does not match the schema 1.4 structure: [metadata] category is missing (found field), [metadata] subcategory is missing (found subfield)` | Use `category` and `subcategory` under `[metadata]`, keeping `domain`. Ignore the guideline's field/subfield wording |
| Oracle Check: `oracle trial ... has reward 0` (it passed locally) | Hardware-dependent numerics: under the AVX-512 OpenBLAS kernel, one Newton trial step led the stiff integrator into a crawl and blew the 120 s limit. Fix: give every integration a work budget (about 10× a normal call's right-hand-side evaluations) and require it to reach its end time; otherwise reject the step like any failed step. Then rerun all cases under five kernels (section 12) |

### Auto review, task 1 (score 3.9)

| Dimension | Finding | Fix |
| --- | --- | --- |
| Execution contract | the spec said 14 held-out calibrations and 7 uncertainty calls; the verifier ran 18 and 9 | state the exact counts of shipped inputs, held-out inputs and total calls, and update them whenever cases are added |
| Execution contract | limits given without saying wall-clock or CPU time | "All time limits are wall-clock limits, not CPU-time limits", measured by the verifier from process start to exit |
| Anti-cheat: Isolation | `subprocess.run(..., timeout=)` with pipes and no process group | `Popen(start_new_session=True)`, output to files, `os.killpg(SIGKILL)` on timeout and in `finally`, kill leftover runner-uid processes (template in 9.7) |
| Coverage: boundary leniency | accepted 0.0000999995 when the spec bound is 0.0001; a 2e-5 tolerance also accepted it | validate exact bounds with no slack; clip in both the oracle and the reference |
| Runtime gate | `shutil.copyfile` on a FIFO planted at the artifact path hangs before the timeout starts | regular-file check (no symlink, FIFO or device) and a size check before every copy or read |

### Trial review, task 1 (score 4.5, Task Clarity)

| Finding | Fix |
| --- | --- |
| The runner sets `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1, but the spec doesn't disclose it | state the exact environment passed to the program: every variable and its value |

### Auto review, task 1 (score 4.6, Execution contract)

| Finding | Fix |
| --- | --- |
| The spec claimed "one core", but `[verifier.environment]` declared no cpus; `[environment]` is the agent container | declare `cpus`, `memory_mb`, `storage_mb` and `gpus` in `[verifier.environment]`; state the same values in the spec; run the full verifier under `docker run --cpus=1 --memory=2048m` before upload |

### Auto review, task 2 (score 3.2)

| Dimension | Finding | Fix |
| --- | --- | --- |
| Writing quality | the opening paragraph was scenario and backstory (plant, glass lining, pilot-plant anecdote) | open with the objective: "Write `/root/results/x.py`, a program that ..." |
| Output contract | the verifier capped `recipe_id` at 1 to 100 characters; the spec said only "string" | state every length, range and type limit the verifier enforces |
| Execution contract | the 1 MB limit on each JSON file the verifier reads, and the storage allocation, were not stated | add a "file conventions" paragraph (regular file, non-empty, at most 1 MB, UTF-8, no duplicate keys) and state the storage |
| Genuine solution | `solve.sh` copied a stored `diagnosis.json` | compute every artifact at run time; `diagnose.py` finds the witnesses by running the legacy script and the corrected program on candidates derived from the shipped inputs |
| Coverage | a defect description of "x" passed although the instruction asked the agent to "name" defects | say explicitly that the text is required but not graded and that the witness is what is graded |

### Auto review, task 2 (score 4.6, tests Correctness)

| Finding | Fix |
| --- | --- |
| The spec said the attractor temperature is "repeated"; the verifier allowed a 1e-6 K difference | exact equality, exactly as the spec says |
| Conversion accepted -1e-10, although the spec says [0, 1] | exact bounds |
| No rationale for the conversion (1e-4) and orbit-extreme (0.05 K) tolerances | add a README table giving the measured basis of EVERY graded tolerance, plus a reproducible study (section 11) |

### Trial review, task 2 (score 4.5, Requirement Coverage)

| Finding | Fix |
| --- | --- |
| Behaviours the spec requires were exercised by no executed case: an empty `operating_points` list, and an oscillation window with no event inside the recipe window | add a held-out case for each, with expected values from the independent reference; update every count; name both behaviours in the spec's list of covered structures |

### Manual review, task 2 (score 4.7, tests - Structure)

| Finding | Fix |
| --- | --- |
| `tests/reference/README.txt`, `regenerate.py` and `tolerance_study.py` are not used by grading | removed them from `tests/` and folded their content into a README.md section "Reproducing the reference values". The reviewer suggested a top-level `validation/` folder, but that breaks the six-entry root rule, and the guideline names the README as the home for authoring material |

### Earlier lessons from the original project handoff

- An earlier reactor task (review 431946) failed on "real workflow" and "domain-specific crux"
  even though its writing passed. The task must be a real research or plant workflow with a
  crux specific to the domain.
- The "expert voice" rejection covered the named spec as well as instruction.md. Keep
  development narration, harness-budget justifications, duplicated acceptance paragraphs and
  padding out of the spec as well.
- Use `pytest -rA` explicitly. Award a binary reward only when the full expected set of distinct
  nodes is present, the CTRF report is consistent and failures happen in the call phase. A pytest
  exit status above 1 means no score.
- For statelessness, prose is not enough: provide a fresh scratch directory, make shared
  writable paths unwritable, clean up processes, protect the log directory, and have a stateful
  control fail.
- Don't promise support (for example, leading comment lines in inputs) that no input or test
  exercises.

---

## 5. What each review dimension checks

These are the numbered checks quoted in our review texts. Use them as a self-review before you
upload.

**instruction.md: Writing quality and form** (blocks completion)
1. The opening is a direct objective, not scenario or backstory. Contract context, such as naming
   the legacy script or the CLI, is fine.
2. No algorithm, implementation sequence or library is prescribed.
3. No private verifier functions, assertions or internal paths are disclosed.
4. The closing line is exact: `You have X seconds to complete this task. Do not cheat by using
   online solutions or hints specific to this task.` X equals `[agent].timeout_sec` as a plain
   integer.
5. All paths are absolute.
6. Terminology matches the spec, and no sentence has two meaningfully different readings.
7. The markdown is clean: well-formed fences, backticked paths, no stray HTML.

**instruction.md: Output contract**
1. Every artifact path in task.toml is named as required in the instruction.
2. Every schema is given.
3. Every constraint the verifier enforces is stated (string lengths, ranges, types).
4. Vocabularies are closed.
5. Counts are stated.
6. Schemas are described in prose, not only by example.
7. The image creates the output directory and does not pre-place outputs.
8. Every scored property is named.
9. Stated tolerances match the verifier exactly.
10. Binary grading is stated.
11. Absolute and relative tolerances are distinguished.

**instruction.md: Execution contract** (blocks completion)
1. Applicability: does the verifier execute agent code?
2. Held-out inputs are declared accurately: how many, schema, domain and workload. Counts must
   match the verifier exactly.
3. The separate runtime is disclosed: offline, Python and library versions, unprivileged user,
   writable locations, environment variables.
4. Resource limits match `[verifier.environment]` (cpus, memory_mb, storage_mb) and every
   per-call, per-file and total limit.
5. The CLI and report contract are stated, along with exit status, a fresh working directory
   and no state between calls.
6. The clock basis is stated: wall-clock or CPU time.
7. All of the above appear in instruction.md or a spec it names.

**instruction.md: Author-chosen items stated**, **Contested conventions resolved** and **Scoring
transparency** (manual review): every convention you picked is written down (sort orders,
counting rules, tie-breaks, merge rules, reporting for empty lists, endpoint conventions), and
the instruction states what is scored and at what unit.

**instruction.md: Similarity** (blocks completion): the task must not be too close to existing
TB-Science tasks or to your own earlier ones.

**task: Scientific validity** (blocks completion): the specialist's method, standard practice and
a defensible answer, with tolerances drawn from the science. Cite the source of the data.

**task: Security and malicious behavior**: nothing harmful.

**solution: Genuine solution** (blocks completion)
1. Outputs are computed from parsed input.
2. There is no stored or constant answer, and no copied artifact.
3. Nothing reads from `tests/`.
4. Large source lives in separate files, with no big heredocs in solve.sh.
5. There is no working-directory assumption; use absolute paths.
6. Invoked and generated code resolves.

**tests: Reference-Object Anti-Cheat** (blocks completion)
1. Authorised inputs only: the verifier reads the declared artifacts and nothing else from the
   agent.
2. Independent recomputation: results are checked against verifier-held references, never
   against self-reported scores.
3. Isolation protocol: process group, killpg, unprivileged uid, file-backed output.
4. Reference-object anchoring: returning shipped inputs or the legacy program verbatim cannot
   earn reward.

**tests: Correctness, Coverage, and Determinism** (blocks completion)
1. Independent source: the expected values do not come from the oracle.
2. Coverage and docstrings:
   - requirement → verifier;
   - boundary exactness;
   - input-domain variety;
   - verifier → requirement (no unpublished constraints);
   - leniency (never accept values the spec forbids);
   - do-not-modify;
   - a docstring on every test.
3. Contract before correctness: validate the schema before comparing values.
4. Runtime gate: wall-clock bound, regular-file checks before any copy or read.
5. Determinism: pinned hash seed and thread counts; clocks only in timestamps.
6. Threshold rationale: measured rationale for EVERY graded tolerance.
7. Outcome-only grading: never inspect the agent's source.

**tests: Structure** (manual review): `tests/` holds only files on the grading path.

**tests: Trust boundary** (manual review): agent output is untrusted. The verifier runs it
sandboxed and never lets it touch the reward.

**environment: Clean and Complete / Cleanliness**: pinned packages, complete data, no solution,
test or answer material in the agent image.

**Trial review: Task Clarity** (blocks completion). It checks:
- usable run evidence (no truncation);
- the roster outcome;
- conventions and definitions;
- hidden requirements;
- execution-contract completeness (this is where the undisclosed thread variables were caught);
- identifiability;
- thresholds and submittability;
- pragmatic consistency (paths, timeout match);
- instruction-caused misunderstanding.

The reviewer reads the trajectories. "None confirmed" on the last item is what makes a failure
count as scientific.

**Trial review: Requirement Coverage** (blocks completion). Every behaviour the spec requires
must be exercised by at least one executed case, covering structure, value domains, field
formats, ordering, thresholds, derived quantities, prohibited actions and explicitly ungraded
items. Other trial dimensions: Test Accuracy (blocks), False Positive Risk, Test Failure
Attribution, Error Message Actionability, Environment Adequacy, Trajectory Integrity (blocks).

---

## 6. Pre-upload checklist

**Package layout**
- [ ] The ZIP root holds exactly `instruction.md`, `task.toml`, `README.md`, `environment/`,
  `solution/`, `tests/`. No other entries: no authoring/, docs/, validation/ or .gitignore.
- [ ] No canary strings ("canary", "BENCHMARK DATA SHOULD NEVER") anywhere. No secret-shaped
  strings. No `__pycache__` or .pyc files.
- [ ] `tests/` holds Dockerfile, test.sh, at least one test_*.py, and only grading-path files.
  Allowed extensions: .py .sh .r .jl .c .h .cpp .hpp .f .f90 .m .csv .tsv .json .jsonl .ndjson
  .npy .npz .parquet .parq .h5 .hdf5 .fits .pkl .txt .dat .nc .mat .xyz .pdb .cif .fasta .fa
  .fastq .vcf .sdf .mol2 .gz. No .md, .log or dotfiles. Even a .txt README that grading doesn't
  use was flagged by manual review.
- [ ] Build the ZIP deterministically (sorted entries, fixed timestamps) and record its SHA256.

**task.toml**
- [ ] `schema_version = "1.4"`.
- [ ] `name = "turing/<folder-name>"`. The folder name is at most three lower-case hyphenated
  words.
- [ ] `version` bumped on every change. Use x.y.z: bump the patch for packaging fixes and the
  minor version for content.
- [ ] Top-level `artifacts` lists every file the verifier reads.
- [ ] `[metadata]` has `domain`, **`category`**, **`subcategory`**, `reward_type = "binary"`,
  `source = "Written by PhD annotators"`, `public_overlap` (state any overlap honestly, for
  example published kinetics from a textbook), and the author fields.
- [ ] `network_mode` is on all four tables: `[verifier]` and `[verifier.environment]`
  "no-network", `[agent]` and `[environment]` "public".
- [ ] `[verifier.environment]` declares `cpus`, `memory_mb`, `storage_mb` and `gpus`, and they
  match the spec.
- [ ] `[agent].timeout_sec` is a plain integer equal to the instruction's closing line.

**Instruction and spec**
- [ ] The instruction opens with the objective, and names the spec as authoritative for the
  model, schemas, tolerances and execution contract.
- [ ] Shipped and held-out counts are exact (for example, "6 shipped + 22 held-out = 28 calls").
  The held-out domain and the kinds of structure covered are stated; their contents are never
  revealed.
- [ ] Every verifier constraint is disclosed: per-call wall-clock limit, total verifier
  wall-clock limit, the clock basis, CPU, memory, storage, GPU, thread variables, the exact
  environment passed, the offline unprivileged runtime, the fresh working directory as the only
  writable location, statelessness, program size limit, file conventions for every JSON file read,
  string lengths, exact key sets, integer vs float, ranges, sort orders and counting rules.
- [ ] Every comparison is stated exactly as the verifier performs it (element-wise in a stated
  order, lengths must match, which fields are exact, which use a tolerance, absolute or relative).
- [ ] Every convention you chose is stated, for example a merge rule ("a fold of cycles within
  the endpoint tolerance of a saddle connection is reported as homoclinic") or the SNIC rule.
- [ ] Ungraded items are explicitly called ungraded (for example, free-text defect
  descriptions).
- [ ] Input identifiers carry no answer information. Rename shipped files from "hopf_island" to
  "commissioning_03".

**Solution**
- [ ] It computes everything at run time. No stored answers, not even for a diagnosis file.
- [ ] solve.sh uses absolute paths, calls separate script files, and sets the thread variables
  to 1.
- [ ] Every iterative or integration loop has a work budget, so no input can hang it on other
  hardware.
- [ ] The slowest call is at most about 20 % of the per-call limit on one CPU.

**Verifier**
- [ ] test.sh writes 0 to reward.txt first; finalize_reward.py writes 1 only after a complete,
  consistent CTRF report.
- [ ] The hardened runner (template 9.7) is used: unprivileged uid, start_new_session, killpg,
  file-backed output, a regular-file guard before every read or copy, a size cap, strict JSON
  that rejects duplicate keys.
- [ ] Contract validation runs before comparison, and every failure message names the field.
- [ ] Validation is exact wherever the spec is exact. No slack on bounds or repetitions.
- [ ] Every spec-required behaviour is exercised by at least one case, including the edge
  behaviours: empty lists, nothing to report, a feature spanning the whole window, boundary
  values.
- [ ] Every test function has a docstring.

**Evidence** (run locally, recorded in the README and outside the ZIP)
- [ ] The oracle scores 1 and nop scores 0 in plain Docker and in Harbor.
- [ ] An offline oracle run (`docker run --network none`) completes and writes all artifacts.
  The README's Verification section says so.
- [ ] A full verifier run under the declared allocation (`--cpus=1 --memory=2048m`) scores 1,
  with time margins noted.
- [ ] Planting a FIFO at the program path gives reward 0 with no hang.
- [ ] The wrong-method controls all score 0.
- [ ] Under five OpenBLAS kernels, the oracle reproduces the answer key on every case.
- [ ] The independent reference agrees with the oracle within tolerance on every case, and the
  agreement table is in the README.

---

## 7. Making both models fail: what actually worked

**The evidence.**
- In R9 of task 1, Opus passed 36/36 and Sol failed one case. Opus 5.5 low is very good at
  careful numerics: dense root grids, Newton polish, edge refinement, catching its own bugs.
- A sweep over 1,366 in-domain cases found almost nothing that Opus failed reliably.
- Conclusion: **picking harder input cases does not stump Opus.** You need a deliverable that
  requires a concept or method the models skip or get subtly wrong.

**Traps that worked in both tasks.**
1. **Exact location of discrete events** (to 0.002 K) where the obvious method is a parameter
   mesh. Include features narrower than any affordable mesh: a fold and a Hopf point 0.053 K
   apart, or a second miscibility gap that exists for only 0.1 to 0.5 K.
2. **Classification between kinds that look alike**: critical vs three-phase; fold vs Hopf; the
   end of an oscillation window as Hopf, fold of cycles, homoclinic or window end.
3. **Stable vs unstable or metastable.** Metastable critical points are not events. A trace-sign
   test mislabels saddles. An unstable middle branch is not an operating state.
4. **Near-degenerate points**: a Hopf point about 1 % from a Bautin point, where criticality must
   be computed rather than assumed, or gaps hugging a pure-component edge.
5. **Following a family of solutions to where it really ends.** Periodic-orbit continuation runs
   to saddle connections or folds of cycles; models stop at the local event.
6. **Many graded nodes with all-or-nothing grading.** Opus failed only 3 of 30 nodes and 3 of 42.
   One trap is not enough. Build five or more independent traps and spread them over many
   held-out cases, so each model is likely to hit at least one.

**Framing that the platform accepted twice: "audit a legacy script".**
- Ship a plausible legacy script with three or four real scientific defects: a mesh sweep, a
  trace-only test, assumed supercriticality, a trace-only stability test.
- The agent writes a corrected program and a `diagnosis.json` with executable witnesses. Each
  witness gives a recipe, a quantity, the legacy value and the correct value.
- The verifier runs a pristine copy of the legacy script and an independent computation on each
  witness, and requires the two values to differ.
- Require at least three distinct quantity types, and say that the free-text description is not
  graded.

**Wrong-method controls.** Implement the shortcuts a model would plausibly take (legacy script,
mesh-only, trace-only, assumed supercritical, windows from Hopf points only, spinodal-count
events) and grade each with the verifier's own functions. All must score 0. Report the pass
counts in the README, for example "legacy 1/28, supercritical 20/28, Hopf-only windows 14/28,
0.05 K mesh 3/28".

**Keep it legitimate.**
- Every definition, convention and limit is in the spec.
- The tolerance is far coarser than the method-to-method spread and far finer than the nearest
  wrong answer.
- When a model fails on a case that a reviewer could call borderline, say so honestly. Example:
  Opus's edge-hugging gaps, where the defence was "dilute-side gaps are real thermodynamics and
  the spec defines gaps on all of 0 < x < 1".

**Be honest about prediction.** You cannot know pass@1 before the platform trials. Say "this is
designed to fail them for reasons X, Y, Z" and never "they will fail".

**Ideas for the next chemical-engineering task.** These are unverified suggestions that reuse
the same trap pattern: exact events, look-alike classes, near-degenerate cases, an
independent route. Avoid topics close to the two submitted tasks (phase stability, CSTR
bifurcation) because of similarity review. A friend already has `gel-effect-runaway`.
- **Catalyst pellet multiplicity** (Weisz–Hicks, a reaction–diffusion boundary-value problem):
  exact ignition and extinction Thiele moduli, isolas, the stability of interior solutions. A
  shooting method misses solution branches. Some similarity risk with the CSTR task.
- **Packed-bed runaway boundary**: the exact parametric-sensitivity boundary (Morbidelli–Varma
  generalized sensitivity maximum) versus the Semenov and Barkelew criteria models will reach
  for. Building an independent route is harder.
- **Multicomponent fixed-bed adsorption** with Langmuir isotherms: shock and simple-wave
  structure and exact shock velocities from coherence or h-transformation theory. The traps are
  numerical dispersion faking dispersed waves, and the ordering of transitions. An analytic
  answer key is checked by a high-resolution PDE solver.
- **Reactive or extractive distillation feasibility**: the exact pinch and tangent-pinch
  conditions that set minimum reflux. A stage-to-stage mesh misses tangent pinches. Some
  similarity risk with task 1's thermodynamics.

---

## 8. Task architecture that passed

```
<task-name>/
├── instruction.md            objective, CLI, deliverables, artifact paths, counts, binary outcome, closing line
├── task.toml                 template 9.1
├── README.md                 Difficulty / Reference solution / Verification (+ tolerance table) / Reproducing the reference values
├── environment/
│   ├── Dockerfile            python:3.11-slim + pinned numpy/scipy, COPY data /root/data, mkdir /root/results
│   └── data/
│       ├── <NAME>_SPEC.md    authoritative spec: model, domain, input schema, output schema, tolerances, diagnosis, execution contract
│       ├── recipes/*.json    shipped inputs with neutral IDs
│       └── legacy/<script>.py  legacy script with real scientific defects
├── solution/
│   ├── solve.sh              copies the program to /root/results, runs the base case, runs the diagnosis search
│   ├── <program>.py          single-file oracle (bundle your modules into one file; the agent's program must be one file too)
│   └── diagnose.py           finds witnesses at run time
└── tests/
    ├── Dockerfile            pinned deps + pytest==8.4.1 + pytest-json-ctrf==0.3.5, runner uid 10001, /sandbox
    ├── test.sh               fail-safe reward 0, lock down writable paths, pytest -rA --ctrf, finalize_reward.py
    ├── conftest.py           rewrites ctrf.json so every parametrized node is listed
    ├── finalize_reward.py    binary reward only for a complete, consistent report
    ├── test_outputs.py       saved-artifact test, parametrized fresh-call test, diagnosis test
    ├── expected.json         answer key from the INDEPENDENT reference
    ├── cases/*.json          shipped + held-out inputs
    ├── legacy/<script>.py    pristine copy of the legacy script for witness checks
    └── reference/reference.py  independent implementation, imported only for diagnosis witnesses
```

---

## 9. Templates (copy and adapt; these passed review)

### 9.1 task.toml

```toml
schema_version = "1.4"

artifacts = ["/root/results/program.py", "/root/results/base_case_report.json", "/root/results/diagnosis.json"]

[task]
name = "turing/<folder-name>"
version = "1.0.0"
description = "<one sentence saying what the task asks for>"
authors = [{ name = "Gourav Kumar", email = "gouravantalvines20@gmail.com" }]
keywords = ["<k1>", "<k2>", "<k3>"]

[metadata]
author_name = "Gourav Kumar"
author_email = "gouravantalvines20@gmail.com"
author_organization = "Independent Researcher"
author_profile = "https://www.linkedin.com/in/gourav-kumar-193b651b5"
research_advisor = ""
referred_by = ""
domain = "engineering-sciences"
category = "chemical-engineering"
subcategory = "<e.g. reaction-engineering>"
tags = ["<k1>", "<k2>", "<k3>"]
expert_time_estimate_hours = 20.0
relevant_experience = "B.Tech in Computer Science and Engineering; research-engineer contractor on scientific computing benchmark tasks (Python data analysis, numerical simulation, Docker-based validation). No industrial refinery employment."
conflicts_of_interest = "Engaged as a paid contractor by Turing to author this task."
reward_type = "binary"
source = "Written by PhD annotators"
public_overlap = "None"   # or state it, e.g. "Kinetic parameters are published values (...); the task itself is not public"

[verifier]
timeout_sec = 7200
environment_mode = "separate"
network_mode = "no-network"

[verifier.environment]
network_mode = "no-network"
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0

[agent]
timeout_sec = 10800
network_mode = "public"

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
network_mode = "public"
```

The pinned upstream CI script `check-task-fields.sh` flags the `turing/` prefix and the
category/subcategory keys. Both are platform requirements and known conflicts; ignore that one
script.

### 9.2 environment/Dockerfile

```dockerfile
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.11.4

COPY data /root/data
RUN mkdir -p /root/results
WORKDIR /root
```

### 9.3 tests/Dockerfile

```dockerfile
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.11.4 \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

RUN mkdir -p /root/results
RUN useradd --create-home --uid 10001 runner && \
    mkdir -p /logs/verifier /sandbox && \
    chmod 755 /sandbox

COPY . /tests/
RUN chmod -R 700 /tests
WORKDIR /tests
```

### 9.4 tests/test.sh

```bash
#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
# Fail-safe: a reward of 0 exists before any grading step; finalize_reward.py overwrites it with 1 on success.
echo 0 > /logs/verifier/reward.txt
# The artifact runs as uid 10001. Host bind mounts may otherwise expose a writable
# reward directory, letting a detached child rename and replace the final reward.
chmod 700 /logs/verifier
# Candidate code may write only its fresh per-call working directory. Shared
# temporary/home locations must not carry state between invocations.
chown root:root /home/runner
chmod 700 /tmp /var/tmp /home/runner /dev/shm /dev/mqueue /run/lock
rm -f /logs/verifier/ctrf.json
python -c 'import os; os.setgroups([]); os.setgid(10001); os.setuid(10001); assert all(not os.access(p, os.W_OK) for p in ["/logs/verifier", "/tmp", "/var/tmp", "/home/runner", "/dev/shm", "/dev/mqueue", "/run/lock"]), "candidate can write persistent verifier state"'
pytest_status=0
pytest -rA --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py || pytest_status=$?
# Interrupted collection, internal errors, usage errors and empty collections
# are infrastructure failures. Preserve diagnostics without issuing a score.
if (( pytest_status > 1 )); then
    exit "$pytest_status"
fi
python /tests/finalize_reward.py "$pytest_status"
```

### 9.5 tests/finalize_reward.py

```python
"""Issue a binary reward only for a complete, consistent grading report."""
import json
from pathlib import Path
import sys

CASES = Path('/tests/cases')


def expected_nodes():
    names = sorted(path.stem for path in CASES.glob('*.json'))
    nodes = {'test_outputs.py::test_saved_base_case', 'test_outputs.py::test_diagnosis'}
    nodes |= {f'test_outputs.py::test_fresh_case[{name}]' for name in names}
    return nodes


def grade(report, pytest_status):
    if pytest_status not in (0, 1):
        raise ValueError('pytest did not complete grading')
    results = report['results']
    tests = results['tests']
    expected = expected_nodes()
    names = [item['name'] for item in tests]
    if len(names) != len(expected) or set(names) != expected:
        raise ValueError('missing, duplicated or unexpected grading nodes')
    statuses = [item['status'] for item in tests]
    if any(status not in ('passed', 'failed') for status in statuses):
        raise ValueError('grading was skipped or incomplete')
    for item in tests:
        phases = item.get('extra', {}).get('failure_phases', [])
        if item['status'] == 'failed' and (not phases or any(phase != 'call' for phase in phases)):
            raise ValueError('verifier setup/teardown error or missing failure evidence')
    summary = results['summary']
    counts = {status: statuses.count(status) for status in ('passed', 'failed', 'skipped', 'pending', 'other')}
    if summary['tests'] != len(expected) or any(summary.get(key, 0) != value for key, value in counts.items()):
        raise ValueError('inconsistent grading summary')
    failed = counts['failed'] > 0
    if pytest_status != int(failed):
        raise ValueError('pytest exit status disagrees with actual test outcomes')
    return int(not failed)


if __name__ == '__main__':
    logs = Path('/logs/verifier')
    score = grade(json.loads((logs / 'ctrf.json').read_text(encoding='utf-8')), int(sys.argv[1]))
    assert score in (0, 1)
    (logs / 'reward.txt').write_text('1\n' if score == 1 else '0\n', encoding='utf-8')
```

### 9.6 tests/conftest.py

pytest-json-ctrf 0.3.5 collapses parametrized cases by function name. This hook rewrites the
report with every node.

```python
"""Preserve every parametrized pytest node in CTRF using actual phase reports."""
import json
from pathlib import Path
import time

import pytest

_collected = []
_reports = {}
_started = 0


def pytest_sessionstart(session):
    global _started
    _collected.clear()
    _reports.clear()
    _started = int(time.time() * 1000)


def pytest_collection_finish(session):
    _collected.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report):
    entry = _reports.setdefault(report.nodeid, {'name': report.nodeid, 'status': 'pending', 'duration': 0.0})
    entry['duration'] += report.duration * 1000
    if report.when == 'call' and report.user_properties:
        entry.setdefault('extra', {}).update(dict(report.user_properties))
    if report.failed:
        entry['status'] = 'failed'
        entry['message'] = str(report.longrepr)
        entry.setdefault('extra', {}).setdefault('failure_phases', []).append(report.when)
    elif report.skipped and entry['status'] != 'failed':
        entry['status'] = 'skipped'
    elif report.when == 'call' and entry['status'] not in {'failed', 'skipped'}:
        entry['status'] = 'passed'


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    yield
    tests = [_reports.get(nodeid, {'name': nodeid, 'status': 'pending', 'duration': 0.0})
             for nodeid in _collected]
    summary = {status: sum(item['status'] == status for item in tests)
               for status in ('passed', 'failed', 'skipped', 'pending', 'other')}
    summary.update(tests=len(tests), start=_started, stop=int(time.time() * 1000))
    target = Path('/logs/verifier/ctrf.json')
    payload = {'results': {'tool': {'name': 'pytest', 'version': pytest.__version__},
                          'summary': summary, 'tests': tests}}
    target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
```

### 9.7 Hardened runner in test_outputs.py (passed isolation, runtime-gate and trust-boundary review)

```python
import json, os, pwd, shutil, signal, stat, subprocess
from pathlib import Path
import pytest

ARTIFACT = Path('/root/results/program.py')
SANDBOX = Path('/sandbox')
CALL_SECONDS = 120


def strict_pairs(pairs):
    output = {}
    for key, value in pairs:
        assert key not in output, f'duplicate JSON key {key}'
        output[key] = value
    return output


def regular_file(path):
    """A submitted artifact must be a plain regular file: no symlink, FIFO, device or directory."""
    assert not path.is_symlink() and stat.S_ISREG(os.lstat(path).st_mode), f'{path}: not a regular file'


def read_json(path):
    regular_file(path)
    assert 0 < path.stat().st_size <= 1_000_000, 'JSON report must be non-empty and at most 1 MB'
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=strict_pairs)


def _drop_privileges() -> None:
    runner = pwd.getpwnam("runner")
    os.setgroups([])
    os.setgid(runner.pw_gid)
    os.setuid(runner.pw_uid)


def _clear_runner_processes() -> None:
    """Remove candidate-owned processes in this verifier's private PID namespace."""
    uid = pwd.getpwnam("runner").pw_uid
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid == uid:
                os.kill(int(entry.name), signal.SIGKILL)
        except (ProcessLookupError, FileNotFoundError):
            pass


def _invoke(label: str, recipe: dict, program_source: Path = ARTIFACT) -> dict:
    """Run one isolated, time-bounded call without exposing tests or truth to agent code."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    recipe_path = run_dir / "recipe.json"
    output_path = run_dir / "report.json"
    recipe_path.write_text(json.dumps(recipe, indent=1) + "\n", encoding="utf-8")
    recipe_path.chmod(0o444)
    runner = pwd.getpwnam("runner")
    os.chown(run_dir, runner.pw_uid, runner.pw_gid)

    program = SANDBOX / "program.py"
    regular_file(program_source)                       # FIFO/symlink guard BEFORE copying
    assert 0 < program_source.stat().st_size <= 1_000_000, 'program must be non-empty and at most 1 MB'
    shutil.copyfile(program_source, program)
    program.chmod(0o555)
    stdout_path, stderr_path = run_dir / ".stdout", run_dir / ".stderr"
    process = None
    try:
        with stdout_path.open("w") as out, stderr_path.open("w") as err:
            process = subprocess.Popen(
                ["python", str(program), "--recipe", str(recipe_path), "--output", str(output_path)],
                cwd=run_dir,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONHASHSEED": "0",
                     "TMPDIR": str(run_dir), "HOME": str(run_dir),
                     "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True, preexec_fn=_drop_privileges,
            )
            try:
                returncode = process.wait(timeout=CALL_SECONDS)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                returncode = None
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        _clear_runner_processes()
    tail = lambda p: p.read_text(errors="replace")[-2000:] if p.is_file() else ""
    assert not timed_out, f"{label}: program exceeded the {CALL_SECONDS} s wall-clock limit"
    assert returncode == 0, f"{label}: program exited {returncode}; stdout={tail(stdout_path)!r}; stderr={tail(stderr_path)!r}"
    assert output_path.is_file(), f"{label}: program did not create output JSON"
    try:
        return read_json(output_path)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        pytest.fail(f"{label}: output is not valid UTF-8 JSON: {error}")
```

Test functions, each with a docstring:

```python
def test_saved_base_case():
    """The declared artifacts must exist; the saved base-case audit must be correct."""

@pytest.mark.parametrize('case_name', CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """Stateless calls must reproduce the shipped and held-out recipes."""

def test_diagnosis(record_property):
    """Each witness must reproduce the legacy output and agree with the independent reference."""
```

Validation helpers: `number()` requires a finite JSON number (`type(v) in (int, float)` and
`math.isfinite`). `integer()` requires `type(v) is int`. Exact key sets are checked with
`set(obj) == KEYS`. Comparisons go element by element in the spec's sort order, and the lengths
must be equal.

### 9.8 solution/solve.sh

```bash
#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/program.py /root/results/program.py
python /root/results/program.py --recipe /root/data/recipes/base_case.json --output /root/results/base_case_report.json
# diagnosis computed at run time (never copied)
python /solution/diagnose.py --program /root/results/program.py --legacy /root/data/legacy/legacy.py \
    --recipes /root/data/recipes --output /root/results/diagnosis.json
```

### 9.9 instruction.md skeleton (passed writing, output-contract and execution-contract review)

````markdown
Write `/root/results/<program>.py`, a program that <objective in one sentence>. The <inputs> are shipped in `/root/data/recipes/`. Also diagnose the scientific defects of the inherited script `/root/data/legacy/<legacy>.py`, which takes the same command line and writes the same kind of report.

The <model>, every input and output file schema, the numerical tolerances, and the exact conditions under which the verifier runs your program are defined in `/root/data/<NAME>_SPEC.md`, which is authoritative for all of those details.

Your program must accept

```
python /root/results/<program>.py --recipe <recipe.json> --output <report.json>
```

and must report in `<report.json>`:

1. `<key1>`: <what, with closed vocabulary>.
2. `<key2>`: ...
3. `<key3>`: ...

Save the result for `/root/data/recipes/base_case.json` to `/root/results/base_case_report.json`.

Save the legacy diagnosis to `/root/results/diagnosis.json`: one entry per scientific defect you find, each with a numerical witness, the quantity the script gets wrong, and the legacy and correct values of that quantity, in the schema given in the spec. The witnesses are graded; the free-text descriptions are not.

The verifier runs your program on the N shipped recipes and on M held-out recipes that vary <what> within the domain stated in the spec, compares every reported quantity against the spec's tolerances, and checks your diagnosis witnesses by executing the legacy script and an independent computation. The outcome is pass or fail as a whole: every <item> must be correct on every recipe.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
````

### 9.10 Spec skeleton (sections that passed) and execution-contract wording

Sections:
1. The model, with equations, units and the cited source of the parameters.
2. The parameter domain, with exact bounds; held-out inputs stay inside it.
3. The input file: exact keys, types, string length limits, and "carries no information about
   the answer".
4. The output file: exact keys; sort orders; count arithmetic; every convention, including
   endpoint kinds and merge rules; the counting rule ("distinct when they differ by more than
   1e-6 K"); integer vs number; ranges; then the file conventions paragraph.
5. Tolerances and grading, stating every comparison exactly as the verifier performs it.
6. The diagnosis file: quantities, projections, how witnesses are checked, at least three
   distinct quantities, and "required but not graded" for the text.
7. The execution contract.

File conventions wording:

> Every JSON file the verifier reads (the saved report, `diagnosis.json`, and the report written
> by each fresh call) must be a regular file (not a symbolic link or other special file),
> non-empty, at most 1 MB, UTF-8, and free of duplicate keys in any object.

Execution contract wording:

> The verifier evaluates `<artifacts>` and fresh runs of `/root/results/<program>.py` on the N
> recipes shipped in `/root/data/recipes/` and on M held-out recipes of the same schema and
> domain, N+M fresh calls in total. The held-out recipes cover <list every kind of structure,
> including edge behaviours such as an empty list>. Each call must exit with status 0 within 120
> seconds of wall-clock time measured by the verifier from process start to exit; the legacy
> script runs on each diagnosis witness under the same contract. The verifier as a whole has 7200
> seconds of wall-clock time. All time limits are wall-clock limits, not CPU-time limits. Calls
> run in a separate verifier container, offline, as an unprivileged user in a fresh empty writable
> working directory that is the only writable location, with Python 3.11, NumPy 1.26.4 and SciPy
> 1.11.4 and nothing else; the program may rely only on its own source and its arguments, and must
> require neither other files nor state from earlier calls. The verifier environment is allocated
> 1 CPU, 2048 MB of memory, 10240 MB of storage and no GPU, and sets `OPENBLAS_NUM_THREADS`,
> `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to `1`; the environment passed to the program holds only
> `PATH`, `PYTHONHASHSEED=0`, those three variables, and `HOME` and `TMPDIR` set to the working
> directory. The program must be a regular file of at most 1 MB, and the report it writes must
> follow the file conventions of section 4. Anything the program writes to standard output or
> standard error is ignored.

### 9.11 README skeleton

The README has four sections:
- `## Difficulty` (at most about 400 words): what makes the task hard, the real-world workflow,
  who does this work, real or synthetic data, and the exact traps.
- `## Reference solution` (at most about 300 words): the strategy and key insight. It must match
  `solution/`.
- `## Verification` (at most about 600 words; tables don't count):
  - the independent reference's method, and its agreement with the solution (worst differences);
  - what the tests check;
  - the tolerance table;
  - the wrong-method control results;
  - oracle 1 and nop 0 in Docker and Harbor;
  - the offline oracle run sentence;
  - the verifier run under the declared 1-CPU allocation.
- `## Reproducing the reference values`: the regeneration commands and the tolerance-study script
  with its results. Authoring material goes here, not into `tests/` or a new folder.

Tolerance table format (one row per graded quantity, no exceptions):

| Graded quantity | Tolerance | Agreement of the two codes | Basis |
| --- | --- | --- | --- |
| Event value | 0.002 K | 1.6e-9 K | 1/25 of the closest fold–Hopf separation (0.053 K): far below any affordable mesh, far above any converged solution |
| Conversion | 1e-4 | 6e-14 | conversion change from a 0.01 K error at the median state (dX/dT = 1.36e-2/K); distinct states differ by at least 1.35e-2 |
| Orbit extremes | 0.05 K | 2.7e-5 K | four standard integrators spread up to 0.029 K; nearest steady state at least 1.6 K away |

---

## 10. Building the independent answer key

- **Never use the oracle's outputs as expected values.** That is circular, and reviewers check.
- **Have a separate agent build the reference by a different route,** reading the oracle only to
  understand the schema. In task 2:

  | Oracle | Reference |
  | --- | --- |
  | steady-state manifold parameterized by T | fixed-parameter dense scans plus parameter bisection with a second-pass confirmation |
  | Guckenheimer–Holmes Lyapunov coefficient | Kuznetsov normal form with finite differences, cross-checked by simulation |
  | pseudo-arclength shooting | `solve_bvp` collocation |
  | — | a brute-force integration sweep at 100 parameter values per recipe as a final referee |

- **The reference will catch bugs in your oracle.** In task 2 it disagreed on 8 of 26 recipes,
  and brute-force integration sided with the reference every time: the oracle's cycle
  continuation was stopping early, running off the window edge, leaking "unknown" labels and
  duplicating attractors. Fix the oracle and regenerate. Budget time for this; it cost about a
  day in task 1, where a 1.5 mK disagreement on critical points needed refinement in both codes.
- **Write the agreement into the README** as worst differences per quantity, and say that both
  codes agree on every discrete label.
- **Keep the reference fast enough** for diagnosis witnesses, which are recomputed by the
  verifier (about 30 s each). Ship only `reference.py` under `tests/reference/`.

---

## 11. Choosing tolerances (the method reviewers accepted)

Every tolerance must sit between two measured numbers:

1. **The spread between legitimate methods.** Re-solve the graded quantities with several
   standard methods, for example four integrators at rtol 1e-6.
2. **The distance to the nearest wrong answer** the tolerance must reject: the smallest
   separation between distinct states, or the closest pair of events.

Write the rationale for every graded quantity, including the ones that seem obvious
(conversion, extremes). Ship the study script in the README, not in `tests/`.

---

## 12. Local verification workflow (Claude Code cloud container)

The cloud container has no Docker daemon running. Start one detached, so it survives shell
restarts:

```bash
setsid nohup dockerd --host=unix:///tmp/dock.sock --data-root=/tmp/dockerdata > /tmp/dockerd.log 2>&1 &
export DOCKER_HOST=unix:///tmp/dock.sock DOCKER_BUILDKIT=0
```

Notes on Docker:
- Build with `DOCKER_BUILDKIT=0 docker build --network=host ...`. BuildKit hit Docker Hub 429
  limits.
- pip inside builds failed TLS through the session proxy. The fix was to re-tag a local
  `python:3.11-slim` that trusts the session CA, keeping the original as `python-orig:3.11-slim`.
  This is local only; never ship the CA in the task.

```bash
cd <task>
docker build --network=host -q -t task-env environment/
docker build --network=host -q -t task-tests tests/
# offline oracle (record in README)
docker run --rm --network none -v $PWD/solution:/solution:ro -v /tmp/oracle_out:/root/results task-env bash /solution/solve.sh
# verifier under the declared allocation
docker run --rm --network none --cpus=1 --memory=2048m -v /tmp/oracle_out:/root/results:ro -v /tmp/v_logs:/logs/verifier task-tests bash /tests/test.sh; cat /tmp/v_logs/reward.txt   # expect 1
# nop: empty results dir -> expect 0
docker run --rm --network none --cpus=1 --memory=2048m -v /tmp/empty:/root/results:ro -v /tmp/nop_logs:/logs/verifier task-tests bash /tests/test.sh; cat /tmp/nop_logs/reward.txt
# FIFO control: mkfifo /tmp/fifo_out/program.py (plus other artifacts) -> expect 0, no hang
```

Harbor (installed with `uv tool install harbor`; version 0.24.0 was used):

```bash
harbor run -p <task> -a oracle -e docker --jobs-dir /tmp/harbor_jobs --job-name oracle1   # expect 1.0
harbor run -p <task> -a nop    -e docker --jobs-dir /tmp/harbor_jobs --job-name nop1      # expect 0.0
```

`harbor check` pulls `python:3.13-slim` from Docker Hub and can be rate-limited (429). That is
not a package error.

Floating-point portability sweep. Run this before every upload that changes numerics:

```bash
for ct in default Prescott SandyBridge SkylakeX Zen; do
  env $( [ "$ct" = default ] || echo OPENBLAS_CORETYPE=$ct ) OPENBLAS_NUM_THREADS=1 \
    timeout 300 python -I solution/program.py --recipe tests/cases/<case>.json --output /tmp/ct_$ct/<case>.json
done
```

Then grade every output with the verifier's own validate and compare functions on the host (a
small script that imports test_outputs.py helpers), plus the time per call.

Static checks:
- The pinned TB-Science CI scripts gave 20 of 21. The only failure is `check-task-fields.sh`, a
  known conflict.
- A native V2.2 audit of 8 items.
- Before zipping, scan for canary strings and secrets.

Build the ZIP with a deterministic builder: the six root entries only, sorted, fixed
1980-01-01 timestamps, UTF-8 check, scan, SHA256 manifest written outside the ZIP. Always run it
from a clean task tree.

**When the user wants speed:** a change that is documentation or packaging only, with no verifier,
oracle or answer-key change, needs only the static checks and a host grade, not the full Docker
and Harbor rerun. Say which checks you skipped and why.

---

## 13. Evaluation comment and Complete Conversation

**Evaluation comment** (after all nodes pass). First read the trial folders. Then write:

```
Trials: both frontier models fail at pass@1, with no harness or environment errors.

GPT-6 Sol (max): reward 0.0, <a> of <n> nodes. <case names + the scientific mistake, 2–4 sentences>.

Claude Opus 5.5 (low): reward 0.0, <b> of <n> nodes. <case names + the scientific mistake, 2–4 sentences>.

Both models got <what they got right>. Both failed only on <the hardest science>.

Task-side checks: the oracle scores 1 in Docker, in Harbor and offline, including under the declared
1-CPU, 2048 MB verifier, and reproduces the answer key on all <n> cases under five CPU math kernels.
A do-nothing agent scores 0. The expected values come from an independent implementation with no
shared code or method; it agrees with the oracle to <worst differences>. Each tolerance is set from
measured method-to-method spread and the distance to the nearest wrong answer. <k> wrong-method
controls all score 0. <If relevant: changes after the trials were documentation/packaging only; no
verifier, oracle or answer-key file changed, so the trial outcomes apply to the current version.>
```

If one of a model's failures is arguably borderline, don't lead with it. Lead with the
failures that are clearly scientific, and keep the framing honest.

**Complete Conversation dialog** (time logging):
- **Duration** needs a unit. Type `2h` or `120` (minutes); a bare `2` reads as 0 minutes.
  Formats such as `1h`, `90` and `2h 30m` work. Only the user knows the real number; never
  guess it.
- "Current session" means this platform conversation for this task ID: from its first upload to
  clicking Complete. Earlier logged work must not be counted twice.
- **Notes** take 3 to 5 sentences: what was built or fixed, the version, oracle 1 and nop 0, the
  trial outcomes, and that the failures were scientific.

Example notes (rework session):

```
Rework for manual review: moved tests/reference/README.txt, regenerate.py and tolerance_study.py out of tests/ (only reference.py, used by the verifier, remains). Their content now lives in README.md under "Reproducing the reference values"; task-root entries kept to the six standard Harbor entries. Version 1.3.1; grading, solution and answer key unchanged; oracle passes all 28 recipes.
```

---

## 14. Technical gotchas we hit

| Problem | Fix |
| --- | --- |
| Oracle passes locally but scores 0 on the platform | Different CPU (AVX-512) changes floating-point results, and a sensitive Newton or continuation step amplifies the difference. Use work budgets on integrators, require the end time to be reached, and run the five-kernel sweep. Keep the slowest call far below the limit |
| Stiff integration hangs on odd trial points | LSODA, reachable-region bounds, a cap on right-hand-side calls, and rejecting the step |
| `pkill -f` / `pgrep -f` matched my own shell and killed it (exit 144) | Use bracket patterns (`pgrep -f '[d]ockerd'`) and separate commands |
| dockerd died with the shell or after a container restart | `setsid nohup`, and check `docker ps` before each run |
| A background waiter hung after the job it watched crashed (lost an hour) | Poll status files with timeouts, and check for crash markers, not just completion |
| A safety block on `rm` with globs | Write to a fresh output directory instead of deleting |
| `solve_ivp` event functions | They receive `args` too, so the signature must be `event(t, y, *args)` |
| pytest-json-ctrf collapses parametrized nodes | the conftest.py hook (9.6) |
| Expected-node mismatch after adding cases | finalize_reward.py derives the nodes from `tests/cases/*.json`, so add each case file there |
| An "unknown" label leaked into a report | Validate the oracle's output against the closed vocabulary before writing |
| Duplicate attractor entries when two continuation segments cover one parameter | Deduplicate by distance |
| Hashes in a provenance manifest went stale after records were refined | Regenerate the manifests after every data change, or don't ship manifests in tests/ at all |

---

## 15. Time and cost expectations

- **Task 2 build**: design, oracle, independent reference, 26 recipes, controls, verifier and
  README took about 8 to 10 hours of agent time across two days, including a pause. Review rounds
  added about 9 hours of platform session.
- **Review rounds**: expect 3 to 5 rounds, even with care. Each auto review costs $1.2 to $2.2.
  The pre-upload constraint inventory (rule 0.8) and the checklist (section 6) are how you cut
  the number of rounds.
- **Subagents**: helpers in parallel can write the independent reference, the legacy script and
  the verifier scaffold while you build the oracle. Hitting usage or session limits can stop them
  mid-run; resume rather than restart.

---

## 16. Where the files are (this container is temporary)

These paths exist only in the current cloud session and disappear when it ends. Ask the user to
keep the backups.

- `/home/user/tb-science/r10/heteroazeotrope-audit/`: the task 1 tree, plus its readiness note
  `heteroazeotrope-R10-readiness.md`.
- `/home/user/tb-science/cstr/task/cstr-bifurcation-audit/`: the task 2 tree (v1.3.1). Its ZIP
  is `SUBMIT-cstr-bifurcation-audit.zip` (SHA256 `ec670633…b95010`); the readiness note is
  `cstr-readiness.md`; tools are in `cstr/tools/` (build_zip.py, static_checks.py,
  bundle_oracle.py).
- `/home/user/tb-science/cstr-final-backup.zip`: the full CSTR working folder (oracle modules,
  reference, scans, controls, evidence).
- `/home/user/tb-science/HARDNESS-ASSESSMENT.md`: why case selection could not stump Opus.
