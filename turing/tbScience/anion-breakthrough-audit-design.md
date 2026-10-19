# Design: `anion-breakthrough-audit`

Proposed TB-Science task, designed 19 October 2026 against `TB-SCIENCE-PLAYBOOK.md`. This is a
design for approval, not a build. Nothing here has been coded or verified yet; every numerical
claim about the system is a target to be confirmed by the independent references in the build.

| | |
| --- | --- |
| Working name | `anion-breakthrough-audit` (alternatives: `nitrate-dumping-audit`, `ion-exchange-fronts`) |
| Domain / category / subcategory | engineering-sciences / chemical-engineering / separation-processes |
| Science | multicomponent ion exchange in a fixed bed under local equilibrium: exact wave structure (shocks, spreading waves, zero-strength waves), chromatographic peaking of nitrate above its feed concentration, run length to the nitrate MCL, and the exact interaction of fronts after a mid-run feed change |
| Deliverable pattern | the one that passed twice: a program the verifier reruns on shipped and held-out recipes, a saved base-case report, and a `diagnosis.json` with executable witnesses against a shipped legacy script |
| Answer key | two independent exact routes (h-transformation front tracking vs generic hyperbolic-system machinery) plus a high-resolution PDE referee |

## 1. The problem and why it is real

A utility runs a chloride-form strong-base anion exchange bed to remove nitrate from groundwater
that also carries sulfate and bicarbonate. Sulfate is held more strongly than nitrate, so late in
the run sulfate displaces nitrate already on the resin and the effluent nitrate rises above the
influent value, sometimes well above the 10 mg/L-N limit. This "nitrate dumping" or
chromatographic peaking is a documented drinking-water hazard (Clifford and Weber; Clifford's
chapter in AWWA *Water Quality and Treatment*), and the run length a plant can safely use is set
by when the peak arrives, not by when nitrate first appears. Process engineers compute this
with equilibrium (local-equilibrium, plug-flow) theory, which for constant separation factors
has an exact solution: the Helfferich-Klein h-transformation, equivalent to the Rhee-Aris-
Amundson theory for Langmuir systems.

The task asks for a program that, given a column, resin selectivities, the resin's initial
loading, and a feed program with at most one composition change, produces the exact effluent
history: every front at the outlet with its kind and bed-volume position, the plateau
compositions, the nitrate peak, the first bed volume at which nitrate exceeds the limit, and the
effluent composition at requested bed volumes. It also asks for a diagnosis of the utility's
legacy script, which embodies four shortcuts practitioners actually make.

Data: separation factors for type 1 strong-base resins (sulfate, nitrate, bicarbonate relative
to chloride) from the published tables, with the task's recipes varying them inside a stated
range. `public_overlap` will state that the selectivity values are published and the task is
not. The model is textbook; the exactness demanded is not.

## 2. The model (what the spec will state)

Ions Cl⁻, NO₃⁻, SO₄²⁻, HCO₃⁻ in equivalent fractions. Total normality `C_T` is constant within
a recipe (service cycle, no normality front). Local equilibrium, plug flow, isothermal, no
dispersion, no kinetics. Constant separation factors `alpha_i` relative to chloride (`alpha_Cl`
= 1), so the resin phase is `y_i = alpha_i x_i / sum_j alpha_j x_j`. Column of voidage `eps`,
resin capacity `Q` (eq/L of bed... exact basis stated), throughput in bed volumes `BV`.

For each ion: `eps dx_i/dt + (1 - eps) (Q / C_T) dy_i/dt + u dx_i/dz = 0`. With four ions and
`sum x_i = 1` there are three independent components, so every step change in feed produces
three waves. Each wave is one of:

- a **shock** (self-sharpening front) whose position in BV follows from the jump condition;
- a **simple wave** (spreading front) whose head and tail arrive at different BV and whose
  interior composition varies along a straight line in the h-coordinates;
- a **zero-strength wave** (the two end states coincide), which is not reported.

Which of the first two applies is set by the direction in which the wave's own h-root changes
across it (the Helfferich-Klein rule, stated in the spec in exact terms). The spec gives the
h-function (`sum_i alpha_i x_i / (alpha_i - h) = 0`, roots interlacing the `alpha_i`), the fact
that across a wave of family `k` all other roots are invariant, the speed of a characteristic
and of a shock in terms of the roots, and the inverse map from roots to composition. It states
the model completely but prescribes no algorithm.

A feed change at `BV_s` launches a second set of three waves into the plateau left by the first
set. Faster second waves overtake slower first waves. Because the system is of Temple class the
invariants pass through each other unchanged, but the speeds do not: a shock crossing a
spreading wave of another family follows a curved path, and the spreading wave is refracted
behind it; a shock overtaking a spreading wave of its own family absorbs it, its strength
changing along the way. The exact outlet history after a switch requires tracking these
interactions to the outlet. The spec states the physics (conservation and the jump condition
hold everywhere; invariants are preserved across waves of other families) and leaves the
construction to the agent.

## 3. The deliverable and how it is graded

Program CLI: `python /root/results/ixfront.py --recipe <recipe.json> --output <report.json>`.

Recipe (neutral ids, no answer information): column (`eps`, `Q_eq_per_L`, `C_T_meq_per_L`),
selectivities (`alpha` for the four ions), `initial_resin` (equivalent fractions on the resin),
`feed_program` (one or two feed compositions with the switch BV), `run_bv`, `sample_bv` (a list
of 0 to 12 BV values), `nitrate_limit_meq_per_L`.

Report (exact key set, prose-defined schema, closed vocabularies):

1. `outlet_waves`: the waves that reach the outlet before `run_bv`, sorted by arrival BV. Each
   has `kind` in `{"shock", "simple"}`, `bv_start`, `bv_end` (equal for a shock), the effluent
   composition before and after (meq/L per ion, fixed ion order), and for a simple wave the
   composition at its midpoint in BV. Zero-strength waves and waves arriving after `run_bv` are
   absent; the count is whatever the physics gives (0 to 6).
2. `plateaus`: the constant-composition intervals between waves, with their BV spans.
3. `nitrate_peak`: the maximum effluent nitrate over `[0, run_bv]` and the first BV at which it
   is attained.
4. `nitrate_limit_bv`: the first BV at which effluent nitrate exceeds the limit, or `null` if it
   never does within the run. Exceedance inside a spreading wave requires inverting the wave.
5. `samples`: effluent composition at each requested BV (empty list if none requested).

Grading: binary over all nodes. Contract validation first (exact keys, finite numbers, sort
order, fixed ion order, closed vocabulary, file conventions). Then element-wise comparison in
the stated order: wave count and kinds exact; BV values within a relative tolerance; compositions
within an absolute tolerance in meq/L; `null` exact. Tolerances are set by the study in section
7 and written in the README table with their basis.

Diagnosis: `diagnosis.json` with one entry per defect found in `/root/data/legacy/ixbreak.py`,
each with a witness: a recipe (derived from shipped inputs, within the stated domain), the
quantity (closed vocabulary: `wave_bv`, `plateau_composition`, `nitrate_peak`,
`nitrate_limit_bv`, `sample`), the legacy value and the correct value. At least three distinct
quantities. The verifier reruns the pristine legacy script on each witness and recomputes the
correct value with the independent reference; the legacy value must match what the agent
reported, the correct value must match the reference, and the two must differ by more than the
tolerance. Free-text descriptions are required but not graded (stated).

Calls: 6 shipped + 22 held-out recipes = 28 fresh calls, plus the legacy and reference runs for
the witnesses. Per-call limit 60 s wall-clock on 1 CPU (the exact method runs in milliseconds;
a PDE solver fine enough to meet the tolerances is unlikely to fit, and the limit is disclosed
with every other execution-contract item from playbook template 9.10). Verifier 7200 s, 1 CPU,
2048 MB, 10240 MB, no GPU; agent 10800 s.

## 4. The traps (mapped to playbook section 7)

1. **Exact location of discrete events where the obvious method is a mesh.** Front positions in
   BV to a relative tolerance a PDE solver with numerical dispersion cannot meet in 60 s on one
   CPU; a shock and the head of a spreading wave of the next family designed to arrive within a
   few parts in 10⁴ of each other, so dispersion merges them.
2. **Classification between look-alike kinds.** Shock vs simple wave is decided by the h-root
   direction, not by which ion is "favourable"; pre-loaded resins (partial regeneration, a
   previous cycle's sulfate) give mixed sets where the naive rule fails. A simple wave's
   `bv_start`/`bv_end` pair against a shock's single BV is graded exactly.
3. **Family is not ion.** The k-th wave is not "the k-th ion's front". Plateau compositions
   between waves follow from the invariants, and the less-preferred ion rolls up: nitrate
   plateaus above both feed and initial values. A component-wise material balance gives the
   right final state and the wrong intermediate ones.
4. **Zero-strength and pole-hugging roots.** An ion absent from both the feed and the resin
   puts an h-root exactly on its `alpha`; an ion present at 1e-4 equivalent fraction puts the
   root 1e-4 from the pole. The first wave must be absent from the report, the second present
   with the correct strength. This is the analogue of task 1's edge-hugging miscibility gaps.
5. **Following the solution to where it really ends.** After a feed switch the fronts interact;
   superposing the two Riemann solutions gives the right plateaus far from the interaction and
   the wrong arrival BVs and wrong sample values near it. Held-out switches are placed so that
   (a) a second-set shock crosses a first-set spreading wave of another family before the
   outlet, (b) a second-set shock absorbs a first-set spreading wave of its own family, (c) the
   switch comes after all first-set waves have left (no interaction, as a control), and (d) the
   second-set waves do not reach the outlet within `run_bv`.
6. **Derived events inside spreading waves.** `nitrate_limit_bv` often falls inside a simple
   wave and requires inverting the wave's composition path exactly; the nitrate peak can sit at
   the end of a spreading wave rather than on a plateau.
7. **Many nodes, all-or-nothing.** 28 recipes, each exercising a subset of 1 to 6, so a model
   that gets any one concept wrong fails several nodes.

Standard parts a competent model will get right, and which are therefore not where difficulty
is claimed: the h-roots themselves, the chloride-form all-shock base case, unit handling, the
schema and the CLI.

## 5. The legacy script and its defects

`/root/data/legacy/ixbreak.py` is a plausible plant script (same CLI, same report schema). Its
four defects are scientific, each producing a measurable wrong value on specific recipes:

| Defect | What it does | Where it shows |
| --- | --- | --- |
| D1 sharp-front assumption | treats every transition as a stoichiometric shock | desorbing transitions on pre-loaded resins: wrong BV, no spreading wave, wrong samples inside the wave |
| D2 component-wise fronts | assigns front k to ion k in selectivity order and computes plateaus by sequential single-ion balances | intermediate plateaus and the nitrate peak on any recipe with roll-up |
| D3 effluent capped at influent | clamps predicted effluent to the feed value "as a sanity check" | nitrate peak and `nitrate_limit_bv` on every peaking recipe |
| D4 superposition after a feed switch | restarts the calculation at the switch and adds the shifted result, ignoring interactions | post-switch wave BVs and samples on interacting recipes |

The agent must find them by comparison, since the script's comments describe the shortcuts as
features. The verifier's witness check (section 3) is independent of how the agent describes
them.

## 6. The independent answer key

Three routes, built by separate agents, sharing only the recipe schema:

| Route | Method | Role |
| --- | --- | --- |
| Oracle (`solution/`) | h-transformation: roots by bracketed root-finding between poles, invariants, closed-form shock and characteristic speeds, inverse map to composition; front tracking in the (BV, position) plane with ODE integration of curved shock paths through spreading waves and of absorbed waves | the reference solution |
| Reference A (`tests/reference/reference.py`) | generic hyperbolic-system machinery with no h-coordinates: numerical Jacobian and eigen-decomposition on the constrained manifold, rarefaction curves by ODE integration at rtol 1e-12, Hugoniot loci by Newton on the jump conditions, Riemann solution by nested root-finding on wave curves, interactions by event-driven front tracking | expected values; also recomputes diagnosis witnesses in the verifier (fast) |
| Reference B (README only) | conservative finite-volume solver for the hyperbolic system in the conserved variable `eps c + (1 - eps) q(c)`, second-order TVD with SSP-RK3, 20k to 80k cells, Richardson extrapolation on event BVs (midpoint crossings), plateaus and samples | referee for wave kinds, counts and interactions; sets the method-spread leg of every tolerance |

Expected agreement: oracle vs A around 1e-9 (both exact); B within a few 1e-5 on plateau
compositions and samples after extrapolation and within about 1e-4 relative on front BVs. If A
and the oracle disagree, B decides, as in task 2 (the playbook says to budget a day for this).

## 7. Tolerances (the method the reviewers accepted)

Each graded quantity gets a tolerance between the measured method spread and the distance to the
nearest wrong answer, written in the README table:

| Quantity | Candidate tolerance | Spread leg (to measure) | Nearest-wrong leg (to measure) |
| --- | --- | --- | --- |
| wave BV | 2e-4 relative | oracle vs A; B after extrapolation | the designed near-coincident pair (about 1e-3 apart); legacy D1/D4 errors (1e-2 and larger); a 5000-cell PDE in 60 s |
| composition (meq/L) | 1e-4 absolute at `C_T` 2 to 12 meq/L | oracle vs A vs B | D2/D3 plateau errors (0.05 meq/L and larger); roll-up magnitude |
| nitrate peak | 1e-4 meq/L, BV 2e-4 relative | as above | D3 clamps to feed, typically 0.3 to 1 meq/L below the true peak |
| `nitrate_limit_bv` | 2e-4 relative; `null` exact | inversion inside a simple wave, two codes | D1 (shock instead of fan) moves it by 1e-2 or more |
| samples | 1e-4 meq/L | as above | dispersion smears samples near fronts by 1e-2 |
| wave count and kinds | exact | both codes agree on every label | - |

Candidate values are placeholders until the study runs. The study script and results go in the
README ("Reproducing the reference values"), not in `tests/`.

## 8. Held-out case design (coverage for the trial review)

28 recipes: 6 shipped (neutral ids `service_01`..`service_06`), 22 held-out. Every behaviour the
spec requires is exercised by at least one executed case:

- chloride-form resin, four-ion feed, all three waves shocks (baseline)
- resin pre-loaded with bicarbonate; pre-loaded with sulfate; mixed shock and simple waves
- complete elution at constant normality (all simple waves)
- an ion absent from feed and resin (zero-strength wave, three waves reported as two)
- an ion at 1e-4 equivalent fraction (pole-hugging root, wave present)
- near-coincident arrivals of two families (3e-4 to 1e-3 apart in BV)
- nitrate peak on a plateau; nitrate peak at the end of a spreading wave
- `nitrate_limit_bv` inside a spreading wave; never exceeded (`null`); exceeded on the first
  plateau
- feed switch with cross-family shock-fan interaction; same-family absorption; switch after all
  first waves exit; switch whose waves never reach the outlet within `run_bv`
- `run_bv` shorter than the first arrival (empty `outlet_waves`, one plateau)
- empty `sample_bv` list; samples placed inside spreading waves and inside interaction regions
- selectivities at both ends of the stated range; `C_T` at both ends

Each held-out recipe is generated from a parameter domain stated in the spec, screened so that
no graded value sits within 3 tolerances of a verifier boundary (`run_bv`, the MCL) unless the
case is designed to exercise that boundary with margin on the right side.

## 9. Wrong-method controls (all must score 0)

Legacy as shipped; "all shocks"; "component-wise plateaus"; "clamped effluent"; "superposition
after switch"; upwind PDE with 200 cells; TVD PDE with the most cells that fit in 60 s on one
CPU; Reference B at 2000 cells without extrapolation. Report pass counts per control in the
README, as the playbook shows ("legacy 1/28 ...").

## 10. Risks and honest assessment

- **Similarity.** No overlap with the two submitted tasks (NRTL phase stability; CSTR
  bifurcation) or with `gel-effect-runaway`. Equilibrium theory of multicomponent fixed beds is
  a classic subject, so a public TB-Science task on chromatography could exist; the exact
  interaction tier and the ion-exchange safety framing make this one specific. To be checked
  against the public task list before building.
- **Could Opus 5.5 pass?** It knows the h-transformation exists. Traps 1 to 4 and 6 are the
  kind it gets subtly wrong under exact tolerances (pole-hugging roots, inversion inside fans,
  zero-strength waves), but a careful implementation could clear them. Trap 5 (interactions) is
  the main bet: a model that reaches for superposition or a PDE after the switch fails those
  nodes. The playbook's lesson is that one trap is not enough; this design has seven spread over
  28 nodes. This is designed to fail both models for those reasons; whether it does is known only
  after the platform trials.
- **Build risk.** Exact front tracking of interactions is the hardest part of the oracle and of
  Reference A, and the part most likely to disagree between them. The PDE referee resolves
  disagreements. If interactions cannot be made exact and reproducible in the time available,
  the fallback is to drop the feed switch (keep traps 1 to 4, 6, 7) and say so.
- **Floating point.** The method is algebraic and ODE-based with bracketed roots, so the
  five-kernel OpenBLAS sweep should be uneventful; still mandatory before upload.

## 11. Build plan

| Phase | Work | Estimate |
| --- | --- | --- |
| 0 | Confirm public-task similarity; fix selectivity ranges and the domain; write the spec skeleton (sections per playbook 9.10) | 1 h |
| 1 | Oracle: h-transformation Riemann solver, outlet history, derived quantities; then interactions | 4 to 6 h |
| 2 | Reference A (separate agent, sees only the schema) and Reference B (PDE referee); reconcile all three on 40+ candidate recipes | 4 to 6 h |
| 3 | Legacy script with D1 to D4; `diagnose.py` finding witnesses at run time; recipe generation and screening; tolerance study | 2 to 3 h |
| 4 | Verifier from the playbook templates (hardened runner, conftest, finalize_reward); controls; Docker, Harbor, offline and 1-CPU runs; five-kernel sweep; README; constraint inventory (rule 0.8); deterministic ZIP | 3 to 4 h |

Total about 14 to 20 hours of agent time across two or three days, in line with task 2's 8 to
10 hours plus the extra for interactions. Local Harbor and Docker are already working on this
machine (jobs dir must be under `$HOME`).

## 12. Decisions needed before building

1. **Author fields.** The playbook's `task.toml` carries Gourav Kumar's name, email, profile,
   organization and experience text. This task is yours, so `[task].authors` and the
   `[metadata]` author fields need your name, email, profile URL, organization, relevant
   experience, conflicts of interest and AI disclosure wording.
2. **Include the feed-switch tier** (trap 5)? Recommended yes; it is the strongest bet against
   Opus and the largest build item.
3. **Framing**: ion exchange with nitrate peaking (recommended; real safety workflow, published
   selectivities) versus the mathematically identical Langmuir adsorption of micropollutants on
   activated carbon.
4. **Per-call limit**: 60 s (recommended) or 120 s.
5. **Go / no-go.**
