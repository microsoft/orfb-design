"""Aqueous-solubility predictor for the soltrannet server.

Thin wrapper over the in-kernel SolTranNet model (``_model``). Solubilities are
reported as ``logS`` — the base-10 logarithm of the aqueous solubility ``S`` in
mol/L.
"""

from __future__ import annotations

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
        ``failure_reason``.
    """
    return _model.predict(smiles_list)
