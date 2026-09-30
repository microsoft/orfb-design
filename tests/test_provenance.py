"""Tests for the shared structured provenance envelope."""

from orfb_provenance import attach_provenance


def _attach(result, inputs):
    return attach_provenance(
        result,
        tool_name="example_tool",
        tool_distribution="missing-example-distribution",
        tool_version_fallback="1.2.3",
        inputs=inputs,
        model={"name": "example", "version": "4.5.6"},
    )


def test_input_hash_is_deterministic_and_order_independent():
    first = _attach({"results": []}, {"b": 2, "a": [1, 3]})
    second = _attach({"results": []}, {"a": [1, 3], "b": 2})

    assert first["provenance"]["input"]["sha256"] == second["provenance"]["input"]["sha256"]
    assert first["provenance"]["tool"]["version"] == "1.2.3"


def test_execution_summary_reports_partial_results():
    result = _attach(
        {
            "results": [
                {"status": "succeeded", "warning": "review applicability", "failure_reason": None},
                {"status": "failed", "warning": None, "failure_reason": "invalid input"},
            ]
        },
        {"items": ["valid", "invalid"]},
    )

    execution = result["provenance"]["execution"]
    assert execution["status"] == "partial"
    assert execution["warnings"] == ["review applicability"]
    assert execution["failure_reasons"] == ["invalid input"]
    assert execution["record_counts"] == {"total": 2, "succeeded": 1, "failed": 1, "warned": 1}
    assert execution["record_warnings"] == [
        {"index": 0, "input": None, "message": "review applicability"},
    ]
    assert execution["invocation_id"]
    assert execution["envelope_created_at_utc"].endswith("+00:00")
