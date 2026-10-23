# Reference A: method, independence, measured precision

`reference.py` (single file, numpy + scipy only) implements CABLE_SPEC.md section 4 from a route
that shares no formula with the oracle's terminal-to-soma admittance recursion.

Run: `python reference.py --neuron <neuron.json> --output <report.json>` (an optional
`--verbose` flag is accepted but changes nothing; diagnostics go to stderr, which the verifier
ignores). Runtime 1.3 to 2.9 s per test neuron on one CPU (Intel Mac, OPENBLAS_NUM_THREADS=1);
the 40 s budget is never approached. Deterministic (the only iterative solver, ARPACK, is given a
fixed start vector; the result of every refinement is a brentq root of an analytic function).

## 1. Units

Lengths um -> cm, Cm uF/cm2 -> F/cm2, nS -> S, time in s internally, `s` in 1/s. Soma area is
`pi d_s^2` (sphere). `lambda_i = sqrt(Rm d/(4 Ri))` cm, `G_inf = (pi/2) d^1.5 / sqrt(Rm Ri)` S,
`tau_i = Rm Cm` s. Outputs: ohm -> MOhm, s -> ms, phase by `atan2` in degrees mapped to
(-180, 180].

## 2. DC and AC: nodal admittance matrix with analytic interior points

Nodes are the soma and the distal end of every segment (a killed terminal's end is ground and has
no unknown). Each segment is one exact two-port between its two end nodes,

    Y_piece = G_inf gamma [[coth x, -csch x], [-csch x, coth x]],   x = gamma L/lambda,
    gamma = sqrt(1 + s tau),

evaluated as `coth x = (1+e^{-2x})/(1-e^{-2x})`, `csch x = 2 e^{-x}/(1-e^{-2x})` with
`1-e^{-2x} = -expm1(-2x)`, so nothing overflows at 2000 Hz on a long thin segment (|x| up to
10^4) and nothing cancels for a short one. The soma node carries `G_s + s C_s`; a shunt terminal
adds `g_end` to its node. One dense `numpy.linalg.solve` (real at DC, complex at AC) per injection
site gives every nodal potential.

Interior locations never enter the matrix (splitting segments at a query fraction such as 0.001
cost about 1e-12 relative in an earlier version through LU cancellation; the analytic treatment
below is exact to rounding):

* a source at electrotonic position `xi_a` inside a segment of length `x` is equivalent to the
  nodal currents `sinh(x - xi_a)/sinh x` at the proximal end and `sinh(xi_a)/sinh x` at the
  distal end (the end currents of the killed-killed cable driven at `xi_a`), plus the particular
  solution on that segment, the killed-killed Green's function
  `sinh(min) sinh(x - max) / (G_inf gamma sinh x)`;
* the potential at `xi` inside any segment is the hyperbolic interpolation
  `[V_p sinh(x - xi) + V_q sinh(xi)] / sinh x` of its end potentials (plus the Green's function
  term when the source is on the same segment).

`R_in(a) = V(a)` for unit current at `a`; `A(a->b) = V(b)/V(a)` from the same solve (direction
matters because the solve is for current at `a`); `Z(a->b, f) = V(b)` at `s = 2 pi f j`.

## 3. Time constants: entire function from transfer pairs, roots bracketed two ways

For real `s` the tree is propagated from the terminals to the soma as (V, I) pairs:

    [V_p; I_p] = [[cosh x, sinh x / (G_inf gamma)], [G_inf gamma sinh x, cosh x]] [V_d; I_d]

with terminal pairs (1, 0) sealed, (0, 1) killed, (1, g_end) shunt. At a junction the children's
pairs are made consistent by the product rule `V = prod V_c`, `I = sum_c I_c prod_{c' != c} V_c'`.
Everything is written in `u = x^2 = (1 + s tau) (L/lambda)^2` through the even functions
`cosh sqrt(u)` and `sinh(sqrt u)/sqrt u` (series below |u| = 1e-6, trigonometric form for
u < 0), so `E(s) = I_soma + (G_s + s C_s) V_soma` is manifestly entire and real, and
`Z_soma = V_soma / E`. Pairs are rescaled by a positive factor at every junction and each piece
is multiplied by `e^{-Re x}`; these scales multiply V and E alike, so roots, signs and the ratio
`V/E'` at a root are unchanged. The derivative `E'(s)` is carried along analytically
(forward-mode differentiation of every product and of the two even functions, with the scales held
fixed, which is exact at a root). A complex-step derivative was tried first and discarded: for
`s < -1/tau` the intermediate `x` is imaginary and the perturbation leaves the imaginary part, so
the step is rounded away in `exp(x)`; the measured error was a factor 30 at h = 1e-20.

Root location:

1. Compartmental model: vertex-centred second-order discretisation (half membrane area at the
   end points, lumped soma, killed node removed, shunt added), about `max(1500, 40 N_est)` points
   (N_est from the WKB count `sum (L/lambda) sqrt(|s_min| tau - 1) / pi`) and again at twice the
   resolution; eigenvalues of the symmetrised `C^{-1/2} G C^{-1/2}` near 0 from
   `scipy.sparse.linalg.eigsh` in shift-invert mode (dense `eigh` below 600 points); Richardson
   extrapolation `(4 w_fine - w_coarse)/3` with error estimate `|w_fine - w_coarse|/3`.
2. Sign scan of `E` on a geometric grid of relative spacing 2.5e-4 over
   `[-1/tau_min (1 + 2e-3), -1e-4/tau_max]`; every sign change is refined with `brentq`
   (rtol 1e-15). Every compartmental estimate is matched to a refined root (the deviation is
   logged); an unmatched estimate is bracketed at 3, 10 and 30 error estimates and refined.
3. Argument principle: the winding number of `E` (complex evaluation of the same pair product,
   positive scales) around a closed contour of two rays at angle 2e-3 above and below the negative
   real axis from `-1e-4/tau_max` to `-1/tau_min`, closed by short vertical segments, sampled at
   relative spacing 5e-4 and refined adaptively until every phase step is below pi/3. The winding
   number must equal the number of refined roots in `[-1/tau_min, 0)`; otherwise the scan is
   repeated ten times denser (this path is exercised only outside the domain, see NOTES.md).

`C_k = tau_k V(s_k) / E'(s_k)` (equals `tau_k Res Z_soma`; for a single RC it gives `1/G`).

Why the roots of `E` are exactly the spec's time constants: `E = V_soma F` with `F` the total
somatic admittance, a positive-real function with simple real interlacing zeros and poles; the
zeros of `E` are the zeros of `F` (poles of `Z_soma`) plus zeros of `V_soma` not cancelled by poles
of `F`, which occur only when two sibling subtrees share a killed-root eigenvalue (a mode invisible
from the soma, coefficient exactly 0, excluded by guarantees 2 and 4). The compartmental model
counts all tree eigenvalues, so the two counts and the winding number agree in the domain.

## 4. Independence from the oracle

No admittance recursion, no `tanh`, no voltage propagation by hyperbolic ratios from the soma
outward, no scan of the recursion's cleared denominator. DC/AC come from a linear system over the
branch points with Green's-function source handling; modes come from a transfer-matrix product
whose roots are bracketed by a finite-difference eigenproblem and certified by a contour integral;
derivatives are analytic. Agreement with the oracle at 1e-9 therefore means two unrelated
computations coincide.

## 5. Measured precision (tests/check_tests.py, all 8 neurons, 0 failures)

| check | result |
| --- | --- |
| `R_in(soma)`, `R_in(end)`, `R_in` at fraction 0.001 vs closed forms, sealed and killed cable | <= 7.6e-15 rel |
| `A(soma->x)` vs `cosh(X-xi)/cosh X` (sealed) and `sinh(X-xi)/sinh X` (killed) | <= 2.5e-15 rel |
| Rall tree vs equivalent cylinder: `R_in`, `A`, `|Z|` and phase at 100 Hz, `Z` to both tips | <= 7.5e-15 rel, phase 1.4e-14 deg |
| reciprocity `Z(a->b) = Z(b->a)`, 12 pairs, 20 to 2000 Hz | <= 4.4e-16 rel, phase <= 2.9e-14 deg |
| `A(a->b) R_in(a) = A(b->a) R_in(b)` | <= 3.5e-16 rel |
| `tau_k` vs independent brentq on the exact one-cable condition `G_s + s C_s + G_inf gamma tanh(gamma X) = 0` (sealed) and the killed analogue | <= 4.5e-16 rel |
| compartmental (Richardson) vs exact roots, in-domain lists | 2.4e-8 to 1.2e-7 rel |
| argument-principle winding vs number of roots | integer to 1e-6, equal in every test |
| `sum C_k` over an extended list (tau down to tau_min/400, up to 444 modes), Richardson in 1/K, vs `R_in(soma)` | 1e-5 to 1e-4 rel (tail extrapolation limit) |
| hidden mode of the exact Rall tree | found at the quarter-wave value 0.21384 ms with `C = -5e-14` MOhm |

Rounding budget relative to the spec tolerances: `R`, `A`, `|Z|`, `tau` carry about 1e-14, two
hundred thousand times inside 1e-9; coefficients are products of a root (1e-15) and an analytic
derivative, so about 1e-13 of `R_in(soma)`.
