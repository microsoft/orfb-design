# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Aqueous-solubility predictor for the soltrannet server.

Thin wrapper over the in-kernel SolTranNet model (``_model``). Solubilities are
reported as ``logS`` — the base-10 logarithm of the aqueous solubility ``S`` in
mol/L.
"""

from __future__ import annotations

from orfb_provenance import attach_provenance, distribution_version

from soltrannet_tools import _model


def predict_solubility(smiles_list: list[str]) -> dict:
    """Predict aqueous solubility (logS) for a list of molecules.

    Args:
        smiles_list: SMILES strings of candidate molecules (max 256).

    Returns:
        Dict with ``property_name`` ('aqueous_solubility'), ``unit``,
        ``num_molecules`` and ``predictions`` — one record per molecule with
        ``smiles``, ``status``, ``log_solubility`` (logS, log10 mol/L),
        ``unit``, ``warning`` (SolTranNet reliability note) and
        ``failure_reason``, plus a structured ``provenance`` envelope.
    """
    result = _model.predict(smiles_list)
    return attach_provenance(
        result,
        tool_distribution="soltrannet-tools",
        tool_version_fallback="0.1.0",
        model={
            "name": "SolTranNet aqueous-solubility model",
            "version": distribution_version("soltrannet"),
        },
        applicability="reported_per_result",
        uncertainty="not_quantified",
    )
