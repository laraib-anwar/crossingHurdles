"""Reference solution: diffusion-controlled bulk MMA kinetics fitted to ampoule data,
carried into 1-D sheet castings, and used to design a cure program for sheet D1.

1. Published chemically controlled constants, the separately measured cage effect on f (a table
   of f/f0 against Vf; this solution fits the logistic law the table follows to it, see BF, VFF),
   depropagation thermodynamics and physical properties come from /root/data/properties.json.
2. instruction.md states the free volume Vf of the monomer/polymer mixture, the separately
   measured cage effect on f, and the laws for kp and kt in closed form: logistic switches in
   1/Vf for the glass effect on kp and for the gel effect on kt, the latter with a chain-length
   and a temperature term and a reaction-diffusion floor. This solution implements those laws
   exactly as stated:
     Vf = max(0.002, (0.025 + 4.8e-4 (T - Tgp)) (1 - phi_m) + (0.025 + 1.0e-3 (T - Tgm)) phi_m)
     f  = f0  / (1 + exp(B_f (1/Vf - 1/Vf_f)))      cage effect (logistic fitted to the published table)
     kp = kp0 / (1 + exp(B_p (1/Vf - 1/Vf_p)))      glass effect (also slows depropagation)
     kt = kt0 / (1 + exp(z_t)) + C_rd kp [M],       gel effect with reaction diffusion
          z_t = A_t (1/Vf - 1/Vf_t) + m ln(Mw/1e5) + E_t (1/T - 1/343.15)
   Mw is the cumulative weight-average molar mass of the dead polymer in the ampoule or layer
   (the ln term is zero before any has formed, as the instruction says).
   Net propagation is kp ([M] - [M]_eq) with the published ceiling equilibrium. The seven
   constants A_t, Vf_t, m, E_t, C_rd, B_p, Vf_p are not given and are inferred from the ampoule
   data. The data were generated with this family; README.md records which simpler fits of the
   ampoules fail, and that an independent Marten-Hamielec model fitted to the same data (from
   the revisions in which the laws were withheld) also passes the bands.
3. The seven constants are fitted by weighted least squares to the ampoule conversion and GPC
   data, modelling each ampoule as a well-mixed vessel that exchanges heat with the bath
   through its stated UA (the ampoules are not isothermal). The GPC averages are
   polystyrene-equivalent, so the model is compared with them as the instruction says the GPC
   computed them: every slice of absolute molar mass M is reported at the polystyrene molar
   mass of equal hydrodynamic volume, M_PS = C_PS M^BETA (Mark-Houwink constants from
   properties.json), and the averages are taken over the slices. For the gamma-shaped
   instantaneous distributions of step 5 the slice sums are exact fractional moments, so the
   model's polystyrene-equivalent Mn and Mw follow from time integrals of the dead-polymer
   production. The fit starts from a 2 x 2 x 2 design over (A_t, Vf_t, E_t) combined with each
   of two generic settings of the other four constants (none equal to the data-generating
   values); the best start of each setting is refined within physical bounds and the fit with
   the lower cost is kept (see GENERIC).
4. Each casting is integrated as a symmetric 1-D slab in a Lagrangian (mass) coordinate, so
   each finite volume keeps its monomer mass and its thickness follows the local densities;
   conduction with composition-dependent k, convective exchange with the programmed bath.
5. The molar-mass distribution is accumulated from instantaneous chain-length distributions:
   with the radicals at quasi-steady state, live chains are geometric, R_n ~ q^n, with
   kdp q^2 - (kp[M] + kdp + L) q + kp[M] = 0 (kdp = kp[M]_eq, L = 2 kt[R] + ktrm[M]); dead
   chains from disproportionation and transfer have weight distribution ~ n q^n, those from
   combination ~ n^2 q^n. Their production rates are integrated over time and layers.
6. The D1 cure program is a two-stage family (hold, ramp at the maximum rate to a post-cure
   hold; at most the four points design.json allows) ending as soon as the model's mass-average
   conversion reaches the target. Its three parameters (hold temperature, hold end, post-cure
   temperature) are optimised for the shortest cycle, coarse to fine: Nelder-Mead on 10 volumes
   from two safe starts in parallel, then, on 30 volumes, the earliest ramp start that keeps the
   margined bubble limit (bisection). Design runs stop at the margined target and abort on a
   runaway (a layer below the bubble conversion 10 K above the limit), so no candidate drags
   the stiff solver through a runaway. Near the runaway boundary the peak temperature is so
   sensitive to the bath temperature that a margin on the bubble temperature alone protects
   little, so the program must also keep the bubble limit with its bath ROBUST_DT hotter; that
   covers an error of that size in the model's runaway boundary and roughly 10 % in its
   gel-effect timing. The target carries a margin MARGIN_X, which covers the model's error in
   late conversion (a few thousandths: the program ends while the post-cure is still converting
   about 0.001 per minute).
"""
import json
import math
import os
import sys
import time
from pathlib import Path

# One BLAS thread: multi-threaded reductions change trailing digits between runs and hosts.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

from multiprocessing import Pool

import numpy as np
import pandas as pd
from scipy.integrate import cumulative_trapezoid, solve_ivp
from scipy.optimize import least_squares, minimize
from scipy.special import gamma as gamma_fn
from scipy.special import gammainc

DATA = Path("/root/data")
OUT = Path(sys.argv[1])
OUT_PROGRAM = Path(sys.argv[2])

P = json.loads((DATA / "properties.json").read_text())
MM = P["monomer_molar_mass_kg_per_mol"]
MI = P["initiator_molar_mass_kg_per_mol"]
KD = P["initiator_decomposition"]["kd_1_per_s"]
F0 = P["initiator_decomposition"]["efficiency_f_low_conversion"]
# Cage effect: properties.json publishes it as a table of f/f0 against V_f (V_f_nodes,
# f_factors), tabulated from a smooth law. This solution fits the two-parameter logistic
# f/f0 = 1/(1 + exp(B_f (1/V_f - 1/V_ff))) to the whole table by least squares (the residual is
# the table's 6-decimal rounding, below 5e-7 at every node, from any start) and integrates with
# that smooth form. A piecewise-linear interpolant of the table (np.interp) has a derivative
# kink at every node and costs LSODA about 3.6 times the steps per slab run; a smooth fit has
# no such cost.
_CAGE = P["initiator_efficiency_cage_effect"]
_VF_NODES = np.asarray(_CAGE["V_f_nodes"], float)
_F_FACTORS = np.asarray(_CAGE["f_factors"], float)


def _cage_residuals(th):
    z = np.clip(th[0] * (1.0 / _VF_NODES - 1.0 / th[1]), -700.0, 700.0)
    return 1.0 / (1.0 + np.exp(z)) - _F_FACTORS


_cage_fit = least_squares(_cage_residuals, [1.0, 0.03], bounds=([1e-3, 1e-3], [100.0, 1.0]),
                          xtol=1e-14, ftol=1e-14, gtol=1e-14)
BF, VFF = float(_cage_fit.x[0]), float(_cage_fit.x[1])
print(f"cage effect fitted to the published table: B_f {BF:.6f}, V_ff {VFF:.6f}, "
      f"max residual {float(np.abs(_cage_fit.fun).max()):.1e}", flush=True)
KP0 = P["propagation_kp0_L_per_mol_s"]
KT0 = P["termination_kt0_L_per_mol_s"]
CM = P["chain_transfer_to_monomer_Cm"]
DELTA = P["fraction_termination_by_disproportionation"]
DHP = P["propagation_thermodynamics"]["dH_p_J_per_mol"]
DSP = P["propagation_thermodynamics"]["dS_p_J_per_mol_K"]
RM = P["density_monomer_kg_per_m3"]
RP = P["density_polymer_kg_per_m3"]
CP = P["heat_capacity_mixture_J_per_kg_K"]
KM = P["thermal_conductivity_W_per_m_K"]["monomer"]
KPOL = P["thermal_conductivity_W_per_m_K"]["polymer"]
TGP = P["glass_transition_temperature_K"]["polymer"]
TGM = P["glass_transition_temperature_K"]["monomer"]
MHK = P["gpc_calibration"]["mark_houwink"]
K_PS, A_PS = MHK["polystyrene"]["K_mL_per_g"], MHK["polystyrene"]["a"]
K_PMMA, A_PMMA = MHK["poly_methyl_methacrylate"]["K_mL_per_g"], MHK["poly_methyl_methacrylate"]["a"]
CAST = json.loads((DATA / "castings.json").read_text())
EDGES = np.asarray(CAST["mwd_bin_edges_log10_g_per_mol"], float)
SPEC = json.loads((DATA / "design.json").read_text())
MARGIN_X, ROBUST_DT = 0.005, 1.0     # design margins: target conversion, bath temperature (K)
R = 8.314462618
# Reference points of the gel-effect law as instruction.md states it (343.15 K in the
# temperature term, 1e5 g/mol in m ln(Mw/1e5)); moving either would only relabel the fitted
# A_t, Vf_t and E_t.
TREF = 343.15                        # reference temperature of z_t, K (instruction)
NS = 9   # per element, per kg monomer charged: NM, NI, lam0..2, mu0..2, T
M0 = MM * 1e3                        # g/mol per monomer unit
# Universal calibration (instruction): K_PS M_PS^(1 + a_PS) = K_PMMA M^(1 + a_PMMA).
BETA = (1.0 + A_PMMA) / (1.0 + A_PS)
C_PS = (K_PMMA / K_PS) ** (1.0 / (1.0 + A_PS))
# E[n^b] of a weight distribution ~ n^(s-1) exp(-alpha n) is Gamma(s+b) / (Gamma(s) alpha^b);
# s = 2 for disproportionation and transfer, s = 3 for combination.
G_UP = (gamma_fn(2.0 + BETA) / gamma_fn(2.0), gamma_fn(3.0 + BETA) / gamma_fn(3.0))
G_DOWN = (gamma_fn(2.0 - BETA) / gamma_fn(2.0), gamma_fn(3.0 - BETA) / gamma_fn(3.0))
GRID_S = 30.0                        # time grid for the ampoule production integrals, s


def arr(d, T):
    return d["A"] * np.exp(-d["E_over_R_K"] / T)


def sig_down(z):
    return 1.0 / (1.0 + np.exp(np.clip(z, -700.0, 700.0)))


def arr_s(d, T):
    return d["A"] * math.exp(-d["E_over_R_K"] / T)


def sig_s(z):
    return 1.0 / (1.0 + math.exp(min(max(z, -700.0), 700.0)))


def bath_K(program, t_s):
    pts = np.asarray(program, float)
    return np.interp(t_s / 60.0, pts[:, 0], pts[:, 1]) + 273.15


def kinetics(th, Y, w, aux=False):
    """Y (9, n). Returns dY (T row zero), heat release W per kg monomer, specific volume
    m3 per kg monomer, polymer mass fraction; with aux, the rate quantities the chain-length
    distribution needs."""
    NM, NI, l0, l1, l2, m0, m1, m2, T = Y
    NM0 = 1.0 / MM
    NMc = np.maximum(NM, 0.0)
    Tc = T - 273.15
    vm = NMc * MM / (RM["a"] + RM["b"] * Tc)
    vp = np.maximum(NM0 - NMc, 0.0) * MM / (RP["a"] + RP["b"] * Tc)
    v = vm + vp
    V = v * 1e3
    phim = vm / v
    # Free volume: relation and coefficients as stated in the instruction (fixed, not fitted).
    vf = np.maximum((0.025 + 4.8e-4 * (T - TGP)) * (1 - phim) + (0.025 + 1.0e-3 * (T - TGM)) * phim, 2e-3)
    M, I = NMc / V, NI / V
    c0, c1, c2 = l0 / V, l1 / V, l2 / V
    # Mw of the dead polymer; 1e5 before any has formed makes the m ln(Mw/1e5) term zero.
    # The 1e3 floor is only a guard against log(0); it never binds.
    mw = np.where(m1 > 1e-12 * NM0, MM * 1e3 * m2 / np.maximum(m1, 1e-300), 1e5)
    kp = arr(KP0, T) * sig_down(th[5] * (1 / vf - 1 / (th[6] * 1e-2)))
    f = F0 * sig_down(BF * (1 / vf - 1 / VFF))
    zt = th[0] * (1 / vf - 1 / (th[1] * 1e-2)) + th[2] * np.log(np.maximum(mw, 1e3) / 1e5) \
        + th[3] * 1e3 * (1 / T - 1 / TREF)
    kt = arr(KT0, T) * sig_down(zt) + np.exp(th[4]) * kp * M
    kd = arr(KD, T)
    ktrm = arr(CM, T) * kp
    Meq = np.exp(DHP / (R * T) - DSP / R)
    Ri = 2.0 * f * kd * I
    net = kp * (M - Meq)
    dY = np.empty_like(Y)
    dY[0] = -V * (net * c0 + ktrm * M * c0 + Ri)
    dY[1] = -kd * NI
    dY[2] = V * (Ri - 2.0 * kt * c0 * c0)
    dY[3] = V * (Ri + net * c0 + ktrm * M * (c0 - c1) - 2.0 * kt * c0 * c1)
    dY[4] = V * (Ri + kp * M * (2.0 * c1 + c0) + kp * Meq * (c0 - 2.0 * c1)
                 + ktrm * M * (c0 - c2) - 2.0 * kt * c0 * c2)
    dY[5] = V * (ktrm * M * c0 + (1.0 + DELTA) * kt * c0 * c0)
    dY[6] = V * (ktrm * M * c1 + 2.0 * kt * c0 * c1)
    dY[7] = V * (ktrm * M * c2 + 2.0 * kt * c0 * c2 + 2.0 * (1.0 - DELTA) * kt * c1 * c1)
    dY[8] = 0.0
    if aux:
        return dict(V=V, M=M, c0=c0, c1=c1, kp=kp, kt=kt, ktrm=ktrm, Meq=Meq)
    return dY, -DHP * V * net * c0, v, np.maximum(NM0 - NMc, 0.0) * MM / (1.0 + w)


def atol(n):
    a = np.array([1e-10, 1e-12, 1e-23, 1e-20, 1e-16, 1e-18, 1e-12, 1e-8]) / MM
    return np.tile(np.append(a, 1e-7), n)


def y_init(n, w, T0):
    return np.tile(np.r_[1.0 / MM, w / MI, np.zeros(6), T0], n)


def ampoule(th, w, Tb_C, UA, kg, tt, rtol=1e-6):
    """One well-mixed ampoule exchanging heat with the bath; plain-float kinetics (a single
    element, so this is the same chemistry as kinetics() without array overhead). Starts at
    the bath temperature, unreacted (instruction). Returns t and the states y (9, len(t))."""
    Tb = Tb_C + 273.15
    NM0 = 1.0 / MM
    crd = math.exp(th[4])

    def rhs(t, y):
        NM, NI, l0, l1, l2, m0, m1, m2, T = y
        NMc = NM if NM > 0.0 else 0.0
        Tc = T - 273.15
        vm = NMc * MM / (RM["a"] + RM["b"] * Tc)
        vp = max(NM0 - NMc, 0.0) * MM / (RP["a"] + RP["b"] * Tc)
        v = vm + vp
        V = v * 1e3
        phim = vm / v
        # Free volume: relation and coefficients as stated in the instruction (fixed, not fitted).
        vf = max((0.025 + 4.8e-4 * (T - TGP)) * (1 - phim) + (0.025 + 1.0e-3 * (T - TGM)) * phim, 2e-3)
        M, I = NMc / V, NI / V
        c0, c1, c2 = l0 / V, l1 / V, l2 / V
        mw = MM * 1e3 * m2 / m1 if m1 > 1e-12 * NM0 else 1e5
        kp = arr_s(KP0, T) * sig_s(th[5] * (1 / vf - 1 / (th[6] * 1e-2)))
        f = F0 * sig_s(BF * (1 / vf - 1 / VFF))
        zt = th[0] * (1 / vf - 1 / (th[1] * 1e-2)) + th[2] * math.log(max(mw, 1e3) / 1e5) \
            + th[3] * 1e3 * (1 / T - 1 / TREF)
        kt = arr_s(KT0, T) * sig_s(zt) + crd * kp * M
        kd = arr_s(KD, T)
        ktrm = arr_s(CM, T) * kp
        Meq = math.exp(DHP / (R * T) - DSP / R)
        Ri = 2.0 * f * kd * I
        net = kp * (M - Meq)
        wp = max(NM0 - NMc, 0.0) * MM / (1.0 + w)
        dT = (-DHP * V * net * c0 * kg - UA * (T - Tb)) / (kg * (1.0 + w) * (CP["a"] + CP["b"] * wp))
        return [
            -V * (net * c0 + ktrm * M * c0 + Ri),
            -kd * NI,
            V * (Ri - 2.0 * kt * c0 * c0),
            V * (Ri + net * c0 + ktrm * M * (c0 - c1) - 2.0 * kt * c0 * c1),
            V * (Ri + kp * M * (2.0 * c1 + c0) + kp * Meq * (c0 - 2.0 * c1) + ktrm * M * (c0 - c2) - 2.0 * kt * c0 * c2),
            V * (ktrm * M * c0 + (1.0 + DELTA) * kt * c0 * c0),
            V * (ktrm * M * c1 + 2.0 * kt * c0 * c1),
            V * (ktrm * M * c2 + 2.0 * kt * c0 * c2 + 2.0 * (1.0 - DELTA) * kt * c1 * c1),
            dT,
        ]
    s = solve_ivp(rhs, (0.0, float(tt[-1])), y_init(1, w, Tb), method="LSODA", t_eval=tt, rtol=rtol,
                  atol=atol(1), max_step=5.0)
    return s.t, s.y


def slab_system(th, w, prog, thickness_mm, h, n_el):
    """Right-hand side and initial state of the symmetric sheet, mid-plane (element 0) to the
    wall, in a Lagrangian mass coordinate; shared by slab() and the D1 design runs."""
    T0 = bath_K(prog, 0.0)
    dm = (RM["a"] + RM["b"] * (T0 - 273.15)) * thickness_mm * 0.5e-3 / n_el

    def rhs(t, y):
        Y = y.reshape(n_el, NS).T
        dY, q, v, wp = kinetics(th, Y, w)
        T = Y[8]
        Rh = dm * v / (2.0 * (KM + (KPOL - KM) * wp))
        flux = (T[:-1] - T[1:]) / (Rh[:-1] + Rh[1:])
        net = np.zeros(n_el)
        net[:-1] -= flux
        net[1:] += flux
        net[-1] -= (T[-1] - bath_K(prog, t)) / (Rh[-1] + 1.0 / h)
        dY[8] = (net + dm * q) / (dm * (1.0 + w) * (CP["a"] + CP["b"] * wp))
        return dY.T.ravel()
    return rhs, y_init(n_el, w, T0)


def slab(th, w, prog, thickness_mm, h, tt, n_el=30, rtol=1e-7):
    """Symmetric sheet from the mid-plane (element 0) to the wall. Returns t, Y (n_el, 9, nt)."""
    rhs, y0 = slab_system(th, w, prog, thickness_mm, h, n_el)
    s = solve_ivp(rhs, (0.0, tt[-1]), y0, method="LSODA", t_eval=tt, rtol=rtol,
                  atol=atol(n_el), lband=2 * NS - 1, uband=2 * NS - 1, max_step=10.0)
    if not s.success:
        raise RuntimeError(s.message)
    return s.t, s.y.reshape(n_el, NS, -1)


def production(th, w, Yflat):
    """For states Yflat (9, n): alpha = -ln q of the geometric live chain-length distribution
    (quasi-steady radicals with depropagation) and the dead-polymer production rates, in
    monomer units per kg monomer charged per s, by disproportionation + transfer (weight
    ~ n q^n) and by combination (weight ~ n^2 q^n)."""
    a = kinetics(th, Yflat, w, aux=True)
    kpM, kdp = a["kp"] * a["M"], a["kp"] * a["Meq"]
    S = kpM + kdp + 2.0 * a["kt"] * a["c0"] + a["ktrm"] * a["M"]
    q = 2.0 * kpM / (S + np.sqrt(np.maximum(S * S - 4.0 * kdp * kpM, 0.0)))
    alpha = -np.log(np.clip(q, 1e-300, 1.0 - 1e-16))
    Rd = np.maximum(a["V"] * (a["ktrm"] * a["M"] + 2.0 * DELTA * a["kt"] * a["c0"]) * a["c1"], 0.0)
    Rc = np.maximum(a["V"] * 2.0 * (1.0 - DELTA) * a["kt"] * a["c0"] * a["c1"], 0.0)
    return alpha, Rd, Rc


def gpc_ps_averages(th, w, t, y):
    """Polystyrene-equivalent Mn and Mw of all dead polymer made in an ampoule up to each time
    in t, as the GPC computes them slice by slice (instruction): sum(w M_PS) / sum(w) and
    sum(w) / sum(w / M_PS) with M_PS = C_PS M^BETA. The slice sums are the fractional moments
    E[M^(+/-BETA)] of the gamma-shaped instantaneous distributions, integrated over time."""
    alpha, Rd, Rc = production(th, w, y)
    scale = (M0 / alpha) ** BETA
    up = (G_UP[0] * Rd + G_UP[1] * Rc) * scale
    down = (G_DOWN[0] * Rd + G_DOWN[1] * Rc) / scale
    W, S_up, S_down = (cumulative_trapezoid(v, t, initial=0.0) for v in (Rd + Rc, up, down))
    with np.errstate(divide="ignore", invalid="ignore"):
        return C_PS * W / S_down, C_PS * S_up / W


def mwd(th, w, t, Y):
    """Weight fractions of all polymer made up to t[-1] in the bins of EDGES (log10 M), tails
    folded into the end bins."""
    n, _, nt = Y.shape
    alpha, Rd, Rc = production(th, w, np.moveaxis(Y, 1, 0).reshape(NS, n * nt))
    x = alpha[:, None] * (10.0 ** EDGES / (MM * 1e3))[None, :]
    c2, c3 = gammainc(2.0, x), gammainc(3.0, x)       # cumulative weight, shape 2 and 3
    f2, f3 = np.diff(c2, axis=1), np.diff(c3, axis=1)
    f2[:, 0] += c2[:, 0]
    f3[:, 0] += c3[:, 0]
    f2[:, -1] += 1.0 - c2[:, -1]
    f3[:, -1] += 1.0 - c3[:, -1]
    rate = (Rd[:, None] * f2 + Rc[:, None] * f3).reshape(n, nt, -1).sum(0)
    W = (0.5 * (rate[1:] + rate[:-1]) * np.diff(t)[:, None]).sum(0)
    return W / W.sum()


def casting(th, c, n_el=30, rtol=1e-7):
    w, prog = c["w_AIBN"], c["bath_program"]
    tt = np.linspace(0.0, c["t_end_min"] * 60.0, int(c["t_end_min"] * 6) + 1)
    t, Y = slab(th, w, prog, c["thickness_mm"], c["h_W_per_m2K"], tt, n_el, rtol)
    X = (1.0 - Y[:, 0] * MM).mean(0)
    n_out = max(1, round(0.10 * n_el))

    def avg_M(sl):
        mu0, mu1, mu2 = Y[sl, 5, -1].sum(), Y[sl, 6, -1].sum(), Y[sl, 7, -1].sum()
        return MM * 1e3 * mu1 / mu0, MM * 1e3 * mu2 / mu1
    excess = Y[0, 8] - bath_K(prog, t)
    k = int(np.argmax(excess))
    j = int(np.argmax(X >= 0.8))
    Mn, Mw = avg_M(slice(None))
    return dict(
        id=c["id"],
        t80_min=float(np.interp(0.8, X[j - 1:j + 1], t[j - 1:j + 1])) / 60.0,
        dT_mid_max_K=float(excess[k]),
        t_dT_mid_max_min=float(t[k] / 60.0),
        X_avg_t1=float(np.interp(c["t1_min"] * 60.0, t, X)),
        X_avg_end=float(X[-1]),
        Mn_avg_end_g_per_mol=float(Mn),
        Mw_avg_end_g_per_mol=float(Mw),
        Mw_inner_end_g_per_mol=float(avg_M(slice(0, n_out))[1]),
        Mw_outer_end_g_per_mol=float(avg_M(slice(n_el - n_out, n_el))[1]),
        mwd_weight_fractions=[float(v) for v in mwd(th, w, t, Y)],
    )


amp = pd.read_csv(DATA / "ampoules.csv")
conv = pd.read_csv(DATA / "ampoule_conversion.csv")
gpc = pd.read_csv(DATA / "ampoule_gpc.csv")


N_RES = len(conv) + 2 * len(gpc)


def ampoule_grid(a):
    """Data times of one ampoule (s) merged into a GRID_S grid from t = 0."""
    t_data = np.unique(np.concatenate([conv.t_min[conv.run_id == a.run_id].values,
                                       gpc.t_min[gpc.run_id == a.run_id].values])) * 60.0
    grid = np.arange(0.0, t_data[-1], GRID_S)
    grid = grid[np.min(np.abs(grid[:, None] - t_data[None, :]), axis=1) > 1e-6]
    return np.sort(np.concatenate([grid, t_data]))


GRIDS = {a.run_id: ampoule_grid(a) for a in amp.itertuples(index=False)}


def residuals(th):
    """Conversion residuals (scale 0.01 absolute) and log polystyrene-equivalent Mn, Mw
    residuals (scale 0.05), the uncertainties the instruction gives."""
    res = []
    for a in amp.itertuples(index=False):
        cd, gd = conv[conv.run_id == a.run_id], gpc[gpc.run_id == a.run_id]
        tt = GRIDS[a.run_id]
        t, y = ampoule(th, a.w_AIBN, a.T_bath_C, a.UA_W_per_K, a.monomer_g * 1e-3, tt)
        if len(t) != len(tt):
            return np.full(N_RES, 1e3)
        idx = {round(v, 3): i for i, v in enumerate(tt)}
        ic = [idx[round(v * 60.0, 3)] for v in cd.t_min]
        ig = [idx[round(v * 60.0, 3)] for v in gd.t_min]
        Mn_ps, Mw_ps = gpc_ps_averages(th, a.w_AIBN, t, y)
        res.append((1.0 - y[0, ic] * MM - cd.conversion.values) / 0.01)
        res.append(np.log(Mn_ps[ig] / gd.Mn_PS_equiv_g_per_mol.values) / 0.05)
        res.append(np.log(Mw_ps[ig] / gd.Mw_PS_equiv_g_per_mol.values) / 0.05)
    r = np.concatenate(res)
    return np.where(np.isfinite(r), r, 1e3)


# theta = A_t, Vf_t*100, m, E_t/1000, ln C_rd, B_p, Vf_p*100 (the cage effect is published)
# The starts are a 2 x 2 x 2 design over the gel-onset constants (A_t, Vf_t, E_t) combined
# with each of two generic settings of the other four constants that differ in every
# constant. The best start of each setting is refined within physical bounds (switch
# steepness and critical free volumes positive, m >= 0) and the fit with the lower cost is
# kept; two settings guard against a local minimum (both reach the same fit on these data).
GENERIC = ([0.3, np.log(300.0), 0.7, 2.5],
           [1.0, np.log(50.0), 1.5, 2.0])
LOWER = [0.05, 5.0, 0.0, -30.0, 0.0, 0.05, 0.5]
UPPER = [20.0, 40.0, 3.0, 30.0, 12.0, 20.0, 15.0]


def refine(x0):
    r = least_squares(residuals, np.asarray(x0, float), bounds=(LOWER, UPPER),
                      x_scale=[0.5, 0.2, 0.2, 2.0, 0.5, 0.3, 0.2],
                      diff_step=1e-3, xtol=1e-8, ftol=1e-8, max_nfev=150, verbose=1)
    print("refined from", np.round(x0, 4).tolist(), "to", np.round(r.x, 4).tolist(),
          "cost", round(float(r.cost), 3), flush=True)
    return float(r.cost), r.x.tolist()


best_starts = []
for g in GENERIC:
    starts = [[a, v, g[0], e, *g[1:]] for a in (2.0, 5.0) for v in (15.5, 17.0) for e in (-2.0, -8.0)]
    best_starts.append(min(starts, key=lambda x0: float(np.sum(residuals(np.array(x0)) ** 2))))
with Pool(2) as pool:
    fits = pool.map(refine, best_starts)
# The two settings reach the same constants at costs that differ by less than 1e-3 (B_p,
# loosely determined, differs by 0.01). Keep the first setting whose cost is within FIT_TIE of
# the best, so the choice does not turn on trailing digits that vary between hosts.
FIT_TIE = 0.05
best_cost = min(f[0] for f in fits)
fit_cost, theta = next(f for f in fits if f[0] <= best_cost + FIT_TIE)
theta = np.array(theta)
print("theta:", np.round(theta, 4).tolist(), "cost:", round(fit_cost, 2), "n_res:", N_RES, flush=True)

results = [casting(theta, c) for c in CAST["castings"]]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"castings": results}, indent=2) + "\n")
print(json.dumps(results, indent=2), flush=True)


# ---------------------------------------------------------------- D1 cure program
RAMP = SPEC["max_ramp_K_per_min"]
T_LIM, X_LIM = SPEC["bubble_temperature_C"], SPEC["bubble_conversion"]
ABORT_K = 10.0        # a layer below the bubble conversion this far above the bubble limit is a
                      # runaway: the run stops there (the slow, stiff tail of a runaway is never integrated)
BUDGET_S = 20.0       # wall-clock budget of one design run; a run past it fails the candidate
EXTEND_MIN = 400.0    # the open-ended post-cure is integrated at most this long past the ramp
N_COARSE, N_FINE = 10, 30
# Integration settings of the design runs: the coarse stage integrates on a 30 s grid at rtol
# 1e-5 (three times fewer steps), the fine stage on the 10 s grid at rtol 1e-6 of casting().
GRID = {N_COARSE: dict(dt=30.0, rtol=1e-5), N_FINE: dict(dt=10.0, rtol=1e-6)}


RAMP_SLACK = 1e-9     # the ramp is made this fraction longer than |dT|/RAMP: the verifier evaluates the
                      # ramp-rate inequality exactly in double precision, so the slope must not depend
                      # on the last bit of the arithmetic (a few milliseconds over an hour-long ramp)


def staged(x):
    """Hold T1 until t1, ramp at the maximum rate to the post-cure temperature Tpc (open-ended).
    With the end point that finish() adds, a program of this family has at most four points,
    the design.json limit (max_points)."""
    T1, t1, Tpc = x
    return [[0.0, T1], [t1, T1], [t1 + abs(Tpc - T1) / RAMP * (1.0 + RAMP_SLACK), Tpc]]


def run_program(prog, n_el, t_stop_min, x_stop=None):
    """Integrate D1 under prog on n_el volumes from t = 0 to t_stop_min, stopping early (terminal
    events) when the mass-average conversion reaches x_stop, or when a layer below the bubble
    conversion exceeds the bubble limit by ABORT_K (a runaway). Raises RuntimeError past
    BUDGET_S of wall-clock time or on an integrator failure. Returns t (min), X (n_el, nt),
    T (C, n_el, nt) on the stage's output grid up to the stop, and how it stopped: 'target',
    'abort', 'end'."""
    rhs, y0 = slab_system(theta, SPEC["w_AIBN"], prog, SPEC["thickness_mm"], SPEC["h_W_per_m2K"], n_el)
    t0 = time.time()

    def guarded(t, y):
        if time.time() - t0 > BUDGET_S:
            raise RuntimeError("design run over its time budget")
        return rhs(t, y)

    def abort(t, y):
        Y = y.reshape(n_el, NS).T
        X, T = 1.0 - Y[0] * MM, Y[8] - 273.15
        return float(np.max(np.minimum(T - T_LIM - ABORT_K, 100.0 * (X_LIM - X))))
    abort.terminal, abort.direction = True, 1.0
    events = [abort]
    if x_stop is not None:
        def target(t, y):
            return float(np.mean(1.0 - y.reshape(n_el, NS).T[0] * MM)) - x_stop
        target.terminal, target.direction = True, 1.0
        events.append(target)
    g = GRID[n_el]
    tt = np.arange(0.0, t_stop_min * 60.0 + 0.5 * g["dt"], g["dt"])
    s = solve_ivp(guarded, (0.0, tt[-1]), y0, method="LSODA", t_eval=tt, rtol=g["rtol"], atol=atol(n_el),
                  lband=2 * NS - 1, uband=2 * NS - 1, max_step=g["dt"], events=events)
    if not s.success:
        raise RuntimeError(s.message)
    how, k = "end", None
    if s.t_events[0].size:
        how, k = "abort", 0
    elif x_stop is not None and s.t_events[1].size:
        how, k = "target", 1
    t, y = s.t, s.y
    if k is not None:                    # append the event state so the stop is in the trajectory
        t = np.append(t, s.t_events[k][0])
        y = np.column_stack([y, s.y_events[k][0]])
    Y = y.reshape(n_el, NS, -1)
    return t / 60.0, 1.0 - Y[:, 0] * MM, Y[:, 8] - 273.15, how


def excess(X, T):
    """Worst temperature above the bubble limit of any layer below the bubble conversion."""
    return float(np.where(X < X_LIM, T - T_LIM, -np.inf).max())


def finish(x, n_el, dTr, mX):
    """Program of the family ended at the first 10 s at which the model's mass-average
    conversion reaches the (margined) target. Returns (program or None, worst bubble excess
    over the nominal program and over the program run dTr hotter, ok, earliness); earliness
    is how many minutes before its planned end a runaway stopped a run, 0 otherwise."""
    open_prog = staged(x)
    full = open_prog + [[open_prog[-1][0] + EXTEND_MIN, open_prog[-1][1]]]
    t, X, T, how = run_program(full, n_el, full[-1][0], SPEC["target_conversion"] + mX)
    over = excess(X, T)
    if how == "abort":
        return None, over, False, full[-1][0] - t[-1]
    if how != "target":
        return None, over, False, 0.0
    t_end = float(np.ceil(t[-1] * 6.0 - 1e-9) / 6.0)
    pts = [p for p in full if p[0] < t_end - 1e-9]
    prog = pts + [[t_end, float(np.interp(t_end, [p[0] for p in full], [p[1] for p in full]))]]
    if dTr > 0.0:
        t2, X2, T2, how2 = run_program([[a, b + dTr] for a, b in prog], n_el, t_end)
        over = max(over, excess(X2, T2))
        if how2 == "abort":
            return prog, over, False, t_end - t2[-1]
    return prog, over, over <= 0.0, 0.0


def cycle_cost(x, n_el, dTr, mX):
    """Cycle time of a feasible program; otherwise a penalty ordered so that a mild excess
    costs less than a runaway and an early runaway more than a late one."""
    T1, t1, Tpc = x
    lo, hi = SPEC["bath_temperature_min_C"], SPEC["bath_temperature_max_C"]
    if not (lo <= min(T1, Tpc) and max(T1, Tpc) <= hi and t1 > 0):
        return 1e6
    try:
        prog, over, ok, early = finish(x, n_el, dTr, mX)
    except RuntimeError:
        return 1e6
    if prog is None or not ok:
        if early > 0.0:                      # a runaway: the earlier it struck, the worse
            return 1e4 + 100.0 * max(over, 0.0) + early
        return 1e3 + 100.0 * max(over, 0.0)  # a mild excess, or the target not reached in time
    return prog[-1][0]


# Coarse-to-fine search. Stage A: Nelder-Mead on N_COARSE volumes from two physically safe
# starts (holds below the model's runaway boundary, late ramps), run in parallel, best of the
# two kept, with the margins ROBUST_DT and MARGIN_X. Stage B: on N_FINE volumes, keep the hold
# and post-cure temperatures of stage A and find the earliest ramp start that keeps the
# margined bubble limit (bisection to 1 min); the coarse grid overstates the mid-plane and
# understates the wall layers, so the fine grid, not a wider margin, decides the ramp timing.
dTr, mX = ROBUST_DT, MARGIN_X


def search(x0):
    """One Nelder-Mead run of stage A from x0 = [hold C, hold end min, post-cure C]."""
    simplex = np.vstack([x0] + [np.asarray(x0) + np.eye(3)[i] * d for i, d in enumerate((0.5, 20.0, 4.0))])
    r = minimize(cycle_cost, np.asarray(x0, float), args=(N_COARSE, dTr, mX), method="Nelder-Mead",
                 options=dict(maxfev=45, xatol=0.1, fatol=0.5, initial_simplex=simplex))
    return r.fun, r.x.tolist(), r.nfev


STARTS = [[47.5, 600.0, 110.0], [47.8, 570.0, 112.0]]
t_search = time.time()
with Pool(2) as pool:
    found = sorted(pool.map(search, STARTS))
for fun, x, nfev in found:
    print(f"stage A start -> hold {x[0]:.3f} C to {x[1]:.1f} min, post-cure {x[2]:.2f} C: cycle {fun:.1f} min ({nfev} evaluations)", flush=True)
(fun_A, (T1, t1_A, Tpc), _) = found[0]
print(f"stage A (coarse, {N_COARSE} volumes): best cycle {fun_A:.1f} min in {time.time() - t_search:.0f} s", flush=True)


def fine_ok(t1):
    prog, over, ok, _ = finish([T1, t1, Tpc], N_FINE, dTr, mX)
    return ok and prog is not None and len(prog) <= SPEC["max_points"], prog, over


lo, hi = t1_A - 40.0, t1_A + 120.0
ok_lo, prog_lo, over_lo = fine_ok(lo)
ok_hi, prog_hi, over_hi = fine_ok(hi)
if ok_lo:
    best = (lo, prog_lo, over_lo)
elif not ok_hi:
    raise SystemExit(f"no ramp start in [{lo:.0f}, {hi:.0f}] min keeps the margined bubble limit on the fine grid "
                     f"(excess {over_lo:.2f} K at {lo:.0f} min, {over_hi:.2f} K at {hi:.0f} min)")
else:
    best = (hi, prog_hi, over_hi)
    while hi - lo > 1.0:
        mid = 0.5 * (lo + hi)
        ok, prog, over = fine_ok(mid)
        if ok:
            hi, best = mid, (mid, prog, over)
        else:
            lo = mid
t1_B, program, over = best
print(f"stage B (fine, {N_FINE} volumes): earliest safe ramp start {t1_B:.1f} min (coarse {t1_A:.1f}), "
      f"worst margined excess {over:.2f} K, cycle {program[-1][0]:.1f} min, search {time.time() - t_search:.0f} s", flush=True)
if program[-1][0] > SPEC["max_cycle_time_min"]:
    raise SystemExit(f"cycle {program[-1][0]:.1f} min exceeds max_cycle_time_min {SPEC['max_cycle_time_min']} min")
OUT_PROGRAM.write_text(json.dumps({"bath_program": program}, indent=2) + "\n")
print(json.dumps({"bath_program": program}), flush=True)
