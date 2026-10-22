# Reference A test systems

Each `tN_*.json` is a system file inside the domain of PHASE_SPEC.md section 2; `tN_*_report.json`
is the report written by `python ../reference.py --system tN_*.json --output tN_*_report.json`.
`check_report.py system.json report.json` is an independent consistency checker (plain numpy,
only the spec formula) used on every pair below; all pass with residuals at machine precision
(see METHOD.md). The liquid is the reference state (`h = s = 0` for both end members) unless noted.

| file | content | expected and found |
| --- | --- | --- |
| t1_eutectic | two terminal solid solutions `alpha` (A-rich) and `beta` (B-rich), liquid with a small negative excess; alpha and beta both have positive `L0` whose metastable gaps lie under the liquidus | one eutectic at 665.5628 K (alpha 0.00766 / liquid 0.5820 / beta 0.99611); the metastable alpha and beta consolute points (782 K and 824 K, inside the window) are correctly absent |
| t2_lens_minimum | liquid (ideal) and one solid solution `alpha` with `L0 = +6000`; pure melting points 1200 K (A) and 1000 K (B) | one congruent minimum at 928.5486 K, `x = 0.6726`, `phase_above = liquid`, `phase_below = alpha`, `two_phase_side = above`; no invariant; at 950 K the hull is alpha / L+alpha / liquid / L+alpha / alpha as it must be above a minimum |
| t3_gap_eutectoid | regular solid solution `alpha` with constant `L0 = 20000`, a B-rich solid `beta` stable at pure B below 1166.7 K, liquid far above the window | upper consolute point at `T_c = 20000/(2R) = 1202.72355 K`, `x = 0.5`, `gap_side = below` (0 ulp from the closed form); monotectoid `alpha2 -> alpha1 + beta` at 940.7179 K, class eutectic, name `eutectoid` per the table; the pure-end change at 1166.67 K is not reported |
| t4_compound_congruent | terminal `alpha`, `beta`, liquid with `L0 = -6000`, compound `AB` at `x = 0.5` with `G = -22000 + 7.5 T` | congruent melting of AB at 1545.63627 K (`two_phase_side = below`, compound below, liquid above), equal to the closed form `T = (h_AB - L0/4) / (-R ln 2 - s_AB)`; eutectics alpha+L+AB at 1075.4878 K and AB+L+beta at 1062.7950 K; at 800 K and 1000 K the compound is a hull vertex shared by its two tie-lines (no region) |
| t5_compound_peritectic | same terminals with a higher-melting beta, liquid `L0 = -3000`, compound `A2B3` at `x = 0.6` with `G = -8291 + 2 T`, chosen so that its point reaches the liquid-beta tie-line at about 1000 K while it is still above the liquid curve | peritectic `L + beta -> A2B3` at 994.5099 K (class peritectic, name `peritectic`, middle phase A2B3 stable below only); eutectic alpha+L+A2B3 at 828.9510 K; compound absent from the 1200 K isotherm, present at 800 and 1000 K: stable only in the lower part of the window; the metastable compound-liquid tangency at about 1040 K is not reported |
| t6_compound_metastable | t4's phases, window [550, 1700], compound AB lifted to `G = -8000 + 7.5 T` | the compound never touches the hull; the report is byte-identical (apart from `system_id`) to `t6_control_nocompound` (same phases, no compound): one eutectic at 596.5452 K |
| t7_allotropic_noevent | `alpha` and `gamma` solids with `GA_alpha = GA_gamma` at exactly 900 K (gamma stable at pure A below), liquid above the window | no reported event; the 750 K and 850 K isotherms show gamma / gamma+alpha / alpha and the 950 K isotherm is all alpha; the pure-end transition at 900 K is a topology event and is not reported |
| t8_noevent | ideal-like lens, window [1010, 1190] strictly between the two pure melting points | no event of any kind; two isotherms with one L+alpha tie-line each |

## Sanity checks performed

* **Ideal lens** (both phases without excess): `x_S = k_B x_L`, `x_L = (1 - k_A)/(k_B - k_A)` with
  `k_i = exp(-(G_i^S - G_i^L)/RT)`; the tie-line ends from `hull_at` agree to `<= 2.2e-15` at 1140,
  1170 and 1195 K.
* **Regular solution**: `critical_candidates` returns `T_c = L0/(2R)`, `x_c = 0.5` exactly for
  `L1 = L2 = 0`; with `L1 = 3000` the returned point satisfies `G'' = -7e-12`, `G''' = 0`.
* **Compound congruent temperature**: linear closed form reproduced to 0 ulp (t4).
* **Metastability**: t1 (two metastable consolute points), t5 (metastable compound-liquid
  tangency), t6 (metastable compound): none reported; t6 equals its control.
* **Completeness**: brute-force topology scan of the exact hull every 0.2 K over each window finds
  exactly one topology change per reported event or unreported pure-end crossing and nothing else.
* **Determinism and finiteness**: two runs give identical files; `allow_nan=False` plus explicit
  checks guarantee finite numbers.
* **Dev and generated systems**: `../out/` holds the reports for `models/dev_0*.json` and
  `../out_gen/` those for `gen/systems/*.json` (29 systems, all exit 0 without warnings, all pass
  `check_report.py` with `problems=0`; per-system runtimes are listed in METHOD.md). The same
  brute-force topology scan (step 0.25 K) was run on all 29 as a completeness check.
