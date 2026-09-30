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
# source is fetched from a pinned upstream commit during the image build. The
# numeric stack (numpy<2, scipy, pandas, openpyxl, ismember) is installed into
# the conda kernel at image-build time via ``--warm``. Simulation is CPU.

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

# Copy the server package tree and the shared peer topology.
COPY --chown=appuser:appuser servers/ezbattery /app/servers/ezbattery
COPY --chown=appuser:appuser servers/provenance_tools /app/servers/provenance_tools
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py
COPY --chown=appuser:appuser scripts/fetch_ezbattery_source.sh /app/scripts/fetch_ezbattery_source.sh

# Stage only the Python package from the pinned upstream GitHub revision. The
# fetch script also copies the normalized license notice and records the commit.
RUN /app/scripts/fetch_ezbattery_source.sh

# Pre-build the conda environment + EZBattery stack (warm start).
RUN python -m servers.ezbattery.server.ezbattery_server --warm

CMD ["python", "-m", "servers.ezbattery.server.ezbattery_server"]
