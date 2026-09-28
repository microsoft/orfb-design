"""Redox potential predictors (reduction / oxidation) for the graphormer server.

Potentials are in volts versus the standard hydrogen electrode (SHE).

The Graphormer redox model is loaded once per container by a co-located
**sidecar** service (``model_service``) rather than inside every kernel session.
When the server has launched that sidecar it exports its URL as
``GRAPHORMER_MODEL_SERVICE_URL``; these wrappers proxy inference there. If the
variable is unset (unit tests or a dev run without the sidecar), they fall back
to loading and running the model in-process via ``_model``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from graphormer_tools import _model

_SERVICE_TIMEOUT_S = 300.0


def _predict_via_service(base_url: str, smiles_list: list[str], property_name: str) -> dict:
    url = base_url.rstrip("/") + "/predict"
    body = json.dumps({"smiles_list": smiles_list, "property_name": property_name}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=_SERVICE_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400:
            # Bad input surfaced by the service — preserve ValueError semantics.
            raise ValueError(detail) from exc
        raise RuntimeError(f"graphormer model service error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"could not reach graphormer model service at {base_url}: {exc.reason}"
        ) from exc


def _predict(smiles_list: list[str], property_name: str) -> dict:
    # Validate client-side so bad input fails fast without a service round-trip.
    _model.validate_inputs(smiles_list)

    service_url = os.environ.get("GRAPHORMER_MODEL_SERVICE_URL")
    if service_url:
        return _predict_via_service(service_url, smiles_list, property_name)
    return _model.predict(smiles_list, property_name)


def predict_reduction_potential(smiles_list: list[str]) -> dict:
    """Predict reduction potentials (V vs SHE) for a list of molecules.

    Args:
        smiles_list: SMILES strings of candidate molecules (max 32).

    Returns:
        Dict with ``property_name`` ('reduction'), ``unit``, ``num_molecules``
        and ``predictions`` — one record per molecule with ``smiles``,
        ``status``, ``potential``, ``unit`` and ``failure_reason``.
    """
    return _predict(smiles_list, "reduction")


def predict_oxidation_potential(smiles_list: list[str]) -> dict:
    """Predict oxidation potentials (V vs SHE) for a list of molecules.

    Args:
        smiles_list: SMILES strings of candidate molecules (max 32).

    Returns:
        Dict with ``property_name`` ('oxidation'), ``unit``, ``num_molecules``
        and ``predictions`` — one record per molecule with ``smiles``,
        ``status``, ``potential``, ``unit`` and ``failure_reason``.
    """
    return _predict(smiles_list, "oxidation")
