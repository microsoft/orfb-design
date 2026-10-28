# ORFB Hub

The ORFB Hub is the single gateway an MCP-compatible AI agent uses to access
the five scientific domain servers. It is built on the Agora Workbench
`RouterServer`.

You host the hub and domain servers yourself. In the default Docker Compose
deployment, all six run as separate containers on your machine or VM.
Scientific models and simulations run on that host, not through hosted
model-provider APIs. Setup downloads software and some model assets; other
assets must be supplied separately.

## Architecture

```text
MCP-compatible AI agent (chooses tools and orchestrates the workflow)
    |
    v
ORFB Hub (discovers tools and routes requests; does not run models)
    |
    +-- ORFB / RDKit  : molecular characterization
    +-- Graphormer   : redox-potential prediction
    +-- RetroChimera : synthesis planning
    +-- SolTranNet   : aqueous-solubility prediction
    +-- EZBattery    : cell simulation
        [Hub and all five domain servers run on your deployment host]
```

The agent normally connects only to the hub. The hub reaches domain containers
over a private Docker network, and each domain server performs its own
scientific computations. The hub does not autonomously choose the research
workflow; the connected agent does.

## Connection

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
Agents using the hub should preserve it together with the MCP call log. The log
records inputs and invocation details; the compact object adds tool/model
versions and scientific applicability and uncertainty classifications.

## Open-source foundation

The router and domain execution framework come from
[Microsoft Agora Workbench](https://github.com/microsoft/agora-workbench).
Upstream URLs are configured through the shared peer registry in
`docker-compose.yml`.
