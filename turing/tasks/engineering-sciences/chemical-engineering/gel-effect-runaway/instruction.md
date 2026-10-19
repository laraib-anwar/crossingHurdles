Predict four sheet castings of poly(methyl methacrylate), C1 to C4, from sealed-ampoule polymerizations of bulk methyl methacrylate initiated by AIBN. Design the bath program for a fifth sheet, D1. Both are required for a pass.

## Inputs

Read the measurements only from `/root/data/`.

`/root/data/ampoules.csv` has columns `run_id`, `T_bath_C`, `w_AIBN`, `monomer_g`, `UA_W_per_K`. `T_bath_C` is the bath temperature in degrees Celsius, constant for the whole run. `w_AIBN` is kg AIBN per kg methyl methacrylate charged. `monomer_g` is the mass of methyl methacrylate initially charged, in grams. `UA_W_per_K` is the overall heat-transfer conductance between the contents and the bath, in W/K.

`/root/data/ampoule_conversion.csv` has columns `run_id`, `t_min`, `conversion`. Time is in minutes.

`/root/data/ampoule_gpc.csv` has columns `run_id`, `t_min`, `conversion`, `Mn_PS_equiv_g_per_mol`, `Mw_PS_equiv_g_per_mol`.

Conversion in these files is gravimetric, uncertain by about 0.01 absolute. The GPC molar masses are uncertain by about 5% relative. They are polystyrene-equivalent molar masses from a GPC run in tetrahydrofuran, calibrated with narrow-dispersity polystyrene standards. The GPC assigned each elution slice `i` the polystyrene molar mass `M_PS_i` of equal hydrodynamic volume, `K_PS*M_PS_i^(1 + a_PS) = K_PMMA*M_i^(1 + a_PMMA)`, where `M_i` is the absolute molar mass of the poly(methyl methacrylate) in that slice. It then computed `Mn_PS_equiv_g_per_mol = sum(W_i)/sum(W_i/M_PS_i)` and `Mw_PS_equiv_g_per_mol = sum(W_i*M_PS_i)/sum(W_i)`, where `W_i` is the polymer mass in slice `i`. `K_PS`, `a_PS`, `K_PMMA`, and `a_PMMA` are the `polystyrene` and `poly_methyl_methacrylate` Mark-Houwink constants for that eluent in `properties.json` under `gpc_calibration`.

`/root/data/properties.json` is authoritative for the supplied constants, physical properties, and correlations. `T_C` in the two density forms is degrees Celsius; every other correlation takes kelvin. A correlation given by `A` and `E_over_R_K` is `A*exp(-E_over_R_K/T)`, and `R` in `[M]_eq` is the molar gas constant, 8.314462618 J/(mol K).

`/root/data/castings.json` is authoritative for C1, C2, C3, and C4. It also holds `mwd_bin_edges_log10_g_per_mol`. There are no held-out casting inputs.

`/root/data/design.json` is authoritative for sheet D1 and for the limits on its bath program. There are no held-out D1 inputs.

## Conventions

`T` is a local temperature in kelvin. A temperature in degrees Celsius, such as `T_bath_C` or a `bath_program` temperature, converts to kelvin by adding 273.15. A temperature difference has the same value in kelvin and in degrees Celsius.

### Ampoules

The contents of each ampoule are well mixed. At `t = 0` the contents are unreacted and at the bath temperature. Heat flows from the contents to the bath at `UA_W_per_K*(T - T_bath)` watts, where `T` is the temperature of the contents and `T_bath = T_bath_C + 273.15` is the bath temperature, both in kelvin. The thermal effect of the ampoule wall is included in `UA_W_per_K`.

### Mixture

The volume of the monomer-polymer mixture is the volume of unconverted monomer plus the volume of polymer. Each volume is the component's mass divided by its density at the local temperature, and the polymer mass is the mass of monomer converted. The initiator's volume is neglected. Concentrations are in moles per litre of this mixture. `phi_m` is the volume of unconverted monomer divided by the volume of the mixture.

The heat capacity of an ampoule's contents, or of a material layer of a casting, is `cp` times the mass of monomer and initiator charged to it. `cp` is the `heat_capacity_mixture_J_per_kg_K` correlation at `w_p`, the mass of monomer converted divided by that charged mass. The thermal conductivity of a material layer is the `thermal_conductivity_W_per_m_K` correlation at the same `w_p`.

### Kinetics

The reactions are decomposition of the initiator into two primary radicals, initiation of a growing radical by a primary radical adding one monomer, reversible propagation, chain transfer to monomer, and termination of two growing radicals by disproportionation or combination. The fraction `fraction_termination_by_disproportionation` of termination events is by disproportionation, and `kt` is defined by the `termination_rate_convention` in `properties.json`. The supplied `kd_1_per_s` correlation applies at all conversions, and the initiation rate is `2*f*kd*[I]`, where `kd` is that correlation at `T` and `[I]` is the initiator concentration.

`efficiency_f_low_conversion`, `propagation_kp0_L_per_mol_s`, and `termination_kt0_L_per_mol_s` are the chemically controlled values of the initiator efficiency `f`, the propagation rate coefficient `kp`, and the termination rate coefficient `kt`: the values they take when diffusion does not limit the reaction. Diffusion limits all three increasingly as conversion rises, through the fractional free volume `V_f` of the mixture defined below. `kp0` and `kt0` denote the chemically controlled `kp` and `kt` at the local `T`.

The separately measured cage effect on the initiator efficiency, `f/f0`, is provided as an interpolation table (`f_factors` against `V_f_nodes`) in `initiator_efficiency_cage_effect` in `properties.json`; `f0` is `efficiency_f_low_conversion`, and outside the tabulated range `f/f0` takes the end values. `V_f` is the fractional free volume of the monomer-polymer mixture, `V_f = max(0.002, (0.025 + 4.8e-4*(T - Tg_p))*(1 - phi_m) + (0.025 + 1.0e-3*(T - Tg_m))*phi_m)`. `Tg_p` and `Tg_m` are the `polymer` and `monomer` entries of `glass_transition_temperature_K` in `properties.json`.

`kp` and `kt` depend on the conditions at each point of the reacting mixture, at any conversion, only through `V_f`, `T`, the monomer concentration `[M]`, and `Mw`, the cumulative weight-average molar mass of the polymer formed so far at that point:

`kp = kp0/(1 + exp(B_p*(1/V_f - 1/V_fp)))`

`kt = kt0/(1 + exp(z_t)) + C_rd*kp*[M]`, with `z_t = A_t*(1/V_f - 1/V_ft) + m*ln(Mw/1e5) + E_t*(1/T - 1/343.15)`

`Mw` is in g/mol, and before any polymer has formed at a point the term `m*ln(Mw/1e5)` there is zero. The seven constants `B_p`, `V_fp`, `A_t`, `V_ft`, `m`, `E_t`, and `C_rd` are properties of the physical system that produced the supplied data. They are not given here and are to be inferred jointly from the ampoule conversion and GPC measurements. `B_p`, `V_fp`, `A_t`, and `V_ft` are positive and dimensionless, `m` is non-negative and dimensionless, `E_t` is in kelvin, and `C_rd` is non-negative, in L/mol. The same two laws with the same seven values govern every ampoule and every point of every sheet, C1 to C4 and D1.

The castings and D1 take these laws beyond the ampoule conditions: C1 has a lower initiator loading than any ampoule, C3 is post-cured at 120 C, and the interior of a thick sheet runs well above its bath. The seven ampoule runs span 50 to 70 C and three initiator loadings.

`Cm = ktrm/kp` holds at all conversions, with `kp` the actual, diffusion-controlled propagation rate coefficient. The net propagation rate is `kp*([M] - [M]_eq)*[R]`, where `[M]` is the monomer concentration, `[R]` is the concentration of growing radicals, and `[M]_eq` is the equilibrium monomer concentration in `properties.json`. Each growing radical depropagates at the rate `kp*[M]_eq`. Heat is released at `-dH_p_J_per_mol` per mole of monomer consumed by net propagation, in the ampoules and in the castings.

`w_AIBN` means the same thing in the castings as in the ampoules. Conversion is the fraction of the initially charged monomer that has been converted. `Mn` and `Mw` are the cumulative number-average and weight-average molar masses of the polymer produced, in g/mol. All reported molar masses, including the molar-mass distribution, are absolute poly(methyl methacrylate) molar masses, not polystyrene-equivalent values.

### Castings

Each casting begins at `t = 0`, unreacted, at the bath temperature given by its `bath_program` at `t = 0`. It lies between two parallel cell walls. `thickness_mm` is the initial distance between those walls, filled with monomer at that temperature. The sheet is symmetric about the mid-plane, and heat transfer through the thickness is one-dimensional conduction. Each face exchanges heat with the bath at `h*(T_s - T_bath)` watts per square metre, where `T_s` is the temperature of the casting at that face and `T_bath` is the bath temperature from `bath_program`, both in kelvin, and `h` equals `h_W_per_m2K`. The thermal effect of the cell wall is included in `h`. The cell walls follow the shrinking casting. Each material layer retains the mass charged to it, and its thickness changes with the local density.

`bath_program` is a list of `[time_min, temperature_C]` points. Between listed times the bath temperature is the linear interpolation of those points. The mid-plane is the plane of symmetry. The inner region is the 10% of the casting mass nearest the mid-plane. The outer regions are the 10% of the casting mass nearest the two walls, 5% of the casting mass adjacent to each wall. Each casting runs from `t = 0` to its own `t_end_min`.

Mass-average conversion is the mass of monomer converted divided by the mass of monomer initially charged.

## Sheet D1

D1 uses the `thickness_mm`, `h_W_per_m2K`, and `w_AIBN` given in `design.json`, and the casting conventions above. The cure ends at the last time of the program. That last time is the cycle time.

The bath program has 2 to `max_points` points. The first time is 0 and times increase strictly. Every listed temperature lies within `[bath_temperature_min_C, bath_temperature_max_C]`. For consecutive points `[t_a, T_a]` and `[t_b, T_b]`, `|T_b - T_a| <= max_ramp_K_per_min * (t_b - t_a)`, with times in minutes and temperatures in degrees Celsius. The cycle time is at most `max_cycle_time_min`.

The program is evaluated on the physical system that produced the supplied data. At no instant from `t = 0` to the cycle time may a material layer whose conversion is below `bubble_conversion` be hotter than `bubble_temperature_C`; a layer's conversion is taken over the monomer charged to that layer. At the cycle time, the mass-average conversion of the sheet is at least `target_conversion`.

## Outputs

Write both `/root/results/predictions.json` and `/root/results/cure_program.json`.

`predictions.json` is valid JSON. The top-level value is an object whose only key is `castings`. `castings` is an array of exactly four objects, one each for `C1`, `C2`, `C3`, and `C4`, in any order. Each object contains exactly these keys:

- `id`, the casting id as a JSON string
- `t80_min`, the first time in minutes at which the mass-average conversion reaches 0.80
- `dT_mid_max_K`, the maximum, from `t = 0` to `t_end_min`, of mid-plane temperature minus the instantaneous bath temperature, in kelvin
- `t_dT_mid_max_min`, the earliest time in minutes at which `dT_mid_max_K` is attained
- `X_avg_t1`, the mass-average conversion at the casting's `t1_min`
- `X_avg_end`, the mass-average conversion at `t_end_min`
- `Mn_avg_end_g_per_mol`, the cumulative number-average molar mass of all polymer in the casting at `t_end_min`, in g/mol
- `Mw_avg_end_g_per_mol`, the cumulative weight-average molar mass of all polymer in the casting at `t_end_min`, in g/mol
- `Mw_inner_end_g_per_mol`, the cumulative weight-average molar mass of all polymer in the inner region at `t_end_min`, in g/mol
- `Mw_outer_end_g_per_mol`, the cumulative weight-average molar mass of all polymer in the outer regions at `t_end_min`, in g/mol
- `mwd_weight_fractions`, an array of exactly 16 numbers

Entry `i` (from 0) is the mass fraction of all polymer in the casting at `t_end_min` whose molar mass `M` satisfies `e[i] <= log10(M / (g/mol)) < e[i+1]`, where `e` is the ascending 17-element list `mwd_bin_edges_log10_g_per_mol` in `castings.json`. Polymer below `10^e[0]` g/mol is counted in the first entry and polymer above `10^e[16]` g/mol in the last. Entries are non-negative and sum to 1 within 0.01.

Every value other than `id` and `mwd_weight_fractions` is a JSON number, and so is every entry of `mwd_weight_fractions`. Null, NaN, Infinity, -Infinity, numbers encoded as strings, and booleans are not allowed. Numbers are graded exactly as written, so write them at full double precision.

`cure_program.json` is valid JSON. The top-level value is an object whose only key is `bath_program`, an array of points `[time_min, temperature_C]` that meets the D1 program limits above. Each point is an array of exactly two JSON numbers, under the same rules for null, NaN, infinities, numeric strings, booleans, and precision. The program is checked and run exactly as written.

## Acceptance

The reward is binary: it is 1 if both files meet the Outputs contract above, `predictions.json` satisfies the tolerances below for all ten quantities of every casting, and `cure_program.json` meets every requirement stated for sheet D1, and 0 otherwise. The reference value of each casting quantity is that of the physical system that produced the supplied data, which follows the kinetics stated above at that system's values of the seven constants. The tolerances below allow for fitting error and numerical error.

Relative error is the absolute difference divided by the absolute reference. `t80_min` is within 6% relative error of the reference, and `t_dT_mid_max_min` within 12% relative error. `dT_mid_max_K` has absolute error at most the larger of 1.5 K and 25% of the reference value. `X_avg_t1` has absolute error at most 0.010. `X_avg_end` has absolute error at most 0.006. `Mn_avg_end_g_per_mol`, `Mw_avg_end_g_per_mol`, `Mw_inner_end_g_per_mol`, and `Mw_outer_end_g_per_mol` are each within a multiplicative factor of 1.10 of the reference, meaning the ratio of prediction to reference lies between `1/1.10` and `1.10`. `mwd_weight_fractions` has an L1 error, the sum over the 16 entries of the absolute difference from the reference, of at most 0.05. Every inequality in this section and in the D1 program limits is evaluated in double precision exactly as stated, with no tolerance beyond it: a value on a bound passes, a value past it by any amount fails.

You have 18000 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
