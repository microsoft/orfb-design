# ORFB Hub

The ORFB Hub is an Agora Workbench `RouterServer` that aggregates the five
domain servers. It is the normal entry point for an MCP-compatible agent.

| Property | Value |
|---|---|
| Container | `orfb-hub` |
| Host port | `8050` |
| MCP endpoint | `http://127.0.0.1:8050/mcp` |
| Health endpoint | `http://127.0.0.1:8050/health` |

## Function

The hub discovers the tools, skills, and state graphs exposed by its upstream
servers and presents them through one endpoint. It does not run scientific
models itself.

The router connects to:

- `orfb` for molecular characterization;
- `graphormer` for redox potentials;
- `retrochimera` for synthesis planning;
- `soltrannet` for aqueous solubility; and
- `ezbattery` for cell simulation.

## MCP tools

| Tool | Purpose |
|---|---|
| `execute_orfb_code` | Run Python in the RDKit characterization environment |
| `execute_graphormer_code` | Run Python in the Graphormer redox environment |
| `execute_retrochimera_code` | Run Python in the RetroChimera planning environment |
| `execute_soltrannet_code` | Run Python in the SolTranNet environment |
| `execute_ezbattery_code` | Run Python in the EZBattery simulation environment |
| `search_orfb-hub_tools` | Search domain tools and inspect their signatures |
| `plan_orfb-hub_workflow` | Inspect tool-state requirements and outputs |

Agora Workbench also contributes session, object-transfer, artifact, and
background-job utilities. The exact set visible to an agent depends on the
upstream server and execution mode.

## Skills

The hub does not define a separate scientific skill. It makes the five upstream
domain skills discoverable through the unified endpoint:

- `orfb-design`
- `graphormer-redox`
- `retrochimera-retrosynthesis`
- `soltrannet-solubility`
- `ezbattery-cell-simulation`

An agent should discover and load the relevant domain skill before writing
substantial execution code.

Each scientific evaluation result includes a top-level `provenance` object.
Agents using the hub should preserve the object from every domain-tool call so
the user can reconstruct inputs, versions, configuration, warnings, failures,
assumptions, applicability guidance, and uncertainty scope across the workflow.

## Open-source foundation

The router and domain execution framework come from
[Microsoft Agora Workbench](https://github.com/microsoft/agora-workbench).
Upstream URLs are configured through the shared peer registry in
`docker-compose.yml`.
