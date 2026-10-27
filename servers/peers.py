# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Shared peer topology for the ORFB design server network.

Each domain server passes ``peer_registry=peer_registry_for("<name>")`` into its
``ServerConfig`` so the unified ``{name}_send`` tool can push Python objects
directly between server kernels (e.g. ``orfb_send(to="graphormer")`` to hand a
list of candidate molecules to the redox predictor's kernel).

These are **local-dev defaults** (each server on ``localhost`` at the port its
``docker-compose.yml`` publishes). For the dockerised network, override at launch
with ``AGORA_PEER_REGISTRY`` (inline JSON or a path to a JSON file) — it takes
precedence over the values baked in here. The base URL is the server root (where
``/object-transfer/receive`` lives), NOT the ``/mcp`` endpoint.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

LOGGER = logging.getLogger(__name__)

PEER_URLS: dict[str, str] = {
    "orfb": "http://localhost:8040",
    "graphormer": "http://localhost:8041",
    "retrochimera": "http://localhost:8042",
    "soltrannet": "http://localhost:8043",
    "ezbattery": "http://localhost:8044",
}


def _env_peer_overrides() -> dict[str, str]:
    """Parse ``AGORA_PEER_REGISTRY`` (inline JSON or a path to a JSON file)."""
    raw = os.getenv("AGORA_PEER_REGISTRY", "").strip()
    if not raw:
        return {}
    try:
        if not raw.startswith("{"):
            raw = Path(raw).read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            LOGGER.warning("AGORA_PEER_REGISTRY is not a JSON object; ignoring")
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to parse AGORA_PEER_REGISTRY: %s", exc)
        return {}


def resolve_peer_urls() -> dict[str, str]:
    """Full peer registry, with ``AGORA_PEER_REGISTRY`` overriding the defaults.

    Used by connector servers (e.g. the hub RouterServer) so their upstream
    topology matches the ``CodeExecutionServer`` peers, which merge the same env
    var. Domain servers don't need this — ``ServerConfig.peer_registry`` plus the
    framework's own ``AGORA_PEER_REGISTRY`` merge handles them.
    """
    return {**PEER_URLS, **_env_peer_overrides()}


def peer_registry_for(server_name: str) -> dict[str, str]:
    """Return the peer registry for *server_name*: every other domain server.

    The server is excluded from its own registry (a server never sends to
    itself). ``ServerConfig`` also drops self defensively, so passing the full
    map would be harmless — excluding it here just keeps the value tidy.
    """
    return {name: url for name, url in PEER_URLS.items() if name != server_name}
