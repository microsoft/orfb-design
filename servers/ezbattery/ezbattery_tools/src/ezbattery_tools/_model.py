"""In-kernel EZBattery cell-level redox-flow-battery simulation.

Wraps `EZBattery <https://github.com/pnnl/EZBattery>`_ (Pacific Northwest
National Laboratory; Simplified BSD) — a fast, pure-Python cell/system-level
physics simulator for redox-flow batteries — to run **inside the ezbattery
CodeExecutionServer's kernel**. Where the molecular servers (graphormer,
soltrannet, retrochimera) predict *molecule-level* properties, EZBattery closes
the loop at the *device level*: given electrolyte/cell parameters it integrates
the coupled electrochemistry and returns cell KPIs — coulombic / voltage /
energy efficiency, charge & discharge energy, cycle times and the cell-voltage /
SOC curve.

For an ORFB **negolyte** (anode-side) design campaign the key entry point is
:func:`simulate_negolyte`, which maps molecular predictions onto the anode
parameters of a validated organic DHPS–ferrocyanide reference cell and reports
the resulting device performance:

* reduction standard potential (V)      -> ``AnodeStandardPotential``
* aqueous solubility (mol/L)            -> ``AnodeOxidant1InitialConcentrationInAnode`` (x1000 -> mol/m^3)
* electrons transferred per molecule    -> ``AnodeElectronNumber``

To bridge the remaining physicochemical gap between the atomistic predictors and
the cell model, :func:`simulate_negolyte` optionally also derives:

* bulk diffusivity (``Anode{Oxidant,Reductant}1Diffusivity``) from the molar
  mass via a Stokes-Einstein estimate (:func:`estimate_diffusivity_stokes_einstein`);
* the redox-species charges (``Anode{Oxidant,Reductant}1Valence``) from the
  molecule's formal charge (affects membrane crossover / Donnan terms);
* the kinetic rate constant (``AnodeReactionRateConstant``) if supplied.

Every override is tagged in a ``parameter_provenance`` block as ``predicted``
(from an atomistic model), ``estimated`` (semi-empirical) or ``assumed_default``
(left at the DHPS reference value), so downstream KPIs carry an honest
confidence signal. :func:`negolyte_sensitivity` brackets the headline KPIs over
the most uncertain inputs (diffusivity, rate constant). Note the cell model does
not consume a molar-mass field directly, so molar mass feeds only the diffusivity
estimate and is echoed as metadata.

The vendored EZBattery package (:mod:`ezbattery_tools._vendor.EZBattery`) is
pure Python (numpy / scipy / pandas / ismember), so there is no external
checkpoint to fetch or bake. The stack is imported lazily so this module stays
importable during server setup. Simulation runs on CPU.
"""

from __future__ import annotations

import functools
import json
import math
from importlib import resources
from typing import Any, Optional

# Reference cell bundled with the package: the validated organic
# DHPS(anode)-ferrocyanide(cathode) aqueous ORFB from EZBattery's demo config.
_TEMPLATE_RESOURCE = "organic_dhps_ferrocyanide.json"
_TEMPLATE_PACKAGE = "ezbattery_tools.data"

# Negolyte -> anode-parameter mapping (see module docstring).
_ANODE_STANDARD_POTENTIAL = "AnodeStandardPotential"
_ANODE_CONCENTRATION = "AnodeOxidant1InitialConcentrationInAnode"
_ANODE_ELECTRON_NUMBER = "AnodeElectronNumber"
_ANODE_OXIDANT_DIFFUSIVITY = "AnodeOxidant1Diffusivity"
_ANODE_REDUCTANT_DIFFUSIVITY = "AnodeReductant1Diffusivity"
_ANODE_OXIDANT_VALENCE = "AnodeOxidant1Valence"
_ANODE_REDUCTANT_VALENCE = "AnodeReductant1Valence"
_ANODE_OXIDANT_MOLAR_MASS = "AnodeOxidant1MolarMass"
_ANODE_REDUCTANT_MOLAR_MASS = "AnodeReductant1MolarMass"
_ANODE_RATE_CONSTANT = "AnodeReactionRateConstant"
_ANODE_VISCOSITY = "AnodeElectrolyteViscosity"
_ANODE_DENSITY = "AnodeElectrolyteDensity"
_ANODE_CONDUCTIVITY = "AnodeElectrolyteConductivity"
_TEMPERATURE = "Temperature"

# Physical constants for the Stokes-Einstein diffusivity estimate.
_BOLTZMANN = 1.380649e-23  # J/K
_AVOGADRO = 6.02214076e23  # 1/mol
# Assumed condensed-phase density (kg/m^3) of the dissolved organic active
# species, used only to turn a molar mass into a hydrodynamic radius. Picked to
# sit near typical aqueous-organic electrolyte densities (~1.3-1.5 g/cm^3).
_DEFAULT_ACTIVE_DENSITY = 1400.0

# Empirical validity envelope of the reference cell's transport solver. Once the
# Stokes-Einstein active-species diffusivity drops below ~2.5e-11 m^2/s (roughly
# an anode viscosity above ~30 cP for a small molecule) EZBattery's RFB stops
# converging and returns a degenerate result (see run_real_simulation's guard).
# The warn thresholds sit a margin *above* that failure edge so we flag runs that
# are merely approaching it — giving a heads-up before a run silently lands at, or
# fails past, the boundary rather than making the user rediscover it.
_SOLVER_MAX_VISCOSITY = 0.03  # Pa.s (~30 cP)
_SOLVER_MIN_DIFFUSIVITY = 5.0e-11  # m^2/s (failure sets in around ~2.5e-11)

# Cap the returned time-series so we never dump a multi-thousand-row curve into
# the kernel's stdout / MCP response (see the Agora large-object guidance).
_MAX_CURVE_POINTS = 60

# --------------------------------------------------------------------------
# Supporting-electrolyte profiles
# --------------------------------------------------------------------------
# The reference cell's bulk transport properties (viscosity, density, ionic
# conductivity) are dominated by the *supporting electrolyte*, not the active
# species. Rather than force a scientist to look these up per candidate, we
# offer a small menu of named regimes. Selecting one sets the anode-side
# ``AnodeElectrolyte{Viscosity,Density,Conductivity}`` and, because the viscosity
# also enters the Stokes-Einstein diffusivity estimate, shifts the estimated
# diffusivity accordingly.
#
# SCOPE: profiles currently set only the ANODE (negolyte) half-cell so the
# validated posolyte / membrane of the reference cell stay fixed — the whole
# point of the tool is "hold the cell constant, vary the anolyte". A shared
# supporting electrolyte physically also sets the cathode + membrane transport;
# extending profiles to those is a deliberate future decision.
#
# CONSISTENCY CAVEAT: ``dhps_koh`` mirrors the bundled reference-cell template,
# whose transport values describe the *active-loaded* DHPS/ferrocyanide
# electrolyte (hence it is more viscous/dense than a bare KOH support). The other
# profiles are single-salt *supporting-electrolyte* values at 25 C without active
# loading, so switching profiles approximates the change in bulk-transport regime
# rather than an exactly like-for-like electrolyte. All values are at ~25 C.
# Units: viscosity Pa.s, density kg/m^3, conductivity S/m.
#
# ``polymer_laden`` remains ``calibrated=False``: polymer/nanofluid transport is
# strongly system-specific, so it carries a representative (not validated) value
# and is flagged ``assumed_default`` in the provenance.
_ELECTROLYTE_PROFILES: dict[str, dict[str, Any]] = {
    "dhps_koh": {
        "label": "Alkaline DHPS reference electrolyte (active-loaded, validated cell)",
        "calibrated": True,
        "citation": "Bundled organic_dhps_ferrocyanide reference-cell template (validated)",
        "params": {
            _ANODE_VISCOSITY: 0.00436,
            _ANODE_DENSITY: 1391.0,
            _ANODE_CONDUCTIVITY: 21.0,
        },
    },
    "concentrated_koh": {
        "label": "Concentrated alkaline supporting electrolyte (30 wt% ~ 6.9 M KOH, 25 C)",
        "calibrated": True,
        "citation": (
            "density 1286 kg/m3 & viscosity 2.14 cP: CRC Handbook / KOH property tables, "
            "30 wt% 25 C; conductivity ~0.60 S/cm near-peak: Gilliam et al., Int. J. "
            "Hydrogen Energy 32 (2007) 359-364"
        ),
        "params": {
            _ANODE_VISCOSITY: 0.00214,
            _ANODE_DENSITY: 1286.0,
            _ANODE_CONDUCTIVITY: 60.0,
        },
    },
    "acidic_h2so4": {
        "label": "Concentrated acidic supporting electrolyte (25 wt% ~ 3 M H2SO4, 25 C)",
        "calibrated": True,
        "citation": (
            "density 1196 kg/m3: Engineering ToolBox / Perry's; viscosity 2.38 cP: "
            "Anton Paar sulfuric-acid viscosity table, 25 wt% 25 C; conductivity ~0.75 "
            "S/cm: H2SO4 conductivity tables (near-peak, 25 C)"
        ),
        "params": {
            _ANODE_VISCOSITY: 0.00238,
            _ANODE_DENSITY: 1196.0,
            _ANODE_CONDUCTIVITY: 75.0,
        },
    },
    "neutral_nacl": {
        "label": "Near-neutral supporting salt (1 M NaCl, 25 C)",
        "calibrated": True,
        "citation": (
            "density 1038 kg/m3 (1.0386 g/cm3) & viscosity 1.09 cP: CRC Handbook NaCl "
            "solution tables, 1 M 25 C; conductivity 8.6 S/m (85.8 mS/cm): standard "
            "1 M NaCl conductivity, 25 C"
        ),
        "params": {
            _ANODE_VISCOSITY: 0.00109,
            _ANODE_DENSITY: 1038.0,
            _ANODE_CONDUCTIVITY: 8.6,
        },
    },
    "polymer_laden": {
        "label": "Viscosified / polymer-thickened regime (~20 cP, representative stress test)",
        "calibrated": False,
        "citation": (
            "REPRESENTATIVE ONLY: viscosity 0.02 Pa.s (20 cP) as a heavily-thickened / "
            "polymer-laden regime, cf. Wei et al., J. Mater. Chem. A 1 (2013) 15208 "
            "(semi-solid slurries reach ~100-300 mPa.s); density/conductivity approximate. "
            "Value is deliberately capped: the reference cell's validated solver diverges "
            "above ~30 cP (active-species diffusivity falls below its convergence range), "
            "so true semi-solid slurries are out of scope for this cell model. Polymer/"
            "nanofluid transport is system-specific — treat as a high-viscosity stress "
            "test, not a validated electrolyte."
        ),
        "params": {
            _ANODE_VISCOSITY: 0.02,
            _ANODE_DENSITY: 1100.0,
            _ANODE_CONDUCTIVITY: 10.0,
        },
    },
}


def list_electrolyte_profiles() -> list[dict]:
    """Return the catalog of named supporting-electrolyte profiles.

    Each entry gives the profile ``name``, a human ``label``, whether it is
    ``calibrated`` against real literature data (all profiles except
    ``polymer_laden`` are), its ``citation`` (primary-source references for the
    calibrated profiles; a representative note for ``polymer_laden``) and the
    anode-electrolyte ``params`` it sets. Use a name as the ``electrolyte_profile``
    argument to :func:`simulate_negolyte` / :func:`negolyte_sensitivity`.
    """
    return [
        {
            "name": name,
            "label": spec["label"],
            "calibrated": spec["calibrated"],
            "citation": spec["citation"],
            "params": dict(spec["params"]),
        }
        for name, spec in _ELECTROLYTE_PROFILES.items()
    ]


@functools.lru_cache(maxsize=1)
def _load_template() -> dict:
    """Load the bundled reference-cell parameter template (205 params)."""
    text = resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_RESOURCE).read_text(encoding="utf-8")
    return json.loads(text)


def estimate_diffusivity_stokes_einstein(
    molar_mass_g_per_mol: float,
    viscosity_pa_s: float,
    temperature_k: float,
    density_kg_per_m3: float = _DEFAULT_ACTIVE_DENSITY,
) -> float:
    """Estimate an aqueous diffusion coefficient (m^2/s) via the Stokes-Einstein
    relation ``D = kT / (6 * pi * eta * r)``.

    The active molecule is modelled as a hard sphere whose volume follows from
    its molar mass and an assumed condensed-phase density, giving a hydrodynamic
    radius ``r = (3 V / 4 pi)**(1/3)`` with ``V = M / (rho * N_A)``.

    This is a deliberately simple, RDKit-free estimate: with a stick boundary
    condition and a bulk-density radius it tends to *under*estimate D for small
    molecules (e.g. ~1e-10 vs the ~5e-10 m^2/s fitted for DHPS), so treat it as a
    conservative lower bound and bracket the resulting cell KPIs with
    :func:`negolyte_sensitivity`.

    Args:
        molar_mass_g_per_mol: Molar mass of the active species (g/mol).
        viscosity_pa_s: Dynamic viscosity of the electrolyte (Pa.s).
        temperature_k: Absolute temperature (K).
        density_kg_per_m3: Assumed condensed-phase density of the species
            (kg/m^3); only sets the hydrodynamic radius.

    Returns:
        The estimated diffusion coefficient in m^2/s.
    """
    if not isinstance(molar_mass_g_per_mol, (int, float)) or isinstance(molar_mass_g_per_mol, bool):
        raise TypeError("molar_mass_g_per_mol must be a number (g/mol)")
    if molar_mass_g_per_mol <= 0:
        raise ValueError("molar_mass_g_per_mol must be positive")
    if viscosity_pa_s <= 0:
        raise ValueError("viscosity_pa_s must be positive")
    if temperature_k <= 0:
        raise ValueError("temperature_k must be positive")
    if density_kg_per_m3 <= 0:
        raise ValueError("density_kg_per_m3 must be positive")

    molar_mass_kg = molar_mass_g_per_mol / 1000.0
    volume_per_molecule = molar_mass_kg / (density_kg_per_m3 * _AVOGADRO)
    radius_m = (3.0 * volume_per_molecule / (4.0 * math.pi)) ** (1.0 / 3.0)
    return _BOLTZMANN * temperature_k / (6.0 * math.pi * viscosity_pa_s * radius_m)


def _descriptors_from_smiles(smiles: str) -> tuple[float, int]:
    """Return ``(molar_mass_g_per_mol, formal_charge)`` for a SMILES via RDKit.

    Both are exact, deterministic structural descriptors (not predictions), so
    deriving them here spares the caller a separate cross-server round-trip to
    the RDKit-native ``orfb`` server. Raises ``ValueError`` on an unparseable
    SMILES; ``ImportError`` if RDKit is not installed in the kernel.
    """
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"could not parse SMILES: {smiles!r}")
    return float(Descriptors.MolWt(mol)), int(Chem.GetFormalCharge(mol))


def _validate_overrides(overrides: Optional[dict]) -> dict:
    """Validate a raw parameter-override mapping, returning a clean copy."""
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise TypeError("overrides must be a dict of EZBattery parameter names to values")
    template = _load_template()
    clean: dict[str, Any] = {}
    for key, value in overrides.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("override keys must be non-empty parameter-name strings")
        if key not in template:
            raise ValueError(f"unknown EZBattery parameter: {key!r}")
        clean[key] = value
    return clean


def _downsample(values: list[float], max_points: int = _MAX_CURVE_POINTS) -> list[float]:
    """Evenly subsample *values* to at most *max_points* (keeps first and last)."""
    n = len(values)
    if n <= max_points:
        return [round(float(v), 6) for v in values]
    step = (n - 1) / (max_points - 1)
    idx = sorted({round(i * step) for i in range(max_points)} | {0, n - 1})
    return [round(float(values[i]), 6) for i in idx]


def _extract_kpis(result: dict) -> dict:
    """Reduce a raw ``RFB`` result to concise, JSON-friendly cell KPIs."""
    stats = result["Statistics"]
    potentials = result["Potentials"]

    cycles: list[dict] = []
    for _, row in stats.iterrows():
        ce = float(row["CE"])
        ee = float(row["EE"])
        cycles.append(
            {
                "cycle": int(row["Cycle"]),
                "coulombic_efficiency": round(ce, 4),
                "voltage_efficiency": round(ee / ce, 4) if ce else None,
                "energy_efficiency": round(ee, 4),
                "charge_energy_wh": round(float(row["Charge_energy_Wh"]), 6),
                "discharge_energy_wh": round(float(row["Discharge_energy_Wh"]), 6),
                "charge_time_s": round(float(row["Time_charge_s"]), 3),
                "discharge_time_s": round(float(row["Time_discharge_s"]), 3),
            }
        )

    last = cycles[-1] if cycles else {}
    first_discharge = cycles[0]["discharge_energy_wh"] if cycles else None
    last_discharge = last.get("discharge_energy_wh")
    capacity_fade_pct = None
    if first_discharge and last_discharge is not None and len(cycles) > 1:
        capacity_fade_pct = round((1.0 - last_discharge / first_discharge) * 100.0, 4)

    curve = {
        "time_s": _downsample(potentials["Time_s"].tolist()),
        "soc": _downsample(potentials["SOC"].tolist()),
        "cell_voltage_v": _downsample(potentials["Ec_V"].tolist()),
    }

    return {
        "num_cycles": len(cycles),
        "cycles": cycles,
        "final_cycle": last,
        "capacity_fade_pct": capacity_fade_pct,
        "voltage_curve": curve,
    }


def run_real_simulation(overrides: dict) -> dict:
    """Build a ``BatteryParameter`` from the template + overrides and run ``RFB``.

    Raises on environment/model problems.
    """
    from ezbattery_tools._vendor.EZBattery import RFB, BatteryParameter

    params = BatteryParameter(filepath=None)
    for key, value in _load_template().items():
        setattr(params, key, value)
    for key, value in overrides.items():
        setattr(params, key, value)

    result = RFB(params)
    if not isinstance(result, dict) or "Potentials" not in result:
        raise RuntimeError(
            "EZBattery's RFB solver did not converge to a valid result for these "
            "parameters (it returned a degenerate output). This usually means the "
            "electrolyte transport regime is outside the reference cell's validated "
            "range -- most often an active-species diffusivity that is too low "
            "(e.g. from an extreme electrolyte viscosity). Try a less viscous "
            "electrolyte_profile or a larger diffusivity."
        )
    return _extract_kpis(result)


def simulate_cell(overrides: Optional[dict] = None) -> dict:
    """Simulate the reference ORFB cell, optionally overriding template parameters.

    Args:
        overrides: Optional mapping of EZBattery parameter names (as found in the
            bundled ``organic_dhps_ferrocyanide`` template) to override values.

    Returns:
        Dict with the applied ``overrides`` and a ``kpis`` block (per-cycle
        efficiencies, charge/discharge energy & times, capacity fade, and a
        downsampled cell-voltage / SOC curve).
    """
    clean = _validate_overrides(overrides)
    kpis = run_real_simulation(clean)

    return {
        "cell": "organic_dhps_ferrocyanide",
        "overrides": clean,
        "kpis": kpis,
    }


def _build_negolyte_overrides(
    standard_potential: float,
    solubility_mol_per_L: Optional[float],
    electron_number: Optional[int],
    molar_mass: Optional[float],
    formal_charge: Optional[int],
    active_density_kg_per_m3: float,
    reaction_rate_constant: Optional[float],
    extra_overrides: Optional[dict],
    smiles: Optional[str] = None,
    electrolyte_profile: Optional[str] = None,
) -> tuple[dict, list[dict], dict]:
    """Validate negolyte inputs and assemble the EZBattery override set.

    Returns ``(overrides, provenance, meta)`` where *provenance* is a list of
    per-parameter records tagging each override as ``predicted`` (atomistic
    model), ``estimated`` (semi-empirical), ``literature`` (measured empirical
    profile) or ``assumed_default`` (untouched DHPS reference), and *meta*
    carries derived/echoed values (e.g. the estimated diffusivity and any
    reference-frame warnings).

    If *smiles* is given, molar mass and formal charge are computed from it via
    RDKit unless the caller passed explicit values, which take precedence.

    If *electrolyte_profile* names a known supporting-electrolyte regime, its
    anode-side viscosity / density / conductivity are applied (and the viscosity
    feeds the diffusivity estimate).
    """
    if electrolyte_profile is not None and electrolyte_profile not in _ELECTROLYTE_PROFILES:
        available = ", ".join(_ELECTROLYTE_PROFILES)
        raise ValueError(f"unknown electrolyte_profile {electrolyte_profile!r}; available: {available}")

    mw_from_smiles = False
    charge_from_smiles = False
    if smiles is not None:
        if not isinstance(smiles, str) or not smiles.strip():
            raise ValueError("smiles must be a non-empty string")
        derived_mw, derived_charge = _descriptors_from_smiles(smiles)
        if molar_mass is None:
            molar_mass = derived_mw
            mw_from_smiles = True
        if formal_charge is None:
            formal_charge = derived_charge
            charge_from_smiles = True

    if not isinstance(standard_potential, (int, float)) or isinstance(standard_potential, bool):
        raise TypeError("standard_potential must be a number (volts)")
    if solubility_mol_per_L is not None:
        if not isinstance(solubility_mol_per_L, (int, float)) or isinstance(solubility_mol_per_L, bool):
            raise ValueError("solubility_mol_per_L must be a number (mol/L)")
        if solubility_mol_per_L <= 0:
            raise ValueError("solubility_mol_per_L must be positive")
    if electron_number is not None and (
        not isinstance(electron_number, int) or isinstance(electron_number, bool) or electron_number < 1
    ):
        raise ValueError("electron_number must be a positive integer")
    if molar_mass is not None:
        if not isinstance(molar_mass, (int, float)) or isinstance(molar_mass, bool):
            raise ValueError("molar_mass must be a number (g/mol)")
        if molar_mass <= 0:
            raise ValueError("molar_mass must be positive")
    if formal_charge is not None and (not isinstance(formal_charge, int) or isinstance(formal_charge, bool)):
        raise ValueError("formal_charge must be an integer")
    if reaction_rate_constant is not None:
        if not isinstance(reaction_rate_constant, (int, float)) or isinstance(reaction_rate_constant, bool):
            raise ValueError("reaction_rate_constant must be a number (m/s)")
        if reaction_rate_constant <= 0:
            raise ValueError("reaction_rate_constant must be positive")

    template = _load_template()
    overrides: dict[str, Any] = {}
    provenance: list[dict] = []
    meta: dict[str, Any] = {"warnings": []}

    def _record(param: str, value: Any, source: str, basis: str) -> None:
        overrides[param] = value
        provenance.append({"parameter": param, "value": value, "source": source, "basis": basis})

    if electrolyte_profile is not None:
        spec = _ELECTROLYTE_PROFILES[electrolyte_profile]
        source = "literature" if spec["calibrated"] else "assumed_default"
        calib_note = "" if spec["calibrated"] else " [PLACEHOLDER, not yet calibrated]"
        for param, value in spec["params"].items():
            _record(
                param,
                float(value),
                source,
                f"'{electrolyte_profile}' supporting-electrolyte profile "
                f"({spec['label']}); {spec['citation']}{calib_note}",
            )
    meta["electrolyte_profile"] = electrolyte_profile

    _record(
        _ANODE_STANDARD_POTENTIAL,
        float(standard_potential),
        "predicted",
        "reduction standard potential from the redox predictor (graphormer)",
    )
    # Negolytes sit negative of the posolyte; a positive value usually signals a
    # sign / reference-frame mismatch (the cell template is on the SHE scale).
    if standard_potential > 0.2:
        meta["warnings"].append(
            f"standard_potential={standard_potential} V is unusually positive for a "
            "negolyte on the SHE scale used by the reference cell; confirm the sign "
            "convention and reference frame of the redox predictor."
        )

    if solubility_mol_per_L is not None:
        _record(
            _ANODE_CONCENTRATION,
            float(solubility_mol_per_L) * 1000.0,
            "predicted",
            "aqueous solubility (mol/L) from the solubility predictor (soltrannet), x1000 -> mol/m^3",
        )
    if electron_number is not None:
        _record(
            _ANODE_ELECTRON_NUMBER,
            int(electron_number),
            "predicted",
            "electrons transferred per molecule",
        )

    estimated_diffusivity: Optional[float] = None
    if molar_mass is not None:
        viscosity = float(overrides.get(_ANODE_VISCOSITY, template[_ANODE_VISCOSITY]))
        temperature = float(template[_TEMPERATURE])
        estimated_diffusivity = estimate_diffusivity_stokes_einstein(
            molar_mass, viscosity, temperature, active_density_kg_per_m3
        )
        mw_origin = "SMILES-derived" if mw_from_smiles else "supplied"
        basis = (
            f"Stokes-Einstein estimate from {mw_origin} molar_mass={molar_mass:g} g/mol, "
            f"density={active_density_kg_per_m3} kg/m^3, viscosity={viscosity} Pa.s, T={temperature} K"
        )
        _record(_ANODE_OXIDANT_DIFFUSIVITY, estimated_diffusivity, "estimated", basis)
        _record(_ANODE_REDUCTANT_DIFFUSIVITY, estimated_diffusivity, "estimated", basis)
        mw_basis = (
            f"exact molar mass ({mw_origin.lower()}); the cell physics does not read this "
            "field directly, but it is set for template self-consistency and feeds the "
            "diffusivity estimate above"
        )
        _record(_ANODE_OXIDANT_MOLAR_MASS, float(molar_mass), "user", mw_basis)
        _record(_ANODE_REDUCTANT_MOLAR_MASS, float(molar_mass), "user", mw_basis)
    else:
        provenance.append(
            {
                "parameter": _ANODE_OXIDANT_DIFFUSIVITY,
                "value": template[_ANODE_OXIDANT_DIFFUSIVITY],
                "source": "assumed_default",
                "basis": "DHPS reference diffusivity (pass smiles or molar_mass to estimate it)",
            }
        )

    if formal_charge is not None:
        charge_origin = "SMILES-derived" if charge_from_smiles else "supplied"
        _record(
            _ANODE_OXIDANT_VALENCE,
            int(formal_charge),
            "estimated",
            f"oxidized-form charge from the molecule's {charge_origin} formal charge "
            "(affects membrane crossover / Donnan)",
        )
        if electron_number is not None:
            _record(
                _ANODE_REDUCTANT_VALENCE,
                int(formal_charge) - int(electron_number),
                "estimated",
                "reduced-form charge = formal_charge - electron_number (reduction adds electrons)",
            )

    if reaction_rate_constant is not None:
        _record(
            _ANODE_RATE_CONSTANT,
            float(reaction_rate_constant),
            "predicted",
            "user-supplied electrochemical rate constant (m/s)",
        )
    else:
        provenance.append(
            {
                "parameter": _ANODE_RATE_CONSTANT,
                "value": template[_ANODE_RATE_CONSTANT],
                "source": "assumed_default",
                "basis": "DHPS reference kinetics (no per-molecule kinetics model yet)",
            }
        )

    if extra_overrides:
        for key, value in _validate_overrides(extra_overrides).items():
            _record(key, value, "user", "explicit extra_overrides")

    meta["estimated_diffusivity_m2_per_s"] = estimated_diffusivity
    meta["molar_mass_g_per_mol"] = molar_mass
    meta["formal_charge"] = formal_charge

    # Soft envelope check: flag runs that sit near the cell solver's convergence
    # edge so the caller doesn't have to rediscover it (a run past the edge fails
    # with the clear error raised in run_real_simulation).
    effective_viscosity = float(overrides.get(_ANODE_VISCOSITY, template[_ANODE_VISCOSITY]))
    if effective_viscosity > _SOLVER_MAX_VISCOSITY:
        meta["warnings"].append(
            f"anode electrolyte viscosity {effective_viscosity} Pa.s exceeds the reference "
            f"cell's validated range (~{_SOLVER_MAX_VISCOSITY} Pa.s / 30 cP); the RFB solver "
            "may not converge and the simulation could fail."
        )
    if estimated_diffusivity is not None and estimated_diffusivity < _SOLVER_MIN_DIFFUSIVITY:
        meta["warnings"].append(
            f"estimated active-species diffusivity {estimated_diffusivity:.2e} m^2/s is below "
            f"the reference cell's validated range (~{_SOLVER_MIN_DIFFUSIVITY:.0e} m^2/s); the "
            "RFB solver may not converge and the simulation could fail."
        )

    meta["molar_mass_from_smiles"] = mw_from_smiles
    meta["formal_charge_from_smiles"] = charge_from_smiles
    return overrides, provenance, meta


def simulate_negolyte(
    standard_potential: float,
    solubility_mol_per_L: Optional[float] = None,
    electron_number: Optional[int] = None,
    name: Optional[str] = None,
    smiles: Optional[str] = None,
    molar_mass: Optional[float] = None,
    formal_charge: Optional[int] = None,
    active_density_kg_per_m3: float = _DEFAULT_ACTIVE_DENSITY,
    reaction_rate_constant: Optional[float] = None,
    electrolyte_profile: Optional[str] = None,
    extra_overrides: Optional[dict] = None,
) -> dict:
    """Evaluate a candidate **negolyte** (anode-side species) at the device level.

    Maps molecule-level predictions (from the graphormer / soltrannet / RDKit
    servers) onto the anode parameters of the validated organic
    DHPS–ferrocyanide reference cell, then runs a full charge/discharge
    simulation and reports the resulting cell KPIs.

    Args:
        standard_potential: Reduction standard potential of the negolyte redox
            couple, in volts, on the same reference (SHE) as the cell's posolyte
            (ferro/ferricyanide). Maps to ``AnodeStandardPotential``. A more
            negative value widens the cell voltage window.
        solubility_mol_per_L: Aqueous solubility of the active species in mol/L
            (e.g. ``10**logS`` from soltrannet). Maps to
            ``AnodeOxidant1InitialConcentrationInAnode`` (x1000 -> mol/m^3);
            higher solubility raises accessible capacity / energy density.
        electron_number: Electrons transferred per molecule (e.g. 2 for a
            two-electron negolyte). Maps to ``AnodeElectronNumber``.
        name: Optional label for the candidate, echoed back in the result.
        smiles: SMILES of the active species. When given, its molar mass and
            formal charge are computed automatically via RDKit (deterministic
            structural descriptors), so you normally don't pass ``molar_mass`` /
            ``formal_charge`` by hand. Explicit values still take precedence.
        molar_mass: Molar mass of the active species (g/mol). Usually derived
            from ``smiles``; pass explicitly only to override. Used to estimate
            the bulk diffusivity (``Anode{Oxidant,Reductant}1Diffusivity``) via
            Stokes-Einstein; the cell model does not consume molar mass directly.
        formal_charge: Net formal charge of the (oxidized) active species.
            Usually derived from ``smiles``; sets the oxidant/reductant valences
            (affects membrane crossover / Donnan).
        active_density_kg_per_m3: Assumed condensed-phase density used only for
            the diffusivity estimate (defaults to ~1400 kg/m^3).
        reaction_rate_constant: Optional electrochemical rate constant (m/s) for
            ``AnodeReactionRateConstant``; left at the DHPS default if omitted.
        electrolyte_profile: Optional name of a supporting-electrolyte regime
            (see :func:`list_electrolyte_profiles`) setting the anode-side
            viscosity / density / conductivity (viscosity also feeds the
            diffusivity estimate). NOTE: only ``dhps_koh`` is calibrated today;
            the others are placeholders pending literature sourcing and are
            flagged ``assumed_default`` in the provenance.
        extra_overrides: Optional additional EZBattery parameter overrides
            (validated against the template) for advanced use.

    Returns:
        The :func:`simulate_cell` result dict, plus a ``negolyte`` block echoing
        the interpreted inputs and the anode parameters they set, and a
        ``parameter_provenance`` list tagging each override as ``predicted`` /
        ``estimated`` / ``literature`` / ``assumed_default`` / ``user`` so KPIs
        carry an honest confidence signal.
    """
    overrides, provenance, meta = _build_negolyte_overrides(
        standard_potential,
        solubility_mol_per_L,
        electron_number,
        molar_mass,
        formal_charge,
        active_density_kg_per_m3,
        reaction_rate_constant,
        extra_overrides,
        smiles=smiles,
        electrolyte_profile=electrolyte_profile,
    )

    result = simulate_cell(overrides)
    result["negolyte"] = {
        "name": name,
        "smiles": smiles,
        "standard_potential_v": float(standard_potential),
        "solubility_mol_per_L": solubility_mol_per_L,
        "electron_number": electron_number,
        "molar_mass_g_per_mol": meta["molar_mass_g_per_mol"],
        "formal_charge": meta["formal_charge"],
        "estimated_diffusivity_m2_per_s": meta["estimated_diffusivity_m2_per_s"],
        "electrolyte_profile": electrolyte_profile,
        "anode_parameters": dict(overrides),
    }
    result["parameter_provenance"] = provenance
    result["warnings"] = meta["warnings"]
    return result


def negolyte_sensitivity(
    standard_potential: float,
    solubility_mol_per_L: Optional[float] = None,
    electron_number: Optional[int] = None,
    name: Optional[str] = None,
    smiles: Optional[str] = None,
    molar_mass: Optional[float] = None,
    formal_charge: Optional[int] = None,
    active_density_kg_per_m3: float = _DEFAULT_ACTIVE_DENSITY,
    reaction_rate_constant: Optional[float] = None,
    electrolyte_profile: Optional[str] = None,
    diffusivity_factors: tuple = (0.3, 1.0, 3.0),
    rate_constant_factors: tuple = (0.1, 1.0, 10.0),
    extra_overrides: Optional[dict] = None,
) -> dict:
    """Bracket the headline cell KPIs over the two most uncertain physical inputs.

    Bulk diffusivity and the kinetic rate constant are the parameters least
    constrained by the current atomistic predictors, so this sweeps them over
    multiplicative factors around the baseline negolyte mapping and reports the
    resulting spread — letting a design campaign rank candidates *with* error
    bars rather than trusting a single point estimate.

    Args:
        standard_potential .. electrolyte_profile: As in
            :func:`simulate_negolyte` — define the baseline mapping (``smiles``
            auto-derives molar mass and formal charge; ``electrolyte_profile``
            selects the supporting-electrolyte regime).
        diffusivity_factors: Multipliers applied to the baseline anode
            diffusivity (oxidant & reductant together).
        rate_constant_factors: Multipliers applied to the baseline anode
            reaction rate constant.
        extra_overrides: Optional additional EZBattery parameter overrides.

    Returns:
        Dict with the ``baseline`` KPIs, per-KPI ``ranges`` (min / max / span)
        over the grid, and the compact ``grid`` of (diffusivity_factor,
        rate_constant_factor) -> headline KPIs. No voltage curves are returned.
    """
    for factors, label in (
        (diffusivity_factors, "diffusivity_factors"),
        (rate_constant_factors, "rate_constant_factors"),
    ):
        if not factors or any((not isinstance(f, (int, float)) or isinstance(f, bool) or f <= 0) for f in factors):
            raise ValueError(f"{label} must be a non-empty sequence of positive numbers")

    base_overrides, _, meta = _build_negolyte_overrides(
        standard_potential,
        solubility_mol_per_L,
        electron_number,
        molar_mass,
        formal_charge,
        active_density_kg_per_m3,
        reaction_rate_constant,
        extra_overrides,
        smiles=smiles,
        electrolyte_profile=electrolyte_profile,
    )
    template = _load_template()
    base_diffusivity = base_overrides.get(_ANODE_OXIDANT_DIFFUSIVITY, template[_ANODE_OXIDANT_DIFFUSIVITY])
    base_rate = base_overrides.get(_ANODE_RATE_CONSTANT, template[_ANODE_RATE_CONSTANT])

    _headline_keys = ("coulombic_efficiency", "voltage_efficiency", "energy_efficiency", "discharge_energy_wh")

    def _headline(overrides: dict) -> dict:
        fc = simulate_cell(overrides)["kpis"]["final_cycle"]
        return {k: fc.get(k) for k in _headline_keys}

    baseline = _headline(base_overrides)

    grid: list[dict] = []
    accum: dict[str, list[float]] = {k: [] for k in _headline_keys}
    for df in diffusivity_factors:
        for kf in rate_constant_factors:
            overrides = dict(base_overrides)
            overrides[_ANODE_OXIDANT_DIFFUSIVITY] = base_diffusivity * df
            overrides[_ANODE_REDUCTANT_DIFFUSIVITY] = base_diffusivity * df
            overrides[_ANODE_RATE_CONSTANT] = base_rate * kf
            kpis = _headline(overrides)
            grid.append({"diffusivity_factor": df, "rate_constant_factor": kf, "kpis": kpis})
            for k, v in kpis.items():
                if isinstance(v, (int, float)):
                    accum[k].append(float(v))

    ranges = {}
    for k, values in accum.items():
        if values:
            lo, hi = min(values), max(values)
            ranges[k] = {"min": round(lo, 6), "max": round(hi, 6), "span": round(hi - lo, 6)}

    return {
        "cell": "organic_dhps_ferrocyanide",
        "name": name,
        "smiles": smiles,
        "electrolyte_profile": electrolyte_profile,
        "baseline": baseline,
        "baseline_diffusivity_m2_per_s": base_diffusivity,
        "baseline_rate_constant_m_per_s": base_rate,
        "ranges": ranges,
        "grid": grid,
        "warnings": meta["warnings"],
    }
