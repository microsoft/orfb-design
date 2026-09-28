---
name: ezbattery-cell-simulation
description: Evaluate ORFB negolyte candidates and full cells at the device level with the open-source EZBattery physics simulator (PNNL), via the simulate_negolyte / negolyte_sensitivity / simulate_cell tools and the execute_ezbattery_code tool.
states:
  - ezbattery.negolyte_evaluated
  - ezbattery.negolyte_sensitivity_analyzed
  - ezbattery.cell_simulated
---

# EZBattery Cell-Level RFB Simulation

Use this skill to close the ORFB design loop at the **device level**. The
molecular servers predict *molecule* properties (graphormer → redox potentials,
soltrannet → aqueous solubility, retrochimera → synthesizability, RDKit →
descriptors); EZBattery turns those into **cell KPIs** for a validated organic
**DHPS–ferrocyanide** aqueous reference cell.

EZBattery (Pacific Northwest National Laboratory, Simplified BSD) is a fast,
pure-Python cell/system-level RFB physics simulator. It is vendored in-kernel;
there is no external checkpoint. Simulation runs on CPU.

## Tools

- `simulate_negolyte(standard_potential, solubility_mol_per_L=None,
  electron_number=None, name=None, smiles=None, molar_mass=None,
  formal_charge=None, active_density_kg_per_m3=1400.0,
  reaction_rate_constant=None, extra_overrides=None)` — the primary
  negolyte-campaign entry point. Maps molecular predictions onto the **anode**
  (negolyte) of the reference cell:
  - `standard_potential` (V) → `AnodeStandardPotential` — the reduction standard
    potential of the negolyte couple. **Supply it on the same reference (SHE) as
    the posolyte** (ferro/ferricyanide). More negative widens the cell voltage
    window. A positive value triggers a reference-frame `warning`.
  - `solubility_mol_per_L` (mol/L, e.g. `10**logS` from soltrannet) →
    `AnodeOxidant1InitialConcentrationInAnode` (×1000 → mol/m³). Higher
    solubility raises accessible capacity / energy density.
  - `electron_number` → `AnodeElectronNumber` (e.g. 2 for a two-electron
    negolyte).
  - `smiles` → the preferred way to supply structure. When given, **molar mass
    and formal charge are computed from it via RDKit** (exact, deterministic
    descriptors), so you normally don't pass `molar_mass` / `formal_charge` by
    hand. Explicit numeric values still take precedence over the derived ones.
  - `molar_mass` (g/mol) → estimates the bulk diffusivity
    (`Anode{Oxidant,Reductant}1Diffusivity`) via Stokes-Einstein. Usually
    derived from `smiles`; pass explicitly only to override. This is a
    **conservative** estimate (tends to under-predict D); use
    `negolyte_sensitivity` to bracket its effect.
  - `formal_charge` → `Anode{Oxidant,Reductant}1Valence` (affects membrane
    crossover / Donnan terms; small effect when crossover is off). Usually
    derived from `smiles`.
  - `reaction_rate_constant` (m/s) → `AnodeReactionRateConstant`; left at the
    DHPS default (flagged `assumed_default`) if omitted.
  Returns a `parameter_provenance` list tagging every override as `predicted`
  (atomistic model), `estimated` (semi-empirical), `assumed_default` (untouched
  DHPS value) or `user` — so KPIs carry an honest confidence signal. Molar mass
  is also written through to `Anode{Oxidant,Reductant}1MolarMass` for template
  self-consistency, but note this reference cell's physics doesn't read that
  field — molar mass affects KPIs only via the diffusivity estimate.
  - `electrolyte_profile` → optionally select a named supporting-electrolyte
    regime (see `list_electrolyte_profiles`) that sets the anode
    viscosity / density / conductivity (viscosity also feeds the diffusivity
    estimate). Only `polymer_laden` is uncalibrated — a representative
    high-viscosity stress test flagged `assumed_default` with a
    `[PLACEHOLDER, not yet calibrated]` note in its `basis`. The other regimes
    (`dhps_koh`, `concentrated_koh`, `acidic_h2so4`, `neutral_nacl`) carry
    literature/reference-cell-calibrated values tagged `literature`. Extreme
    viscosities push the cell solver outside its validated range: if the
    effective anode viscosity exceeds ~30 cP (0.03 Pa·s) or the estimated
    active-species diffusivity falls below ~5e-11 m²/s, the result's `warnings`
    list flags that the run is near the solver's edge; if it actually fails to
    converge, the tool raises a clear error rather than a cryptic one.
- `negolyte_sensitivity(... same negolyte args ..., diffusivity_factors=(0.3,
  1.0, 3.0), rate_constant_factors=(0.1, 1.0, 10.0))` — sweeps the two least
  constrained inputs (bulk diffusivity and kinetic rate constant) around the
  baseline mapping and returns the **KPI spread** (`baseline`, per-KPI `ranges`
  with min/max/span, and the compact `grid`). Use it to rank candidates with
  error bars and check whether a ranking is robust to the physicochemical gap.
- `list_electrolyte_profiles()` — return the catalog of named
  supporting-electrolyte regimes (`dhps_koh`, `concentrated_koh`,
  `acidic_h2so4`, `neutral_nacl`, `polymer_laden`), each with its `label`,
  `calibrated` flag, `citation` and the anode transport `params` it sets. Pass a
  `name` as the `electrolyte_profile` argument above.
- `simulate_cell(overrides=None)` — simulate the reference cell directly, with
  an optional mapping of any of the ~205 EZBattery parameters to override
  values (validated against the bundled template). Use for parameter sweeps or
  when you need full control.

## Bridging the atomistic → cell gap

The atomistic predictors constrain only a few of EZBattery's molecule-dependent
inputs. `simulate_negolyte` fills the tractable ones and is explicit about the
rest via `parameter_provenance`:

| Cell input | Source | Provenance tag |
|---|---|---|
| E°, solubility, electron count | graphormer / soltrannet | `predicted` |
| bulk diffusivity | Stokes-Einstein from `molar_mass` (auto from `smiles`) | `estimated` |
| redox valences | `formal_charge` (auto from `smiles`) | `estimated` |
| electrolyte viscosity/density/conductivity | `electrolyte_profile` (all calibrated except `polymer_laden`) | `literature` / `assumed_default` |
| kinetics (k₀), crossover | **no predictor yet** | `assumed_default` |

Because the diffusivity estimate and the assumed kinetics are the biggest
unknowns, always pair a single `simulate_negolyte` call with
`negolyte_sensitivity` before trusting an absolute KPI.

## KPIs returned

Both tools return a `kpis` block:

- `cycles` — per-cycle list with `coulombic_efficiency`, `voltage_efficiency`,
  `energy_efficiency`, `charge_energy_wh`, `discharge_energy_wh`,
  `charge_time_s`, `discharge_time_s`.
- `final_cycle` — the last cycle's KPIs (a convenient summary).
- `capacity_fade_pct` — discharge-energy fade across cycles (needs >1 cycle).
- `voltage_curve` — a **downsampled** (≤60-point) `time_s` / `soc` /
  `cell_voltage_v` trace for plotting. The full trace is intentionally not
  returned to keep responses small.

## Typical negolyte-campaign flow

```python
# From upstream servers: reduction potential (V) and solubility (mol/L). Pass
# the SMILES so molar mass and formal charge are derived automatically (RDKit).
e_red = -0.85  # e.g. from graphormer, on the SHE frame
sol = 10 ** (-0.3)  # e.g. from soltrannet logS
smiles = "Oc1cc(O)c(cc1[N+](C)(C)C)[N+](C)(C)C"  # candidate structure
res = simulate_negolyte(
    standard_potential=e_red, solubility_mol_per_L=sol, electron_number=2, smiles=smiles, name="candidate-A"
)
fc = res["kpis"]["final_cycle"]
print(fc["energy_efficiency"], fc["discharge_energy_wh"])
# Bracket the uncertain diffusivity / kinetics before trusting the number:
sens = negolyte_sensitivity(
    standard_potential=e_red, solubility_mol_per_L=sol, electron_number=2, smiles=smiles, name="candidate-A"
)
print(sens["ranges"]["energy_efficiency"])  # {min, max, span}
```

Rank candidates by `discharge_energy_wh` (proxy for energy density) and
`energy_efficiency`; note that E° interacts with the fixed voltage cutoffs, so a
more negative potential does not always raise deliverable energy — that coupling
is exactly why device-level simulation adds value over the molecular E° alone.

## Notes

- Cross-server: pull SMILES/predictions in from peers with `ezbattery_send` /
  the object-transfer channel rather than pasting large objects through stdout.
- Follow the large-object rules: inspect `final_cycle` and slices of
  `voltage_curve`; don't print whole result dicts verbatim.
- The reference cell is the validated organic DHPS–ferrocyanide config from
  EZBattery's demo; the fixed posolyte is ferro/ferricyanide.
