# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Tanimoto similarity to a target molecule using Morgan fingerprints.

Native RDKit implementation mirroring the ``molecule_properties`` endpoint's
``similarity`` calculation: Morgan fingerprints (radius 2, 2048 bits) compared
by Tanimoto coefficient. Useful for scoring how close candidate ORFB molecules
are to a desired reference structure.
"""

from __future__ import annotations

from orfb_provenance import attach_provenance
from rdkit import DataStructs
from rdkit.Chem import AllChem
from rdkit.rdBase import rdkitVersion

_UNIT = "dimensionless (0-1, higher is more similar to target)"
_RADIUS = 2
_N_BITS = 2048


def tanimoto_similarity(smiles_list: list[str], target_smiles: str) -> dict:
    """Compute Tanimoto similarity of each molecule to a target molecule.

    Args:
        smiles_list: SMILES strings of candidate molecules.
        target_smiles: SMILES string of the reference/target molecule.

    Returns:
        Dict with ``target_smiles``, ``unit``, ``num_molecules`` and
        ``results`` — one record per molecule with ``smiles``, ``status``,
        ``similarity`` (float, 0.0 on failure) and ``failure_reason`` — plus a
        structured ``provenance`` envelope.
    """
    if not isinstance(smiles_list, list) or not smiles_list:
        raise ValueError("smiles_list must be a non-empty list of SMILES strings")
    if not isinstance(target_smiles, str) or not target_smiles.strip():
        raise ValueError("target_smiles must be a non-empty SMILES string")

    target_mol = AllChem.MolFromSmiles(target_smiles)
    if target_mol is None:
        raise ValueError(f"Invalid target SMILES: {target_smiles}")
    target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, _RADIUS, nBits=_N_BITS, useChirality=False)

    results = []
    for smiles in smiles_list:
        mol = AllChem.MolFromSmiles(smiles)
        if mol is None:
            results.append(
                {"smiles": smiles, "status": "failed", "similarity": 0.0, "failure_reason": f"Invalid SMILES: {smiles}"}
            )
            continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, _RADIUS, nBits=_N_BITS, useChirality=False)
        similarity = float(DataStructs.TanimotoSimilarity(fp, target_fp))
        results.append(
            {"smiles": smiles, "status": "succeeded", "similarity": round(similarity, 4), "failure_reason": None}
        )

    result = {
        "target_smiles": target_smiles,
        "unit": _UNIT,
        "num_molecules": len(smiles_list),
        "results": results,
    }
    return attach_provenance(
        result,
        tool_distribution="orfb-tools",
        tool_version_fallback="0.1.0",
        model={"name": "RDKit Morgan fingerprint Tanimoto similarity", "version": rdkitVersion},
        configuration={"fingerprint": "Morgan", "radius": _RADIUS, "num_bits": _N_BITS, "use_chirality": False},
        applicability="not_calibrated",
        uncertainty="not_applicable_deterministic",
    )
