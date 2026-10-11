"""Tests: building the message sent to n8n."""

from datetime import datetime, timezone

from delivery_ops_hub.payload import build_from_report, build_not_checked, validate

NOW = datetime(2026, 10, 11, 18, 32, 5, tzinfo=timezone.utc)


def test_problems_found_report_becomes_a_small_payload(make_report):
    folder = make_report()
    payload = build_from_report(folder, now=NOW, event_id="evt-1")
    assert payload == {
        "schema_version": 1,
        "event_id": "evt-1",
        "sent_at": "2026-10-11T18:32:05+00:00",
        "status": "PROBLEMS_FOUND",
        "exit_code": 1,
        "tree": "D:/Incoming/ShowA",
        "report_path": str(folder),
        "counts": {"ERROR": 2, "WARNING": 1, "INFO": 0},
        "top_causes": [
            {"code": "CAUSE_DUPLICATE_LISTING", "severity": "ERROR",
             "summary": "1 path is listed more than once.", "file_count": 1},
            {"code": "CAUSE_WRAPPER_FOLDER", "severity": "WARNING",
             "summary": "3 files only match once...", "file_count": 3},
        ],
        "error_message": None,
        "tool_version": "0.1.0",
    }
    assert validate(payload) == []


def test_clean_and_warning_results_map_to_their_status(make_report):
    clean = build_from_report(make_report("r1", result="CLEAN", exit_code=0, causes=[]))
    warned = build_from_report(make_report("r2", result="PASSED WITH WARNINGS", exit_code=0))
    assert (clean["status"], warned["status"]) == ("CLEAN", "PASSED_WITH_WARNINGS")


def test_only_the_top_three_causes_are_sent(make_report):
    causes = [{"code": f"CAUSE_{n}", "severity": "WARNING", "summary": str(n), "paths": ["x"], "note": ""}
              for n in range(5)]
    payload = build_from_report(make_report(causes=causes))
    assert [c["code"] for c in payload["top_causes"]] == ["CAUSE_0", "CAUSE_1", "CAUSE_2"]


def test_full_findings_are_not_sent():
    # The report stays on disk; the message only carries what a person needs to decide to look.
    import inspect
    from delivery_ops_hub import payload as module
    assert "findings" not in inspect.signature(module.build_from_report).parameters


def test_every_event_gets_a_unique_id(make_report):
    folder = make_report()
    assert build_from_report(folder)["event_id"] != build_from_report(folder)["event_id"]


def test_not_checked_payload_carries_the_reason(make_report):
    payload = build_not_checked("D:/Incoming/ShowA", "delivery-verify: error: D:/x does not exist",
                                exit_code=2, now=NOW, event_id="evt-2")
    assert payload["status"] == "NOT_CHECKED"
    assert payload["exit_code"] == 2
    assert payload["error_message"] == "delivery-verify: error: D:/x does not exist"
    assert (payload["report_path"], payload["counts"], payload["top_causes"]) == (None, None, [])
    assert validate(payload) == []


def test_long_error_messages_are_shortened_with_a_marker():
    payload = build_not_checked("D:/x", "e" * 900, exit_code=2, max_chars=500)
    assert len(payload["error_message"]) == 500
    assert payload["error_message"].endswith("…")


def test_validate_reports_each_problem():
    problems = validate({"schema_version": 2, "status": "FINE"})
    assert any("schema_version" in p for p in problems)
    assert any("status" in p for p in problems)
    assert any("event_id" in p for p in problems)
