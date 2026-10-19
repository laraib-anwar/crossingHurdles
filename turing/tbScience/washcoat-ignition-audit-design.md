# Design: `washcoat-ignition-audit`

Proposed third TB-Science task, 19 October 2026. Design for approval; nothing built.

| | |
| --- | --- |
| Working name | `washcoat-ignition-audit` (alternatives: `catalyst-layer-multiplicity`, `pellet-ignition-audit`) |
| Domain / category / subcategory | engineering-sciences / chemical-engineering / reaction-engineering (heterogeneous catalysis) |
| Science | non-isothermal reaction-diffusion in a catalytic washcoat layer with external film resistances: exact ignition and extinction points, isolated solution branches (isolas), multiplicity counts, and the stability of every steady state from the linearised transient problem with a Lewis number |
| Deliverable | the pattern that passed: a program the verifier reruns on shipped and held-out recipes, a saved base-case report, and a `diagnosis.json` with executable witnesses against a legacy script |
| Answer key | slab geometry has a first integral: the steady problem reduces to one-dimensional quadratures and root finding (exact, independent route); the oracle uses collocation plus pseudo-arclength continuation; a transient PDE code referees stability |

## 1. The problem and why it is real

A monolith catalytic converter's active material is a thin porous washcoat on the channel wall.
At cold start the exothermic oxidation (CO, hydrocarbons) in the layer is diffusion-limited and
self-heating: the layer sits on a cold "extinguished" branch, then jumps to an "ignited" branch
as the gas warms (light-off). The Weisz-Hicks problem (non-isothermal reaction-diffusion with
Arrhenius kinetics) has multiple steady states for large heat-of-reaction and activation
parameters, and emission engineers compute light-off and hysteresis from exactly this model.
With external film resistances (heat and mass Biot numbers) the picture changes: ignition can
move to the film, isolas appear for some parameter sets, and with a Lewis number different from
one the ignited branch can lose stability through a Hopf bifurcation (Luss and coworkers), which a
steady-state-only analysis misses entirely.

The task: for a given layer (Prater number `beta`, Arrhenius number `gamma`, heat and mass Biot
numbers, Lewis number, reaction order 1), locate every fold of the steady-state branch in the
Thiele modulus `phi`, every isola, the number of steady states at given `phi` values, the
effectiveness factor and centre temperature on each branch at those `phi`, the stability class of
each state (stable node/focus, saddle, unstable focus) and every Hopf point, over a stated
`phi` window. Then diagnose a legacy script that uses an effectiveness-factor chart approach, a
shooting method and a "middle branch is unstable, outer branches stable" rule.

## 2. Model (what the spec states)

Slab (washcoat on an impermeable wall), symmetric about the wall-side centre; dimensionless
reactant `c(x,t)`, temperature `theta(x,t)` on `0 < x < 1`, first-order Arrhenius reaction:

```
Le dtheta/dt = d2theta/dx2 + beta phi^2 c exp(gamma theta / (1 + theta))
   dc/dt    = d2c/dx2     -       phi^2 c exp(gamma theta / (1 + theta))
```

Centre `x = 0`: zero flux. Surface `x = 1`: `-dc/dx = Bi_m (c - 1)`, `-dtheta/dx = Bi_h theta`
(bulk gas at `c = 1`, `theta = 0`). Steady states: `d/dt = 0`. Effectiveness factor
`eta = (1/phi^2) * (-dc/dx at x = 1)`... (stated exactly in the spec, with the convention). A
steady state is stable when every eigenvalue of the linearised operator has negative real part;
a fold is where the branch turns in `phi`; a Hopf point is where a complex pair crosses the
imaginary axis; an isola is a closed branch disconnected from the main one. The spec fixes every
convention (ordering of states, how many decimals, which quantities per state, how an isola is
reported, degenerate cases) and no method.

## 3. Traps (playbook section 7 pattern)

1. **Exact fold positions** in `phi` to 1e-6 relative where a mesh in `phi` plus Newton misses
   the turning point; two folds designed to lie within 1e-3 of each other (near-cusp parameter
   sets).
2. **Isolas**: continuation from the low-temperature branch never reaches them; the recipe
   domain includes parameter sets with one isola (and the count of steady states jumps 1 -> 3 ->
   5 -> 3 -> 1 across the window). Finding them needs a global method (the slab first integral,
   a two-parameter continuation from the cusp, or a sweep in centre temperature instead of `phi`).
3. **Stability is not "middle branch unstable"**: with `Le < 1`... (direction to be confirmed in
   the build) the ignited branch has a Hopf point; the stability class must come from the
   eigenvalue problem of the two-field linearisation, not from a slope rule. Hopf points are
   graded as events to 1e-6 in `phi`.
4. **Film resistances**: finite `Bi_m`, `Bi_h` change the fold positions by tens of percent and
   can move ignition to the external film; using the Dirichlet (infinite Biot) problem fails.
5. **Near-degenerate points**: a Hopf point within 1 % of a fold (Bogdanov-Takens
   neighbourhood) where the classification must be computed, and a cusp where two folds merge
   (the recipe domain crosses the cusp locus, so some recipes have no multiplicity: an empty fold
   list is a required output).
6. **Many nodes**: 28 recipes graded all-or-nothing; each exercises several traps.

Legacy script defects: effectiveness-factor correlation (generalised Thiele modulus
approximation) instead of solving the layer; shooting from the centre that misses branches;
stability from the slope rule; Dirichlet boundary conditions regardless of Biot numbers.

## 4. Answer key

| Route | Method |
| --- | --- |
| Oracle | Chebyshev collocation of the steady BVP, pseudo-arclength continuation in `phi` with fold detection by the sign of `d phi/ds`, isola search by two-parameter continuation from the cusp locus and by a sweep in centre temperature; stability from the generalised eigenvalue problem of the linearised two-field operator (collocation), Hopf detection by tracking the rightmost pair and bisection on its real part |
| Reference A (independent) | slab first integral: for the steady problem `theta - beta_eff c` satisfies... with `Le`-free steady states the two equations combine (with the Biot boundary conditions handled through the surface values) into a single second-order ODE with a first integral, so each steady state is a root of a one-dimensional function of the centre temperature evaluated by quadrature; folds are extrema of `phi(theta_c)`; isolas appear as closed loops of that curve. Eigenvalues by a shooting method on the linearised equations with the Lewis number (Prüfer-type), independent of collocation |
| Reference B (referee) | method-of-lines transient simulation (finite volumes, implicit) to confirm stability classes, Hopf oscillations and light-off/extinction hysteresis |

Expected agreement oracle vs A: 1e-9 in `phi` at folds and Hopf points; eigenvalues 1e-8.

## 5. Risks and honest assessment

- **Similarity.** The CSTR task (Gourav's) also grades folds, Hopf points and stability
  classes, in a two-ODE lumped reactor. This one is a distributed reaction-diffusion problem
  (BVP, eigenvalue problem of a PDE operator, Biot numbers, isolas) in heterogeneous catalysis,
  with a different deliverable structure. Vocabulary overlaps ("fold", "Hopf", "stable
  focus"). The similarity check is content-based; I judge the risk moderate and would phrase
  the spec in the washcoat/light-off language of the field.
- **Could Opus pass?** Collocation plus continuation is within its reach for the main branch.
  Isolas, the Lewis-number Hopf and the near-degenerate classifications are where I expect
  failures; a steady-state-only solver fails every recipe with a Hopf point.
- **Build risk.** The first-integral route for the slab with Robin (Biot) boundary conditions
  must be derived carefully (it exists because the steady equations give `theta + beta c =
  const` only with equal Biot numbers; with unequal Biot numbers the invariant is linear with a
  surface-determined constant). If it does not close in general, Reference A becomes a shooting
  method, still independent of collocation. Estimate 14 to 20 agent hours.

## 6. Alternative considered

`stefan-maxwell-condenser` (multicomponent film condensation with exact Maxwell-Stefan
transport, Toor's reverse and osmotic diffusion and diffusion barriers, Ackermann correction,
bootstrap conditions): clean exactness (matrix exponential solution) and real workflow, no
similarity risk, but it is algebra that a careful model is likely to get right; fewer traps.

## 7. Decisions needed

1. Go with `washcoat-ignition-audit` (recommended) or the Maxwell-Stefan alternative?
2. Same author fields as the ion-exchange task (yours; profile and experience still to fill).
3. Go / no-go.
