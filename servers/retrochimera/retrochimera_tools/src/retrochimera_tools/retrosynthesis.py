"""Retrosynthesis route prediction for the retrochimera server.

The RetroChimera planning model is loaded once per container by a co-located
**sidecar** service (``model_service``) rather than inside every kernel session.
When the server has launched that sidecar it exports its URL as
``RETROCHIMERA_MODEL_SERVICE_URL``; this wrapper proxies planning requests there.

If the variable is unset (e.g. unit tests or a dev run without the sidecar), it
falls back to loading and running the model in-process via ``_model`` — so the
tool behaves identically, just without the shared-service memory savings.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from retrochimera_tools import _model
from orfb_provenance import attach_provenance, distribution_version

# Planning can take many minutes on memory-constrained hosts; allow a generous
# (one-hour) client-side ceiling so slow multi-target runs aren't cut short.
_SERVICE_TIMEOUT_S = 3600.0


def _predict_via_service(base_url: str, smiles: str, num_results: int) -> dict:
    url = base_url.rstrip("/") + "/predict"
    body = json.dumps({"smiles": smiles, "num_results": num_results}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=_SERVICE_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400:
            # Bad input surfaced by the service — preserve ValueError semantics.
            raise ValueError(detail) from exc
        raise RuntimeError(f"retrosynthesis model service error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not reach retrosynthesis model service at {base_url}: {exc.reason}") from exc


def predict_retrosynthesis(smiles: str, num_results: int = 5) -> dict:
    """Plan retrosynthetic routes for a target molecule.

    Args:
        smiles: SMILES string of the target molecule.
        num_results: Number of routes to return (1–50, default 5).

    Returns:
        Dict with ``status``, ``attempts``, ``routes`` (each with ``reactions``,
        ``num_steps`` and ``starting_materials_in_catalog``),
        ``all_routes_resolved``, ``message`` and a structured ``provenance``
        envelope.
    """
    # Validate client-side so bad input fails fast without a service round-trip.
    _model.validate_inputs(smiles, num_results)

    service_url = os.environ.get("RETROCHIMERA_MODEL_SERVICE_URL")
    if service_url:
        result = _predict_via_service(service_url, smiles, num_results)
        backend = "sidecar"
    else:
        result = _model.predict_retrosynthesis(smiles, num_results)
        backend = "in_process"

    inventory_path = os.environ.get("RETROCHIMERA_INVENTORY_PATH")
    route_source = result.get("route_source")
    provenance_warnings = []
    if route_source == "single_step_fallback":
        provenance_warnings.append(
            "Multi-step planning did not produce a route; returned single-step fallback results."
        )
    if route_source != "inventory_match" and not result.get("routes"):
        provenance_warnings.append("No retrosynthetic route was returned.")
    return attach_provenance(
        result,
        tool_name="predict_retrosynthesis",
        tool_distribution="retrochimera-tools",
        tool_version_fallback="0.1.0",
        inputs={"smiles": smiles, "num_results": num_results},
        model={
            "name": "RetroChimera Pistachio retrosynthesis model",
            "version": distribution_version("retrochimera"),
            "artifact": "pistachio",
        },
        configuration={
            "num_results": num_results,
            "num_routes_returned": len(result.get("routes", [])),
            "route_source": route_source,
            "inference_backend": backend,
            "inventory_identifier": Path(inventory_path).name if inventory_path else None,
            "inventory_configured": bool(inventory_path),
        },
        assumptions=[
            "Routes are computational planning suggestions and are not experimentally validated procedures.",
            "Purchasability annotations depend on the user-supplied inventory.",
        ],
        applicability={
            "status": "not_assessed",
            "details": (
                "The planner reports route resolution and catalog annotations, but no calibrated route-success "
                "probability or chemical applicability-domain score."
            ),
        },
        uncertainty={
            "quantified": False,
            "details": "Route rankings do not include calibrated yield, selectivity, safety, or success uncertainty.",
        },
        warnings=provenance_warnings,
    )
