# Reference B: compartmental referee for CABLE_SPEC reports

`referee.py` checks a report against values obtained by a method that shares nothing with the
analytic cable theory used by the task solution and by Reference A: the tree is discretised into
compartments, the resulting sparse linear systems and eigenproblems are solved numerically on a
nested family of meshes, and the results are Richardson-extrapolated to zero spacing.

```
python referee.py --neuron N.json --report R.json [--out verdict.json] [--quiet]   # exit 0 iff pass
python referee.py --solve --neuron N.json --output R.json                           # spec-schema report
```

Dependencies: Python 3.11, NumPy 1.26.4, SciPy 1.11.4. No compiled helper is needed (the only
scalar loop, the Sturm count, runs in ~10 ms on 15000 nodes).

## Units

Conductance uS, capacitance nF, time ms, current nA, voltage mV, resistance MOhm. For a cylinder
of diameter `d` (um) and length `dx` (um): membrane conductance `pi d dx 1e-2 / Rm` uS, membrane
capacitance `pi d dx Cm 1e-5` nF, axial conductance between two points `dx` apart
`100 pi d^2 / (4 Ri dx)` uS. Soma: `pi d_s^2 1e-2 / Rm_s + g_s 1e-3` uS and `pi d_s^2 Cm_s 1e-5` nF.
With these units `tau = C/G` is in ms and `V/I` for `I = 1 nA` is in MOhm.

## Discretisation

Vertex-centred finite volume. Every segment is cut at the queried fractions, so every queried
location is exactly a node (no interpolation anywhere). Each piece of length `l` gets
`n = ceil(l / h0) * 2^level` equal intervals; nodes sit at interval boundaries. Each interval
contributes half of its membrane conductance and capacitance to each of its two end nodes, so
segment ends carry half compartments, and the axial conductance between adjacent nodes is
`100 pi d^2 / (4 Ri dx)`. The proximal end node of a segment is the distal end node of its parent
(the soma node for `parent = 0`): potential continuity and Kirchhoff's law at branch points and at
the soma are then built into the matrix (the shared node simply accumulates every adjoining half
compartment plus, at the soma, the lumped somatic membrane and shunt). Terminals: sealed needs
nothing (the half compartment is the second-order ghost-point treatment), shunt adds `g_end` to the
distal node's diagonal, killed removes the distal node (Dirichlet `V = 0`; the neighbour keeps its
axial conductance to ground). The matrix `G` is a symmetric irreducibly diagonally dominant
Stieltjes matrix (an M-matrix), so sparse LU solves are componentwise accurate despite a condition
number of ~1e8; one step of iterative refinement is applied anyway.

Mesh family: `h0 = 4 um` and four levels (4, 2, 1, 0.5 um); `h0` is raised if the finest mesh
would exceed 20000 nodes (never happens inside the domain: 12 x 600 um gives 14415). Because the
levels are nested by exact halving of every piece, the error of every quantity is a clean series
in `h`, and Richardson extrapolation with exponents (2, 3, 4) over the four levels is used (the
`h^3` term exists in principle at interfaces where the spacing changes, but the observed order is
2.00 everywhere and the extrapolated values from unrelated families `h0 = 3, 4, 5` agree to
1e-10). The uncertainty reported for each quantity is the difference between the four-level
extrapolant and the three-finest-level extrapolant.

AC queries at high frequency see a short AC length constant `lambda / |gamma|`,
`|gamma| = (1 + (w tau_i)^2)^(1/4)` (down to ~10 um in the domain at 2000 Hz). Any frequency for
which `min_i lambda_i/|gamma_i| / 8 < h0` gets its own nested mesh family with that coarser
spacing (capped at 40000 nodes on the finest level), and the extrapolation uses that family's
spacings.

## Quantities

* DC: `G V = e_a`; `R_in(a) = V_a`, `A(a -> b) = V_b / V_a`. One LU factorisation per level, one
  solve per distinct source.
* AC: `(G + j w C) V = e_a` with `w = 2 pi f 1e-3` rad/ms, complex sparse LU; `Z = V_b`,
  magnitude and `atan2` phase in degrees.
* Modes: `G v = mu C v` (C diagonal). The number of eigenvalues below `mu0 = 1/tau_min` is
  obtained exactly by a Sturm (Sylvester inertia) count: `LDL^T` of `G - mu0 C` by eliminating the
  tree from the leaves towards the soma (no fill-in), counting negative pivots. ARPACK shift-invert
  (`eigsh`, `sigma = 0`, `tol = 0`) then returns the `count + 6` slowest modes; each eigenvalue is
  replaced by its Rayleigh quotient `v^T G v / v^T C v` (second-order accurate in the eigenvector
  error). The ARPACK count of `tau >= tau_min`, the Sturm count at the finest level and the count
  from the extrapolated taus must all equal the report's count.
* Coefficients: `C_k = tau_k v_k(soma)^2 / (v_k^T C v_k)` (modal expansion of the somatic input
  impedance `Z(s) = sum_k v_k(soma)^2 / ((v_k^T C v_k)(mu_k + s))`, so the residue at
  `s = -mu_k` is `v_k(soma)^2 / (v_k^T C v_k)`). Extrapolated like every other quantity.
* Transient: on the finest level with at most 8000 nodes, Crank-Nicolson for the somatic unit
  current step with a Rannacher start (the first two steps as pairs of implicit-Euler half steps,
  which damps the compartment-scale stiff modes), `dt = tau_min / 50` (at most 20000 steps), run
  at `dt` and `2 dt` and extrapolated in time. The simulated `V_soma(t)` is compared at eight
  geometrically spaced times in `[12 tau_min, 3 tau_1]` with the modal sum built from the
  REPORTED `(tau_k, C_k)`, completed by the referee's own faster modes (`tau < tau_min`, same
  level) and by the remainder `R_in,sim(soma) - sum C_k` as a constant (all coefficients of a
  passive tree are positive, so the omitted part is bounded by `remainder * exp(-t / tau_c)`,
  which is reported alongside). The residual is reported relative to `R_in(soma)`.

## Verdict

`pass` requires: schema as in spec section 4 (keys, order, locations and frequencies echoed
exactly, modes strictly decreasing); `R_MOhm`, `factor`, `magnitude_MOhm`, `tau_ms` within 1e-6
relative of the extrapolated reference; `phase_deg` within 1e-5 degrees; mode count equal (all
three counts); `coefficient_MOhm` within 1e-6 R_in(soma); transient residual within 1e-5
R_in(soma). The JSON lists, for every item, the report value, the reference, the residual, the
per-level values, the observed convergence order and the extrapolation uncertainty.

An undefined query (source on a killed terminal, where `V = 0`) yields an infinite residual and
fails; the domain guarantees exclude such queries.

## Measured precision and runtime

* `tests/cable_sealed.json` (textbook sealed cable, L = 500 um, lambda = 353.6 um, tau_m = 20 ms,
  soma of 1e-4 um so that it is negligible to 1e-11): extrapolated values agree with
  `coth(L/lambda)/G_inf`, `cosh((L-x)/lambda)/cosh(L/lambda)`, the AC transfer formula and
  `tau_n = tau_m / (1 + (n pi lambda/L)^2)`, `C_0 = tau_m/C_tot`, `C_n = 2 tau_n/C_tot` to 5e-11
  (DC), 5e-10 (|Z| at 2000 Hz across 500 um, attenuation 5.7e-5), 6e-8 degrees (phase at 2000 Hz),
  1e-10 (tau, 7 modes) and 7e-11 R_in (coefficients). Finest-level (0.5 um) values alone are
  accurate to ~1e-7 (DC) and ~1e-6 to 1e-5 (tau near tau_min, high-frequency AC); the
  extrapolation gains 3 to 4 digits.
* `tests/ytree_killed_shunt.json` (soma + parent + killed and shunted children, queries at
  fractions 0.37, 0.5, 1.0, 1 to 2000 Hz): DC and AC agree with the closed-form admittance
  recursion in `tests/run_tests.py` to 6e-11 (6e-10 degrees).
* Domain-extreme random tree (12 segments, 300 to 600 um, d 0.3 to 1.5 um, 53 modes, tau_min
  0.1 ms, 2000 Hz): unrelated mesh families h0 = 3, 4, 5 agree to 1.4e-10 (R_in), 3.6e-10
  (attenuation), 2.3e-10 (|Z|), 9e-9 degrees, 1.1e-8 (tau; the modes nearest tau_min have the
  largest finest-level error, 3.6e-5, and are the least extrapolated), 2.2e-9 R_in (C_k).
  Transient residual 3.6e-7 R_in (dominated by the time-stepping remainder, which is reported).
* Runtime: 0.3 s (Y tree), 3 s (cable, transient dominated), 13 s (53-mode tree, 10527 nodes),
  27 s for the largest neuron the domain allows (12 x 600 um, 14415 nodes, 73 modes, eight
  distinct frequencies up to 2000 Hz with their own AC meshes). The transient (20000 CN steps on
  up to 8000 nodes, twice) is the dominant cost.

## Tests

`python tests/run_tests.py` writes the two neurons and their `--solve` reports, compares the
reports with the analytic values, runs the referee on each report (must pass) and on eight
perturbed copies (one quantity off by 3e-6 relative, phase off by 1e-4 degrees, a dropped mode,
weight moved between two coefficients; every one must fail).
