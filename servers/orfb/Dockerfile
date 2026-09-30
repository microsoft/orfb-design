# ORFB Design MCP Server (RDKit molecular characterization)
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/orfb/Dockerfile -t orfb-server:local .

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

# Copy the ORFB server package tree (includes the orfb_tools kernel package) and
# the shared peer topology.
COPY --chown=appuser:appuser servers/orfb /app/servers/orfb
COPY --chown=appuser:appuser servers/provenance_tools /app/servers/provenance_tools
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

# Pre-build the conda environment (warm start) so the container starts
# immediately at runtime without a network install.
RUN python -m servers.orfb.server.orfb_server --warm

CMD ["python", "-m", "servers.orfb.server.orfb_server"]
