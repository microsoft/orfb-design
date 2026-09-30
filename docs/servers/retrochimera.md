# RetroChimera retrosynthesis

The `retrochimera` server plans synthesis routes and annotates whether route
leaves are present in a configured purchasable-compound inventory.

| Property | Value |
|---|---|
| Container | `retrochimera-server` |
| Host port | `8042` |
| Execution tool | `execute_retrochimera_code` |
| Skill | `retrochimera-retrosynthesis` |
| Execution mode | Adaptive, with background-job promotion |

## Domain tool

| Function | Purpose |
|---|---|
| `predict_retrosynthesis(smiles, num_results=5)` | Return up to 50 multi-step routes, route reactions, step counts, and purchasability status |

Planning uses the RetroChimera single-step model with RetroStar multi-step
search. If multi-step extraction fails to produce a route, the implementation
falls back to single-step predictions.

Results include a compact `provenance` object with installed tool/model
versions, a SHA-256 identity of the canonicalized loaded inventory, and applicability and
uncertainty classifications. The ordinary result reports whether routes came
from multi-step planning, a single-step fallback, or an inventory match.

## Skill guidance

The `retrochimera-retrosynthesis` skill describes route interpretation,
inventory semantics, and long-running execution. Planning can take tens of
minutes for one target. Calls still running after approximately 45 seconds are
promoted to background jobs; submit one target per job and poll the returned
job handle.

## Open-source foundation

The synthesis planner comes from
[`microsoft/retrochimera`](https://github.com/microsoft/retrochimera) 1.3.0. It
uses [`microsoft/syntheseus`](https://github.com/microsoft/syntheseus) to run
RetroStar multi-step search, with RDKit, PyTorch, and supporting graph packages
providing the chemistry and model runtime.

## Model and inventory assets

The Pistachio-trained model is downloaded from the public
[Figshare release](https://doi.org/10.6084/m9.figshare.30591107.v1). The model
artifact is not the Pistachio reaction dataset.

A separate UTF-8 inventory containing one purchasable SMILES per line is
required through `RETROCHIMERA_INVENTORY_PATH`. The inventory controls only the
purchasability annotations and route termination; use data that you are
permitted to use.
