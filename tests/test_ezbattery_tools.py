# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Tests for the ezbattery cell-simulation tools.

The pinned EZBattery source staged by scripts/fetch_ezbattery_source.sh is pure
Python (numpy / scipy / pandas / openpyxl / ismember), so these run real cell
simulations. The numeric stack is provided by the ``test`` optional-dependency
group (see the root ``pyproject.toml``).
"""

from importlib.resources import files
from pathlib import Path

import pytest
from ezbattery_tools._model import _build_negolyte_overrides, estimate_diffusivity_stokes_einstein
from ezbattery_tools.cell import simulate_cell
from ezbattery_tools.negolyte import (
    list_electrolyte_profiles,
    negolyte_sensitivity,
    simulate_negolyte,
)

_ROOT = Path(__file__).resolve().parent.parent


def test_upstream_source_provenance():
    package = files("ezbattery_tools._vendor.EZBattery")
    expected_commit = (_ROOT / "servers" / "ezbattery" / "EZBattery.COMMIT").read_text().strip()
    assert package.joinpath("UPSTREAM_COMMIT").read_text().strip() == expected_commit
    assert "Simplified BSD" in package.joinpath("LICENSE").read_text()


def test_simulate_cell_real():
    result = simulate_cell()
    expected_commit = (_ROOT / "servers" / "ezbattery" / "EZBattery.COMMIT").read_text().strip()
    assert result["cell"] == "organic_dhps_ferrocyanide"
    assert result["overrides"] == {}
    assert "mode" not in result
    kpis = result["kpis"]
    assert kpis["num_cycles"] >= 1
    fc = kpis["final_cycle"]
    for key in (
        "coulombic_efficiency",
        "voltage_efficiency",
        "energy_efficiency",
        "charge_energy_wh",
        "discharge_energy_wh",
    ):
        assert isinstance(fc[key], float)
    assert 0.0 < fc["coulombic_efficiency"] <= 1.0
    assert 0.0 < fc["energy_efficiency"] <= 1.0
    assert result["provenance"]["model_version"] == expected_commit


def test_simulate_cell_deterministic():
    a = simulate_cell({"AnodeStandardPotential": -1.1})
    b = simulate_cell({"AnodeStandardPotential": -1.1})
    assert a["kpis"] == b["kpis"]
    assert a["overrides"] == {"AnodeStandardPotential": -1.1}


def test_simulate_cell_unknown_parameter_rejected():
    with pytest.raises(ValueError):
        simulate_cell({"NotARealParameter": 1.0})


def test_simulate_cell_non_dict_overrides_rejected():
    with pytest.raises(TypeError):
        simulate_cell(overrides=[1, 2, 3])


def test_simulate_negolyte_real():
    result = simulate_negolyte(standard_potential=-1.05, solubility_mol_per_L=1.0, electron_number=2, name="cand-A")
    assert "mode" not in result
    assert result["kpis"]["num_cycles"] >= 1
    neg = result["negolyte"]
    assert neg["name"] == "cand-A"
    assert neg["standard_potential_v"] == -1.05
    assert neg["anode_parameters"]["AnodeStandardPotential"] == -1.05
    # solubility mol/L -> mol/m^3
    assert neg["anode_parameters"]["AnodeOxidant1InitialConcentrationInAnode"] == 1000.0
    assert neg["anode_parameters"]["AnodeElectronNumber"] == 2


def test_simulate_negolyte_minimal():
    result = simulate_negolyte(standard_potential=-0.9)
    assert result["overrides"] == {"AnodeStandardPotential": -0.9}
    assert result["negolyte"]["solubility_mol_per_L"] is None


def test_simulate_negolyte_bad_potential():
    with pytest.raises(TypeError):
        simulate_negolyte(standard_potential="not-a-number")


def test_simulate_negolyte_bad_electron_number():
    with pytest.raises(ValueError):
        simulate_negolyte(standard_potential=-1.0, electron_number=0)


def test_simulate_negolyte_bad_solubility():
    with pytest.raises(ValueError):
        simulate_negolyte(standard_potential=-1.0, solubility_mol_per_L=-1.0)


def test_estimate_diffusivity_order_of_magnitude():
    # DHPS-like molecule should land near the ~1e-10 m^2/s scale of aqueous
    # organic active species (conservative vs the ~5e-10 fitted value).
    d = estimate_diffusivity_stokes_einstein(302.0, 0.00436, 298.0)
    assert 1e-11 < d < 1e-9
    # Heavier molecules diffuse more slowly.
    assert estimate_diffusivity_stokes_einstein(600.0, 0.00436, 298.0) < d


def test_estimate_diffusivity_bad_inputs():
    with pytest.raises(ValueError):
        estimate_diffusivity_stokes_einstein(-1.0, 0.00436, 298.0)
    with pytest.raises(ValueError):
        estimate_diffusivity_stokes_einstein(300.0, 0.0, 298.0)


def test_simulate_negolyte_bridge_provenance():
    result = simulate_negolyte(
        standard_potential=-0.95,
        solubility_mol_per_L=1.0,
        electron_number=2,
        molar_mass=250.0,
        formal_charge=-2,
        name="cand-B",
    )
    prov = {p["parameter"]: p for p in result["parameter_provenance"]}
    # Molar mass drives a diffusivity estimate for both redox forms.
    assert prov["AnodeOxidant1Diffusivity"]["source"] == "estimated"
    assert prov["AnodeReductant1Diffusivity"]["source"] == "estimated"
    assert result["negolyte"]["estimated_diffusivity_m2_per_s"] > 0
    # Molar mass is written through to the template's MolarMass fields.
    assert result["overrides"]["AnodeOxidant1MolarMass"] == 250.0
    assert result["overrides"]["AnodeReductant1MolarMass"] == 250.0
    assert prov["AnodeOxidant1MolarMass"]["source"] == "user"
    assert result["overrides"]["AnodeOxidant1Diffusivity"] == result["negolyte"]["estimated_diffusivity_m2_per_s"]
    # E° / solubility / electrons are model-predicted.
    assert prov["AnodeStandardPotential"]["source"] == "predicted"
    # Reduced-form valence = formal_charge - electron_number.
    assert prov["AnodeReductant1Valence"]["value"] == -4
    # Kinetics untouched -> flagged as an assumption.
    assert prov["AnodeReactionRateConstant"]["source"] == "assumed_default"
    assert result["provenance"]["applicability"] == "qualified_by_parameter_provenance"


def test_simulate_negolyte_reference_frame_warning():
    # Positive potential is implausible for a negolyte on the SHE frame.
    result = simulate_negolyte(standard_potential=0.5)
    assert any("reference frame" in w for w in result["warnings"])
    # A sensible negolyte potential produces no such warning.
    assert simulate_negolyte(standard_potential=-0.9)["warnings"] == []


def test_simulate_negolyte_smiles_autoderives_descriptors():
    # DHPS-like neutral species: molar mass derived, formal charge 0.
    result = simulate_negolyte(
        standard_potential=-0.95,
        solubility_mol_per_L=1.0,
        electron_number=2,
        smiles="CCO",
        name="cand-smiles",
    )
    neg = result["negolyte"]
    assert neg["smiles"] == "CCO"
    # RDKit MolWt for ethanol ~46.07 g/mol.
    assert 45.0 < neg["molar_mass_g_per_mol"] < 47.0
    assert neg["formal_charge"] == 0
    prov = {p["parameter"]: p for p in result["parameter_provenance"]}
    assert "SMILES-derived" in prov["AnodeOxidant1Diffusivity"]["basis"]


def test_simulate_negolyte_smiles_charge():
    # Carboxylate carries a formal charge of -1.
    result = simulate_negolyte(standard_potential=-0.9, smiles="CC(=O)[O-]")
    assert result["negolyte"]["formal_charge"] == -1


def test_list_electrolyte_profiles():
    profiles = {p["name"]: p for p in list_electrolyte_profiles()}
    assert "dhps_koh" in profiles
    # dhps_koh mirrors the calibrated reference-cell template.
    assert profiles["dhps_koh"]["calibrated"] is True
    # Single-salt supporting-electrolyte regimes are now literature-calibrated.
    assert profiles["concentrated_koh"]["calibrated"] is True
    # The polymer/nanofluid regime stays representative (system-specific).
    assert profiles["polymer_laden"]["calibrated"] is False
    assert "AnodeElectrolyteViscosity" in profiles["dhps_koh"]["params"]


def test_simulate_negolyte_electrolyte_profile():
    result = simulate_negolyte(
        standard_potential=-0.95,
        solubility_mol_per_L=1.0,
        electron_number=2,
        smiles="CCO",
        electrolyte_profile="concentrated_koh",
    )
    o = result["overrides"]
    assert o["AnodeElectrolyteViscosity"] == 0.00214
    assert o["AnodeElectrolyteConductivity"] == 60.0
    assert result["negolyte"]["electrolyte_profile"] == "concentrated_koh"
    prov = {p["parameter"]: p for p in result["parameter_provenance"]}
    # Calibrated profile is tagged literature and cites a source.
    assert prov["AnodeElectrolyteViscosity"]["source"] == "literature"
    assert "Gilliam" in prov["AnodeElectrolyteConductivity"]["basis"]


def test_placeholder_profile_flagged():
    # The representative polymer regime must stay honestly flagged.
    result = simulate_negolyte(
        standard_potential=-0.95,
        smiles="CCO",
        electrolyte_profile="polymer_laden",
    )
    prov = {p["parameter"]: p for p in result["parameter_provenance"]}
    assert prov["AnodeElectrolyteViscosity"]["source"] == "assumed_default"
    assert "PLACEHOLDER" in prov["AnodeElectrolyteViscosity"]["basis"]


def test_electrolyte_profile_shifts_diffusivity():
    # Higher-viscosity profile lowers the Stokes-Einstein diffusivity estimate.
    base = simulate_negolyte(standard_potential=-0.95, smiles="CCO")
    thick = simulate_negolyte(
        standard_potential=-0.95,
        smiles="CCO",
        electrolyte_profile="polymer_laden",
    )
    assert thick["negolyte"]["estimated_diffusivity_m2_per_s"] < base["negolyte"]["estimated_diffusivity_m2_per_s"]


def test_simulate_negolyte_bad_electrolyte_profile():
    with pytest.raises(ValueError):
        simulate_negolyte(standard_potential=-0.9, electrolyte_profile="nonexistent")


def test_simulate_negolyte_explicit_overrides_smiles():
    # Explicit molar_mass / formal_charge win over the SMILES-derived values.
    result = simulate_negolyte(
        standard_potential=-0.95,
        electron_number=2,
        smiles="CCO",
        molar_mass=250.0,
        formal_charge=-2,
    )
    neg = result["negolyte"]
    assert neg["molar_mass_g_per_mol"] == 250.0
    assert neg["formal_charge"] == -2
    prov = {p["parameter"]: p for p in result["parameter_provenance"]}
    # Origin flagged as supplied, not SMILES-derived.
    assert "supplied" in prov["AnodeOxidant1Diffusivity"]["basis"]


def test_nonconvergent_overrides_raise_clear_error():
    # An extreme (too-low) active-species diffusivity pushes EZBattery's solver
    # out of its validated range; it returns a degenerate result. We must surface
    # a clear RuntimeError rather than a cryptic TypeError.
    with pytest.raises(RuntimeError, match="did not converge"):
        simulate_cell(
            overrides={
                "AnodeOxidant1Diffusivity": 1e-13,
                "AnodeReductant1Diffusivity": 1e-13,
            }
        )


def test_high_viscosity_warns_near_solver_edge():
    # A viscosity above the validated envelope should be flagged before running.
    _, _, meta = _build_negolyte_overrides(
        -0.95,
        None,
        None,
        150.0,
        None,
        1400.0,
        None,
        {"AnodeElectrolyteViscosity": 0.05},
        smiles=None,
    )
    assert any("viscosity" in w and "validated range" in w for w in meta["warnings"])


def test_low_diffusivity_warns_near_solver_edge():
    # A heavy molecule in a viscous electrolyte drives the estimated diffusivity
    # below the solver's validated range and should be flagged.
    _, _, meta = _build_negolyte_overrides(
        -0.95,
        None,
        None,
        800.0,
        None,
        1400.0,
        None,
        None,
        smiles=None,
        electrolyte_profile="polymer_laden",
    )
    assert any("diffusivity" in w and "validated range" in w for w in meta["warnings"])


def test_no_envelope_warning_for_normal_run():
    # A benign small molecule at reference viscosity must not warn.
    result = simulate_negolyte(standard_potential=-0.95, smiles="CCO")
    assert not any("validated range" in w for w in result["warnings"])


def test_simulate_negolyte_bad_smiles():
    with pytest.raises(ValueError):
        simulate_negolyte(standard_potential=-0.9, smiles="not a molecule")
    with pytest.raises(ValueError):
        simulate_negolyte(standard_potential=-0.9, smiles="   ")


def test_negolyte_sensitivity_smiles():
    result = negolyte_sensitivity(
        standard_potential=-0.95,
        solubility_mol_per_L=1.0,
        electron_number=2,
        smiles="CCO",
        diffusivity_factors=(0.5, 1.0, 2.0),
        rate_constant_factors=(1.0,),
    )
    assert result["smiles"] == "CCO"
    assert result["baseline_diffusivity_m2_per_s"] > 0


def test_negolyte_sensitivity_spread():
    result = negolyte_sensitivity(
        standard_potential=-0.95,
        solubility_mol_per_L=1.0,
        electron_number=2,
        molar_mass=250.0,
        name="cand-C",
        diffusivity_factors=(0.5, 1.0, 2.0),
        rate_constant_factors=(1.0,),
    )
    assert len(result["grid"]) == 3
    ee = result["ranges"]["energy_efficiency"]
    assert ee["min"] <= result["baseline"]["energy_efficiency"] <= ee["max"]
    assert ee["span"] >= 0.0
    assert result["baseline_diffusivity_m2_per_s"] > 0


def test_negolyte_sensitivity_bad_factors():
    with pytest.raises(ValueError):
        negolyte_sensitivity(standard_potential=-0.9, diffusivity_factors=())
    with pytest.raises(ValueError):
        negolyte_sensitivity(standard_potential=-0.9, rate_constant_factors=(-1.0,))
