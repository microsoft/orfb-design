# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Tool definitions (metadata) for the graphormer redox domain.

Server-side schemas only — implementations live in the ``graphormer_tools``
package installed into the execution kernel. The Graphormer service in the
original ORFB tooling also served a solubility model; that is intentionally
**not** exposed here (redox potentials only).
"""

from agora_workbench.code_execution import ReturnSpec, StateTransition, ToolDefinition, ToolParameter

predict_reduction_potential = ToolDefinition(
    name="predict_reduction_potential",
    module="graphormer_tools.redox",
    description=(
        "Predict the reduction potential (volts versus the standard hydrogen "
        "electrode) for each molecule in a list using the Graphormer redox model. "
        "Relevant for ORFB anolyte selection."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of SMILES strings (max 32)"),
    ],
    return_spec=[
        ReturnSpec(name="property_name", type=str, description="Always 'reduction'"),
        ReturnSpec(name="unit", type=str, description="Potential unit (V versus SHE)"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="predictions", type=list, description="Per-molecule reduction potential records"),
        ReturnSpec(
            name="provenance", type=dict, description="Compact versions, applicability, and uncertainty metadata"
        ),
    ],
    state_transition=StateTransition(
        produces=frozenset({"graphormer.reduction_predicted"}),
    ),
    affordances=[
        "predict the reduction potential of a molecule",
        "estimate anolyte redox potential",
        "rank molecules by reduction potential",
    ],
)

predict_oxidation_potential = ToolDefinition(
    name="predict_oxidation_potential",
    module="graphormer_tools.redox",
    description=(
        "Predict the oxidation potential (volts versus the standard hydrogen "
        "electrode) for each molecule in a list using the Graphormer redox model. "
        "Relevant for ORFB catholyte selection."
    ),
    required_parameters=[
        ToolParameter(name="smiles_list", type=list, description="List of SMILES strings (max 32)"),
    ],
    return_spec=[
        ReturnSpec(name="property_name", type=str, description="Always 'oxidation'"),
        ReturnSpec(name="unit", type=str, description="Potential unit (V versus SHE)"),
        ReturnSpec(name="num_molecules", type=int, description="Number of input molecules"),
        ReturnSpec(name="predictions", type=list, description="Per-molecule oxidation potential records"),
        ReturnSpec(
            name="provenance", type=dict, description="Compact versions, applicability, and uncertainty metadata"
        ),
    ],
    state_transition=StateTransition(
        produces=frozenset({"graphormer.oxidation_predicted"}),
    ),
    affordances=[
        "predict the oxidation potential of a molecule",
        "estimate catholyte redox potential",
        "rank molecules by oxidation potential",
    ],
)
