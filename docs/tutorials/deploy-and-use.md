# Deploy the network and connect an agent

This tutorial builds the complete local ORFB Design network, connects an
MCP-compatible agent to the hub, and runs a first screening workflow.

## 1. Prerequisites

Install:

- Docker with Docker Compose v2;
- GNU Make;
- a Linux x86_64 host, or a Docker environment capable of running the
  repository's Linux x86_64 scientific Python images;
- `curl`, `unzip`, and `md5sum`; and
- enough disk and memory for the scientific images and model assets.

The complete network additionally requires:

- compatible Graphormer reduction and oxidation checkpoints; and
- a RetroChimera purchasability inventory that you are permitted to use.

The RetroChimera image and runtime are the most resource intensive.

## 2. Clone the repository

```bash
git clone https://github.com/microsoft/orfb-design.git
cd orfb-design
```

## 3. Configure model assets

Point the staging script at the two local Graphormer checkpoints:

```bash
export GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE=/absolute/path/to/reduction_checkpoint_best.pt
export GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE=/absolute/path/to/oxidation_checkpoint_best.pt
```

Create a Compose override that mounts the RetroChimera inventory:

```bash
export RETROCHIMERA_INVENTORY_HOST_PATH=/absolute/path/to/inventory.smi

cat > docker-compose.inventory.yml <<'YAML'
services:
  retrochimera-server:
    volumes:
      - type: bind
        source: ${RETROCHIMERA_INVENTORY_HOST_PATH}
        target: /data/retrochimera-inventory.smi
        read_only: true
    environment:
      RETROCHIMERA_INVENTORY_PATH: /data/retrochimera-inventory.smi
YAML

export COMPOSE_FILE=docker-compose.yml:docker-compose.inventory.yml
```

The inventory is a UTF-8 file with one SMILES per line. Blank lines and lines
beginning with `#` are ignored.

## 4. Build and start

```bash
make up
```

This command:

1. stages the Graphormer checkpoints;
2. downloads and verifies the public RetroChimera model;
3. builds the shared Agora Workbench base image;
4. builds the five domain images and the hub; and
5. starts the network in the background.

Initial builds can take substantial time. RetroChimera can also require several
minutes to become healthy while it loads its planning model.

Check the deployment:

```bash
make ps
curl --fail http://127.0.0.1:8050/health
```

Follow logs if a service remains unhealthy:

```bash
make logs
```

## 5. Connect an agent

Any MCP client that supports Streamable HTTP can connect to:

```text
http://127.0.0.1:8050/mcp
```

For example, a VS Code workspace can define `.vscode/mcp.json`:

```json
{
  "servers": {
    "orfb-design": {
      "type": "http",
      "url": "http://127.0.0.1:8050/mcp"
    }
  }
}
```

See the
[VS Code MCP configuration reference](https://github.com/microsoft/vscode-docs/blob/main/docs/agents/reference/mcp-configuration.md)
for client-specific options.

!!! warning "Local development security"

    The default servers use no-op authentication. Published ports are bound to
    loopback, but anyone who can access an endpoint can execute code inside its
    container. Do not expose these endpoints to an untrusted network.

## 6. Ask the agent to discover the network

Start with a prompt that encourages tool and skill discovery:

> Discover the ORFB Design tools and skills. Explain which servers you would
> use to characterize a molecule, predict reduction potential and aqueous
> solubility, assess synthesis, and estimate device-level performance. Do not
> run a model yet.

The agent should use `search_orfb-hub_tools`, inspect the relevant skill, and
identify the domain execution tools before writing Python.

## 7. Run a small workflow

For an inexpensive first run, avoid RetroChimera and ask for characterization,
redox prediction, and solubility:

> Evaluate ethanol (`CCO`) and benzene (`c1ccccc1`). Compute molecular
> descriptors, predict reduction potential and aqueous solubility, and return a
> compact comparison table. Keep intermediate objects in the server kernels
> and report model warnings.

The agent will typically:

1. call `execute_orfb_code` and use `molecular_properties`;
2. call `execute_graphormer_code` and use
   `predict_reduction_potential`;
3. call `execute_soltrannet_code` and use `predict_solubility`; and
4. summarize the returned records.

Retrosynthesis requests can take tens of minutes and are normally promoted to
background jobs. Submit one target per planning job and poll the returned
`retrochimera_check_job` handle.

## 8. Stop the network

```bash
make down
```

Staged checkpoints remain under the git-ignored `model-assets/` directory. To
remove them and the download cache:

```bash
make clean-checkpoints
```
