"""Tool definitions (metadata) for the ORFB molecule-design domain.

This module contains only ``ToolDefinition`` objects — server-side schemas,
state transitions and affordances. Implementations live in the ``orfb_tools``
package installed into the execution kernel. The ``module`` field on each
definition points at the installed package so the kernel's lazy
``from {module} import {name}`` import resolves correctly.
"""

from agora_workbench.code_execution import ReturnSpec, StateTransition, ToolDefinition, ToolParameter

# ============================================================================
# Molecular property characterization (RDKit, native to the kernel)
# ============================================================================

molecular_properties = ToolDefinition(
    name="molecular_properties",
    module="orfb_tools.molecular_properties",
    description=(
        "Compute physicochemical descriptors (molecular weight, formula, LogP, "
        "H-bond donors/acceptors, TPSA, rotatable bonds, ring counts, fraction "
        "sp3, heavy-atom count, formal charge) for a list of molecules using "
        "RDKit. The entry point for ORFB candidate characterization."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of SMILES strings to characterize"),
    ],
    optional_parameters=[
        ToolParameter(
            name="properties",
            type=list,
            description=(
                "Optional list of descriptor names to compute. If omitted, all are "
                "returned. Valid: molecular_weight, molecular_formula, logp, hbd, hba, "
                "tpsa, rotatable_bonds, ring_count, aromatic_rings, fraction_csp3, "
                "heavy_atom_count, formal_charge."
            ),
            default=None,
        ),
    ],
    return_spec=[
        ReturnSpec(name="properties_computed", type=list, description="Descriptor names computed"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="results", type=list, description="Per-molecule descriptor records"),
        ReturnSpec(name="provenance", type=dict, description="Structured inputs, versions, status, and limitations"),
    ],
    state_transition=StateTransition(
        produces=frozenset({"orfb.properties_computed"}),
    ),
    affordances=[
        "compute molecular descriptors",
        "calculate molecular weight, LogP, TPSA",
        "characterize a redox-flow-battery candidate molecule",
        "get the molecular formula and formal charge",
    ],
)

# ============================================================================
# Similarity & synthesizability scoring (RDKit, native to the kernel)
# ============================================================================

tanimoto_similarity = ToolDefinition(
    name="tanimoto_similarity",
    module="orfb_tools.tanimoto_similarity",
    description=(
        "Compute Tanimoto similarity of each candidate molecule to a target "
        "molecule using Morgan fingerprints (radius 2, 2048 bits). Use to rank "
        "candidates by closeness to a desired reference structure."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of candidate SMILES strings"),
        ToolParameter(name="target_smiles", type=str, description="SMILES string of the reference/target molecule"),
    ],
    return_spec=[
        ReturnSpec(name="target_smiles", type=str, description="The reference molecule SMILES"),
        ReturnSpec(name="unit", type=str, description="Similarity unit description"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="results", type=list, description="Per-molecule similarity records"),
        ReturnSpec(name="provenance", type=dict, description="Structured inputs, versions, status, and limitations"),
    ],
    state_transition=StateTransition(
        requires=frozenset({"orfb.properties_computed"}),
        produces=frozenset({"orfb.similarity_scored"}),
    ),
    affordances=[
        "score similarity to a target molecule",
        "rank candidates by Tanimoto similarity",
        "molecular similarity search",
    ],
)

sa_score = ToolDefinition(
    name="sa_score",
    module="orfb_tools.sa_score",
    description=(
        "Compute the synthetic accessibility (SA) score for each molecule using "
        "RDKit's SA_Score contrib. Lower scores (typical range 1-10) indicate "
        "molecules that are easier to synthesize."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of SMILES strings to score"),
    ],
    return_spec=[
        ReturnSpec(name="unit", type=str, description="SA score unit description"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="results", type=list, description="Per-molecule SA score records"),
        ReturnSpec(name="provenance", type=dict, description="Structured inputs, versions, status, and limitations"),
    ],
    state_transition=StateTransition(
        requires=frozenset({"orfb.properties_computed"}),
        produces=frozenset({"orfb.synthesizability_scored"}),
    ),
    affordances=[
        "compute synthetic accessibility score",
        "score how easy a molecule is to synthesize",
        "filter candidates by synthesizability",
    ],
)
