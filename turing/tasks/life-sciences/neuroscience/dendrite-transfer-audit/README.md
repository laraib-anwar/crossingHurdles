# dendrite-transfer-audit

Compute the exact passive electrotonic properties of a reconstructed neuron (isopotential soma,
tree of cylindrical segments with their own membrane and axial parameters, sealed, killed and
shunted terminals, somatic shunt): steady-state input resistances, directional attenuation
factors, complex transfer impedances, and the complete set of equalization time constants above a
threshold with the coefficients of the somatic step response. Then diagnose a legacy
equivalent-cylinder script by executable witnesses.

| | |
| --- | --- |
| Domain | life-sciences / neuroscience / cellular-neurophysiology |
| Agent budget | 10800 s; 1 CPU, 2 GB, open internet |
| Verifier | separate container, offline, 1 CPU, 2048 MB, 7200 s; 30 nodes, binary reward |

## Difficulty

Passive cable theory is how cellular neurophysiologists turn a reconstructed morphology into
measurable numbers: the input resistance at a recording site, how much a synaptic potential
decays on its way to the soma, the frequency response, and the equalizing time constants that
"peeling" a voltage transient yields. For cylinders every one of these is exact (hyperbolic
functions and a recursion over the tree), so every answer has a definite value. The spec states
the model and the definitions and no method.

What a competent solver gets right: the input resistance of a sealed cable (`model_01`
reproduces `coth(L/lambda)/G_inf` with the somatic load), a lens-free bifurcation, the
reciprocity of transfer impedances. Where the difficulty is, each exercised by several of the 28
neurons:

1. **Boundary conditions.** A killed terminal (`V = 0`) and a shunted terminal change the input
   resistance, the attenuation and every time constant of the tree; treating them as sealed (the
   `sealed` control, and the legacy script) fails every neuron that has one.
2. **Directional attenuation with real loads.** `A(a -> b)` is `V(b)/V(a)` for current at `a`;
   it depends on the load beyond `b` and is not symmetric (`A(soma -> tip)` differs from
   `A(tip -> soma)` by a factor of several). The infinite-cable law `exp(-X/lambda)` (the
   `infinite` control) is symmetric and off by orders of magnitude.
3. **Frequency response of a cable, not of an RC.** The complex length constant
   `lambda / sqrt(1 + j w tau)` makes the transfer impedance fall and its phase lag grow with
   distance; phases beyond -90 degrees occur at 2000 Hz (`held_13`). The lumped RC model (the
   `lumped` control) fails every neuron with a transfer query.
4. **All the time constants, exactly.** The equalization time constants are the eigenvalues of
   the tree: roots of an entire function, graded to `1e-9` relative, with the count above
   `tau_min` graded exactly. Scanning the somatic admittance for sign changes (the `somatic`
   control) confuses roots with poles and misses the modes of nearly symmetric subtrees, whose
   root and pole lie within `1e-3` of each other (`model_05`, `held_10`, `held_21`). A
   compartmental model at 4 um resolution without extrapolation (the `fd` control) is `1e-4` off.
5. **Coefficients, including the nearly hidden ones.** `C_k = tau_k Res Z_soma(s_k)` is graded to
   `1e-9 R_in(soma)` absolute; the nearly hidden modes have coefficients of `1e-3 R_in` or
   smaller and must still be right. A one-sided finite difference of the admittance across a
   nearby pole gives nonsense.
6. **Units and geometry.** um to cm, nS to S, a soma area of `pi d^2`, `fraction` measured from
   the proximal end, locations that split a segment into two loaded cables, a soma that is
   negligible (`held_08`) or dominant (`held_09`), electrotonic lengths up to `L/lambda ~ 8`
   where naive `cosh`/`sinh` ratios overflow (`held_14`).
7. **28 all-or-nothing nodes** plus the saved base case and the diagnosis.

The legacy script `cableprop.py` is the classic lab script: Rall equivalent cylinder (3/2 rule at
the soma, mean electrotonic length, mean parameters, sealed ends), `exp(-X/lambda)` attenuation,
lumped RC transfer impedance, Rall's `tau_m / (1 + (n pi / L_eq)^2)` time constants with the
cylinder's coefficients.

## Reference solution

`solution/cabletree.py` is exact cable theory with three care points:

- **Admittances both ways.** `Ydown[i]` (looking into segment `i` from its proximal end) by the
  hyperbolic recursion from the terminals, and `Yup[i]` (looking away from `i` at its proximal
  node) from the soma downwards, so that a current injected anywhere splits into two loaded
  cables and the potential propagates outwards over the whole tree with the two-point transfer
  ratio of a loaded cable, written with decaying exponentials (no overflow for long or fast
  cables). DC is `s = 0`, AC is `s = j 2 pi f`.
- **Entire characteristic function.** Clearing the denominators of the recursion with
  `cosh(gamma a)`, `gamma sinh(gamma a)` and `sinh(gamma a)/gamma` (all even in `gamma`, hence
  single-valued in `s`) gives `E(s)` with `Z_soma = prod(D) / E`: its roots are all the
  eigenvalues (including the nearly hidden ones, which the somatic admittance hides behind a
  neighbouring pole), with no poles to confuse the bracketing. They are bracketed on a geometric
  scan of ratio `1 + 2e-4` (the domain guarantees `1e-3` separation) and polished with `brentq`;
  the coefficients come from `tau_k prod(D)(s_k) / E'(s_k)` with `E'` from a complex step.
- **Checks built into the dev pipeline.** Every generated neuron is cross-counted against a
  second-order compartmental eigenproblem (count and values to `2e-3`), reciprocity
  `Z(a -> b) = Z(b -> a)` holds to rounding, and the coefficients sum to `R_in(soma)` as
  `tau_min -> 0`.

`solution/diagnose.py` runs the legacy script and the program on the shipped neurons and writes
witnesses for the five diagnosis quantities; nothing is stored.

## Verification

Every expected value in `tests/expected.json` comes from Reference A (`tests/reference/reference.py`),
an independent implementation built without access to the oracle: a nodal admittance matrix over
the soma and the segment ends with exact two-port cable matrices (interior query points handled
by the segment's Green's function, not by splitting), the characteristic function in the even
variable `gamma^2` with carried analytic derivatives, roots located from a Richardson-extrapolated
compartmental eigenproblem and polished on the exact function, and the count certified by the
argument principle (winding number of `E` on a contour). Reference B (`refB/referee.py` in the
dev folder) shares nothing with cable theory: a vertex-centred finite-volume model at four nested
resolutions (4, 2, 1, 0.5 um; up to 14,000 nodes) with Richardson extrapolation, sparse LU for DC
and AC, exact Sturm counts plus shift-invert eigenvalues for the modes, modal coefficients from the
eigenvectors, and a Crank-Nicolson transient of the somatic step response compared with the
reported modal sum.

| Check | Result |
| --- | --- |
| Oracle vs Reference A, 28 neurons | mode counts equal; worst input resistance 1.9e-14, attenuation 3.4e-15, impedance modulus 1.0e-14 relative, phase 9e-13 degrees, time constants 4.4e-16 relative, coefficients 3.6e-13 R_in(soma) |
| Reference B referee, 28 neurons | 28 pass: extrapolated finite-volume values within 3.2e-10 (R_in), 2.7e-10 (A), 2.5e-10 (modulus), 1.3e-8 degrees, 3.1e-10 (tau), 2.6e-10 R_in (coefficients) of the oracle; transient somatic step within 8.1e-7 R_in of the reported modal sum; 0.2 to 8.2 s per neuron |
| Totals graded | 118 input resistances, 129 attenuation factors, 150 transfer impedances (16 with a positive principal-value phase), 233 modes (37 nearly hidden with coefficient below 1e-3 R_in, 54 modes in `held_11`), terminals 53 sealed / 28 killed / 26 shunted |
| Oracle in the environment image (`solve.sh`) | base case + diagnosis in 23 s; witnesses: `mode_count` (model_03), `tau`, `attenuation`, `input_resistance`, `impedance_magnitude` (model_01) |
| Verifier on the oracle artifacts | 30 passed, reward 1, 115 s; fresh calls 1.6 to 6.6 s |
| Verifier on empty `/root/results` | 30 failed, reward 0 |
| Verifier with a FIFO as `cabletree.py` | 30 failed, reward 0 |
| Generator screening | every neuron cross-counted against a second-order compartmental eigenproblem (count equal, values within 2e-3), all 28 pass the verifier's `validate_neuron` |

### Controls (wrong methods, graded with the verifier's comparison against Reference A)

| Control | Shortcut | Fails |
| --- | --- | --- |
| `legacy` | the shipped equivalent-cylinder script | 28 / 28 |
| `sealed` | every terminal treated as sealed | 23 / 28 (every neuron with a killed or shunted terminal) |
| `infinite` | attenuation by `exp(-X/lambda)` | 27 / 28 (error up to 1.2e3 relative) |
| `lumped` | lumped RC transfer impedance | 28 / 28 (error 9e-2 to 1e8) |
| `somatic` | modes from sign changes of the somatic admittance on a 1e-3 scan | 28 / 28 (wrong counts; where counts agree, tau off by 0.6 or more) |
| `fd` | 4 um compartmental model, no extrapolation | 28 / 28 (tau error 4.3e-6 to 1.6e-3; DC/AC exact to 1e-14 because that control only replaces the modes) |

### Tolerances

| Quantity | Tolerance | Method spread (oracle vs Reference A / referee) | Nearest wrong answer |
| --- | --- | --- | --- |
| `R_MOhm`, `factor`, `magnitude_MOhm` | 1e-9 relative | 1.9e-14 / 3.2e-10 | 7.6e-2 (`legacy` R_in), 9.4e-2 (`lumped`) |
| `phase_deg` | 1e-7 degrees | 9e-13 / 1.3e-8 | tens of degrees (`lumped`, `legacy`) |
| `tau_ms` | 1e-9 relative | 4.4e-16 / 3.1e-10 | 4.3e-6 (`fd`) |
| `coefficient_MOhm` | 1e-9 R_in(soma) absolute | 3.6e-13 / 2.6e-10 | 2.5e-2 (`somatic`) |

The tolerances sit at least three orders of magnitude above the method spread and three below the
nearest wrong method; a double-precision cable-theory solver meets them routinely, a careful
compartmental solver only with extrapolation.

### Coverage of the 28 neurons

| Neuron | segments | terminals | tau_min (ms) | modes | smallest coefficient / R_in | sites / pairs / queries | structure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `held_01` | 3 | killed | 1.855 | 3 | 1.9e-01 | 4 / 6 / 8 | unbranched cable with a killed end |
| `held_02` | 3 | shunt | 0.7478 | 3 | 4.2e-02 | 4 / 3 / 5 | unbranched cable with a shunted end |
| `held_03` | 3 | sealed | 0.3419 | 3 | 4.6e-04 | 7 / 2 / 6 | bifurcation close to the 3/2 rule |
| `held_04` | 3 | killed, sealed | 0.2903 | 3 | 4.9e-02 | 3 / 2 / 4 | asymmetric bifurcation |
| `held_05` | 11 | killed, sealed, shunt | 0.4145 | 7 | 3.7e-04 | 5 / 4 / 5 | tree with four branch orders |
| `held_06` | 8 | sealed, shunt | 1.699 | 3 | 3.2e-02 | 3 / 4 / 6 | non-uniform membrane along the tree |
| `held_07` | 10 | killed, sealed, shunt | 0.4091 | 9 | 2.4e-06 | 6 / 7 / 2 | sealed, killed and shunted terminals in one tree |
| `held_08` | 10 | killed, sealed, shunt | 1.345 | 2 | 3.3e-02 | 4 / 2 / 8 | negligible soma |
| `held_09` | 11 | killed, sealed, shunt | 0.2082 | 16 | 2.3e-04 | 7 / 4 / 5 | dominant soma |
| `held_10` | 7 | sealed | 0.2931 | 7 | 5.9e-05 | 4 / 2 / 4 | nearly symmetric subtrees: close time constants |
| `held_11` | 10 | killed, sealed | 0.1403 | 54 | 1.3e-05 | 8 / 7 / 6 | forty or more modes |
| `held_12` | 9 | killed, sealed | 1.693 | 2 | 1.2e-02 | 2 / 7 / 5 | two or three modes |
| `held_13` | 10 | sealed, shunt | 0.5016 | 6 | 1.4e-03 | 5 / 8 / 5 | high-frequency queries with phases beyond -90 degrees |
| `held_14` | 3 | shunt | 0.6955 | 4 | 9.0e-02 | 3 / 4 / 6 | long thin cables, large electrotonic length |
| `held_15` | 5 | shunt | 0.1505 | 2 | 1.5e-02 | 6 / 8 / 4 | thick short segments, compact tree |
| `held_16` | 8 | sealed, shunt | 1.194 | 3 | 8.7e-03 | 4 / 5 / 7 | several trunks on the soma |
| `held_17` | 6 | shunt | 2.74 | 2 | 2.5e-02 | 4 / 2 / 7 | every terminal shunted |
| `held_18` | 8 | killed, sealed | 0.1814 | 14 | 1.3e-03 | 2 / 4 / 5 | killed terminals in a tree |
| `held_19` | 12 | killed, sealed | 0.7847 | 6 | 4.0e-03 | 7 / 6 / 8 | ten or more segments |
| `held_20` | 12 | killed, sealed, shunt | 0.2375 | 17 | 1.4e-04 | 5 / 6 / 8 | non-uniform tree with killed and shunted ends |
| `held_21` | 7 | sealed | 0.2598 | 7 | 8.1e-06 | 3 / 8 / 4 | nearly symmetric bifurcation |
| `held_22` | 12 | killed, sealed | 0.1977 | 16 | 8.1e-05 | 2 / 4 / 2 | tree with fifteen or more modes |
| `model_01` | 3 | sealed | 1.339 | 3 | 3.2e-02 | 4 / 6 / 5 | unbranched sealed cable (base case) |
| `model_02` | 3 | killed, shunt | 1.364 | 2 | 1.5e-01 | 3 / 4 / 3 | asymmetric bifurcation with a killed terminal |
| `model_03` | 11 | killed, sealed, shunt | 0.574 | 7 | 3.3e-05 | 3 / 3 / 8 | tree with non-uniform membrane and a shunted terminal |
| `model_04` | 7 | killed, sealed, shunt | 0.6635 | 4 | 1.9e-02 | 2 / 3 / 6 | dominant soma with shunt, few modes |
| `model_05` | 3 | sealed | 0.2956 | 3 | 1.2e-05 | 4 / 4 / 2 | nearly symmetric siblings: nearly hidden mode |
| `model_06` | 10 | killed, shunt | 0.1521 | 25 | 1.7e-04 | 4 / 4 / 6 | large tree, many modes |

### Reproduction (dev folder `turing/tbScience/dendrite-transfer-audit-dev`)

`tools/gen_neurons.py` (28-slot plan, guarantee screening with the compartmental cross-count),
`tools/run_fin.sh`, `tools/agree.py`, `controls/controls.py`, `tools/controls_study.py`,
`tools/docker_chain.sh`, `refA/` (Reference A with METHOD.md and tests), `refB/` (referee with
METHOD.md and tests), `evidence/` (Docker logs, CTRF, rewards), `tools/build_zip.py`.
