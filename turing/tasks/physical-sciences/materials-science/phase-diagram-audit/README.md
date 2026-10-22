# phase-diagram-audit

Compute the exact equilibrium phase diagram of a binary system from CALPHAD-style Gibbs energy
models (Redlich-Kister solution phases and stoichiometric compounds): the isothermal sections as
single-phase regions and tie-lines, every three-phase invariant with its class and name, every
congruent point and every consolute point in a temperature window. Then diagnose a legacy
pairwise common-tangent script by executable witnesses.

| | |
| --- | --- |
| Domain | physical-sciences / materials-science / computational-thermodynamics |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Phase diagram calculation from assessed Gibbs energy functions is the daily workflow of
computational thermodynamics (Thermo-Calc, Pandat, OpenCalphad, pycalphad): the equilibrium at a
temperature is the lower convex hull of all phases, and the diagram is the set of temperatures at
which the hull's topology changes. Every quantity asked for is an exact root of smooth equations,
so every answer has a definite value. The spec states the model and the definitions and no method.

What a competent solver gets right: a simple eutectic between two terminal solid solutions, the
common tangent of two convex curves, the lens of a complete solid solution. Where the difficulty
is, each exercised by several of the 28 systems:

1. **Global, not pairwise, equilibrium.** A common tangent of two phases is an equilibrium only
   if no third phase (or compound) lies below it. Pairwise tangents give metastable tie-lines
   inside the liquid field, admit compounds that are never stable and miss ones that are. The
   legacy script makes exactly these errors; the `legacy` control fails 27 of the 28 systems (it
   survives only `held_11`, a window with no event).
2. **Compounds as hull vertices.** A stoichiometric compound is a point, stable only while it is
   a vertex of the hull: it appears through a peritectic or a congruent point, disappears through
   a eutectoid or by melting, and may be stable only inside part of the window or never
   (`held_05`, `held_06`, `model_03`). Its tie-lines end exactly at `x_theta`.
3. **Class and name of every invariant.** Whether a three-phase line is eutectic-type or
   peritectic-type is decided by the stability of the middle phase just above the invariant, not
   by which phases take part. Monotectics (two liquids and a solid), syntectics, metatectics and
   peritectoids are in the held-out set; the "liquid present means eutectic" rule (the `rule`
   control) fails every peritectic-class system.
4. **Exact event temperatures.** Invariants, congruent and critical points are graded to `1e-7`
   relative in temperature (about 1e-4 K): the event has to be solved from its own equations
   (three states on one line and T; tangency of two curves; `G'' = G''' = 0`), not read off a
   temperature scan. A 0.1 K scan without refinement (the `scan` control) fails all 27 systems
   that have an event.
5. **Exact compositions.** Tie-line ends and region bounds are graded to `1e-8` absolute,
   including dilute terminal solubilities of order 1e-5: a hull on a 5e-4 composition grid without
   Newton polishing (the `grid` control) is 9e-5 to 7e-4 off and fails all 28 systems. Near the pure ends `1 - x` must be carried
   without cancellation.
6. **Miscibility gaps and consolute points.** Binodal, not spinodal, boundaries (the `spinodal`
   control fails all 5 systems whose sections contain a gap, by 0.1 to 0.18 in x); upper and lower consolute points (temperature-dependent
   interaction parameters give a lower critical point in `held_09`); metastable critical points
   under a stable liquid are not reported.
7. **Topology bookkeeping.** Pure end-member transitions change the hull but are not events of
   the diagram; events can lie within a few kelvin of each other (`held_12`); windows can contain
   no event at all (`held_11`); a lens that closes and a three-phase line that forms both make a
   single-phase region vanish and must be told apart.
8. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `tangentdiag.py` is a plausible departmental script: pairwise common tangents
checked only at their midpoint, compounds admitted by the mechanical-mixture line, miscibility
gaps bounded by the spinodal, invariants from changes of the tangent set on a 5 K scan classified
by the "liquid present" rule, critical points from the regular-solution formula.

## Reference solution

`solution/phasediagram.py` is event-driven and exact:

- **Certified hull** at anchor temperatures (window start, every isotherm, just after every
  event): the lower hull of a point cloud of all phases (geometric spacing near the pure ends),
  every tie-line polished by Newton on the supporting-line equations (`G = m x + c`, `G' = m`
  for solution states, `G_theta = m x_theta + c` for compounds), merged where a shared state is
  not a hull vertex, and certified against every phase: any point below the hull is inserted and
  the hull recomputed, so the structure is exact whatever the grid.
- **Continuation with indicators.** Between anchors the tie-lines are continued in temperature
  by Newton, and every way the topology can change is watched by a continuous indicator that is
  positive while the structure is valid: a third phase or compound reaching a tie-line
  (invariant, eutectic class), a single-phase region or a compound vertex collapsing (invariant,
  peritectic class), a phase or compound touching a region from above (congruent point, lens
  above), a lens or compound lens closing (congruent point, lens below), `G''` reaching zero in
  a region or a gap closing (critical point). The first indicator to cross zero brackets the
  event; `brentq` locates it and the event's own equations give it to machine precision. Pure
  end-member transitions are solved analytically and crossed without continuing the dilute
  tie-lines. The step is adaptive (0.02 K after an event, up to 0.25 K; the domain guarantees
  events at least 0.5 K apart), closing lenses and gaps use indicators that need no tie-lines
  because their Newton systems degenerate at the closing point, and compositions are carried
  as logits with the complement `1 - x` computed exactly.
- **Self-checks.** At every isotherm and at the window end the continued structure must agree
  with an independent certified hull; an event within 0.02 K of an isotherm or of the window end
  is an error, not a report.

`solution/diagnose.py` runs the legacy script and the program on the shipped systems and writes
witnesses for the five diagnosis quantities; nothing is stored.

## Verification

Every expected value in `tests/expected.json` comes from Reference A (`tests/reference/reference.py`),
an independent implementation built without access to the oracle: common tangents as roots of
the intercept-difference function on slope intervals where it is monotone (split at the exact
roots of `G_P' - G_Q'`), congruent and critical points from the exact polynomials obtained by
eliminating `T`, three-phase events by continuation with smooth indicators, every candidate
accepted only if it lies on the exact hull. Reference B (`refB/referee.py` in the dev folder) is
a certificate checker in 80-bit arithmetic: tangent and collinearity residuals, global stability
of every reported line on a 200,599-point composition grid, Newton re-solution of every event
from the reported values, class and sides from hulls at `T +- 0.1 K`, and a completeness scan of
the window (0.1 K label scan plus a spinodal detector for consolute points) that must match the
reported events and the analytic pure-end transitions one to one.

| Check | Result |
| --- | --- |
| Oracle vs Reference A, 28 systems | every label, class, name and side equal; worst composition difference 3.7e-15 absolute, worst event temperature difference 1.5e-13 relative |
| Reference B referee, 28 systems | 28 pass: tangent residuals <= 7.7e-9 J/mol (double rounding of the reported numbers), stability violations <= 3.2e-12 J/mol, isotherm compositions vs independent construction <= 3.8e-15, event temperatures <= 2.1e-15 relative, no unmatched topology change |
| Totals graded | 104 isothermal sections (91 with tie-lines, 9 miscibility-gap tie-lines), 41 invariants (eutectic 29, peritectic 5, eutectoid 3, monotectic 2, metatectic 1, syntectic 1), 16 congruent points (12 maxima, 4 minima), 6 critical points (5 upper, 1 lower) |
| Oracle in the environment image (`solve.sh`) | base case + diagnosis in 240 s; diagnosis witnesses: `peritectic_count` (model_03), `critical_count` (model_01), `invariant_count` (model_03), `tie_line_count` (model_05), `two_phase_fraction` (model_04) |
| Verifier on the oracle artifacts | 30 passed, reward 1, 429 s; fresh calls 2 to 20 s each |
| Verifier on empty `/root/results` | 30 failed, reward 0 |
| Verifier with a FIFO as `phasediagram.py` | 30 failed, reward 0 |
| Determinism | two runs of the oracle on `model_03` and `held_18` byte-identical and identical to the installed reports |
| Domain | all 28 systems pass the verifier's own `validate_system` |

### Controls (wrong methods, graded with the verifier's comparison against Reference A)

| Control | Shortcut | Fails |
| --- | --- | --- |
| `legacy` | the shipped script | 27 / 28 (passes only `held_11`, no event) |
| `scan` | event temperatures from a 0.1 K scan without refinement | 27 / 28 (all systems with an event); relative error 2.1e-6 to 1.4e-4 |
| `grid` | compositions rounded to the 5e-4 hull grid, no Newton polish | 28 / 28; error 9.0e-5 to 7.2e-4 |
| `rule` | class by "liquid takes part -> eutectic type" | 6 / 28 (every system with a peritectic-class invariant) |
| `spinodal` | gap boundaries at `G'' = 0` | 5 / 28 (every section with a gap); error 0.11 to 0.18 |

### Tolerances

| Quantity | Tolerance | Method spread (oracle vs Reference A / referee) | Nearest wrong answer |
| --- | --- | --- | --- |
| compositions (`x_lo`, `x_hi`, `x_left`, `x_right`, `x`) | 1e-8 absolute | 3.7e-15 | 9.0e-5 (`grid`) |
| event `temperature_K` | 1e-7 relative | 1.5e-13 | 2.1e-6 (`scan`) |
| `two_phase_fraction` witness | 1e-6 absolute | 1e-14 | legacy errors >= 0.05 on the shipped systems |

The tolerances sit more than four orders of magnitude above the method spread and more than an
order of magnitude below the nearest wrong method; they also admit a solver that is 1e4 times
less precise than the oracle (compositions to 1e-8 are what a double-precision Newton on the
tangent equations delivers routinely).

### Coverage of the 28 systems

| System | phases / compounds | window (K) | isotherms | max tie-lines | invariants | congruent | critical | fresh call (s) | structure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `held_01` | 3 / 0 | 591-909 | 3 | 1 | eutectic | 1 | 0 | 8 | simple eutectic |
| `held_02` | 3 / 0 | 645-1809 | 3 | 3 | eutectoid, eutectic, peritectic | 0 | 0 | 16 | peritectic between terminal solid solutions |
| `held_03` | 2 / 0 | 1606-1937 | 5 | 2 | - | 1 | 0 | 5 | lens with a congruent maximum |
| `held_04` | 2 / 0 | 486-1674 | 3 | 2 | - | 1 | 0 | 9 | lens with a congruent minimum |
| `held_05` | 3 / 2 | 1153-1951 | 6 | 3 | eutectic, eutectic | 0 | 0 | 12 | a compound that is never stable |
| `held_06` | 3 / 1 | 715-1867 | 5 | 2 | eutectic, peritectic | 0 | 0 | 19 | compound stable only inside part of the window |
| `held_07` | 3 / 2 | 831-1646 | 2 | 2 | eutectic, eutectic | 1 | 0 | 13 | congruently melting compound with eutectics |
| `held_08` | 2 / 0 | 1025-2008 | 6 | 2 | - | 1 | 1 | 11 | solid miscibility gap, two tie-lines at an isotherm |
| `held_09` | 2 / 0 | 1076-1434 | 2 | 2 | eutectic | 0 | 1 | 6 | lower consolute point |
| `held_10` | 2 / 0 | 301-1104 | 6 | 2 | syntectic | 0 | 1 | 9 | syntectic |
| `held_11` | 3 / 0 | 360-465 | 2 | 1 | - | 0 | 0 | 2 | window with no event |
| `held_12` | 3 / 1 | 474-1440 | 4 | 4 | eutectic, eutectic | 1 | 0 | 15 | two invariants close in temperature |
| `held_13` | 4 / 0 | 820-1570 | 2 | 3 | eutectoid, eutectic | 0 | 0 | 15 | allotropic transition with two invariants |
| `held_14` | 4 / 0 | 1274-1817 | 3 | 4 | eutectic, eutectic | 1 | 0 | 12 | intermediate solid solution melting congruently |
| `held_15` | 4 / 0 | 301-1350 | 3 | 1 | eutectic, peritectic | 0 | 0 | 20 | intermediate solid solution forming peritectically |
| `held_16` | 3 / 0 | 994-1326 | 4 | 2 | monotectic | 0 | 1 | 5 | monotectic and liquid consolute point |
| `held_17` | 3 / 2 | 588-1564 | 2 | 3 | eutectic, eutectic, eutectic | 2 | 0 | 16 | several compounds, three or more invariants |
| `held_18` | 4 / 1 | 568-1751 | 3 | 3 | eutectoid, eutectic, peritectic, eutectic | 1 | 0 | 18 | mixed system with four or more events |
| `held_19` | 3 / 1 | 628-1297 | 3 | 3 | eutectic, eutectic | 1 | 0 | 11 | mixed system with three or more tie-lines at one isotherm |
| `held_20` | 2 / 0 | 1467-1837 | 5 | 2 | - | 1 | 0 | 5 | congruent maximum, two tie-lines |
| `held_21` | 3 / 0 | 609-1725 | 5 | 2 | eutectic | 0 | 0 | 15 | eutectic, two tie-lines at an isotherm |
| `held_22` | 3 / 1 | 927-1613 | 3 | 2 | eutectic, eutectic | 1 | 0 | 12 | mixed system with a compound |
| `model_01` | 3 / 0 | 517-1578 | 4 | 1 | eutectic | 0 | 0 | 14 | simple eutectic between two terminal solid solutions (base case) |
| `model_02` | 2 / 0 | 402-835 | 3 | 2 | - | 1 | 1 | 5 | lens with a congruent minimum |
| `model_03` | 3 / 2 | 561-1514 | 5 | 3 | eutectic, peritectic, eutectic | 1 | 0 | 16 | compounds: peritectic decomposition and eutectics |
| `model_04` | 2 / 0 | 1110-1803 | 4 | 2 | - | 1 | 1 | 9 | solid miscibility gap with an upper consolute point |
| `model_05` | 4 / 0 | 563-1476 | 4 | 3 | eutectic, metatectic | 0 | 0 | 16 | allotropic transition of pure A inside the window |
| `model_06` | 3 / 0 | 620-1164 | 4 | 1 | eutectic, monotectic | 0 | 0 | 7 | liquid miscibility gap: monotectic |

### Reproduction (dev folder `turing/tbScience/phase-diagram-audit-dev`)

`tools/gen_systems.py` (28-slot plan, guarantee screening), `tools/repick.py`,
`tools/final_pipeline.sh`, `tools/agree.py`, `controls/controls.py`, `tools/controls_study.py`,
`refA/` (Reference A with METHOD.md and tests), `refB/` (referee with METHOD.md and tests),
`evidence/` (Docker logs, CTRF, rewards), `tools/build_zip.py`.
