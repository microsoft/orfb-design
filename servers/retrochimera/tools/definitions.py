"""Tool definitions (metadata) for the retrochimera retrosynthesis domain.

Server-side schemas only — the implementation lives in the
``retrochimera_tools`` package installed into the execution kernel.
"""

from agora_workbench.code_execution import ReturnSpec, StateTransition, ToolDefinition, ToolParameter

predict_retrosynthesis = ToolDefinition(
    name="predict_retrosynthesis",
    module="retrochimera_tools.retrosynthesis",
    description=(
        "Plan retrosynthetic routes for a target molecule using the RetroChimera "
        "single-step model with RetroStar multi-step search and a configured "
        "purchasable-compound inventory. Relevant for assessing ORFB candidate "
        "synthesizability."
    ),
    required_parameters=[
        ToolParameter(name="smiles", type=str, description="SMILES string of the target molecule"),
    ],
    optional_parameters=[
        ToolParameter(
            name="num_results",
            type=int,
            description="Number of routes to return (1–50, default 5)",
            default=5,
        ),
    ],
    return_spec=[
        ReturnSpec(name="status", type=int, description="HTTP-style status code (200)"),
        ReturnSpec(name="attempts", type=int, description="Number of planning attempts"),
        ReturnSpec(name="routes", type=list, description="Synthesis routes (reactions, num_steps, catalog flag)"),
        ReturnSpec(
            name="route_source",
            type=str,
            description="multi_step, single_step_fallback, or inventory_match",
        ),
        ReturnSpec(
            name="all_routes_resolved", type=bool, description="Whether all routes end in purchasable materials"
        ),
        ReturnSpec(name="message", type=str, description="Optional status / diagnostic message"),
        ReturnSpec(
            name="provenance", type=dict, description="Compact versions, applicability, and uncertainty metadata"
        ),
    ],
    state_transition=StateTransition(
        produces=frozenset({"retrochimera.routes_predicted"}),
    ),
    affordances=[
        "plan a retrosynthesis route for a molecule",
        "assess whether a candidate is synthesizable from purchasable building blocks",
        "find precursor / starting materials for a target molecule",
    ],
)
