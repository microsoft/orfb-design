# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Input-validation tests for the soltrannet aqueous-solubility tool.

Real inference needs the SolTranNet model stack (soltrannet + torch + rdkit),
which is baked into the server's Docker image but absent from the test
environment. These tests therefore exercise the input validation, which raises
before any model is touched.
"""

import pytest
from soltrannet_tools import solubility as solubility_module
from soltrannet_tools.solubility import predict_solubility


def test_solubility_batch_limit():
    with pytest.raises(ValueError):
        predict_solubility(["CCO"] * 257)


def test_solubility_empty_input():
    with pytest.raises(ValueError):
        predict_solubility([])


def test_solubility_non_string_entry():
    with pytest.raises(ValueError):
        predict_solubility(["CCO", ""])


def test_solubility_adds_structured_provenance(monkeypatch):
    monkeypatch.setattr(
        solubility_module._model,
        "predict",
        lambda smiles_list: {
            "property_name": "aqueous_solubility",
            "unit": "logS",
            "num_molecules": 1,
            "predictions": [
                {
                    "smiles": "CCO",
                    "status": "succeeded",
                    "log_solubility": -0.2,
                    "warning": "example applicability warning",
                    "failure_reason": None,
                }
            ],
        },
    )

    result = predict_solubility(["CCO"])

    provenance = result["provenance"]
    assert provenance["applicability"] == "reported_per_result"
    assert provenance["uncertainty"] == "not_quantified"
    assert result["predictions"][0]["warning"] == "example applicability warning"
