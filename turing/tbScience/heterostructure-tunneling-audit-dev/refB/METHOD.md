# Reference B: method, checks, measured precision

Ref B is an independent referee for HETERO_SPEC reports. It shares no code and no formula route with
the analytic solution (no Airy functions, no closed-form layer transfer matrices). It integrates the
ODE numerically inside every layer. It was written from HETERO_SPEC.md alone. The task's solution/,
refA/, tools/ and controls/ were not opened.

```
python referee.py --structure S.json --report R.json [--out verdict.json] [--quiet]   # exit 0 iff pass
python referee.py --solve --structure S.json --output R.json                          # own full report
sh run_set.sh SYSDIR REPDIR OUTDIR [PAR] [referee args]                               # batch, OUTDIR/<id>.json/.log
python tests/run_tests.py [--regen-hand] [--skip-long]                                # test suite
```
Options: `--kh` (max k*h per step, default 1), `--precision long` (80-bit long double), `--no-tight`.
Runtime dependencies: numpy only (scipy is used only by the tests).

## 1. Integrator

With `phi = psi'/m`, which is continuous at every interface, each layer obeys

    psi' = m phi,      phi' = (V(x) - E) psi / C,      V(x) = V0 + g (x - x0).

**Taylor one-step method.** Over a step of signed length `h`, the scaled coefficients `a_k = c_k h^k` of
`psi(x0 + t h)` satisfy the exact recurrence
`(k+1) k a_{k+1} = A a_{k-1} + B a_{k-2}`, with `A = (m/C)(V0 - E) h^2` and `B = (m/C) g h^3`.
Summing the series for the two basis solutions, `(psi,phi) = (1,0)` and `(0,1)`, gives the 2x2 step matrix.

- **Step size.** Every layer is cut into `n` equal steps with
  `h * max(k_max, (m|g|/C)^(1/3)) <= kh` (kh = 1), where `k_max^2 = (m/C) max|V - E|` over the layer
  and the energy batch. So `|A| <= 1` and `|B| <= 1`.
- **Number of terms.** It comes from a majorant series that bounds both the solution and the
  E-derivative series below 1e-22 (1e-26 in long double). In practice this is about 20 to 30 terms.
- **Vectorised.** The step matrices of a sloped layer are built for all steps and all energies at once.
  A flat layer needs a single matrix. The state is then propagated step by step.
- **Renormalised.** The state is rescaled every 32 steps and at every interface, and the log scale is
  tracked, so thick barriers cannot overflow.
- **Variational equations.** For `d/dE` (`(k+1)k b_{k+1} = A b_{k-1} + B b_{k-2} - (m/C) h^2 a_{k-1}`),
  the derivative matrices are propagated alongside: `v_E <- M v_E + M_E v`.

## 2. Bound states

**Shooting.** The solution that decays to the left starts at x = 0 as `(1, kappa_L/m_L)`. The one that
decays to the right starts at x = X as `(1, -kappa_R/m_R)`. Each is integrated towards the matching
interface, which is an edge of the layer holding the lowest potential.

**Matching residual.** It is dimensionless:
`R(E) = s (psi_L phi_R - phi_L psi_R) / (|(psi_L, s phi_L)| |(psi_R, s phi_R)|)`, with `s = sqrt(C m)`.
`R` equals `sin(theta_L - theta_R)`. Since `theta_L` increases with E and `theta_R` decreases, `R` has
exactly one simple zero per eigenvalue, no poles and no spurious zeros.

**Node count (oscillation theorem).** This uses a scaled Prufer angle `theta = atan2(psi, s_j phi)`.
In each layer `s_j = m_j / k_j`, with `k_j^2 = (m_j/C) max|V - E|`. Then `|theta'| <= k_j`, so a step
turns the angle by at most `kh = 1` rad, and unwrapping is unambiguous. When `s` changes at an
interface the angle stays in the same quadrant.

- `theta' = m/s > 0` wherever `psi = 0`, so the number of nodes in (0, X] is `floor(theta(X)/pi)`.
- A node in the right lead exists iff `psi(X)` and the growing coefficient `psi(X) + m_R phi(X)/kappa_R`
  have opposite signs. The left lead `exp(kappa_L x)` has none.
- N(E), the number of nodes on the whole line, equals the number of eigenvalues below E.
- As a self-check, the sign changes of `psi` at the step ends are counted too. They must equal the
  Prufer count.

**Own solution (`--solve` and the reference for check 1).**
1. `n_tot = N(E_th - 1e-5)`.
2. Parallel bisection on N(E), starting from `[min V_layers, E_th - 1e-5]`, until every bracket holds
   exactly one eigenvalue (`N(lo) = n`, `N(hi) = n + 1`).
3. Vectorised Ridders on `R` to 1e-14 eV.

## 3. Transmission

The outgoing wave `(1, i k_R/m_R)` starts at X and is integrated leftwards with complex states. At
x = 0 it is decomposed into `A e^{ik_L x} + B e^{-ik_L x}`. Then:

- `T = (k_R/m_R)/(k_L/m_L) / |A|^2`, with the log scale restored.
- `r = B/A`.
- The variational state, which starts at `(0, i/(2 C k_R))`, gives
  `d ln T/dE = 1/(2(E-V_R)) - 1/(2(E-V_L)) - 2 Re(A_E/A)`.

## 4. Maxima

**Scan.** The grid steps through `[E_lo, E_hi]` at `<= 1e-4` eV, ends included, and evaluates
`d ln T/dE` at every point. Guarantee 3 puts consecutive extrema at least 2e-4 eV apart and at least
2e-4 eV from the ends. So each grid interval holds at most one extremum, and the extrema are exactly the
sign changes of `dT/dE` between neighbouring grid points: + to - is a maximum, - to + a minimum. A step
just under 2e-4 would already be enough; 1e-4 gives a factor of 2 margin.

**Refinement.** Every bracket is refined by Ridders on `d ln T/dE` to 1e-13 eV, and T is evaluated
there. This uses an analytic derivative, not a fit to T, so the location is limited only by the error
in `d ln T/dE` (about 1e-13) divided by the curvature.

**Cross-check.** The number of discrete maxima of T on the grid must equal the number of sign changes;
otherwise a warning is issued.

## 5. Checks and verdict

**Format** (sections 4 and 5.1):
- regular file, non-empty, at most 1,000,000 bytes, UTF-8;
- no duplicate keys, no NaN or Infinity;
- exact key sets and the right `structure_id`;
- bound energies and maxima strictly increasing;
- `transmission[i].E_eV` equal, as a float, to the queried energy.

**1. Bound states.**
- Reported count = `N(E_th - 1e-5)`.
- For every reported `E_i`:
  - `R` changes sign between `E_i - 1e-9` and `E_i + 1e-9`;
  - the node count steps from `i` to `i+1` across `E_i -/+ 1e-9`, which is independent of `R`;
  - `|E_i - E_own,i| <= 1e-9`.
- Completeness: `N` at each midpoint between consecutive reported energies equals `i+1`, and
  `N(E_0 - 5e-7) = 0`.

**2. Transmission.** `|T_rep - T_own| <= 1e-9 T_own` at every query. Self-check: `||r|^2 + T - 1| <= 1e-10`.

**3. Maxima.** The count must be equal. Element by element in increasing order:
`|dE| <= 1e-8` and `|dT| <= 1e-9 T_own`.

**4. Domain.** Every table range of section 2, with a 1e-12 slack for binary rounding, and every
guarantee: at most 40 states, spacing, threshold gap, query energy, `T >= 1e-30`, `|d ln T/dE| <= 1e3`,
`E_lo`, extremum spacing and end distance, prominence. These are reported as **warnings**, never as
failures.

**Self-precision.** A second run with half the step size and 6 extra Taylor terms recomputes every own
bound energy (Ridders on `R` within +-1e-10 eV), every query T and every maximum (Ridders on
`d ln T/dE` within +-1e-9 eV, then T). If any difference exceeds 10% of its tolerance, the referee
declares itself unreliable and does not pass. The same happens if conservation fails or the Prufer count
disagrees with the sign-change count.

**Output.** Stdout gets one line per structure: `<id> pass=... bound_dE= T_rel= max_dE= max_T_rel=
cons= self=(4 numbers) fail= warn= runtime=`. The verdict JSON holds the failures, the warnings, the
worst residuals and the per-item details (own values, R(E -/+ 1e-9), node counts).

## 6. Measured precision

Numbers are the largest deviation over all items. Hand references are closed forms; see
`tests/hand.py`.

| comparison | bound E (eV) | T (rel) | max E (eV) | max T (rel) |
| --- | --- | --- | --- | --- |
| own solver vs hand closed forms (4 structures) | 4.4e-15 | 4.5e-14 | 4.8e-14 | 8.7e-14 |
| double vs 80-bit long double (10 test structures) | 4.9e-15 | 3.9e-14 | 3.6e-14 | 6.8e-14 |
| tighter second run (28 task structures) | 3.9e-15 | 4.7e-14 | 2.3e-14 | 4.2e-14 |
| DOP853 rtol 1e-13 vs reports (11 structures, DOP853's own error dominates) | 7.7e-15 | 1.9e-12 | n/a | 1.1e-12 |

Further figures:
- Current conservation `||r|^2+T-1|`: at most 1e-13. On the 150 nm, m = 1, 1 eV-window stress
  structure it is 9.8e-14.
- The sign-change margin of check 1 on the 28 task structures: `min |R(E -/+ 1e-9)|` is 6e-9 against
  residual noise of about 1e-14.

Ref B's precision is therefore about 1e-13 or better, four orders of magnitude inside every tolerance.

## 7. Tests (`tests/`)

**Hand structures.**
- `hand_barrier`: a 5.5 nm, 0.32 eV barrier with mass 0.092, split over two layers, between leads
  (0.067, 0 eV) and (0.080, -0.05 eV). Closed-form T for different masses on all three sides; maxima
  from the holomorphic T via a Cauchy-integral derivative and brentq.
- `hand_well`: a 10 nm square well (m_w 0.067) in a 0.35 eV barrier (m_b 0.092). Even and odd
  BenDaniel-Duke transcendental equations; closed-form T. The maxima are exactly T = 1 at
  `k_w L = n pi`.
- `hand_well_edge`: the same as `hand_well` with a 12.06 nm well, so the top level is 1.45e-4 eV
  below `E_th`.
- `hand_triangle`: a biased triangular well. Two layers with slope 0.02 eV/nm and masses 0.067 and
  0.092, a 0.30 eV offset, leads at 0.90 and 0.40 eV. Hand route: Airy-function layer matrices (in the
  test only) plus brentq.

The two hand routes for the wells and the barrier (single-layer formula versus Airy/trig matrix product)
agree to at most 4e-15.

**Stress structures** (`make_stress.py`, all inside the domain and free of warnings):
- `stress_doublewell`: a doublet split by 1.69e-6 eV.
- `stress_thickbarrier`: T down to 2.8e-27.
- `stress_superlattice`: 13 layers, 7 maxima.
- `stress_manylevels`: 32 bound states.
- `stress_graded150`: 150 nm, masses up to 1, a 1 eV window above 1.95 eV; the slowest case at 13 to
  18 s.
- `stress_nobound`: lead masses 0.03 and 0.9, no bound state, no maximum.

**Negative tests** (`run_tests.py`, on 8 structures). Each of these must FAIL:
- a bound energy shifted by +3e-9 or -3e-9 eV;
- a query T scaled by (1 +- 3e-9);
- a maximum energy shifted by +3e-8 or -3e-8 eV;
- a maximum T scaled by (1 + 3e-9);
- the first or the last bound state dropped;
- a maximum dropped, or an extra maximum added;
- a spurious bound state;
- an extra key, a query energy off by 1 ulp, a wrong id, a duplicate key, NaN.

The 0.9x-tolerance shifts (0.9e-9 eV, 0.9e-9 relative, 0.9e-8 eV) must PASS. The last run gave 0
unexpected results; see `tests/results.txt`.

**`crosscheck_dop853.py`** is an independent second integrator (scipy DOP853, rtol 1e-12 and 1e-13).
Its deviation from the reports drops tenfold per decade of rtol.

## 8. Results on the task set (`out/`)

- **Oracle reports.** All 28 (`gen/structures`, `fin/oracle`) PASS with no warnings. Runtime is at most
  2.3 s per structure and 23 s in total. The set holds 118 bound states, 142 queries and 89 maxima.
  Worst differences: bound 5e-15 eV, T 1.6e-13, max E 1.3e-10 eV, max T 3.8e-14.
- **Max E scatter.** The 1e-10 eV differences in maximum energy come from the oracle. At the oracle's
  energies, long-double `d ln T/dE` is about -1e-6/eV. With the measured curvature that places them
  exactly 1.0 to 1.3e-10 eV from the stationary point. At Ref B's energies the derivative is at most
  1e-10/eV, about 1e-14 eV off. This is 1.3% of the 1e-8 tolerance and harmless.
- **T differences.** The largest, 1.6e-13 in held_07 and held_19, is also on the oracle side when
  checked against long double.
- **Legacy reports.** Reports from the legacy script `qwell.py` (run as a black box) FAIL on all 28.

## 9. Spec sentences found ambiguous

1. Guarantee 3: "at every local maximum `T` exceeds the adjacent local minima (or the value at the window
   end ...) by at least `1e-3` relative". It does not say relative to which value. Ref B warns when
   `(T_max - T_adj) < 1e-3 T_max`, the stricter reading.
2. Section 4: "at most 1 MB". This could mean 10^6 or 2^20 bytes. Ref B uses 1,000,000.
3. Section 4: "`E_eV` (the energy exactly as given)". This could mean float equality or textual
   identity: is `0.10` against `0.1`, or `1` against `1.0`, allowed? Ref B uses float equality.
4. Section 4: "Numbers are finite JSON numbers at full double precision". The phrase "full double
   precision" cannot be checked, and it is not stated whether an integer literal is acceptable, for
   example `"T": 1` at a symmetric resonance. Ref B accepts integers but not booleans.
5. Section 5: "within `1e-9` relative of the reference". Ref B reads this as `|x - x_ref| <= 1e-9 |x_ref|`,
   with the reference value as the denominator.
