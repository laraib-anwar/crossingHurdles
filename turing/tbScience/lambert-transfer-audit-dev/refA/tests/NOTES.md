# Reference A test systems

`systems/` holds the inputs and `reports/` holds the output of `reference.py`. Every system except
t1 passes the guarantees of LAMBERT_SPEC section 2, checked by `harness/guarantees.py`; that check
includes guarantee 5 and the rule that t1 and t2 are subject to guarantee 3.

| system | what it checks | transfers (theta, solutions, best) |
| --- | --- | --- |
| t1_hohmann_textbook | **Textbook checks; deliberately outside the domain** (LEO a = 7000 km, theta = 180.0000036 deg, Vallado T = 76 min). (1) LEO->GEO arriving 1e-8 day after the Hohmann time: dv = 3.770727233304142 against the textbook 3.7707272333041297 (3e-15), a = 24582.000000000033 against 24582, e = 0.71523879261 (rp 7000, ra 42164). (2) Vallado, *Fundamentals of Astrodynamics*, Example 7-5: v0 = (2.0589134, 2.9159644, 0) and v = (-3.4515648, 0.9103142, 0) km/s; the book gives (2.058913, 2.915965) and (-3.451565, 0.910315). The 1e-6 difference comes from rebuilding the book's r vector from circular elements. | 180.0000036 / 1 / 0; 40.0000012 / 1 / 0 |
| t2_hyperbolic_object | Heliocentric system with a retrograde hyperbolic object (a = -1.2723e8 km, e = 1.20113, i = 122.74 deg); ephemeris at \|M\| up to about 37. Covers hyperbolic N = 0 arcs with A > 0 (theta < 180) and with A < 0 (theta > 180), plus a T_min(1) of about 1821 days that is not reached. | 161.3 / 1; 199.7 / 1; 171.8 / 1 (hyperbolic arc); 265.2 / 1 (hyperbolic arc) |
| t3_five_solutions | Exactly 5 solutions in three queries: n_max = 3, 4 and 2 with T between T_min(2) and T_min(3). Includes a Molniya orbit (e = 0.7222) queried about 1997 periods from its epoch. | 278.1 / 5 / best N=1 low; 72.4 / 5 / best N=2 low; 63.7 / 5 / best N=2 high |
| t4_theta_above_180 | theta > 180 with multi-revolution arcs: 9 solutions (n_max = 4, T > T_min(4)) with best on N=4 high; a 3-solution case at theta = 320; an N = 0 elliptic arc at 193 deg with T < T_min(1). Retrograde target (i = 170). | 193.3 / 9 / 8 (N=4 high); 320.1 / 3 / 1 (N=1 low); 193.4 / 1 / 0 |
| t5_best_multirev | Saturn-like moons. The best solution is on a multi-revolution branch in every query. | 346.9 / 5 / 3 (N=2 low); 338.5 / 3 / 1 (N=1 low); 345.6 / 3 / 1 (N=1 low) |
| t6_distant_epochs | Epochs 1 800 to 2 000 periods from the queried times. Includes an e = 0.95 orbit with an ephemeris query 0.02 day after its epoch (at periapsis), a near-polar hyperbolic flyby (e = 3.5) and a retrograde object (i = 179). | 279.2 / 5 / 1; 162.8 / 1 (hyperbolic arc); 345.4 / 1 (hyperbolic arc) |
| t7_angle_edges | mu = 1e4 (domain minimum). theta at 178.68, 181.03 and 358.63 deg, near the guarantee-1 limits, with multi-revolution arcs; 9 solutions at T = 1000 days. | 178.68 / 3; 181.03 / 3; 358.63 / 1; 298.3 / 9 / 7 (N=4 low) |
| t8_small_angle_fast | mu = 2e11 (domain maximum). theta = 1.002 and 1.001 deg (guarantee-1 minimum), reached by fast hyperbolic arcs at r of about 1e8 km. Ephemerides at t = +-19999.5 days. A 5-solution query with T = 1341 days. | 1.002 / 1; 1.001 / 1 (n_max = 4, all T_min reported); 193.7 / 5 / 1 |

## Validation results

These were produced with `harness/validate.py REFA_DIR system.json ...` and cover all of the systems
above together with `models/dev_01.json` and the 28 `gen/systems` files dated 2026-10-24 11:48:

- Every count, label, `best`, `T_min` and solution agrees with the dense naive `TOF(z)` scan.
- Errors against the 60-digit references:
  - v1 and v2 agree with the shooting solution to 1.8e-14.
  - a agrees to 7.1e-15, e to 1.6e-14 and dv to 9.1e-15.
  - Ephemeris r and v agree with the Decimal Kepler-equation states to 1.8e-15.
  - T_min agrees with the Decimal TOF at the minimiser to 9.8e-16.
- Re-propagating `(r1, v1)` for T lands on r2 within 3.2e-11. This is limited by conditioning: the
  e = 0.9986 multi-revolution arcs in held_11 have `|dr2/dv1| |v1| / |r2|` of about 6.5e4.

The regenerated `gen/systems` dated 12:49 all pass the guarantee check. Their reports are in
`../out_gen/`. On that set every check passes:

- v1 and v2 agree to 6.7e-15.
- dv agrees to 3.0e-15.
- Ephemeris states agree to 1.8e-15.
- T_min agrees with the Decimal TOF to 1.0e-15 and with the dense scan to 1.1e-14.
- The 60-digit re-propagation miss is at most 4.0e-12.

## Observations

- The f, g velocity formula `v1 = (r2 - f r1)/g` loses about 8 digits on the dev Hohmann case, where
  theta is about 180 deg. `fg_vs_rt` = 2e-8 in `validate.py` shows this. Reference A therefore uses
  the radial/transverse form; see METHOD.md.
- On every elliptic z interval y is at least `y0 = |r2-r1|^2/(r1+r2+sqrt2|A|) > 0`, including
  theta > 180 (A < 0) near the ends of the multi-revolution intervals. y <= 0 happens only on the
  hyperbolic side with A > 0.
- Guarantee 5 rules out theta near 1 or 359 deg for slow arcs: those transfers are nearly rectilinear,
  with periapsis below 1e3 km. In-domain theta of about 1 deg needs fast hyperbolic arcs (t8). theta
  of about 359 deg needs a near-circular N = 0 arc with T close to one period, with n_max = 0 (t7).

## Rebuilding

    python harness/build_tests.py <refA_dir> <out_dir>

This regenerates the systems with a T search. It writes them flat into `<out_dir>`; move them into
`systems/` afterwards. `harness/stress.py <refA_dir> NSYS SEED NSHOOT [NWORST]` is the random
stress run, and `harness/shoot_worst.py` checks its worst re-propagation cases in Decimal. All
harness scripts import `hp.py`, the Decimal propagator and shooting solver, which is used for
validation only.
