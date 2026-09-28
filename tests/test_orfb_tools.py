"""Smoke tests for the ORFB kernel tool implementations (RDKit-native).

These exercise the RDKit characterization tools (real computation). They run
outside the conda kernel, so install the test extra first:

    uv sync --extra test    # or: pip install -e ".[test]"
"""

import pytest

from orfb_tools.molecular_properties import molecular_properties
from orfb_tools.sa_score import sa_score
from orfb_tools.tanimoto_similarity import tanimoto_similarity


def test_molecular_properties_basic():
    result = molecular_properties(["CCO", "c1ccccc1"])
    assert result["num_molecules"] == 2
    ethanol = result["results"][0]
    assert ethanol["status"] == "succeeded"
    assert ethanol["properties"]["molecular_formula"] == "C2H6O"
    assert ethanol["properties"]["molecular_weight"] == pytest.approx(46.07, abs=0.1)


def test_molecular_properties_invalid_smiles():
    result = molecular_properties(["not_a_smiles"])
    assert result["results"][0]["status"] == "failed"


def test_molecular_properties_subset():
    result = molecular_properties(["CCO"], properties=["logp", "formal_charge"])
    assert set(result["results"][0]["properties"]) == {"logp", "formal_charge"}


def test_molecular_properties_unknown_property():
    with pytest.raises(ValueError):
        molecular_properties(["CCO"], properties=["bogus"])


def test_tanimoto_similarity_self_is_one():
    result = tanimoto_similarity(["CCO"], target_smiles="CCO")
    assert result["results"][0]["similarity"] == pytest.approx(1.0)


def test_tanimoto_invalid_target():
    with pytest.raises(ValueError):
        tanimoto_similarity(["CCO"], target_smiles="xyz!")


def test_sa_score_basic():
    result = sa_score(["CCO", "c1ccccc1"])
    assert result["num_molecules"] == 2
    first = result["results"][0]
    assert first["status"] == "succeeded"
    assert 1.0 <= first["sa_score"] <= 10.0


def test_sa_score_invalid_smiles():
    result = sa_score(["not_a_smiles"])
    assert result["results"][0]["status"] == "failed"
