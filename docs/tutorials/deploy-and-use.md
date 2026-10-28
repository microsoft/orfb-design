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

The complete network additionally requires compatible Graphormer reduction and
oxidation checkpoints.

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

RetroChimera uses the bundled `retrochimera_inventory.csv` by default. To use a
different UTF-8, one-SMILES-per-line inventory, mount it into the container and
set `RETROCHIMERA_INVENTORY_PATH` to its container path.

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

See [Troubleshooting](#troubleshooting) if assets are missing, startup stalls,
or the agent cannot reach the hub.

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

## Troubleshooting

Run the following commands from the repository root, using the same
`COMPOSE_FILE` setting as your deployment. If you opened a new shell, restore
the inventory override and its host-path variable from step 3 first.

### The hub is not ready

```bash
docker compose ps -a
docker compose logs --tail=100
curl --fail --max-time 10 http://127.0.0.1:8050/health
```

The hub waits for all five domains to become healthy before starting.
RetroChimera can take several minutes to load its model. While a service shows
`starting`, check its logs for progress rather than repeatedly restarting it.
If it becomes `unhealthy` or exits, inspect that domain's logs for the cause.
Review logs for sensitive inputs or local paths before sharing them.

### Missing model assets or inventory

The full network requires compatible Graphormer reduction and oxidation
checkpoints; this repository does not provide a public download for them.
If staging reports missing checkpoints, set
`GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE` and
`GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE` to readable, nonempty local files as
shown in step 3, then run:

```bash
make graphormer-checkpoints
make up
```

RetroChimera's default inventory is bundled in its Python package. If it reports
a missing or unreadable inventory, rebuild the image from the current
repository and check whether an override is set:

```bash
docker compose config
```

Unset `RETROCHIMERA_INVENTORY_PATH` to return to the bundled inventory. If you
intentionally replace it, confirm that the configured container path is backed
by a readable, read-only mount. After correcting the configuration, rebuild and
apply it:

```bash
docker compose up -d --build retrochimera-server orfb-hub
```

### The agent is on another machine

First run the hub health check on the Docker host. If it fails there, resolve
service startup before changing the client. If health succeeds, configure the
MCP client with `/mcp`, not `/health`, and ensure it supports Streamable HTTP.

`127.0.0.1` refers to the machine where the MCP client runs, not a remote VM.
Keep the default loopback binding and run an SSH tunnel on the client machine:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8050:127.0.0.1:8050 user@docker-host
```

Replace `user@docker-host` with your SSH destination and keep the tunnel open.
On the client machine, verify
`curl --fail --max-time 10 http://127.0.0.1:8050/health`, then connect the MCP
client to `http://127.0.0.1:8050/mcp`. If local port 8050 is occupied, use
`127.0.0.1:18050:127.0.0.1:8050` in the tunnel and port 18050 in the client URLs.

The default endpoints have no authentication and allow code execution inside
the containers; do not expose them directly to an untrusted network.
