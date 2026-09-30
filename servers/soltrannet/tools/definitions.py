"""Tool definitions (metadata) for the soltrannet aqueous-solubility domain.

Server-side schemas only — the implementation lives in the ``soltrannet_tools``
package installed into the execution kernel. It predicts logS, the base-10
logarithm of aqueous solubility in mol/L.
"""

from agora_workbench.code_execution import ReturnSpec, StateTransition, ToolDefinition, ToolParameter

predict_solubility = ToolDefinition(
    name="predict_solubility",
    module="soltrannet_tools.solubility",
    description=(
        "Predict the aqueous solubility (logS, the base-10 logarithm of the "
        "solubility S in mol/L) for each molecule in a list using the SolTranNet "
        "model (open-source, trained on AqSolDB). Relevant for ORFB electrolyte "
        "solubility screening."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of SMILES strings (max 256)"),
    ],
    return_spec=[
        ReturnSpec(name="property_name", type=str, description="Always 'aqueous_solubility'"),
        ReturnSpec(name="unit", type=str, description="logS (log10 of aqueous solubility S in mol/L)"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="predictions", type=list, description="Per-molecule aqueous solubility (logS) records"),
        ReturnSpec(name="provenance", type=dict, description="Structured inputs, versions, status, and limitations"),
    ],
    state_transition=StateTransition(
        produces=frozenset({"soltrannet.solubility_predicted"}),
    ),
    affordances=[
        "predict the aqueous solubility of a molecule",
        "estimate how soluble an ORFB electrolyte is in water",
        "rank molecules by aqueous solubility (logS)",
    ],
)
