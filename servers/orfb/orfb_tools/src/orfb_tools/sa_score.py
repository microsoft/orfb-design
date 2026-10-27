# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Synthetic accessibility (SA) score using RDKit's contrib SA_Score.

Native RDKit implementation mirroring the ``molecule_properties`` endpoint's
``sa_score`` calculation. Lower scores indicate molecules that are easier to
synthesize (typical range 1-10).
"""

from __future__ import annotations

import os
import sys

from orfb_provenance import attach_provenance
from rdkit.Chem import AllChem
from rdkit.rdBase import rdkitVersion

_UNIT = "dimensionless (lower is easier to synthesize, typical range 1-10)"

# RDKit ships sascorer under its Contrib directory, which is not on the default
# import path. Add it once so ``from SA_Score import sascorer`` resolves. Prefer
# RDKit's own RDContribDir (works for both pip and conda installs); fall back to
# the conda layout under CONDA_PREFIX.
_contrib_candidates = []
try:
    from rdkit.Chem import RDConfig
except ImportError:  # pragma: no cover - depends on the RDKit distribution
    RDConfig = None
if RDConfig is not None:
    _contrib_candidates.append(RDConfig.RDContribDir)
_contrib_candidates.append(os.path.join(os.environ.get("CONDA_PREFIX", ""), "share", "RDKit", "Contrib"))

for _contrib in _contrib_candidates:
    if _contrib and _contrib not in sys.path and os.path.isdir(_contrib):
        sys.path.append(_contrib)

try:
    from SA_Score import sascorer  # type: ignore
except ImportError:  # pragma: no cover - depends on RDKit contrib availability
    sascorer = None


def sa_score(smiles_list: list[str]) -> dict:
    """Compute the synthetic accessibility score for each molecule.

    Args:
        smiles_list: SMILES strings to score.

    Returns:
        Dict with ``unit``, ``num_molecules`` and ``results`` — one record per
        molecule with ``smiles``, ``status`` ("succeeded"/"failed"),
        ``sa_score`` (float, or 10.0 on failure) and ``failure_reason``, plus a
        structured ``provenance`` envelope.
    """
    if not isinstance(smiles_list, list) or not smiles_list:
        raise ValueError("smiles_list must be a non-empty list of SMILES strings")
    if sascorer is None:
        raise RuntimeError("RDKit SA_Score contrib module is not available in this environment")

    results = []
    for smiles in smiles_list:
        mol = AllChem.MolFromSmiles(smiles)
        if mol is None:
            results.append(
                {"smiles": smiles, "status": "failed", "sa_score": 10.0, "failure_reason": f"Invalid SMILES: {smiles}"}
            )
            continue
        try:
            score = float(sascorer.calculateScore(mol))
            results.append(
                {"smiles": smiles, "status": "succeeded", "sa_score": round(score, 4), "failure_reason": None}
            )
        except Exception as exc:  # noqa: BLE001 - report per-molecule failure
            results.append(
                {"smiles": smiles, "status": "failed", "sa_score": 10.0, "failure_reason": f"SA score error: {exc}"}
            )

    return attach_provenance(
        {"unit": _UNIT, "num_molecules": len(smiles_list), "results": results},
        tool_distribution="orfb-tools",
        tool_version_fallback="0.1.0",
        model={"name": "RDKit SA_Score", "version": rdkitVersion},
        applicability="not_calibrated",
        uncertainty="not_quantified",
    )
