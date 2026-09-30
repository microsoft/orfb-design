"""Aqueous-solubility predictor for the soltrannet server.

Thin wrapper over the in-kernel SolTranNet model (``_model``). Solubilities are
reported as ``logS`` — the base-10 logarithm of the aqueous solubility ``S`` in
mol/L.
"""

from __future__ import annotations

from soltrannet_tools import _model
from orfb_provenance import attach_provenance, distribution_version


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
        tool_name="predict_solubility",
        tool_distribution="soltrannet-tools",
        tool_version_fallback="0.1.0",
        inputs={"smiles_list": smiles_list},
        model={
            "name": "SolTranNet aqueous-solubility model",
            "version": distribution_version("soltrannet"),
            "weights": "bundled with the installed SolTranNet distribution",
        },
        configuration={"max_batch_size": _model.MAX_BATCH_SIZE, "output": "logS (log10 mol/L)"},
        assumptions=[
            "Predictions represent aqueous solubility for the supplied SMILES representation.",
            "No pH-specific protonation, tautomer, salt formulation, or temperature adjustment is performed.",
        ],
        applicability={
            "status": "reported_per_molecule",
            "details": "SolTranNet warnings for salts or out-of-domain atom types are preserved in execution.warnings.",
        },
        uncertainty={
            "quantified": False,
            "details": "SolTranNet returns point predictions and qualitative reliability warnings, not calibrated intervals.",
        },
    )
