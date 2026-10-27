# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Co-located RetroChimera model service (Agora Workbench sidecar).

The RetroChimera planning stack (a ~4.4 GB checkpoint that balloons to ~10 GB
resident, plus a rule-application worker pool) is far too heavy to load inside
every isolated kernel session. This module is the **sidecar** that loads the
model **once per container** and serves route planning over loopback HTTP, so
kernels stay cheap. It is launched by the retrochimera ``CodeExecutionServer``
via its ``SidecarConfig`` and reached by in-kernel tool code through the
``RETROCHIMERA_MODEL_SERVICE_URL`` environment variable.

Endpoints:
    GET  /health   -> 200 {"status": "ok"} once the model is loaded.
    POST /predict  -> {"smiles": str, "num_results": int} -> route dict
                      (the same payload ``_model.predict_retrosynthesis`` returns).

The model is loaded synchronously at startup *before* the HTTP server binds, so
a failed load exits the process (the sidecar manager then reports the failure
immediately) and ``/health`` only ever answers once planning is actually usable.
Predictions are serialized with a lock: the model is not safe for concurrent
inference, and serializing bounds peak memory.

Long-running stability
----------------------
Two mitigations keep a long-lived container healthy:

* RetroChimera 1.3.0 escalates rule-application worker teardown from SIGTERM to
  SIGKILL when required, preventing timed-out workers from being abandoned.
* The recycle guard below periodically re-forks the rule-application worker
  pools as defence-in-depth against memory growth *inside* those long-lived
  workers. Tunable with ``RETROCHIMERA_RECYCLE_AFTER_JOBS`` (default 100, ``0``
  disables) and ``RETROCHIMERA_RECYCLE_RSS_MB`` (default unset / disabled).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from retrochimera_tools import _model

LOGGER = logging.getLogger("retrochimera_tools.model_service")

_DEFAULT_PORT = 8901
_MODEL_LOCK = threading.Lock()

# Default number of predictions between rule-application pool recycles.
_DEFAULT_RECYCLE_AFTER_JOBS = 100

# Guarded by ``_MODEL_LOCK``.
_jobs_since_recycle = 0


def _int_env(name: str, default: int) -> int:
    """Read a non-negative integer env var, falling back to ``default`` if unusable."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        LOGGER.warning("Ignoring non-integer %s=%r; using %d", name, raw, default)
        return default
    return value if value >= 0 else default


def _maybe_recycle_worker_pools() -> None:
    """Recycle the rule-application worker pools when a threshold is crossed.

    Called with ``_MODEL_LOCK`` held, so no prediction can be in flight. A recycle
    failure is logged rather than raised, and leaves the counter untouched so the
    next prediction retries; if the pool really is unusable, that prediction fails
    loudly on its own.
    """
    global _jobs_since_recycle

    _jobs_since_recycle += 1
    rss_mb = _model.total_rss_mb()
    reasons = []

    after_jobs = _int_env("RETROCHIMERA_RECYCLE_AFTER_JOBS", _DEFAULT_RECYCLE_AFTER_JOBS)
    if after_jobs and _jobs_since_recycle >= after_jobs:
        reasons.append(f"{_jobs_since_recycle} jobs since last recycle (limit {after_jobs})")

    rss_limit = _int_env("RETROCHIMERA_RECYCLE_RSS_MB", 0)
    if rss_limit and rss_mb is not None and rss_mb >= rss_limit:
        reasons.append(f"RSS {rss_mb:.0f} MiB (limit {rss_limit} MiB)")

    LOGGER.info(
        "prediction complete: jobs_since_recycle=%d workers=%d rss_mb=%s",
        _jobs_since_recycle,
        _model.live_worker_count(),
        f"{rss_mb:.0f}" if rss_mb is not None else "unknown",
    )

    if not reasons:
        return

    LOGGER.info("Recycling rule application worker pools: %s", "; ".join(reasons))
    try:
        recycled = _model.recycle_rule_application_pools()
    except Exception:
        LOGGER.exception("Failed to recycle rule application worker pools")
        return

    _jobs_since_recycle = 0
    LOGGER.info(
        "Recycled %d rule application pool(s); workers=%d rss_mb=%s",
        recycled,
        _model.live_worker_count(),
        f"{_model.total_rss_mb() or 0:.0f}",
    )


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
            smiles = payload["smiles"]
            num_results = int(payload.get("num_results", _model.DEFAULT_NUM_RESULTS))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"invalid request: {exc}"})
            return

        try:
            # Serialize: the model is not concurrency-safe, and one-at-a-time
            # planning bounds peak memory on a shared host. The recycle guard runs
            # in the same critical section so no prediction is in flight while the
            # worker pools are being re-forked.
            with _MODEL_LOCK:
                try:
                    result = _model.predict_retrosynthesis(smiles, num_results)
                finally:
                    # Runs for failed predictions too: a failure often means a
                    # wedged worker was just restarted, which is precisely when
                    # recycling is worth doing. Guarded so a fault in the guard
                    # can never mask the planning exception being propagated.
                    try:
                        _maybe_recycle_worker_pools()
                    except Exception:
                        LOGGER.exception("recycle guard failed")
        except ValueError as exc:  # bad input surfaced by the planner
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            LOGGER.exception("retrosynthesis prediction failed")
            self._send_json(500, {"error": str(exc)})
        else:
            self._send_json(200, result)

    def log_message(self, *args) -> None:  # silence per-request stderr logging
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("SIDECAR_HOST", "127.0.0.1")
    port = int(os.environ.get("SIDECAR_PORT", str(_DEFAULT_PORT)))

    LOGGER.info("Validating user-supplied purchasability inventory...")
    _model._load_inventory()

    override = _model._num_processes_override()
    LOGGER.info(
        "Loading RetroChimera model (num_processes=%s)...",
        override if override is not None else "auto (cpu_count)",
    )
    # Load synchronously so a failure exits before we advertise readiness.
    _model._load_model()
    LOGGER.info(
        "Model ready; serving on %s:%d (workers=%d, rss_mb=%s, recycle_after_jobs=%d, recycle_rss_mb=%d)",
        host,
        port,
        _model.live_worker_count(),
        f"{_model.total_rss_mb() or 0:.0f}",
        _int_env("RETROCHIMERA_RECYCLE_AFTER_JOBS", _DEFAULT_RECYCLE_AFTER_JOBS),
        _int_env("RETROCHIMERA_RECYCLE_RSS_MB", 0),
    )

    server = ThreadingHTTPServer((host, port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
