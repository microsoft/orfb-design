# EZBattery Cell-Level RFB Simulation MCP Server (real model, CPU)
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/ezbattery/Dockerfile -t ezbattery-server:local .
#
# Like the soltrannet server (and unlike the redox / retrosynthesis servers)
# there is NO external checkpoint to bake: EZBattery is pure Python and its
# source is vendored inside the tools package. The numeric stack (numpy<2,
# scipy, pandas, openpyxl, ismember) is installed into the conda kernel at
# image-build time via ``--warm``. Simulation is CPU.

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

# Copy the server package tree and the shared peer topology.
COPY --chown=appuser:appuser servers/ezbattery /app/servers/ezbattery
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

# Pre-build the conda environment + EZBattery stack (warm start).
RUN python -m servers.ezbattery.server.ezbattery_server --warm

CMD ["python", "-m", "servers.ezbattery.server.ezbattery_server"]
