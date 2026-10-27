# ORFB Design

ORFB Design is a local Model Context Protocol (MCP) server network for
screening molecules for aqueous organic redox-flow batteries. It combines five
scientific domains behind one MCP endpoint:

- molecular descriptors, structural similarity, and synthetic accessibility;
- reduction and oxidation potential prediction;
- aqueous-solubility prediction;
- retrosynthetic route planning; and
- cell-level redox-flow-battery simulation.

!!! warning "Research software"

    Model predictions and simulated cell metrics are computational screening
    results, not experimental evidence. Retrosynthetic routes are planning
    suggestions rather than laboratory procedures. ORFB Design does not provide
    toxicology, chemical-reactivity, process-hazard, containment, or
    waste-management assessments. Evaluate these considerations separately
    before experimental use.

## Start here

- [Understand the server network](servers/index.md)
- [Deploy the network and connect an agent](tutorials/deploy-and-use.md)
- [Read the repository README](https://github.com/microsoft/orfb-design#readme)
- [Learn about Agora Workbench](https://microsoft.github.io/agora-workbench/)

## Servers

| Server | What it contributes |
|---|---|
| [ORFB Hub](servers/hub.md) | Unified MCP endpoint, tool discovery, workflow planning, and routing to every domain |
| [ORFB Characterization](servers/orfb.md) | RDKit descriptors, Morgan-fingerprint similarity, and synthetic-accessibility scoring |
| [Graphormer](servers/graphormer.md) | Reduction and oxidation potentials in volts versus the standard hydrogen electrode |
| [RetroChimera](servers/retrochimera.md) | Multi-step retrosynthetic planning with purchasable-starting-material annotations |
| [SolTranNet](servers/soltrannet.md) | Aqueous-solubility prediction as logS |
| [EZBattery](servers/ezbattery.md) | Device-level cell simulation and sensitivity analysis |

The domain servers can run independently, but the full network is designed for
an agent to move from molecular characterization through model prediction and
synthesis assessment to cell-level evaluation.

The servers are built with
[Agora Workbench](https://github.com/microsoft/agora-workbench). Each domain
server provides an isolated Python execution environment, domain tools, and an
agent skill. The `orfb-hub` router presents the complete network through one
Streamable HTTP endpoint:

```text
http://127.0.0.1:8050/mcp
```

## Repository layout

```text
servers/<domain>/                  domain server, tools, skill, and Docker files
servers/hub/                       router that aggregates the domain servers
deployment/docker/base.Dockerfile shared Agora Workbench base image
scripts/fetch_checkpoints.sh       external model-asset staging
docker-compose.yml                 complete local network
tests/                             lightweight regression tests
```

Large model assets and commercial inventory data are deliberately not stored
in the repository. See the [deployment tutorial](tutorials/deploy-and-use.md)
for the required Graphormer checkpoints and RetroChimera inventory.

---

[Disclaimers](disclaimers.md)
