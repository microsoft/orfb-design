# ORFB Design

ORFB Design is a local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server network built on **[Microsoft Agora Workbench](https://github.com/microsoft/agora-workbench)**
for screening molecules for organic redox-flow batteries. It combines molecular
descriptors, redox-potential and solubility models, retrosynthesis planning, and
cell-level simulation behind a single Workbench router.

## Built on Agora Workbench

Agora Workbench provides the MCP routing and execution framework for the hub
and all five domain servers, not just the router. It supplies persistent Python
execution environments, tool and skill discovery, workflow-state inspection,
and utilities for sessions, cross-server object transfer, artifacts, and
background jobs. ORFB Design adds the domain-specific scientific tools and
model integrations.

Learn more in the [Agora Workbench documentation](https://microsoft.github.io/agora-workbench/).

## Deployment architecture

You host the network yourself: the default Docker Compose deployment runs the
hub and five domain servers as separate containers on your machine or VM.
Scientific models and simulations run on that host, not through hosted
model-provider APIs. Setup downloads software and some model assets; other
assets must be supplied separately.

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

The agent connects to one hub endpoint; the hub reaches the domain containers
over a private Docker network. Each domain server performs its own scientific
computations. See the [hub documentation](docs/servers/hub.md) for details.

The project is research software intended for computational screening. Model
predictions and simulated cell metrics are not experimental evidence, and
retrosynthetic routes are planning suggestions rather than laboratory
procedures. The project does not provide toxicology, chemical-reactivity,
process-hazard, containment, or waste-management assessments. Evaluate these
considerations separately before experimental use.

## Structured tool provenance

Scientific evaluation tools return an additive top-level `provenance` object so
user-supplied agents can build an end-to-end audit record. The envelope includes:

- the tool package version;
- the available model, checkpoint, or simulator version;
- compact applicability and uncertainty classifications; and
- material configuration that is not otherwise evident from the tool call or
  ordinary result.

Inputs, invocation identity, ordering, timestamps, statuses, warnings, and
failure details remain in the MCP call log or ordinary tool result rather than
being duplicated in the provenance object. The package cannot ensure that a
user-supplied agent retains or presents the complete workflow record. Consumers
should preserve the MCP call log and the compact `provenance` object from every
tool call. Catalog-only tools, such as `list_electrolyte_profiles`, continue to
return their documented catalog shape rather than an evaluation provenance
envelope.

## Capabilities

| Server | Default port | Main tools | Purpose |
|---|---:|---|---|
| `orfb-hub` | 8050 | tool search, workflow planning, `execute_*_code` routing | Unified MCP entry point |
| `orfb` | 8040 | `molecular_properties`, `tanimoto_similarity`, `sa_score` | RDKit descriptors, similarity, and synthetic-accessibility scoring |
| `graphormer` | 8041 | `predict_reduction_potential`, `predict_oxidation_potential` | Redox potentials in volts versus SHE |
| `retrochimera` | 8042 | `predict_retrosynthesis` | Multi-step retrosynthesis with purchasability annotations |
| `soltrannet` | 8043 | `predict_solubility` | Aqueous solubility as logS (log10 mol/L) |
| `ezbattery` | 8044 | `simulate_negolyte`, `negolyte_sensitivity`, `simulate_cell` | Cell-level performance and sensitivity analysis |

Connect an MCP client to:

```text
http://localhost:8050/mcp
```

Host ports are bound to `127.0.0.1` by default. Keep them loopback-only unless
you add real authentication and appropriate network controls.

## Requirements

- Docker with Docker Compose v2
- GNU Make
- A Linux x86_64 host, or a Docker environment capable of running the
  repository's Linux x86_64 scientific Python images
- `curl`, `unzip`, and `md5sum` for checkpoint staging
- Sufficient disk and memory for several model images and checkpoints;
  RetroChimera is the most resource-intensive service
- Two Graphormer redox checkpoint files supplied separately
- A RetroChimera purchasability inventory supplied separately

The first image build downloads scientific Python environments and can take a
substantial amount of time.

## External model assets

Large models and third-party inventory data are not committed to this
repository.

| Asset | How it is supplied |
|---|---|
| Graphormer reduction checkpoint | Local file set with `GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE` |
| Graphormer oxidation checkpoint | Local file set with `GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE` |
| RetroChimera Pistachio-trained model | Downloaded from the [`microsoft/retrochimera`](https://github.com/microsoft/retrochimera) [Figshare release](https://doi.org/10.6084/m9.figshare.30591107.v1) by `scripts/fetch_checkpoints.sh` |
| RetroChimera purchasability inventory | User-provided UTF-8 file containing one SMILES per line |
| SolTranNet weights | Included by the upstream Python package |
| EZBattery model | Source is fetched from a pinned [`pnnl/EZBattery`](https://github.com/pnnl/EZBattery) commit during the image build; reference-cell data are included locally |

The Graphormer checkpoint paths are needed when staging the files for the first
time. Staged copies are stored under `model-assets/`, which is git-ignored.
This repository does not currently provide a public download for compatible
Graphormer redox checkpoints; without them, run the asset-free services
individually rather than the complete network.

The inventory controls which leaf molecules RetroChimera labels as
purchasable. Blank lines and lines beginning with `#` are ignored. Use an
inventory that you are permitted to use and redistribute; the repository does
not provide commercial-catalog data.

## Quick start

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/microsoft/orfb-design.git
   cd orfb-design
   ```

2. Set the paths to the two Graphormer checkpoints:

   ```bash
   export GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE=/absolute/path/to/reduction/checkpoint_best.pt
   export GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE=/absolute/path/to/oxidation/checkpoint_best.pt
   ```

3. Create a local Compose override for the RetroChimera inventory:

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

4. Build and start the network:

   ```bash
   make up
   ```

   `make up` stages the model assets, builds the shared Agora Workbench base
   image, builds the six service images, and starts the network in the
   background.

5. Check service status:

   ```bash
   make ps
   curl --fail http://localhost:8050/health
   ```

The RetroChimera container can take several minutes to become healthy because
it loads a large planning model and reaction-rule inventory at startup.

## Common operations

```bash
make checkpoints             # stage all external model assets
make graphormer-checkpoints  # stage only the two local Graphormer files
make retrochimera-checkpoint # download and unpack the public RetroChimera model
make base-image              # build mcp-server-base:local
make build                   # build every service image
make up                      # build and start the network
make ps                      # show container status
make logs                    # follow service logs
make down                    # stop and remove the network
make clean-checkpoints       # remove staged model assets and download cache
```

To run one domain without the hub, use the Compose file under
`servers/<domain>/docker-compose.yml`. Graphormer and RetroChimera still require
their respective external assets.

## Using the tools

The hub exposes one persistent Python execution tool per domain:

- `execute_orfb_code`
- `execute_graphormer_code`
- `execute_retrochimera_code`
- `execute_soltrannet_code`
- `execute_ezbattery_code`

The domain functions are preloaded inside the matching execution environment.
For example:

```python
# Run inside execute_graphormer_code
result = predict_reduction_potential(["CCO", "c1ccccc1"])
print(result["predictions"])
```

Use `search_orfb-hub_tools` to discover tools and signatures, and
`plan_orfb-hub_workflow` to inspect the available state transitions. Keep large
intermediate objects in persistent kernels and print concise summaries.

## Model and workflow notes

### Graphormer

- Accepts batches of up to 32 SMILES.
- Reports reduction or oxidation potential in volts versus SHE.
- Molecules with more than 128 non-hydrogen atoms are rejected.
- The two fine-tuned checkpoints emit potentials directly; no output
  de-normalization is applied.
- The runtime builds public
  [`microsoft/Graphormer`](https://github.com/microsoft/Graphormer) commit
  `59c0decffcade9df81d29dcc178a489b31958bab` and its pinned Fairseq submodule.

### SolTranNet

- Accepts batches of up to 256 SMILES.
- Reports logS, the base-10 logarithm of aqueous solubility in mol/L.
- Salts and molecules outside the training distribution may receive reliability
  warnings.

### RetroChimera

- Requires the public model checkpoint and a user-provided inventory.
- Planning is CPU-intensive and may take tens of minutes for one target,
  depending on the molecule and host.
- Calls that run longer than about 45 seconds are promoted to background jobs.
  Poll the returned `retrochimera_check_job` handle until completion.
- Promoted jobs have a maximum one-hour execution budget. Submit one target per
  job when planning time is uncertain.
- Purchasability labels are only as complete and current as the configured
  inventory.

### EZBattery

- Uses a bundled DHPS-ferrocyanide aqueous reference-cell configuration.
- `simulate_negolyte` maps predicted molecular properties onto cell parameters
  and reports parameter provenance.
- Diffusivity and kinetics are important uncertainties; use
  `negolyte_sensitivity` before comparing candidates on absolute KPIs.

## Configuration

| Variable | Purpose |
|---|---|
| `GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE` | Local source file used to stage the reduction checkpoint |
| `GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE` | Local source file used to stage the oxidation checkpoint |
| `GRAPHORMER_CHECKPOINT_DIR` | Checkpoint directory inside the Graphormer container; defaults to `/app/checkpoints` |
| `GRAPHORMER_DEVICE` | Torch device; defaults to `cpu` |
| `RETROCHIMERA_INVENTORY_PATH` | Inventory path inside the RetroChimera container |
| `RETROCHIMERA_NUM_PROCESSES` | Rule-application worker count; unset uses available CPUs |
| `RETROCHIMERA_RECYCLE_AFTER_JOBS` | Recreate the worker pool after this many predictions; `0` disables |
| `RETROCHIMERA_RECYCLE_RSS_MB` | Recreate workers above this RSS threshold; `0` disables |
| `BLOB_PUBLISH_ACCOUNT_URL` | Optional Azure Blob account URL for published artifacts |
| `BLOB_PUBLISH_CONTAINER` | Optional Azure Blob container; defaults to `artifacts` |

## Development

Local tests exercise the lightweight tool packages directly. Heavy model
inference is built into the Docker images.

```bash
uv sync --extra test
make ezbattery-source
uv run pytest
uv run --with ruff ruff check .
```

After changing Python dependency inputs, regenerate the root and image-specific
hash locks with `make dependency-locks`.

Repository layout:

```text
deployment/docker/base.Dockerfile  shared Agora Workbench base image
servers/<domain>/                  domain server, tools, skill, and Docker files
servers/hub/                       router that aggregates the domain servers
scripts/fetch_checkpoints.sh       external model-asset staging
scripts/fetch_ezbattery_source.sh  pinned upstream EZBattery source staging
tests/                             local regression tests
docker-compose.yml                 complete local network
```

Agora Workbench is installed from public PyPI and pinned in
[`pyproject.toml`](https://github.com/microsoft/orfb-design/blob/main/pyproject.toml).
The Graphormer and RetroChimera images build their specialized scientific
environments separately.

## Security

The default deployment uses no-op authentication and is intended only for a
trusted local machine. Published ports are loopback-bound. Do not expose the
containers directly to an untrusted network.

The model-execution tools run Python code in persistent kernels. Treat access to
the MCP endpoint as code-execution access to the containers.

## License status

This repository is licensed under the [MIT License](LICENSE.TXT).

This MCP server may use or depend on third-party components, such as third-party
MCP clients, hosts, agents, AI applications, and/or models. You are responsible
for reviewing and complying with the licenses of any third-party components and
vetting the security of any third-party components.

This MCP server may provide access to underlying resources, such as tools,
services, and/or data. Your use of that underlying resource via the MCP server
is governed by the underlying resource's license terms.
