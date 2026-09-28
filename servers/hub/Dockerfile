# ORFB Design Hub — RouterServer
#
# Aggregates the orfb / graphormer / retrochimera servers behind one MCP
# endpoint. The router is lightweight (no conda model env) — it only needs
# agora-workbench installed, which the base image already provides.
#
# Prerequisite — build the PyPI-backed agora-workbench base image:
#   make base-image
#
# Then build from the orfb-design repo root:
#   docker build -f servers/hub/Dockerfile -t orfb-hub:local .

ARG BASE_IMAGE=mcp-server-base:local
FROM ${BASE_IMAGE}

COPY --chown=appuser:appuser servers/hub /app/servers/hub
COPY --chown=appuser:appuser servers/peers.py /app/servers/peers.py
COPY --chown=appuser:appuser servers/__init__.py /app/servers/__init__.py

CMD ["python", "-m", "servers.hub.server.router_server"]
