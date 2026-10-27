# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

# RetroChimera Retrosynthesis MCP Server (real model, CPU inference)
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/retrochimera/Dockerfile -t retrochimera-server:local .
#
# The Pistachio checkpoint is baked into the image at /app/checkpoints (staged
# under model-assets/retrochimera/pistachio in the build context, ~4.4 GB). The
# planning stack (torch, retrochimera, syntheseus, rdkit, ...) is pip-installed
# into the conda kernel at image-build time via ``--warm``. Inference is CPU.

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

# Point the planner at the baked checkpoint. Inference runs on CPU (no GPU
# passthrough); torch submodels just run sequentially without a CUDA device.
ENV RETROCHIMERA_CHECKPOINT_DIR=/app/checkpoints

# Copy the server package tree and shared peer topology. Purchasability
# inventories are user-supplied at runtime and are not baked into the image.
COPY --chown=appuser:appuser servers/retrochimera /app/servers/retrochimera
COPY --chown=appuser:appuser servers/provenance_tools /app/servers/provenance_tools
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

# Bake the Pistachio checkpoint into the image.
COPY --chown=appuser:appuser model-assets/retrochimera/pistachio /app/checkpoints

# Pre-build the conda environment + planning stack (warm start).
RUN python -m servers.retrochimera.server.retrochimera_server --warm

CMD ["python", "-m", "servers.retrochimera.server.retrochimera_server"]
