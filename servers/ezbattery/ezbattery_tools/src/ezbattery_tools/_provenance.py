"""EZBattery provenance metadata that must not invalidate completed simulations."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def upstream_model_metadata() -> dict:
    commit_file = Path(__file__).resolve().parent / "_vendor" / "EZBattery" / "UPSTREAM_COMMIT"
    try:
        commit = commit_file.read_text(encoding="utf-8").strip()
    except OSError:
        return {
            "name": "EZBattery",
            "version": None,
            "version_type": "upstream_git_commit",
            "version_status": "The staged UPSTREAM_COMMIT metadata file is unavailable.",
        }
    return {"name": "EZBattery", "version": commit, "version_type": "upstream_git_commit"}
