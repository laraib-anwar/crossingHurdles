# Reference B: finite-difference eikonal referee

`eikonal_referee.py` computes the first-arrival traveltime of the layered models of
TRAVELTIME_SPEC.md section 1 by solving the eikonal equation `|grad T| = 1/v(z)` on a uniform
grid. It uses no ray parameters, no branch formulas and nothing from the ray codes. It gives an
independent check of three things:

- the first-arrival times `T_1(X)` at the queried offsets;
- the offsets where the first arrival changes: crossovers (slope kinks) and continuous-slope
  transitions;
- the apparent slowness `dT_1/dX` on each part. Wherever ray theory and the eikonal agree, this
  equals the ray parameter of the first-arriving ray.

```
python eikonal_referee.py --model <model.json> --outdir out/<id> [--budget 5e6]
python eikonal_referee.py --model <model.json> --outdir out/<id> --reanalyse   # post-processing only
```

`--budget` is the node count of the finest grid. Outputs per model, in `out/<id>/`:

| file | content |
| --- | --- |
| `summary.json` | queried offsets: extrapolated `t_s` with bar `t_err_s`, per-level values, observed order, apparent slowness `p_s_km` with bar; crossovers (`x_km`, `x_err_km`, `t_s`, slowness on each side); C1 transitions; segments; grids, iterations, timings |
| `T1_levels.csv` | `T_1` at every node of the coarsest grid (shared by all levels): value per level, extrapolated value, bar |
| `T1_finest.csv` | `T_1` and `dT_1/dX` on the finest grid out to `X_max` |
| `surface_levels.npz` | surface rows of all levels plus run metadata (input of `--reanalyse`) |

## 1. Equation and domain

The model is laterally homogeneous and the source is at the surface, so `T(x, z) = T(-x, z)`.
`T` is also non-decreasing in `|x|` at fixed depth. To see this, take the fastest path from
`(0, 0)` to `(x', z)` and reflect its part before its first crossing of the line
`x = (x' - x)/2` about that line. The result is a path of the same cost from `(x' - x, 0)` to
`(x', z)`, which is a translate of a path from `(0, 0)` to `(x, z)`.

The grid therefore covers only `0 <= x <= X_max`, `0 <= z <= Z_max`, with `+inf` ghost nodes
outside. To find `Z_max`, a coarse grid is solved with a margin below the deepest interface,
and the margin is doubled until the surface times change by less than 1e-7 s. `Z_max` is then
the shallower of the two agreeing depths plus 25 % of its margin. Over a constant half-space
this stays shallow; over a gradient half-space it covers the deepest first-arrival turning
point.

## 2. Discretisation

**Grid.** The spacing is `h = G/m`, where `G` is the largest lattice step dividing every
interface depth, every queried offset and `X_max`. Interfaces then lie on grid rows and
offsets on nodes, at every level. Models without such a lattice are rejected, not
approximated.

**Interfaces.** At a velocity jump the viscosity solution uses the lower semicontinuous
envelope of the slowness on the interface, which is the minimum of the two one-sided limits.
This is what carries head waves and waves creeping along an interface. An interface row stores
three slownesses:

- the upper-side limit, for updates whose `z`-upwind neighbour is above;
- the lower-side limit, for updates whose `z`-upwind neighbour is below;
- their minimum, for the pure horizontal update along the row.

Other rows use the node slowness `1/v(z)`.

**Local solver.** At each node the solver takes the `x`-upwind side (the smaller neighbour),
tries both `z` sides, and takes the minimum over these candidates:

- the quadrant (Godunov) solutions of `ax^2 (T - Ax)^2 + az^2 (T - Az)^2 = s^2`, accepted only
  if `T >= max(Ax, Az)`;
- the vertical updates `Az + s/az`;
- the horizontal update `Ax + s_min/ax`.

In the first-order pass, `A` is the nearest neighbour's value and `a = 1/h`. In the
second-order pass, `A = (4 T1 - T2)/3` and `a = 3/(2h)` (the one-sided three-point
difference), used where `T2` is finite and `T2 <= T1`. In `z`, the three-point stencil may not
straddle an interface: its three nodes must lie in one closed layer. Elsewhere the update
falls back to first order.

**Sweeping.** Gauss-Seidel sweeps are vectorised along anti-diagonals: in each sweep ordering,
the nodes with `i + j` (or `j - i`) constant depend only on nodes already updated, so each
anti-diagonal is one numpy update on a strided view. Because `T_x >= 0`, iterations use the two
`x+` sweeps. Convergence is accepted only when a full four-direction iteration also changes no
node by more than 1e-12 s. The first-order pass starts from `+inf` and uses `T <- min(T, cand)`;
the second-order pass then iterates `T <- cand` from the first-order solution.

**Source.** Every node of layer 0 where the exact layer-0 time is provably the first arrival is
frozen at that time, `T = arccosh(1 + b0^2 r^2 / (2 a0 v(z))) / |b0|` (`r/a0` if `b0 = 0`).
Two conditions make it provable:

- the minimum-time arc of the linear medium stays in layer 0 (for `b0 > 0`, its deepest point
  lies above `h0`);
- `T_direct <= tau_v(0, h0) + tau_v(z, h0)`, where `tau_v` is the vertical slowness integral.
  This is a strict lower bound for every path that touches depth `h0`.

An earlier version froze only a disc of fixed radius `R` (at most `0.3 h0`). That left a
pre-asymptotic source error, which made the level sequence non-monotone for h >= 0.1 km in
dev_05 (section 5). The exact region removes it.

## 3. Extrapolation and error bars

Each model is solved on four nested grids, `h_c, h_c/2, h_c/4, h_c/8`. For every quantity `Q`
(a time, an apparent slowness, a crossover offset):

- **Primary value.** Observed-order Richardson on the three finest levels, when the observed
  order `p = log2((Q1-Q2)/(Q2-Q3))` lies in (1.2, 3.5). `p` is about 2 in smooth regions and
  about 1.6 where a field leaves an interface tangentially (section 6). Otherwise, the fit
  `Q* + C h^2 + D h^3` to the three finest levels.
- **Bar.** The largest of:
  - twice the largest difference between the primary value and the alternatives (the
    `h^2 + h^3` fit, the two-level `h^2` value, the observed-order value);
  - the difference from the same estimator applied to the three coarser levels, which exposes
    pre-asymptotic levels;
  - half the finest-level correction `|Q_finest - Q*|`.
- **Crossover bars.** Also at least `(dT_left + dT_right)/(p_left - p_right)`: the time bars of
  the two arrivals, read 15 coarse spacings either side, propagated through the slope drop.

## 4. Reading the first arrival

- **Crossovers (kinks).** `k_j = -(T_{j+1} - 2T_j + T_{j-1})/h` approximates the slope drop at a
  kink node and `-h T''` on a smooth arrival. A candidate must stand out from the median of
  `k` over nodes 5 to 30 away (`k - bg > 2e-4 s/km` and `k > 4 |bg|`). Candidates closer than
  12 nodes are merged. Each kink is then refined by fitting quadratics on each side, leaving
  out 12 nodes on each side for the numerical transition. The two fits are intersected, which
  gives `x`, `T`, `p_left`, `p_right`; these are matched across levels and extrapolated.
- **C1 transitions** (slope continuous, curvature changes, e.g. a curved arrival passing into
  a straight head or creeping wave). The spec counts such points as first-arrival interval
  boundaries, so the referee locates them:
  - sliding 2-km quadratic fits flag straight (`|T''| < 5e-6 s/km^2`) and curved parts;
  - the straight-side slope `p0` comes from a line fit 1 to 5 km inside the straight part;
  - the transition is the root of a quadratic fitted to `p - p0` over the 2 km of the curved
    side next to where `|p - p0|` first exceeds `max(20 x noise, 5e-4 s/km)`.

  Locating where a curve leaves its tangent is ill-conditioned for any time-based method: with
  time accuracy `eps` the resolution is about `sqrt(2 eps / |T''|)`. The bar is therefore the
  larger of that limit and a third of the change between the two finest levels.
- **Segments.** For each part between kinks the report gives `dT/dX` at both ends, the apparent
  velocity, and the curvature range. A straight segment is a direct, head or creeping wave,
  with apparent velocity equal to a layer velocity. A curved segment is a turning wave, whose
  `p` decreases with `X`.

## 5. Validation

**dev_01** (three constant layers) has a closed-form first arrival:

| quantity | exact | eikonal |
| --- | --- | --- |
| `T(8)` | 3.7320508 | 3.7320532 +- 4.3e-6 |
| `T(45)` | 11.2490081 | 11.2490081 +- 2.5e-6 |
| crossover 1 | 6.9282032 | 6.928213 +- 1.7e-5 |
| crossover 2 | 24.2034870 | 24.203477 +- 8.2e-5 |

**All 24 queried offsets of dev_01 to dev_05** were also checked against closed-form values.
These are my own `tau-p` integrals for turning and head branches in linear layers, plus the
analytic creeping-wave lines `X/6.0 + 0.5001913` (dev_03) and `X/5.7 + 1.4166310` (dev_04).
They were used only to test the bars; the arrival was identified from the eikonal's own
apparent slowness. All 24 lie inside their bars:

- 18 agree to between 1e-15 and 6e-6 s;
- dev_02 at 60 and 120 km and dev_05 at 10 km differ by about 2e-4 s, inside bars of 0.5 to
  4 ms (section 6, item 6).

The crossovers agree with the closed-form branches as follows:

| model | crossover | eikonal | closed form | difference |
| --- | --- | --- | --- | --- |
| dev_02 | turning 0 to turning 1 | 9.24975 | 9.24995 | -2.0e-4 |
| dev_02 | turning 1 to turning 2 | 129.2649 | 129.2601 | +4.8e-3 (bar 2.1e-2) |
| dev_03 | turning 0 to creeping 6.0 | 9.63727 | 9.63749 | -2.1e-4 |
| dev_04 | creeping 5.7 to turning 2 | 78.92501 | 78.92514 | -1.3e-4 |
| dev_05 | turning 0 to turning 1 | 4.59673 | 4.59684 | -1.1e-4 |
| dev_05 | turning 1 to head 2 | 31.810986 | 31.810981 | +5.6e-6 |

The dev_04 C1 transition comes out at 12.85 +- 0.10 km. Analytically it is the end of the
layer-0 turning branch, 12.80625 km.

**Isolated tests:**

- A two-layer head-wave case gives a constant error along the head wave, set near the
  critical point. It falls by 4.1 to 4.4 per halving of `h`.
- A pure linear-gradient case converges at ratio 4.0 to 4.3.
- A creeping wave below a velocity drop converges at ratio 3.0 to 3.1 (order about 1.6).

## 6. Where the eikonal and ray theory must differ

The eikonal first arrival is the infimum over all continuous paths. It contains energy that
spec section 1 does not:

1. **Creeping along the top of a negative-gradient layer.** If `b_i < 0` and `a_i > V_i^-`,
   ray theory has no head wave (head waves need `b_i = 0`). The eikonal has a wave just below
   the interface at speed `a_i`: `T = X/a_i + tau_c`, where `tau_c` is the intercept of the
   critical reflection at `p = 1/a_i`. It starts at that critical offset and is earlier than
   every ray that has to dive through the low-velocity layer. (dev_03: 6.0 km/s along
   z = 2 km, from X_c = 5.386 km.)
2. **Diffraction into a shadow.** A turning branch in a layer with `b > 0` ends where the ray
   grazes the layer bottom (`p = 1/v_bot`). If the velocity drops below, ray theory's first
   arrival jumps there to a later arrival. The eikonal instead continues tangentially, with a
   wave creeping along the bottom of the layer at `v_bot`. The slope stays continuous, so this
   is a C1 transition with no kink. (dev_04: 5.7 km/s from 12.806 km.)
3. **Free-surface creeping.** If `b_0 < 0`, ray theory has no direct wave, but the eikonal has
   `T = X/a_0`. Not present in the dev models.
4. **Reflections.** A reflection is never the eikonal first arrival. Where ray theory's first
   arrival is a reflection (a shadow), the eikonal is earlier, by items 1 to 3.
5. **Agreement elsewhere.** Direct waves, head waves of constant layers, turning waves, and
   crossovers between them agree in principle. That includes a crossover between two parts of
   one triplicated branch, which the eikonal shows as a kink. Caustics are invisible in `T_1`.
   An interval boundary that ray theory places at the end of a segment, where the next arrival
   continues with the same slope, appears in the eikonal as a C1 transition. One that ray
   theory places where the first arrival jumps to a later arrival has no eikonal counterpart:
   the eikonal continues with diffracted energy.
6. **Accuracy limits that are not physics.** Fields leaving an interface tangentially have
   `T_z ~ sqrt(distance)`, which lowers the convergence order to about 1.6. This covers
   creeping-wave emission, and turning waves entering a layer at near-grazing below a velocity
   jump (dev_02 and dev_05 layer 1). These regions carry the widest bars, up to 4 ms.

## 7. Results and expected comparison with the ray codes

Times in s, offsets in km, slowness in s/km.

**dev_01** (`h` = 1/12 to 1/96 km, 226 s):

- `T` = 1.0000000 (X=2), 3.7320532 +- 4.3e-6 (X=8), 6.7320532 +- 4.3e-6 (X=20),
  11.2490081 +- 2.5e-6 (X=45);
- `p` = 0.5, 0.25, 0.25, 0.1666667;
- crossovers 6.92821 (2.0 to 4.0 km/s) and 24.20348 (4.0 to 6.0 km/s).

Should agree with ray theory exactly: direct, then head 1, then head 2.

**dev_02** (1/3 to 1/24 km, 346 s):

- `T` = 3.0446293 +- 2.6e-4 (X=10), 11.6334862 +- 4.1e-3 (X=60), 21.7262245 +- 4.7e-4
  (X=120), 25.8762797 +- 4.3e-4 (X=150), 32.2048598 +- 6.6e-4 (X=200);
- `p` = 0.17232, 0.170676, 0.165197, 0.126576, 0.126566;
- crossovers 9.2497 +- 0.0031 (turning 0 to turning 1) and 129.265 +- 0.021 (turning 1 to
  half-space turning, 7.90 km/s).

Should agree with ray theory: turning 0, turning 1, turning 2.

**dev_03** (1/6 to 1/48 km, 240 s):

- `T(5)` = 1.1060304 +- 8.8e-7 (p 0.219199): agrees with ray theory (turning 0).
- Beyond the kink at 9.6373 +- 0.0003 km the eikonal first arrival is the 6.0 km/s creeping
  wave of item 1: `T` = 3.8335249 (X=20), 7.1668582 (X=40), 12.1668582 (X=70), 18.8335249
  (X=110), all +- 6.7e-7, `p` = 1/6.0.

Expected discrepancy: ray theory has no such arrival. Its turning-0 branch continues to its end
at 16.000 km, then its first arrival is later (reflections, then the 6.8 km/s head wave from
X_c = 54.61 km). For reference, that head wave arrives at 13.888235 s at X=70 and 19.770588 s
at X=110. The ray-theory first arrival should be later than the eikonal at 20, 40, 70 and
110 km, and its intervals and crossovers differ from the eikonal's beyond 9.6 km. Inside the
window the eikonal never shows the 6.8 km/s head wave, because the creeping wave stays first
to 157.8 km.

**dev_04** (1/4 to 1/32 km, 423 s):

- `T(3)` = 1.1581303 (exact region) and `T(95)` = 17.1832983 +- 2.4e-5 (half-space turning,
  p 0.1132439): both should agree with ray theory.
- `T` = 4.0482122 +- 1.2e-4 (X=15), 6.6797949 +- 1.1e-4 (X=30), 11.9429528 +- 1.1e-4 (X=60):
  the 5.7 km/s shadow-diffracted creeping wave of item 2, starting at the C1 transition
  12.85 +- 0.10 km (analytic 12.80625 km).
- Crossover creeping to half-space turning at 78.9250 +- 0.0026 km.

Expected discrepancy: the ray-theory first arrival at 15, 30 and 60 km should be later than the
eikonal values. Ray theory should also have an interval boundary at 12.80625 km, the end of the
turning-0 branch, where its first arrival jumps. Its crossover into the half-space turning
wave should lie before 78.925 km.

**dev_05** (1/6 to 1/48 km, 380 s):

- `T` = 0.5537848 (X=1), 3.9440590 +- 3.0e-3 (X=10), 11.0250950 +- 1.1e-5 (X=40),
  18.1679522 (X=90), 25.3108093 (X=140) (the last two +- 1.1e-5);
- `p` = 0.5502735, 0.2833024, 1/7.0, 1/7.0, 1/7.0;
- crossovers 4.5967 +- 0.008 (turning 0 to turning 1) and 31.81099 +- 0.0024 (turning 1 to
  7.0 km/s head wave).

Should agree with ray theory.

Timings are wall-clock on a shared 4-core machine with load 8 to 12, for four levels with a
finest grid of 4.4 to 5.7 M nodes. Every level needs 2 first-order iterations. The
second-order pass needs 2 iterations (dev_01, dev_03), 4 to 8 (dev_02, dev_05) or 7 to 16
(dev_04, below the low-velocity layer), rising with refinement; each count includes the
four-direction confirmation. Finest-level solves take 137 to 262 s.

## 8. Limitations

- First arrivals only: later arrivals, arrival counts and caustics are not computed.
- Interfaces, offsets and `X_max` must lie on a common lattice.
- The second-order scheme is not monotone. Coarse levels can show isolated undershoots of up to
  about 1e-2 s at single nodes near shadow boundaries; these vanish with refinement.
- Kinks with slope drop below about 2e-4 s/km, or closer than about 25 finest-grid nodes, are
  not resolved.
- C1 transitions are located only to about 0.1 km.
- The bars are empirical, from observed convergence, not proven bounds. They held for all 24
  closed-form checks.
