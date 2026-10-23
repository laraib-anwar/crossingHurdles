# Test neurons for Reference A

`make_tests.py` writes the neurons, `check_tests.py` runs `../reference.py` on each (timed, with
the verifier's thread variables), compares with closed forms and identities and prints every
deviation. Last run: 8 neurons, 17.4 s total including the extended-mode checks, 0 failures.
Each `<name>_report.json` is the report of `reference.py` for `<name>.json`.

| neuron | N | what it exercises | in domain and guarantees |
| --- | --- | --- | --- |
| cable_sealed | 3 | unbranched sealed cable (3 identical segments in a chain, L/lambda = 0.6), negligible soma (d_s = 8 um, Rm_s = 60000); 3 modes; query at fraction 0.001 | yes |
| cable_killed | 3 | unbranched killed cable, unequal segment lengths; 3 modes | yes |
| rall_exact | 3 | bifurcation obeying Rall's 3/2 rule exactly with children of different diameter (3.0 and 1.99 um) and equal electrotonic length; equivalent-cylinder checks on R_in, attenuation, impedance | no: the two children share killed-root eigenvalues, so hidden modes exist (guarantee 2 violated); DC/AC checks only |
| rall_perturbed | 3 | the same tree with the second child 1 % longer; the hidden mode becomes visible with C/R_in = 4.9e-5 | yes |
| shunt_terminal | 4 | 6 nS shunted terminal next to a sealed one, somatic shunt 3 nS, non-uniform Rm and Cm | yes |
| near_symmetric | 3 | sibling cables 400 and 401.2 um (0.3 % apart); nearly hidden modes with C/R_in = 1.1e-6 and 2.4e-5 next to visible ones | yes (|C| >= 1e-6 R_in holds, narrowly: 1.08e-6) |
| tree10 | 10 | three branch orders, sealed, killed and shunted terminals, Rm 20000 to 60000, Cm 0.8 to 2.0, Ri 70 to 150, somatic shunt; 22 modes; 2000 Hz between distal tips | yes |
| tree12_soma | 12 | dominant soma (d_s = 40, Rm_s = 2000, g_s = 20 nS), fractions 0 and 1 (node coincidences), a coincident attenuation pair, 2000 Hz at the soma | yes |

## Textbook comparisons (deviations from check_tests.py)

* Sealed cable: `R_in(soma) = 1/(G_s + G_inf tanh X)` 7.4e-15; `R_in(end)` 7.6e-15;
  `A(soma->end) = 1/cosh X` 1.7e-15; `A(soma->xi) = cosh(X-xi)/cosh X` at xi = 0.001 L 3.3e-16;
  all three `tau_k` vs brentq on `G_s + s C_s + G_inf gamma tanh(gamma X) = 0`: 0, 4.5e-16, 0.
  Against the soma-free formulas `tau_n = tau_m/(1 + (n pi lambda/L)^2)` and
  `C_0 = Rm/(pi d L)`, `C_n = 2 C_0 tau_n/tau_0`: 1.4 %, 6.4 %, 6.4 % and 1.4 %, 2.1 %, the
  expected size of the 3 % soma (capacitance ratio 1.2e-12 / 3.8e-11 F plus its leak).
* Killed cable: `R_in(soma) = 1/(G_s + G_inf coth X)` 5.2e-16; `A = sinh(X-xi)/sinh X` at two
  interior points 2.2e-16 and 9.0e-16; `tau_k` vs the exact condition 0, 0, 2.7e-16; vs the
  soma-free `tau_m/(1 + ((n+1/2) pi lambda/L)^2)` about 10 % (soma 5 % of the capacitance).
* Rall exact: `R_in(soma)` 7.5e-15, `A` to both tips `= 1/cosh X_eq` 1.2e-16, `|Z|` at 100 Hz
  8.0e-16, phase 1.4e-14 deg, equal transfer impedance to the two tips 2.0e-16. The visible mode
  is tau = 20 ms exactly (uniform membrane with tau_s = tau_m makes the uniform potential an
  eigenmode); the hidden quarter-wave mode `tau_m/(1 + (pi/(2 X_c))^2) = 0.21384 ms` is reported
  with coefficient -5.3e-14 MOhm, i.e. zero to rounding, as it must be.
* Rall perturbed: the same quantities differ from the equivalent cylinder by 6e-5 to 3e-3, the
  size of the 1 % perturbation.

## Internal identities, all neurons

Reciprocity of every impedance query listed in both directions: |Z| <= 4.4e-16 relative, phase
<= 2.9e-14 degrees; `A(a->b) R_in(a) = A(b->a) R_in(b)` <= 3.5e-16; coincident pair gives
exactly 1 and `R_in(soma) = R_in((1, 0))` exactly; `|Z(1 Hz)|` sits 0.06 % to 0.8 % below
`R_in` as `omega tau` dictates.

Mode lists: in every neuron the compartmental count, the number of sign changes of E and the
winding number agree; compartmental Richardson estimates deviate from the refined roots by
2.4e-8 to 1.2e-7 (in-domain lists) and by at most 7e-6 for the extended lists.
`sum C_k` over the list extended to tau_min/400 (up to 444 modes), Richardson-extrapolated in
1/K, reproduces `R_in(soma)` to 1e-5 to 1e-4; the residual is the 1/K tail.

Outside the domain the fallback was exercised once: tree12_soma extended to 231 modes contains a
pair separated by 1.2e-4 relative (below the 1e-3 guarantee), the 2.5e-4 scan found 227 sign
changes, the winding number said 231, the 10x denser rescan found 231.

## Runtimes (one CPU, OPENBLAS/OMP/MKL threads = 1)

cable_sealed 1.75 s, cable_killed 2.87 s, rall_exact 2.34 s, rall_perturbed 2.51 s,
shunt_terminal 2.20 s, near_symmetric 1.32 s, tree10 2.21 s, tree12_soma 2.22 s (process start to
exit, including the Python and SciPy imports).
