# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Negolyte device-level evaluation for the ezbattery server.

Thin wrappers over the in-kernel EZBattery model (``_model``). Map molecule-level
predictions (reduction potential, solubility, electron count, and — to bridge the
remaining physicochemical gap — molar mass, formal charge and optional kinetics)
onto the anode of a validated organic DHPS–ferrocyanide reference cell and return
the resulting cell KPIs with per-parameter provenance.
"""

from __future__ import annotations

from typing import Optional

from orfb_provenance import attach_provenance

from ezbattery_tools import _model
from ezbattery_tools._provenance import upstream_model_metadata

_DEFAULT_ACTIVE_DENSITY = _model._DEFAULT_ACTIVE_DENSITY


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
    """Evaluate a candidate negolyte (anode-side species) at the device level.

    Args:
        standard_potential: Reduction standard potential of the negolyte redox
            couple in volts, on the same reference (SHE) as the cell's
            ferro/ferricyanide posolyte. Maps to ``AnodeStandardPotential``.
        solubility_mol_per_L: Aqueous solubility of the active species in mol/L
            (e.g. ``10**logS`` from soltrannet). Maps to the anode initial
            concentration (x1000 -> mol/m^3).
        electron_number: Electrons transferred per molecule. Maps to
            ``AnodeElectronNumber``.
        name: Optional label for the candidate, echoed back in the result.
        smiles: SMILES of the active species. When given, molar mass and formal
            charge are computed from it via RDKit (deterministic descriptors), so
            you normally don't pass them by hand; explicit values still win.
        molar_mass: Molar mass (g/mol). Usually derived from ``smiles``; pass
            explicitly only to override. Used to estimate bulk diffusivity via
            Stokes-Einstein.
        formal_charge: Net formal charge of the oxidized species. Usually derived
            from ``smiles``; sets the oxidant/reductant valences (affects membrane
            crossover / Donnan).
        active_density_kg_per_m3: Assumed density used only for the diffusivity
            estimate (defaults to ~1400 kg/m^3).
        reaction_rate_constant: Optional electrochemical rate constant (m/s);
            left at the DHPS default if omitted.
        electrolyte_profile: Optional supporting-electrolyte regime name (see
            ``list_electrolyte_profiles``) setting the anode viscosity / density /
            conductivity. Only ``dhps_koh`` is calibrated today; the rest are
            placeholders pending literature sourcing (flagged in the provenance).
        extra_overrides: Optional additional EZBattery parameter overrides.

    Returns:
        The :func:`ezbattery_tools.cell.simulate_cell` result dict plus a
        ``negolyte`` block, a ``parameter_provenance`` list tagging each override
        ``predicted`` / ``estimated`` / ``literature`` / ``assumed_default`` /
        ``user``, any ``warnings`` (e.g. reference-frame sanity checks), and a
        structured ``provenance`` envelope.
    """
    result = _model.simulate_negolyte(
        standard_potential=standard_potential,
        solubility_mol_per_L=solubility_mol_per_L,
        electron_number=electron_number,
        name=name,
        smiles=smiles,
        molar_mass=molar_mass,
        formal_charge=formal_charge,
        active_density_kg_per_m3=active_density_kg_per_m3,
        reaction_rate_constant=reaction_rate_constant,
        electrolyte_profile=electrolyte_profile,
        extra_overrides=extra_overrides,
    )
    return attach_provenance(
        result,
        tool_distribution="ezbattery-tools",
        tool_version_fallback="0.1.0",
        model=upstream_model_metadata(),
        applicability="qualified_by_parameter_provenance",
        uncertainty="not_quantified",
    )


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
    """Bracket a negolyte's headline cell KPIs over its most uncertain inputs.

    Sweeps the bulk diffusivity and the kinetic rate constant — the parameters
    least constrained by the current atomistic predictors — over multiplicative
    factors around the baseline negolyte mapping, so candidates can be ranked
    with error bars rather than a single point estimate.

    Args:
        standard_potential .. electrolyte_profile: As in
            :func:`simulate_negolyte`; define the baseline mapping (``smiles``
            auto-derives molar mass and formal charge; ``electrolyte_profile``
            selects the supporting-electrolyte regime).
        diffusivity_factors: Multipliers on the baseline anode diffusivity.
        rate_constant_factors: Multipliers on the baseline anode rate constant.
        extra_overrides: Optional additional EZBattery parameter overrides.

    Returns:
        Dict with ``baseline`` KPIs, per-KPI ``ranges`` (min/max/span) and a
        compact ``grid`` of (diffusivity_factor, rate_constant_factor) -> KPIs,
        plus a structured ``provenance`` envelope.
    """
    result = _model.negolyte_sensitivity(
        standard_potential=standard_potential,
        solubility_mol_per_L=solubility_mol_per_L,
        electron_number=electron_number,
        name=name,
        smiles=smiles,
        molar_mass=molar_mass,
        formal_charge=formal_charge,
        active_density_kg_per_m3=active_density_kg_per_m3,
        reaction_rate_constant=reaction_rate_constant,
        electrolyte_profile=electrolyte_profile,
        diffusivity_factors=diffusivity_factors,
        rate_constant_factors=rate_constant_factors,
        extra_overrides=extra_overrides,
    )
    return attach_provenance(
        result,
        tool_distribution="ezbattery-tools",
        tool_version_fallback="0.1.0",
        model=upstream_model_metadata(),
        applicability="qualified_by_parameter_provenance",
        uncertainty="sensitivity_analysis_only",
    )


def list_electrolyte_profiles() -> list[dict]:
    """List the named supporting-electrolyte profiles available for the negolyte tools.

    Each entry gives the profile ``name`` (pass as ``electrolyte_profile`` to
    ``simulate_negolyte`` / ``negolyte_sensitivity``), a human ``label``, whether
    it is ``calibrated`` against real data (only ``dhps_koh`` currently is), its
    ``citation`` (a TODO stub for the placeholder profiles), and the anode
    viscosity / density / conductivity ``params`` it sets.

    Returns:
        A list of profile-description dicts.
    """
    return _model.list_electrolyte_profiles()
