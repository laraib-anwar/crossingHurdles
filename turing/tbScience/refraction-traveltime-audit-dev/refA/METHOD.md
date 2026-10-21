# Reference A: method, accuracy evidence, results

`reference.py` is a single file (Python 3.11, NumPy 1.26.4, SciPy 1.11.4).
`python reference.py --model M --output O` writes the section-4 report of TRAVELTIME_SPEC.md.
It never uses the per-layer antiderivatives (the log and square-root formulas). Every X(p) and
T(p) comes from numerical quadrature of the ray integrals.

## 1. Ray integrals by quadrature

For a branch with ray parameter p, X = 2 Σ ∫ p v / sqrt(1 - p²v²) dz and
T = 2 Σ ∫ 1 / (v sqrt(1 - p²v²)) dz, summed over the depth segments the ray crosses: every
layer above the turning layer (or above the reflecting interface) crossed completely, plus
the turning layer from its top down to the turning depth z_t = z_k + (1/p - a_k)/b_k.

**Singularity removal.** Inside one segment v is linear. Let d ≥ 0 be the distance from the
fastest end of the segment (the turning depth; the bottom when b > 0; the top when b < 0).
Then v = v_max - |b| d and 1 - p v = q + c d, with q = 1 - p v_max ≥ 0 and c = p|b|. The
factor 1/sqrt(1 - pv) blows up at a turning point (q = 0) and comes close to blowing up when
grazing (q → 0). It is removed exactly by d = t² + 2t sqrt(q/c). Written with τ = t/t_end ∈ [0, 1]
and D = sqrt(q + c h) + sqrt(q), this gives

    ∫_0^h F(d) / sqrt(q + c d) dd = (2h/D) ∫_0^1 F(d(τ)) dτ,
    d(τ) = (h² c / D²) τ² + (2 h sqrt(q) / D) τ.

This form contains no division by c, so it also holds for constant-velocity layers (c = 0) and
for p = 0. The remainder F is smooth: F_X = p v / sqrt(1 + p v) and F_T = 1 / (v sqrt(1 + p v)).
The nearest singularity of F_T is v = 0, which lies just beyond the slow end for strong
gradients. So the τ integral uses composite Gauss-Legendre with 12 nodes on each of 13 panels,
graded toward τ = 1 (edges 0, 1/2, 3/4, ..., 1 - 2⁻¹², 1): 156 nodes per segment.
`--panel-nodes` and `--graded-panels` change the rule; they are used only for the refinement
tests.

**Derivative.** dX/dp is the complex-step derivative Im X(p + i·10⁻³⁰)/10⁻³⁰ of the same discrete
quadrature. All the arithmetic is analytic in p, so this is exact to rounding. It gives a full
Newton step for the arrival roots and the function whose zeros are the caustics.

**Times at an offset.** After solving X(p) = X_t, the time is computed as
T = (T(p) - p X(p)) + p X_t, which is the intercept τ(p) plus p X_t. Since dτ/dp = -X, the
residual of the root enters only at second order. This matters next to grazing ends, where p is
ill-conditioned in double precision.

## 2. Branches, endpoints, divergence

- turning k (b_k > 0): p ∈ (1/v_k^bot, 1/max(a_k, V_k^-)); the lower end is 0 for the half-space.
- reflection i: p ∈ [0, 1/V_i^-).
- direct (b_0 = 0) and head i (b_i = 0, a_i > V_i^-): straight lines. For head i, X_c and τ_i come
  from the quadrature reflection i at p = 1/a_i.

An end is divergent (X → ∞) only when the grazing velocity is the velocity of a constant layer
crossed completely (b_j = 0, a_j = 1/p_end), or at p → 0 for a half-space turning branch. Every
other end value is evaluated directly at p_end: the quadrature is finite at q = 0, with q clamped
to ≥ 0 against rounding. At the upper end p = 1/a_k of a turning branch (the ray grazes the top of
layer k), the turning-layer depth is set to exactly 0. Computing it as (1/p - a_k)/b_k would leave a
rounding residue of about 1e-16 km. Its square root then gives a spurious end offset of about 4e-7 km.
For k = 0 that offset should be exactly 0; for k > 0 it would shift X_c by about 4e-7 km (fix of
2026-10-21, found on held_09).

## 3. Sampling, caustics, segments

Each branch is sampled with Chebyshev-type clustering, p = p_lo + (p_hi - p_lo)(1 - cos πs)/2
with 2000 points in s. This is uniform in the square root of the distance to either end, which
resolves the √ behaviour of X at turning and grazing ends. 45 geometric points (10⁻¹⁴ to 10⁻³
relative) are added near each end. Then midpoints are inserted wherever min X < 2 X_max and
either |ΔX| > 10⁻³ max(X, 0.01 X_max), or dX/dp keeps its sign but changes by more than 10%.
Caustics come from sign changes of dX/dp, refined by Brent's method on the complex-step dX/dp.
As a safety net, every interior local minimum of |dX/dp| is minimized locally to look for a pair
of zeros between two samples. Caustics and branch ends cut each branch into monotone segments.
Each segment keeps its (p, X, T) samples as a table.

**Arrivals.** For every segment whose open X range contains the offset, the root comes from a
safeguarded, vectorized Newton iteration in p (bisection fallback inside the segment's p bracket,
start from the table), then T comes from the intercept form. Direct and head arrivals are added
from their lines (head if X ≥ X_c). The arrivals are sorted by T.

## 4. First-arrival intervals (segment definition of section 1)

1. Screening: every segment's T(X) comes from a cubic Hermite interpolant of its table
   (dT/dX = p is known exactly). It is evaluated on a geometric grid from 10⁻⁶ X_max to X_max
   with ratio 1 + 10⁻⁴, which is finer than the 10⁻³ crossover separation. Points e(1 ± 10⁻⁹) are
   added around every segment end e. The minimizing segment is taken at each grid point.
2. Each change of minimizer between neighbouring grid points is resolved with exact evaluations.
   If one of the two segments starts or ends inside the cell, the boundary is that segment end
   (for example a head wave starting at X_c, or a branch end). Otherwise the boundary is the
   crossover found by Brent's method on T_a(X) - T_b(X), accepted only if no third segment is
   earlier there. Otherwise the cell is bisected recursively.
3. Touching pairs. Sometimes an end of segment a (X_e, p_e, T_e) lies on segment b with the same p.
   This happens at a cusp where two segments meet, for a turning branch leaving its reflection
   tangentially, and for a head wave leaving its critical reflection. Then
   T_a - T_b = ∫_{X_e}^X (p_a - p_b) dX. The two never cross, and the earlier one is the one with
   the larger p for X < X_e and the smaller p for X > X_e. Within 10⁻⁵ relative of X_e the time
   difference falls below rounding, so there this p rule decides between the pair and no crossover
   is searched for between them. Without it, spurious intervals of width about 10⁻⁸ appeared at
   cusps (seen on two test models before the fix).
4. If some screening point has no arrival at all, the program stops with an error, because the
   model then violates the section-2 guarantee. No report is written.

## 5. Accuracy evidence

These test scripts live outside this folder (session scratchpad). Only their results are quoted.

| Test | Result |
| --- | --- |
| Quadrature refinement, dev models: X, T, dX/dp at about 3000 p per branch, rules (8..16 nodes × 10..14 panels) vs (32 × 24) | all ≤ 2.2e-15 relative |
| Quadrature refinement, 150 random domain models (one third with the extreme gradient 1.5 1/s from v = 1.5 km/s), p down to 1e-9 of grazing | production rule (12 × 12): X 2.6e-15, T 2.4e-15, dX/dp 2.4e-15; (10 × 12) 2.6e-15; (8 × 10) T 2.9e-13 |
| Full report, production rule vs (24 nodes × 20 panels): 5 dev + 6 constructed + 40 random models (3 of the random ones have shadow zones, outside the domain; the program now refuses them) | all structures identical; t, p ≤ 2.6e-15; caustic x ≤ 6.4e-16; first-arrival boundaries ≤ 1.5e-14 relative |
| Independent ray shooting (Hamiltonian ray ODEs in time, DOP853 rtol 1e-13, Snell at interfaces, events for interfaces): X and T at 6 p per branch on dev_01..05 | ≤ 6.5e-12 relative (limited by the ODE tolerance) |
| Hand-derived isolated-layer closed forms (test only): reflection through constant, positive-gradient, negative-gradient and extreme layers, p to 1e-8 of grazing | X, T ≤ 7.3e-15 relative |
| Closed-form arrivals of three simple models (dev_01 reflections; constant lid + gradient half-space; gradient layer + gradient half-space) vs report | p ≤ 5.6e-16, t ≤ 5.6e-16 relative |
| Closed-form crossover (gradient layer / gradient half-space) and closed-form caustic (c1, p = 0.1875 exactly) | crossover 2.7e-15, caustic X 1.1e-16 relative |
| Brute-force logic check (200k-point p scan per branch, all sign changes polished, no segment machinery): arrival counts, kinds, p, t at every offset; caustic count; first-arrival kind on a 1200-point X grid | dev_01..05, 6 constructed caustic/LVZ/head models, 19 random models with caustics or ≥ 4 intervals: all agree |

Remarks on conditioning: at fixed p near a grazing or top-of-layer end, X and T have relative
errors up to about 6e-11 at 1 - pv = 1e-8 (dX/dp ∝ 1/(1 - pv) amplifies the rounding of p in any
method). The intercept τ stays accurate to 1e-13 s, so p and t at a given offset do not suffer
from this (see the closed-form report comparison).

## 6. Results on the dev models

| Model | Arrivals per offset | Caustics | First-arrival intervals |
| --- | --- | --- | --- |
| dev_01 | 3, 4, 5, 5 | 0 | direct 0 → 6.928203230 (= 4√3); head 1 → 24.20348708; head 2 → 60 |
| dev_02 | 4, 2, 3, 3, 3 | 0 | turning 0 → 9.249951982; turning 1 → 129.2601460; turning 2 → 250 |
| dev_03 | 4, 2, 2, 2, 2 | 0 | turning 0 → 16 (branch end); reflection 2 → 57.69299293; head 3 → 120 |
| dev_04 | 3, 1, 2, 1, 1 | 0 | turning 0 → 12.80624847 (branch end); reflection 2 → 26.45148682 (turning 2 starts); turning 2 → 100 |
| dev_05 | 3, 2, 3, 1, 1 | 0 | turning 0 → 4.596843189; turning 1 → 31.81098058; head 2 → 150 |

None of the dev models has a caustic or a triplication. The constructed models c1, c2, c4, c5 and
c6 (scratch) have turning-branch caustics, c2 has a two-caustic triplication, c3 has a reflection →
head transition at X_c, and c5 has six intervals with a repeated kind. All of them were
cross-checked as above.

## 7. Timings

`out/timings.json`: wall time per dev model with OPENBLAS/OMP/MKL_NUM_THREADS=1. They take
1.0 to 2.0 s on this machine (x86_64 macOS). The 28 gen models (held_01..22, model_01..06) take 0.7
to 8.0 s each. The 40 random models took 0.9 to 8 s each (measured while other jobs were running). The largest cost is branch sampling, about 0.5 to 1.5 s per branch,
and there are at most 11 branches for N = 6.

## 8. Open issues

1. **Reflection caustics do not exist in this model.** Every layer crossed completely adds
   ∫ v / (1 - p²v²)^{3/2} dz > 0 to dX/dp, so X(p) is strictly increasing on every reflection
   branch. All caustics are on turning branches. Section 7 of the spec lists "reflection branches
   with caustics" among the held-out coverage, which cannot occur. The code would still report
   one if it appeared.
2. The touching-pair rule (section 4.3) is a necessary numerical device. In double precision,
   offsets within about 10⁻⁸ of a cusp cannot resolve which arm is earlier from the times alone.
   A solver that compares raw times there can produce spurious micro-intervals that change the
   interval count. The section-2 guarantees do not exclude crossovers near branch ends, but the
   analysis shows that touching pairs cannot cross.
3. The screening grid starts at 10⁻⁶ X_max, and the segment that is first there is extended to 0.
   This is exact because the arrivals that exist as X → 0 have their offset ranges starting at
   exactly 0: reflections at p = 0, the direct wave, and the layer-0 turning branch at p = 1/a_0
   (see section 2). Before the 2026-10-21 fix, the layer-0 turning branch started at about 4e-7 km
   instead of 0. That produced a spurious first interval "reflection 1, 0 to 4.42e-7" on held_09.
4. Divergent ends are detected by exact float equality a_j == V for constant layers, which is how
   V_i^- is built from the same floats.
5. The program does not check the other section-2 guarantees, for example offsets near caustics.
   Only the shadow-zone guarantee is enforced (it raises an error).
