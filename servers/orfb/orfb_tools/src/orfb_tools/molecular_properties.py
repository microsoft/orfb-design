"""General molecular property calculation with RDKit.

Native RDKit descriptors useful for organic redox-flow-battery (ORFB) molecule
design: molecular weight, formula, LogP, H-bond donors/acceptors, TPSA,
rotatable bonds, ring counts, fraction sp3, heavy-atom count and net formal
charge. This is the lightweight "molecular property predictor" layer that runs
directly in the execution kernel.
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.rdBase import rdkitVersion

from orfb_provenance import attach_provenance

# Descriptor name -> callable computing it from an RDKit Mol.
_CALCULATORS = {
    "molecular_weight": lambda m: round(Descriptors.MolWt(m), 4),
    "molecular_formula": lambda m: rdMolDescriptors.CalcMolFormula(m),
    "logp": lambda m: round(Descriptors.MolLogP(m), 4),
    "hbd": lambda m: Descriptors.NumHDonors(m),
    "hba": lambda m: Descriptors.NumHAcceptors(m),
    "tpsa": lambda m: round(Descriptors.TPSA(m), 4),
    "rotatable_bonds": lambda m: Descriptors.NumRotatableBonds(m),
    "ring_count": lambda m: rdMolDescriptors.CalcNumRings(m),
    "aromatic_rings": lambda m: rdMolDescriptors.CalcNumAromaticRings(m),
    "fraction_csp3": lambda m: round(Descriptors.FractionCSP3(m), 4),
    "heavy_atom_count": lambda m: m.GetNumHeavyAtoms(),
    "formal_charge": lambda m: Chem.GetFormalCharge(m),
}

ALL_PROPERTY_NAMES = sorted(_CALCULATORS)


def molecular_properties(smiles_list: list[str], properties: list | None = None) -> dict:
    """Compute physicochemical descriptors for a list of molecules.

    Args:
        smiles_list: SMILES strings to characterize.
        properties: Optional list of descriptor names to compute. If omitted,
            all descriptors are returned. Valid names: molecular_weight,
            molecular_formula, logp, hbd, hba, tpsa, rotatable_bonds,
            ring_count, aromatic_rings, fraction_csp3, heavy_atom_count,
            formal_charge.

    Returns:
        Dict with ``properties_computed`` (the descriptor names used),
        ``num_molecules`` and ``results`` — one record per molecule with
        ``smiles``, ``canonical_smiles``, ``status``, ``properties`` (name->value
        map) and ``failure_reason``, plus a structured ``provenance`` envelope.
    """
    if not isinstance(smiles_list, list) or not smiles_list:
        raise ValueError("smiles_list must be a non-empty list of SMILES strings")

    requested = properties if properties else ALL_PROPERTY_NAMES
    unknown = set(requested) - set(ALL_PROPERTY_NAMES)
    if unknown:
        raise ValueError(f"Unknown propert(ies): {sorted(unknown)}. Valid names: {ALL_PROPERTY_NAMES}")

    results = []
    for smiles in smiles_list:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            results.append(
                {
                    "smiles": smiles,
                    "canonical_smiles": None,
                    "status": "failed",
                    "properties": {},
                    "failure_reason": f"Invalid SMILES: {smiles}",
                }
            )
            continue
        values = {name: _CALCULATORS[name](mol) for name in requested}
        results.append(
            {
                "smiles": smiles,
                "canonical_smiles": Chem.MolToSmiles(mol, isomericSmiles=True),
                "status": "succeeded",
                "properties": values,
                "failure_reason": None,
            }
        )

    result = {
        "properties_computed": list(requested),
        "num_molecules": len(smiles_list),
        "results": results,
    }
    return attach_provenance(
        result,
        tool_name="molecular_properties",
        tool_distribution="orfb-tools",
        tool_version_fallback="0.1.0",
        inputs={"smiles_list": smiles_list, "properties": properties},
        model={"name": "RDKit descriptors", "version": rdkitVersion},
        configuration={"properties_computed": list(requested), "canonical_smiles_isomeric": True},
        assumptions=[
            "Descriptors are computed from the supplied SMILES representation.",
            "No aqueous protonation, tautomer, mixture, or formulation state is inferred.",
        ],
        applicability={
            "status": "assessed_per_molecule",
            "details": "SMILES that RDKit cannot parse are marked failed; no broader chemical-domain calibration applies.",
        },
        uncertainty={
            "quantified": False,
            "details": "RDKit descriptors are deterministic calculations; representation and state uncertainty is not quantified.",
        },
    )
