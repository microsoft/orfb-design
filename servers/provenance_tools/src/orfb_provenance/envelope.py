"""Build compact scientific provenance for tool results."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any

SCHEMA_VERSION = "1.0"


def distribution_version(distribution: str, fallback: str | None = None) -> str | None:
    """Return an installed distribution version without making provenance fail."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return fallback


def attach_provenance(
    result: dict,
    *,
    tool_distribution: str,
    tool_version_fallback: str,
    model: dict,
    configuration: dict | None = None,
    applicability: str,
    uncertainty: str,
) -> dict:
    """Return ``result`` with compact metadata absent from ordinary MCP logs."""
    output = dict(result)
    provenance: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": distribution_version(tool_distribution, tool_version_fallback),
        "model_version": model.get("version"),
        "applicability": applicability,
        "uncertainty": uncertainty,
    }
    if model.get("artifact"):
        provenance["model_artifact"] = model["artifact"]
    if configuration:
        provenance["configuration"] = configuration
    build_commit = os.environ.get("ORFB_BUILD_COMMIT")
    if build_commit:
        provenance["build_commit"] = build_commit
    output["provenance"] = provenance
    return output
