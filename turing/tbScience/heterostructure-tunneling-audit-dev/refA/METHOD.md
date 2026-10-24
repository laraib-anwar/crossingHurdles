# Reference A: method, independence and measured precision

`reference.py` is a single file that needs only NumPy 1.26.4 and SciPy 1.11.4:

```
python reference.py --structure <structure.json> --output <report.json>
```

It writes the section-4 report of HETERO_SPEC. The program is deterministic (two runs over all
28 gen structures, in a fresh directory with the verifier's environment, gave byte-identical
files). It writes only finite numbers: `json.dump(..., allow_nan=False)` runs after an explicit
finiteness check, and no unscaled exponential is ever formed. Transmission energies are echoed
exactly as they appear in the structure file.

## 1. Formulation: one global linear system

Units are nm and eV, with C = 0.0380998212 eV nm^2. Write w = psi'/m, which is continuous at
every interface. Layer j (thickness d, mass m) carries psi = c1 f1 + c2 f2 in the local
coordinate s = x - x_{j-1}. Each basis is normalised at the layer ends so that the coefficients
stay O(1):

| layer | condition (q = m (E - V)/C) | f1, f2 |
| --- | --- | --- |
| flat | q d^2 > 1 | cos(k s), sin(k s) |
| flat | \|q\| d^2 <= 1 | C(q,s) = cos(sqrt(q) s), S(q,s)/d with S = sin(sqrt(q) s)/sqrt(q), as power series in q s^2 (entire in E) |
| flat | q d^2 < -1 | exp(-kappa s), exp(kappa (s - d)) |
| sloped, general | z = lambda (V(x) - E), lambda = (m / (C slope^2))^(1/3) | Ai(z)/S_A, Bi(z)/S_B with S_A = Ai(max(z_min, 0)) and S_B = Bi(max(z_max, 0)); `airye` with separated exponents for z > 0, `airy` for z <= 0 |
| sloped, z > 0 on the whole layer | | the same basis; the decay exponent zeta(z_max) - zeta(z_min) is formed without cancellation as (2/3) dz (z1 + sqrt(z1 z2) + z2)/(sqrt z1 + sqrt z2), with dz = lambda \|vr - vl\| taken from the layer data |
| sloped, z <= -12 on the whole layer | x = -z | the Ai, Bi basis rotated by the Airy phase at the left end: M(x) sin(theta - theta_a), M(x) cos(theta - theta_a), where Ai(-x) = M sin(theta) and Bi(-x) = M cos(theta) |

In the last case, M and theta come from my own large-argument series (section 5). The phase
difference theta_b - theta_a across the layer is formed without cancellation, so a layer at
|z| ~ 900 does not inherit the ~4e-12 absolute rounding of a phase of size 18000.

The unknowns are ordered `[lead L, c11, c12, ..., cN1, cN2, lead R]`. The 2(N+1) equations
(psi continuity, and w continuity scaled by the constant sqrt(0.3 C)) at the N+1 interfaces form
a banded 2(N+1) x 2(N+1) matrix D(E):

- **Transmission.** The left lead carries e^{ikx} + r e^{-ikx}, written as `r` plus a right-hand
  side from the unit incident wave. The right lead carries t e^{ik(x-X)}. The program solves
  D x = b (batched `numpy.linalg.solve`) and returns T = (k_R/m_R)/(k_L/m_L) |t|^2. Because the
  exponentially scaled bases make the system self-scaling, elimination keeps t relatively
  accurate down to T ~ 1e-30 (measured below).
- **Bound states.** Both leads decay (coefficient columns (1, kappa_L/m_L) and
  (-1, kappa_R/m_R)), b = 0, and the bound states are the zeros of det D(E). Every change of
  basis between regimes multiplies the determinant by a positive factor:
  - flat, q d^2 = +1: the two forms coincide;
  - flat, q d^2 = -1: factor 2/e;
  - Airy normalisations: S_A, S_B > 0;
  - Airy rotation: determinant S_A S_B > 0.

  So sign(det D) is consistent over the whole energy axis and changes exactly at the (simple)
  bound states. det D is evaluated by LU (`slogdet`: sign and log-magnitude).

## 2. Bound states: Sturm count, isolation, determinant roots

**Independent count.** N(E) is the number of nodes, on the whole real line, of the solution
that decays at -infinity, and it equals the number of eigenvalues below E (oscillation
theorem). It is computed by forward propagation of the normalised vector (psi, w) piece by
piece:

- **Flat oscillatory piece.** The Pruefer phase advances by exactly k d.
- **Sloped oscillatory piece (z <= 0).** The phase advance is |vartheta(z_e) - vartheta(z_s)|,
  where vartheta is the continuous Airy phase (Ai = M cos vartheta, Bi = M sin vartheta). It is
  the principal atan2 for -1 <= z <= 0 and is lifted to pi/4 - (2/3)|z|^{3/2} for z < -1.
- **Counting zeros in an oscillatory piece.** The number of zeros in the open piece lies within
  1 of (phase advance)/pi, and its parity is fixed by the signs of psi at the two ends. The
  count is therefore the integer of that parity nearest to advance/pi. This makes the count
  consistent with the propagated end vector, even when a node sits within rounding of an
  interface.
- **Evanescent pieces (V >= E: flat, or the z >= 0 part of a sloped layer, which is split at the
  turning point).** There is at most one zero, decided by the end signs. Propagation uses
  scaled cosh/sinh, or scaled Airy, growing parts.
- **Right lead.** There is one extra zero when the coefficient of exp(+kappa_R (x - X)) has the
  sign opposite to psi(X).

**Isolation and certification.** N is evaluated at E_top = min(V_L, V_R) - 2e-5 eV (guarantee
1 puts every state at least 1e-4 eV below E_th) and at E_bot = min V - 1e-3. The program then
bisects on N until every bracket holds exactly one eigenvalue (guarantee 1 gives a spacing of at
least 1e-6 eV, so the depth is bounded). The number reported equals N(E_top) by construction.

**Refinement.** Brent's method runs on sign(det) * exp(log|det| - ref) inside each certified
bracket, with xtol = 1e-15 and rtol = 8.9e-16. If the bracket ever showed no determinant sign
change (never observed), the program falls back to bisection on N.

## 3. Transmission maxima

**Grid.** dT/dE is evaluated analytically on a uniform grid of step <= 5e-5 eV that includes
both window ends, and the program looks for sign changes.

**Why the step is sufficient.** Guarantee 3 puts consecutive extrema at least 2e-4 eV apart and
at least 2e-4 eV from the window ends. A closed grid interval of length 5e-5 < 2e-4 therefore
contains at most one extremum. Each interval holding a maximum shows a +/- sign change, and no
other interval does. A plain value scan would need step <= 1e-4 for the same guarantee;
5e-5 adds a factor of 2 margin.

**Analytic derivative.**

- dx/dE = D^{-1} (db/dE - (dD/dE) x).
- dT/dE = T (k_R'/k_R - k_L'/k_L) + (k_R/m_R)/(k_L/m_L) 2 Re(conj(t) t'), with k' = m / (2 C k).
- The basis derivatives are analytic in every regime:
  - flat: chain rule in k or kappa, and term-wise series derivatives in regime 2;
  - Airy, general: dz/dE = -lambda, Ai'' = z Ai, plus the derivative of ln S_A or ln S_B when
    the normalisation point is at z > 0;
  - Airy, rotated: dx/dE = lambda, f'' = -x f, and d(theta_a)/dE = lambda theta'(x_a).

**Refinement and noise filter.** Each maximum is refined by Brent on the analytic dT/dE inside
its grid interval, and T is evaluated at the root. Adjacent extremum pairs whose T values differ
by less than 1e-7 relative are discarded as numerical noise; genuine maxima exceed their
neighbours by at least 1e-3 under guarantee 3. The filter never fired on any structure tested.

## 4. Independence

**What I read.** I read only HETERO_SPEC.md and the structure files in `gen/structures/`. I did
not open `solution/`, `refB/`, `tools/`, `controls/`, `fin/`, `out_controls/`, the gen logs, or
any gen output other than the structure files.

**How Reference A differs from the oracle as described to me:**

| | oracle | Reference A |
| --- | --- | --- |
| formulation | propagates a 2-vector with layer transfer matrices | one global continuity system with layer-end-normalised bases |
| bound states | node count by sampling, then matching the propagated direction to the right-lead decay | roots of det D(E) bracketed by a Pruefer/Airy-phase Sturm count (parity-reconciled, no sampling) |
| transmission | backward propagation of the outgoing solution | linear solve with unit incidence |
| maxima | T scan at 1e-5 eV and central-difference dT/dE | scan of analytic dT/dE signs at 5e-5 eV, roots of the analytic derivative |
| large Airy arguments | separated-exponent scipy values | own asymptotic modulus/phase, with phase and exponent differences formed without cancellation |

The shared ingredients are the model equations, scipy's `airy`/`airye` (only for |z| < 12 or for
mixed layers), and LAPACK.

## 5. Large-argument Airy series (own)

M^2(x) = (pi sqrt x)^-1 sum_k (-1)^k (6k-1)!!/(k! 96^k) x^{-3k}. Note the alternating sign in
|z|: DLMF writes the series in the negative argument itself.

theta(x) = pi/4 + (2/3) x^{3/2} + sum_{k>=1} th_k x^{3/2 - 3k}. The coefficients th_k are derived
in exact fractions from theta' = 1/(pi M^2), and they reproduce DLMF 9.8.22 (-5/32, 1105/6144,
-82825/65536, 1282031525/58720256 relative to (2/3) x^{3/2}).

With 9 terms, the series is used for x >= 12. It matches scipy's Ai(-x), Bi(-x), Ai'(-x) and
Bi'(-x) to 2e-16 to 2e-14 for x in [12, 30], where scipy is reliable. A vectorised path and a
scalar (Horner) path agree to 3e-16.

## 6. Measured precision

**Sources of the measurements:**

- `tests/hp.py` is an independent checker in Python `decimal`, at 50 digits plus the decimal
  growth through barriers. It uses Taylor-series integration of psi'' = (m/C)(V - E) psi across
  every layer, flat and sloped, with no Airy functions and no global matrix.
  - T comes from the real 2x2 transfer matrix.
  - Bound states come from sign bisection of the right-lead mismatch to 1e-19 eV.
  - Maxima come from a secant on a 1e-15 eV central difference of T.
- `tests/closed_form.py` checks the closed forms.
- `tests/run_checks.py` runs the internal checks.

The table gives maximum values over the 28 gen structures (`tests/check_results_gen.json`) and
over my 9 test structures (`tests/check_results_tests.json`).

| check | 28 gen structures | 9 test structures |
| --- | --- | --- |
| bound-state E vs hp | 3.3e-16 eV | 2.9e-15 eV (t9, Airy arguments ~900); others <= 4.4e-16 |
| query T vs hp (relative) | 1.5e-13 (held_07) | 3.0e-13 (t9); others <= 2.1e-14 |
| maximum E vs hp | 4.8e-14 eV (held_17) | 3.6e-15 eV (t9) |
| maximum T vs hp (relative) | 1.3e-14 | 6.4e-14 (t9) |
| analytic dT/dE vs hp central difference (relative to max(\|dT/dE\|, T)) | 1.4e-12 (model_02) | 7.2e-13 (t3) |
| current conservation \|r\|^2 + T - 1 | 1.3e-14 | 1.8e-15 |
| reversal symmetry T(right incidence)/T(left) - 1 | 1.4e-13 | 1.9e-14 |
| Sturm count at E_n -/+ 1e-9 equals n / n+1, and N(E_top) = number reported | all pass | all pass |
| det root vs bisection on the Sturm count alone | 1.1e-15 eV | 9.9e-15 eV (t2), 8e-14 (t9: the count uses scipy at \|z\| ~ 900) |
| maxima count vs an independent T-value scan at 1e-5 eV | all agree | all agree |

**Closed forms** (`tests/closed_form_results.json`):

| case | agreement |
| --- | --- |
| finite square well, BDD even/odd equations (t1) | 9e-17 eV |
| symmetric double well, even/odd with the central-barrier tanh/coth, including a 4.70e-6 eV splitting (t2) | 8e-17 eV |
| triangular well against a step, Airy equation (beta/m) Ai'(z0) = (kappa_L/m_L) Ai(z0), 13 lowest states (t3) | 3.9e-16 eV |
| rectangular barrier, sinh and sin formulas (t1, t7, t8; T from 1.6e-5 down to 1.2e-26) | <= 2e-15 relative |
| rectangular-barrier maxima at q d = n pi with T = 1 | <= 4.4e-16 eV, \|T - 1\| <= 7e-16 |

**Limits:**

- **Infinite square well**, barrier height 1e2, 1e4, 1e6 eV: the relative deviation from
  C (n pi/L)^2/m_w is -0.0775, -0.00819, -0.000823. It approaches the penetration estimate
  -4 m_b/(m_w kappa L) (-0.0824, -0.00824, -0.000824) as 1/sqrt(V).
- **Triangular well with an infinite wall**, wall height 1e2, 1e4, 1e6 eV: the relative
  deviation from (C F^2/m)^{1/3} |a_n| is -1.3e-2, -1.3e-3, -1.3e-4, falling as 1/sqrt(V).

**Analytic vs finite-difference dT/dE in double.** Richardson-extrapolated central differences
with h = 1e-5 agree to 2e-11 to 9e-10. That residual is the finite-difference floor: the
error grows as h shrinks. The hp comparison above is the sharper test.

**Where the remaining error comes from.** scipy's `airye` satisfies its Wronskian only to
3.3e-14 near z ~ 9, and `airy` to 1.4e-14 on [-12, 0]. Thin barriers and resonances amplify
this to the 1e-13 level in T (held_07, t9). Near a resonance with d ln T/dE ~ 5500 per eV, T
values at adjacent doubles jitter by about 6e-12. That is equivalent to an energy error of about
1e-15 eV, and it is inherent to double precision. Before the large-argument Airy treatment
(section 5), t9 had T errors of 3e-11 and jitter of 6.5e-11; the treatment brought both down by
about 100x.

## 7. Runtime

**Gen structures.** On the 28 gen structures, run from the CLI under the verifier's environment
(`env -i`, single-threaded BLAS, fresh working directory) on an idle machine, the wall time is
0.46 to 1.15 s per call (maximum held_10) and 16.4 s for all 28.

**Stress cases.** These are outside the guarantees: 14 sloped layers, X = 150 nm, 185 bound
states, a 1-eV window with 50 maxima, and 8 queries. They run in 13 s on a loaded 4-core
machine. A flat-layer version runs in 9 s.

**Cost breakdown:**

- The window scan uses about 20,000 grid energies for a 1-eV window, solved in batched chunks of
  1024 energies with two LAPACK solves per chunk.
- Each bound state takes about 22 Sturm counts plus about 12 determinant evaluations.
