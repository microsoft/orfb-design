# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

# SolTranNet Aqueous-Solubility MCP Server (real model, CPU inference)
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/soltrannet/Dockerfile -t soltrannet-server:local .
#
# Unlike the redox / retrosynthesis servers, there is NO external checkpoint to
# bake: SolTranNet's trained weights ship inside its pip package. The inference
# stack (CPU torch, soltrannet, rdkit, numpy) is installed into the conda kernel
# at image-build time via ``--warm``. Inference is CPU.

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

# Copy the server package tree and the shared peer topology.
COPY --chown=appuser:appuser servers/soltrannet /app/servers/soltrannet
COPY --chown=appuser:appuser servers/provenance_tools /app/servers/provenance_tools
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

# Pre-build the conda environment + SolTranNet stack (warm start).
RUN python -m servers.soltrannet.server.soltrannet_server --warm

CMD ["python", "-m", "servers.soltrannet.server.soltrannet_server"]
