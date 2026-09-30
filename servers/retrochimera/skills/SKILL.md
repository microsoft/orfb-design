---
name: retrochimera-retrosynthesis
description: Plan retrosynthetic routes for organic redox-flow-battery candidate molecules using the RetroChimera model with RetroStar multi-step search and a user-supplied purchasable-compound inventory, via the predict_retrosynthesis tool and the execute_retrochimera_code tool.
states:
  - retrochimera.routes_predicted
---

# RetroChimera Retrosynthesis

Use this skill to plan **retrosynthetic routes** for ORFB candidate molecules
and assess whether they can be made from purchasable building blocks.

- `predict_retrosynthesis(smiles="...", num_results=5)` — returns up to
  `num_results` routes (1–50). Each route has `reactions` (ordered
  `step` / `reactants` / `product`), `num_steps`, and
  `starting_materials_in_catalog` (whether every leaf reactant is purchasable in
  the configured inventory).

The top-level `all_routes_resolved` indicates whether every returned route
terminates in purchasable starting materials.

## Planning stack

Real route planning requires the planning stack (`syntheseus`, `rdkit`, the
`retrochimera` model package) installed in the execution environment plus the
checkpoints:

```
RETROCHIMERA_CHECKPOINT_DIR=/path/to/checkpoints    # RetroChimera model dir
RETROCHIMERA_INVENTORY_PATH=/path/to/inventory.smi  # required; one SMILES per line
```

The checkpoints are baked into the server's Docker image. Inventory data is not
bundled; mount a user-supplied file and set the path before starting the server.

## Running planning

RetroStar planning is CPU-intensive and may take **tens of minutes for one
target**, depending on the molecule and host. Runtime is not determined only by
`num_results`.

Call `execute_retrochimera_code` normally. If execution is still running after
about 45 seconds, the server automatically promotes it to a background job and
returns a handle. No `background` argument is needed.

Submit one target per job when runtime is uncertain, then poll the returned
handle:

```python
# 1. Call normally. For planning this almost always exceeds the ~45s promotion
#    threshold, so the response is a job handle: {"job_id": ..., "poll_tool":
#    "retrochimera_check_job", ...} rather than an inline result.
execute_retrochimera_code(
    code='r = predict_retrosynthesis("<smiles>", num_results=5)\nprint(r["all_routes_resolved"], len(r["routes"]))',
)
# 2. Poll retrochimera_check_job(job_id=...) every 30–60s until the job is
#    completed or failed.
```

If a call *does* return an inline result (e.g. a fast follow-up that finishes
under the threshold), use it directly — there is no job to poll. Promoted jobs
have a default 30-minute budget and a hard one-hour maximum. A timeout means the
route search did not complete within that budget; it is not a partial success.

## Other notes

- Multi-step planning runs RetroStar over the single-step model and falls back
  to single-step predictions if the search yields no non-trivial routes.
- If the target is already purchasable, `routes` is empty with an explanatory
  `message`.
- Preserve the top-level `provenance` object with any route summary. It records
  model/tool versions, a SHA-256 identity of the canonicalized loaded inventory,
  and compact applicability and uncertainty classifications. Preserve
  `route_source` from the ordinary result to distinguish multi-step routes,
  fallbacks, and inventory matches.
