# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""ORFB Design Hub — RouterServer aggregating the ORFB design network.

A single MCP endpoint that fronts the five domain servers in this repo:

  * ``orfb``         — RDKit molecular characterization (properties, similarity,
                       synthetic accessibility).
  * ``graphormer``   — redox potential prediction (reduction / oxidation).
  * ``retrochimera`` — retrosynthesis route prediction.
  * ``soltrannet``   — aqueous-solubility (logS) prediction.
  * ``ezbattery``    — cell-level RFB simulation (device KPIs / negolyte eval).

The agent sees one ``execute_{name}_code`` tool per upstream plus a unified
``search_orfb-hub_tools`` discovery tool. Upstream base URLs are taken from the
shared peer registry (overridable per-upstream via the ``*_UPSTREAM_URL`` env
vars below) so the hub matches the network topology in ``servers/peers.py``.

The hub also composes a **unified state graph** spanning all five upstreams and
exposes it via ``plan_orfb-hub_workflow``. Each upstream owns a self-consistent
state island and the domain tools are designed to be run independently, so the
hub deliberately declares **no cross-server bridge edges** — the composed graph
is the union of five self-contained islands. (The framework supports injecting
synthetic ``BridgeEdge`` overlays here should a fixed end-to-end campaign ever
warrant stitching the islands together.)

Usage:
    python -m servers.hub.server.router_server
"""

import asyncio
import os

from agora_workbench.connector import RouterServer
from agora_workbench.connector.models import RouterConfig, UpstreamConfig

from servers.peers import resolve_peer_urls


def _upstream_url(name: str, peers: dict[str, str]) -> str:
    return os.getenv(f"{name.upper()}_UPSTREAM_URL") or peers[name]


_PEERS = resolve_peer_urls()

config = RouterConfig(
    name="orfb-hub",
    description=(
        "Unified entry point for the ORFB (organic redox-flow-battery) molecule "
        "design network: RDKit characterization (orfb), redox potential "
        "prediction (graphormer), retrosynthesis route planning (retrochimera), "
        "aqueous-solubility prediction (soltrannet) and cell-level RFB simulation "
        "(ezbattery)."
    ),
    upstreams=[
        UpstreamConfig(name="orfb", url=_upstream_url("orfb", _PEERS)),
        UpstreamConfig(name="graphormer", url=_upstream_url("graphormer", _PEERS)),
        UpstreamConfig(name="retrochimera", url=_upstream_url("retrochimera", _PEERS)),
        UpstreamConfig(name="soltrannet", url=_upstream_url("soltrannet", _PEERS)),
        UpstreamConfig(name="ezbattery", url=_upstream_url("ezbattery", _PEERS)),
    ],
    # No cross-server bridges: the domain tools run independently, so the
    # composed state graph is intentionally the union of five self-contained
    # per-upstream islands.
    bridges=[],
)

server = RouterServer(config)

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    asyncio.run(server.run_http(host=host, port=port))
