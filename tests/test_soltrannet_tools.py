"""Input-validation tests for the soltrannet aqueous-solubility tool.

Real inference needs the SolTranNet model stack (soltrannet + torch + rdkit),
which is baked into the server's Docker image but absent from the test
environment. These tests therefore exercise the input validation, which raises
before any model is touched.
"""

import pytest

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
