"""Data-generating ("true plant") model for bulk MMA / AIBN free-radical polymerization.

Author-side, and copied into the verifier image as tests/plant.py, where it runs the agent's
cure program. It never enters the agent image. The slab equations are built by slab_system(),
which simulate_slab() and the verifier's continuous-time cure run share, so both integrate
exactly the same system with the same LSODA settings (slab_solver_options()).

Chemistry (per material element, method of moments): initiator decomposition, propagation
with depropagation, chain transfer to monomer, termination by combination and
disproportionation. Live radical moments lambda_0..2 and dead polymer moments mu_0..2 are
carried as extensive quantities per kg of monomer charged, so volume contraction from
monomer to polymer is exact.

Depropagation: net propagation rate kp ([M] - [M]_eq) [R], with the ceiling equilibrium
    [M]_eq = exp(dH_p / (R T) - dS_p / R)      (mol/L, standard state 1 mol/L)
and the depropagation step R_n -> R_{n-1} + M at rate kp [M]_eq per radical (applied in the
moment equations as d lambda_1 -= kp[M]_eq lambda_0, d lambda_2 += kp[M]_eq (lambda_0 - 2 lambda_1)).

Diffusion control uses the Bueche free volume of the monomer/polymer mixture,
    Vf = (0.025 + 4.8e-4 (T - Tgp)) phi_p + (0.025 + 1.0e-3 (T - Tgm)) phi_m,
and three effects that switch on smoothly as Vf falls:
  gel effect   kt = kt0 / (1 + exp(z_t)) + C_rd kp [M]
               z_t = A_t (1/Vf - 1/Vf_t) + m ln(Mw / 1e5) + E_t (1/T - 1/343.15)
  glass effect kp = kp0 / (1 + exp(B_p (1/Vf - 1/Vf_p)))       (also scales depropagation)
  cage effect  f  = f0  / (1 + exp(B_f (1/Vf - 1/Vf_f)))
Mw is the cumulative weight-average molar mass of the dead polymer in the element (1e5 g/mol,
which makes the m ln(Mw / 1e5) term zero, before any dead polymer has formed there; the
max(Mw, 1e3) in element_rates() only guards the logarithm and never binds, since dead-polymer
Mw stays above 1e5 g/mol in this system).

Vessels
  lumped   well-mixed contents, overall heat-transfer coefficient UA to a bath.
  slab     sheet casting of initial thickness 2 L0 between two cell walls, symmetric about the
           mid-plane. 1-D transient conduction in a Lagrangian (mass) coordinate: each finite
           volume keeps its monomer mass, its thickness follows the local densities, so the
           casting shrinks as it polymerizes. Conductivity k = k_m + (k_p - k_m) w_p.
           Convective boundary to the bath with overall coefficient h (cell wall included).
           Bath temperature follows a piecewise-linear program.

The published constants (properties.json) are the chemically controlled values (without
diffusion limitation), the cage effect on f as a table of f/f0 against Vf (tabulated from the
law above at Bf and Vff, which are not published themselves), and physical properties.
instruction.md states the free volume Vf, that the cage-effect table applies, and the gel- and
glass-effect laws above in closed form, with their reference points 343.15 K and 1e5 g/mol and
the zero ln term before any polymer has formed. The seven constants in HIDDEN are not
published: the agent infers them from the ampoule data.
Termination convention (IUPAC): d[R]/dt = -2 kt [R]^2.
"""
import numpy as np
from scipy.integrate import solve_ivp

MM = 100.12e-3      # kg/mol, MMA
MI = 164.21e-3      # kg/mol, AIBN
RGAS = 8.314462618
NS = 9              # states per element: NM, NI, l0, l1, l2, m0, m1, m2, T

PUBLIC = dict(
    kd_A=1.053e15, kd_E=15500.0,     # 1/s, K       AIBN decomposition
    f0=0.58,                         # initiator efficiency at low conversion
    kp_A=4.917e5, kp_E=2190.0,       # L/(mol s), K  kp0
    kt_A=9.80e7, kt_E=353.0,         # L/(mol s), K  kt0 (IUPAC)
    Cm_A=1.2e-2, Cm_E=2400.0,        # -, K          Cm = ktrm/kp
    delta=0.75,                      # fraction of termination events by disproportionation
    dH=57.8e3,                       # J/mol of monomer polymerized (heat released); dH_p = -dH
    dS=-134.6,                       # J/(mol K), dS_p of propagation, standard state 1 mol/L
    rho_m=(966.5, -1.1),             # kg/m3 = a + b (T - 273.15)
    rho_p=(1200.0, -0.30),
    cp=(1910.0, -490.0),             # J/(kg K) = a + b w_p
    k_th=(0.150, 0.193),             # W/(m K): monomer, polymer; k = k_m + (k_p - k_m) w_p
    Tgp=387.0, Tgm=167.0,            # K
    Bf=0.5, Vff=0.035,               # cage effect on f (initiator_efficiency_cage_effect)
)

HIDDEN = dict(At=3.0, Vft=0.164, m=0.5, Et=-6000.0, Crd=100.0,
              Bp=1.0, Vfp=0.028)


def _sig_down(z):
    return 1.0 / (1.0 + np.exp(np.clip(z, -700.0, 700.0)))


def element_rates(Y, w, p=PUBLIC, h=HIDDEN, gel=True, deprop=True, aux=False):
    """Kinetics of n material elements.

    Y : (9, n) states per kg of monomer charged (T in K, last row).
    Returns dY (9, n) with the T row left zero, heat release q (W per kg monomer),
    specific volume v (m3 per kg monomer) and polymer mass fraction w_p.
    """
    NM, NI, l0, l1, l2, m0, m1, m2, T = Y
    NM0 = 1.0 / MM
    NMc = np.maximum(NM, 0.0)
    Tc = T - 273.15
    vm = NMc * MM / (p['rho_m'][0] + p['rho_m'][1] * Tc)
    vp = np.maximum(NM0 - NMc, 0.0) * MM / (p['rho_p'][0] + p['rho_p'][1] * Tc)
    v = vm + vp
    V = v * 1e3                                   # L per kg monomer
    phim = vm / v
    M, I = NMc / V, NI / V
    c0, c1, c2 = l0 / V, l1 / V, l2 / V
    kd = p['kd_A'] * np.exp(-p['kd_E'] / T)
    kp0 = p['kp_A'] * np.exp(-p['kp_E'] / T)
    kt0 = p['kt_A'] * np.exp(-p['kt_E'] / T)
    Cm = p['Cm_A'] * np.exp(-p['Cm_E'] / T)
    if gel:
        vf = np.maximum((0.025 + 4.8e-4 * (T - p['Tgp'])) * (1.0 - phim)
                        + (0.025 + 1.0e-3 * (T - p['Tgm'])) * phim, 2e-3)
        mw = np.where(m1 > 1e-12 * NM0, MM * 1e3 * m2 / np.maximum(m1, 1e-300), 1e5)
        kp = kp0 * _sig_down(h['Bp'] * (1.0 / vf - 1.0 / h['Vfp']))
        f = p['f0'] * _sig_down(p['Bf'] * (1.0 / vf - 1.0 / p['Vff']))
        zt = (h['At'] * (1.0 / vf - 1.0 / h['Vft']) + h['m'] * np.log(np.maximum(mw, 1e3) / 1e5)
              + h['Et'] * (1.0 / T - 1.0 / 343.15))
        kt = kt0 * _sig_down(zt) + h['Crd'] * kp * M
    else:
        kp, f, kt = kp0, p['f0'], kt0
    Meq = np.exp(-p['dH'] / (RGAS * T) - p['dS'] / RGAS) if deprop else 0.0 * T
    ktrm = Cm * kp
    d = p['delta']
    Ri = 2.0 * f * kd * I
    net = kp * (M - Meq)
    dY = np.empty_like(Y)
    dY[0] = -V * (net * c0 + ktrm * M * c0 + Ri)
    dY[1] = -kd * NI
    dY[2] = V * (Ri - 2.0 * kt * c0 * c0)
    dY[3] = V * (Ri + net * c0 + ktrm * M * (c0 - c1) - 2.0 * kt * c0 * c1)
    dY[4] = V * (Ri + kp * M * (2.0 * c1 + c0) + kp * Meq * (c0 - 2.0 * c1)
                 + ktrm * M * (c0 - c2) - 2.0 * kt * c0 * c2)
    dY[5] = V * (ktrm * M * c0 + (1.0 + d) * kt * c0 * c0)
    dY[6] = V * (ktrm * M * c1 + 2.0 * kt * c0 * c1)
    dY[7] = V * (ktrm * M * c2 + 2.0 * kt * c0 * c2 + 2.0 * (1.0 - d) * kt * c1 * c1)
    dY[8] = 0.0
    q = p['dH'] * V * net * c0                    # W per kg monomer
    wp = np.maximum(NM0 - NMc, 0.0) * MM / (1.0 + w)
    if aux:
        return dY, q, v, wp, dict(V=V, M=M, c0=c0, c1=c1, kp=kp, kt=kt, ktrm=ktrm, Meq=Meq)
    return dY, q, v, wp


# ---------------------------------------------------------------- chain-length distribution
# Under the quasi-steady state for radicals, live chains of length n >= 2 obey
#   kp[M] R_{n-1} + kdp R_{n+1} - (kp[M] + kdp + L) R_n = 0,  kdp = kp [M]_eq,
#   L = 2 kt [R] + ktrm [M]  (loss of a radical by termination or transfer),
# so R_n ~ q^n with  kdp q^2 - (kp[M] + kdp + L) q + kp[M] = 0  (root q < 1).
# Dead chains made by disproportionation or transfer inherit that geometric distribution
# (weight ~ n q^n, a gamma of shape 2 in the continuum limit); chains made by combination
# are sums of two radicals (weight ~ n^2 q^n, shape 3). Integrating the dead-polymer
# production over time (and over material elements) gives the cumulative weight
# distribution; its first moment is exactly the mu_1 of the moment equations.
from scipy.special import gammainc  # noqa: E402

M0_G = MM * 1e3                                   # g/mol per monomer unit


def mwd_production(Yflat, w, p=PUBLIC, h=HIDDEN, gel=True, deprop=True):
    """Yflat (9, n). Returns alpha = -ln q, and dead-polymer production rates (monomer
    units, mol per kg monomer charged per s) by disproportionation+transfer and by
    combination."""
    _, _, _, _, a = element_rates(Yflat, w, p, h, gel, deprop, aux=True)
    kpM = a['kp'] * a['M']
    kdp = a['kp'] * a['Meq']
    L = 2.0 * a['kt'] * a['c0'] + a['ktrm'] * a['M']
    S = kpM + kdp + L
    q = 2.0 * kpM / (S + np.sqrt(np.maximum(S * S - 4.0 * kdp * kpM, 0.0)))
    alpha = -np.log(np.clip(q, 1e-300, 1.0 - 1e-16))
    d = p['delta']
    Rd = a['V'] * (a['ktrm'] * a['M'] + 2.0 * d * a['kt'] * a['c0']) * a['c1']
    Rc = a['V'] * 2.0 * (1.0 - d) * a['kt'] * a['c0'] * a['c1']
    return alpha, np.maximum(Rd, 0.0), np.maximum(Rc, 0.0)


def bin_fractions(alpha, edges_log10M, fold_tails=True):
    """Fraction of a shape-2 and a shape-3 gamma weight distribution in each bin.
    alpha (...,), returns two arrays (..., nbins)."""
    n_edges = 10.0 ** np.asarray(edges_log10M, float) / M0_G
    x = alpha[..., None] * n_edges
    c2, c3 = gammainc(2.0, x), gammainc(3.0, x)
    f2, f3 = np.diff(c2, axis=-1), np.diff(c3, axis=-1)
    if fold_tails:
        f2[..., 0] += c2[..., 0]
        f3[..., 0] += c3[..., 0]
        f2[..., -1] += 1.0 - c2[..., -1]
        f3[..., -1] += 1.0 - c3[..., -1]
    return f2, f3


def cumulative_mwd(t, Y, w, edges_log10M, fold_tails=True, p=PUBLIC, h=HIDDEN, gel=True,
                   deprop=True, cumulative_in_time=False):
    """Y (n_el, 9, n_t) (or (9, n_t) for one element) on time grid t (s).
    Returns weight (mol monomer units per kg monomer per element-sum) per bin at the last
    time, or for every time if cumulative_in_time."""
    if Y.ndim == 2:
        Y = Y[None]
    n_el, _, n_t = Y.shape
    flat = np.moveaxis(Y, 1, 0).reshape(NS, n_el * n_t)
    alpha, Rd, Rc = mwd_production(flat, w, p, h, gel, deprop)
    f2, f3 = bin_fractions(alpha, edges_log10M, fold_tails)
    rate = (Rd[:, None] * f2 + Rc[:, None] * f3).reshape(n_el, n_t, -1).sum(0)   # (n_t, nb)
    dt = np.diff(t)
    inc = 0.5 * (rate[1:] + rate[:-1]) * dt[:, None]
    if cumulative_in_time:
        return np.vstack([np.zeros((1, inc.shape[1])), np.cumsum(inc, axis=0)])
    return inc.sum(0)


def ps_equivalent_averages(weights, edges_log10M, mh):
    """GPC with polystyrene calibration: each slice of PMMA molar mass M elutes where a
    polystyrene of the same hydrodynamic volume would, K_PS M_PS^(1+a_PS) = K_PMMA M^(1+a_PMMA).
    weights (..., nbins) on fine bins; returns PS-equivalent (Mn, Mw)."""
    e = np.asarray(edges_log10M, float)
    M = 10.0 ** (0.5 * (e[:-1] + e[1:]))
    Kp, ap = mh["PMMA"]["K_mL_per_g"], mh["PMMA"]["a"]
    Ks, as_ = mh["PS"]["K_mL_per_g"], mh["PS"]["a"]
    Mps = (Kp / Ks * M ** (1.0 + ap)) ** (1.0 / (1.0 + as_))
    W = np.asarray(weights, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        Mn = W.sum(-1) / (W / Mps).sum(-1)
        Mw = (W * Mps).sum(-1) / W.sum(-1)
    return Mn, Mw


MARK_HOUWINK_THF = {"PS": {"K_mL_per_g": 0.0114, "a": 0.716},
                    "PMMA": {"K_mL_per_g": 0.0128, "a": 0.690}}


def bath_temperature(program, t_s):
    """program: list of [t_min, T_C] breakpoints, linear in between, constant after."""
    pts = np.asarray(program, float)
    return np.interp(t_s / 60.0, pts[:, 0], pts[:, 1]) + 273.15


def _y0(n, w, T0):
    Y = np.zeros((NS, n))
    Y[0] = 1.0 / MM
    Y[1] = w / MI
    Y[8] = T0
    return Y


def _atol(n):
    NM0 = 1.0 / MM
    a = np.array([1e-12, 1e-14, 1e-25, 1e-22, 1e-18, 1e-20, 1e-14, 1e-10]) * NM0
    return np.tile(np.append(a, 1e-8), n)


def _moments_out(Yt):
    with np.errstate(invalid='ignore', divide='ignore'):
        Mn = MM * 1e3 * Yt[6] / Yt[5]
        Mw = MM * 1e3 * Yt[7] / Yt[6]
    return Mn, Mw


def simulate_lumped(w, program, UA, monomer_kg, t_eval_s, p=PUBLIC, h=HIDDEN, gel=True,
                    deprop=True, isothermal=False, rtol=1e-9):
    """Well-mixed vessel (ampoule or tube). Returns time series of X, T, Mn, Mw."""
    def rhs(t, y):
        Y = y.reshape(NS, 1)
        dY, q, v, wp = element_rates(Y, w, p, h, gel, deprop)
        if not isothermal:
            Tb = bath_temperature(program, t)
            cp = p['cp'][0] + p['cp'][1] * wp[0]
            dY[8, 0] = (q[0] * monomer_kg - UA * (Y[8, 0] - Tb)) / (monomer_kg * (1.0 + w) * cp)
        return dY.ravel()
    y0 = _y0(1, w, bath_temperature(program, 0.0)).ravel()
    sol = solve_ivp(rhs, (0.0, float(t_eval_s[-1])), y0, method='LSODA', t_eval=t_eval_s,
                    rtol=rtol, atol=_atol(1), max_step=2.0)
    if not sol.success:
        raise RuntimeError(sol.message)
    Y = sol.y
    Mn, Mw = _moments_out(Y)
    return dict(t=sol.t, X=1.0 - Y[0] * MM, T=Y[8], Mn=Mn, Mw=Mw, Y=Y)


def slab_solver_options(n_el, rtol=1e-7):
    """LSODA settings of every slab integration (simulate_slab and the verifier's cure run)."""
    return dict(rtol=rtol, atol=_atol(n_el), lband=2 * NS - 1, uband=2 * NS - 1, max_step=10.0)


def slab_system(w, program, half_thickness_m, h_wall, n_el=40, p=PUBLIC, h=HIDDEN, gel=True,
                deprop=True):
    """Right-hand side and initial state of the symmetric sheet casting (see simulate_slab).
    State layout: element j (0 = mid-plane, n_el - 1 = wall) occupies y[NS*j:NS*(j+1)]."""
    T0 = bath_temperature(program, 0.0)
    rho0 = p['rho_m'][0] + p['rho_m'][1] * (T0 - 273.15)
    dm = rho0 * half_thickness_m / n_el            # kg monomer per m2 per element
    km, kpoly = p['k_th']

    def rhs(t, y):
        Y = y.reshape(n_el, NS).T
        dY, q, v, wp = element_rates(Y, w, p, h, gel, deprop)
        T = Y[8]
        dx = dm * v                                # element thickness, m
        k = km + (kpoly - km) * wp
        R_half = dx / (2.0 * k)
        G = 1.0 / (R_half[:-1] + R_half[1:])       # W/(m2 K) between neighbours
        flux = G * (T[:-1] - T[1:])                # from element j to j+1 (towards wall)
        Tb = bath_temperature(program, t)
        q_wall = (T[-1] - Tb) / (R_half[-1] + 1.0 / h_wall)
        net = np.zeros(n_el)
        net[:-1] -= flux
        net[1:] += flux
        net[-1] -= q_wall
        cp = p['cp'][0] + p['cp'][1] * wp
        dY[8] = (net + dm * q) / (dm * (1.0 + w) * cp)
        return dY.T.ravel()

    return rhs, _y0(n_el, w, T0).T.ravel()


def simulate_slab(w, program, half_thickness_m, h_wall, t_eval_s, n_el=40, p=PUBLIC,
                  h=HIDDEN, gel=True, deprop=True, rtol=1e-7, outer_frac=0.10):
    """Symmetric sheet casting, Lagrangian finite volumes from mid-plane (0) to wall (n-1).

    Returns mid-plane temperature, mass-average conversion and molar masses, and the
    cumulative Mw of the inner and outer `outer_frac` of the casting's mass."""
    rhs, y0 = slab_system(w, program, half_thickness_m, h_wall, n_el, p, h, gel, deprop)
    sol = solve_ivp(rhs, (0.0, float(t_eval_s[-1])), y0, method='LSODA', t_eval=t_eval_s,
                    **slab_solver_options(n_el, rtol))
    if not sol.success:
        raise RuntimeError(sol.message)
    Y = sol.y.reshape(n_el, NS, -1)               # element, state, time
    X_el = 1.0 - Y[:, 0, :] * MM
    n_out = max(1, int(round(outer_frac * n_el)))
    def avg_M(sl):
        mu0, mu1, mu2 = Y[sl, 5, :].sum(0), Y[sl, 6, :].sum(0), Y[sl, 7, :].sum(0)
        with np.errstate(invalid='ignore', divide='ignore'):
            return MM * 1e3 * mu1 / mu0, MM * 1e3 * mu2 / mu1
    Mn_avg, Mw_avg = avg_M(slice(None))
    _, Mw_in = avg_M(slice(0, n_out))
    _, Mw_out = avg_M(slice(n_el - n_out, n_el))
    return dict(t=sol.t, T_mid=Y[0, 8, :], T_wall_el=Y[-1, 8, :], X_avg=X_el.mean(0),
                X_mid=X_el[0], Mn_avg=Mn_avg, Mw_avg=Mw_avg, Mw_inner=Mw_in, Mw_outer=Mw_out,
                Y=Y, X_el=X_el, T_el=Y[:, 8, :])
