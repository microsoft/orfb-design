# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

# Graphormer Redox MCP Server (real model, CPU inference)
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/graphormer/Dockerfile -t graphormer-server:local .
#
# The redox checkpoints are baked into the image at /app/checkpoints. The
# compatibility environment uses a pinned public Microsoft Graphormer checkout
# and its pinned Fairseq submodule; no Graphormer source is vendored here.

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

ARG GRAPHORMER_REPOSITORY=https://github.com/microsoft/Graphormer.git
ARG GRAPHORMER_REF=59c0decffcade9df81d29dcc178a489b31958bab

# Run on CPU (no GPU passthrough); cu111 wheels import fine without a device.
ENV GRAPHORMER_CHECKPOINT_DIR=/app/checkpoints \
    GRAPHORMER_DEVICE=cpu \
    GRAPHORMER_SOURCE_DIR=/app/graphormer-source \
    PYTHONPATH=/app/graphormer-source:/app

# Fetch only the pinned public source revision, then initialize the Fairseq
# submodule pinned there (98ebe4f1ada75d006717d84f9d603519d8ff5579).
RUN git init "${GRAPHORMER_SOURCE_DIR}" && \
    cd "${GRAPHORMER_SOURCE_DIR}" && \
    git remote add origin "${GRAPHORMER_REPOSITORY}" && \
    git fetch --depth 1 origin "${GRAPHORMER_REF}" && \
    git checkout --detach FETCH_HEAD && \
    git submodule update --init --depth 1 fairseq

# Copy the server package tree and the shared peer topology.
COPY --chown=appuser:appuser servers/graphormer /app/servers/graphormer
COPY --chown=appuser:appuser servers/provenance_tools /app/servers/provenance_tools
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

# Bake the redox checkpoints into the image.
COPY --chown=appuser:appuser model-assets/graphormer /app/checkpoints

# Build the conda environment, pinned Fairseq, Graphormer Cython extension, and
# in-kernel tools at image-build time.
RUN python -m servers.graphormer.server.graphormer_server --warm

CMD ["python", "-m", "servers.graphormer.server.graphormer_server"]
