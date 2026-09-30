"""Tests for the shared structured provenance envelope."""

from orfb_provenance import attach_provenance


def _attach(result, configuration=None):
    return attach_provenance(
        result,
        tool_distribution="missing-example-distribution",
        tool_version_fallback="1.2.3",
        model={"name": "example", "version": "4.5.6"},
        configuration=configuration,
        applicability="not_assessed",
        uncertainty="not_quantified",
    )


def test_compact_provenance_contains_provider_owned_metadata():
    result = _attach({"results": []})

    assert result["provenance"] == {
        "schema_version": "1.0",
        "tool_version": "1.2.3",
        "model_version": "4.5.6",
        "applicability": "not_assessed",
        "uncertainty": "not_quantified",
    }


def test_optional_metadata_is_only_included_when_present(monkeypatch):
    monkeypatch.setenv("ORFB_BUILD_COMMIT", "abc123")
    result = attach_provenance(
        {},
        tool_distribution="missing-example-distribution",
        tool_version_fallback="1.2.3",
        model={"version": None, "artifact": "checkpoint.pt"},
        configuration={"reference": "SHE"},
        applicability="not_assessed",
        uncertainty="not_quantified",
    )

    assert result["provenance"]["model_artifact"] == "checkpoint.pt"
    assert result["provenance"]["configuration"] == {"reference": "SHE"}
    assert result["provenance"]["build_commit"] == "abc123"
