# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Co-located Graphormer redox model service (Agora Workbench sidecar).

The Graphormer redox checkpoints are loaded **once per container** here and
served over loopback HTTP, rather than being loaded inside every isolated kernel
session. This keeps the pattern uniform with the retrochimera server and avoids
reloading the model per session. Launched by the graphormer
``CodeExecutionServer`` via its ``SidecarConfig`` and reached by in-kernel tool
code through the ``GRAPHORMER_MODEL_SERVICE_URL`` environment variable.

Endpoints:
    GET  /health   -> 200 {"status": "ok"} once both models are loaded.
    POST /predict  -> {"smiles_list": [str], "property_name": str}
                      -> the dict ``_model.predict`` returns.

Both the ``reduction`` and ``oxidation`` models are warm-loaded synchronously at
startup (before the HTTP server binds), so ``/health`` only answers once
inference is usable and a load failure exits the process immediately.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from graphormer_tools import _model

LOGGER = logging.getLogger("graphormer_tools.model_service")

_DEFAULT_PORT = 8902
_MODEL_LOCK = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/predict":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            smiles_list = payload["smiles_list"]
            property_name = payload["property_name"]
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"invalid request: {exc}"})
            return

        try:
            # Serialize: the model is not concurrency-safe.
            with _MODEL_LOCK:
                result = _model.predict(smiles_list, property_name)
        except ValueError as exc:  # bad input surfaced by the model
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            LOGGER.exception("redox prediction failed")
            self._send_json(500, {"error": str(exc)})
        else:
            self._send_json(200, result)

    def log_message(self, *args) -> None:  # silence per-request stderr logging
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("SIDECAR_HOST", "127.0.0.1")
    port = int(os.environ.get("SIDECAR_PORT", str(_DEFAULT_PORT)))

    # Warm-load both properties synchronously so readiness reflects real usability.
    for property_name in ("reduction", "oxidation"):
        LOGGER.info("Loading Graphormer %s model...", property_name)
        _model._load_model(property_name)
    LOGGER.info("Models ready; serving on %s:%d", host, port)

    server = ThreadingHTTPServer((host, port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
