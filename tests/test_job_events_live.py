"""Live tests for job events from job-watch (project D) against the real n8n workflow.
Skipped (with a reason) when n8n isn't running or the secret isn't set.
"""

import json

import pytest

from test_workflow_live import ALERTS, LOG, ROOT, log_rows, pytestmark, sample, send  # noqa: F401

JOB_LOG = ROOT / "runtime" / "logs" / "job-events.csv"


def job_rows():
    return JOB_LOG.read_text(encoding="utf-8-sig").splitlines() if JOB_LOG.exists() else []


@pytest.mark.parametrize("name, event, alerted", [
    ("job_started", "started", False),
    ("job_finished", "finished", True),
    ("job_failed", "failed", True),
    ("job_stalled", "stalled", True),
    ("job_resumed", "resumed", True),
    ("job_interrupted", "interrupted", True),
])
def test_each_job_event_is_logged_separately_and_alerted_when_it_matters(name, event, alerted):
    payload = sample(name)
    delivery_rows_before, before = len(log_rows()), len(job_rows())
    result = send(payload)
    assert result.delivered, result.error
    assert result.reply == {"logged": True, "alerted": alerted,
                            "alert_mode": "dry_run" if alerted else "none", "event_id": payload["event_id"]}
    rows = job_rows()
    assert len(rows) == before + 1 + (1 if before == 0 else 0)          # a new log starts with a header row
    assert rows[0].startswith("received_at,event_id,job_name,program,event")
    assert payload["event_id"] in rows[-1] and f",{event}," in rows[-1]
    assert len(log_rows()) == delivery_rows_before                     # the delivery-check log is untouched
    assert (ALERTS / f"teams-{payload['event_id']}.json").exists() == alerted


def test_alert_cards_say_what_happened_to_which_job():
    expectations = {
        "job_failed": ["FAILED: Restore TAPE001", "exit code 3", "drive not ready"],
        "job_stalled": ["STALLED: Restore TAPE001", "No progress for 0:10:00", "clip_0457.mov"],
        "job_resumed": ["RESUMED: Restore TAPE001", "stalled for 0:23:00"],
        "job_finished": ["FINISHED: Restore TAPE001", "2:14:05", "1204 files"],
        "job_interrupted": ["INTERRUPTED: Restore TAPE001", "outcome unknown"],
    }
    for name, phrases in expectations.items():
        payload = sample(name)
        send(payload)
        text = json.dumps(json.loads((ALERTS / f"teams-{payload['event_id']}.json").read_text(encoding="utf-8")))
        for phrase in phrases:
            assert phrase in text, (name, phrase)


def test_an_invalid_job_event_is_refused_and_not_logged():
    before = job_rows()
    result = send(sample("job_invalid"))
    assert (result.delivered, result.status) == (False, 400)
    assert any("event must be one of" in p for p in result.reply["problems"])
    assert job_rows() == before


def test_a_formula_in_a_job_name_cannot_run_in_excel():
    send(sample("job_formula_in_name"))
    assert "'=HYPERLINK" in job_rows()[-1]
