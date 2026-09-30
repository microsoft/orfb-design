"""Build a consistent, JSON-serializable provenance envelope for tool results."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

SCHEMA_VERSION = "1.0"


def distribution_version(distribution: str, fallback: str | None = None) -> str | None:
    """Return an installed distribution version without making provenance fail."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return fallback


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in output:
            output.append(text)
    return output


def _records(result: dict) -> list[dict]:
    for key in ("results", "predictions"):
        records = result.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def _execution_summary(result: dict, extra_warnings: list[str]) -> dict:
    records = _records(result)
    record_statuses = [str(record["status"]).lower() for record in records if record.get("status") is not None]
    top_status = result.get("status")

    if record_statuses:
        successes = sum(status in {"ok", "success", "succeeded", "200"} for status in record_statuses)
        failures = len(record_statuses) - successes
        if successes and failures:
            status = "partial"
        elif failures:
            status = "failed"
        else:
            status = "succeeded"
    elif top_status is None or str(top_status).lower() in {"ok", "success", "succeeded", "200"}:
        status = "succeeded"
    else:
        status = "unknown"

    warnings: list[Any] = list(extra_warnings)
    top_warnings = result.get("warnings")
    if isinstance(top_warnings, list):
        warnings.extend(top_warnings)
    elif top_warnings:
        warnings.append(top_warnings)
    for record in records:
        warning = record.get("warning")
        if warning:
            warnings.append(warning)

    failure_reasons = [record.get("failure_reason") for record in records]
    if status == "failed" and result.get("message"):
        failure_reasons.append(result["message"])

    record_warnings = [
        {
            "index": index,
            "input": record.get("smiles"),
            "message": str(record["warning"]).strip(),
        }
        for index, record in enumerate(records)
        if record.get("warning")
    ]
    return {
        "status": status,
        "raw_status": top_status,
        "warnings": _unique_strings(warnings),
        "failure_reasons": _unique_strings(failure_reasons),
        "record_counts": {
            "total": len(records),
            "succeeded": sum(value in {"ok", "success", "succeeded", "200"} for value in record_statuses),
            "failed": sum(value not in {"ok", "success", "succeeded", "200"} for value in record_statuses),
            "warned": len(record_warnings),
        },
        "record_warnings": record_warnings,
    }


def attach_provenance(
    result: dict,
    *,
    tool_name: str,
    tool_distribution: str,
    tool_version_fallback: str,
    inputs: dict,
    model: dict,
    configuration: dict | None = None,
    assumptions: list[str] | None = None,
    applicability: dict | None = None,
    uncertainty: dict | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Return ``result`` with a consistent top-level ``provenance`` envelope."""
    normalized_inputs = _json_value(inputs)
    canonical_inputs = json.dumps(normalized_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    output = dict(result)
    output["provenance"] = {
        "schema_version": SCHEMA_VERSION,
        "tool": {
            "name": tool_name,
            "package": tool_distribution,
            "version": distribution_version(tool_distribution, tool_version_fallback),
            "build_commit": os.environ.get("ORFB_BUILD_COMMIT"),
        },
        "input": {
            "values": normalized_inputs,
            "sha256": hashlib.sha256(canonical_inputs.encode("utf-8")).hexdigest(),
        },
        "model": _json_value(model),
        "configuration": _json_value(configuration or {}),
        "execution": {
            "invocation_id": str(uuid.uuid4()),
            "envelope_created_at_utc": datetime.now(timezone.utc).isoformat(),
            **_execution_summary(output, warnings or []),
        },
        "assumptions": _unique_strings(assumptions or []),
        "applicability": _json_value(
            applicability
            or {
                "status": "not_assessed",
                "details": "No calibrated applicability-domain assessment is available for this tool.",
            }
        ),
        "uncertainty": _json_value(
            uncertainty
            or {
                "quantified": False,
                "details": "This tool does not return calibrated predictive uncertainty.",
            }
        ),
    }
    return output
