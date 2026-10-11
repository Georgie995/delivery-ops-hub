"""Live tests against the real n8n workflow on this PC. Skipped (with a reason) when n8n
isn't running or the secret isn't set.

They post each sample in samples/ to the published webhook and check the reply, the CSV log
and the dry-run alert files in runtime/.
"""

import json
import os
import uuid
from pathlib import Path

import pytest

from delivery_ops_hub.send import post_json

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:5678/webhook/delivery-check"
LOG = ROOT / "runtime" / "logs" / "delivery-checks.csv"
ALERTS = ROOT / "runtime" / "dry-run-alerts"


def _secret():
    secret = os.environ.get("OPS_HUB_WEBHOOK_SECRET", "").strip()
    if not secret and os.name == "nt":
        # A secret saved for the Windows user isn't visible to programs started before it was set.
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                secret = winreg.QueryValueEx(key, "OPS_HUB_WEBHOOK_SECRET")[0].strip()
        except OSError:
            pass
    return secret


def _n8n_running():
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:5678/healthz", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


SECRET = _secret()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _n8n_running(), reason="n8n is not running on http://127.0.0.1:5678"),
    pytest.mark.skipif(not SECRET, reason="OPS_HUB_WEBHOOK_SECRET is not set"),
]


def sample(name):
    payload = json.loads((ROOT / "samples" / f"{name}.json").read_text(encoding="utf-8"))
    payload["event_id"] = f"test-{uuid.uuid4().hex[:12]}"   # unique per run, so rows can be found
    return payload


def log_rows():
    if not LOG.exists():
        return []
    return LOG.read_text(encoding="utf-8-sig").splitlines()


def send(payload, secret=None):
    return post_json(URL, payload, secret or SECRET, timeout=15, delays=())


@pytest.mark.parametrize("name, status, alerted", [
    ("clean", "CLEAN", False),
    ("passed_with_warnings", "PASSED_WITH_WARNINGS", False),
    ("problems_found", "PROBLEMS_FOUND", True),
    ("not_checked", "NOT_CHECKED", True),
])
def test_each_status_is_logged_and_alerted_only_when_needed(name, status, alerted):
    payload = sample(name)
    before = len(log_rows())
    result = send(payload)
    assert result.delivered, result.error
    assert result.reply == {"logged": True, "alerted": alerted,
                            "alert_mode": "dry_run" if alerted else "none", "event_id": payload["event_id"]}
    rows = log_rows()
    assert len(rows) == before + 1 + (1 if before == 0 else 0)  # a new log starts with a header row
    assert rows[0].startswith("received_at,event_id,status")
    assert payload["event_id"] in rows[-1] and f",{status}," in rows[-1]
    card = ALERTS / f"teams-{payload['event_id']}.json"
    assert card.exists() == alerted


def test_new_log_file_has_the_excel_marker():
    send(sample("clean"))
    assert LOG.read_bytes().startswith(b"\xef\xbb\xbf")


def test_alert_card_says_what_happened_and_where_to_look():
    payload = sample("problems_found")
    send(payload)
    card = json.loads((ALERTS / f"teams-{payload['event_id']}.json").read_text(encoding="utf-8"))
    content = card["attachments"][0]["content"]
    text = json.dumps(content)
    assert card["type"] == "message" and content["type"] == "AdaptiveCard"
    assert "PROBLEMS FOUND" in text and payload["report_path"] in text
    assert "Probable causes (not verdicts)" in text and "(5 files)" in text


def test_not_checked_card_gives_the_reason():
    payload = sample("not_checked")
    send(payload)
    text = (ALERTS / f"teams-{payload['event_id']}.json").read_text(encoding="utf-8")
    assert "NOT CHECKED: nothing was verified" in text and "does not exist" in text


def test_invalid_payload_is_rejected_with_reasons_and_not_logged():
    before = log_rows()
    result = send(sample("invalid"))
    assert (result.delivered, result.status) == (False, 400)
    assert any("schema_version" in p for p in result.reply["problems"])
    assert log_rows() == before


def test_wrong_secret_is_refused_and_not_logged():
    before = log_rows()
    result = send(sample("clean"), secret="not-the-real-secret")
    assert (result.delivered, result.status) == (False, 403)
    assert log_rows() == before


def test_instruction_like_file_name_is_shown_as_plain_text_and_changes_nothing():
    payload = sample("instruction_like_filename")
    result = send(payload)
    assert result.reply["alerted"] is True            # still treated as PROBLEMS_FOUND
    assert f",PROBLEMS_FOUND," in log_rows()[-1]
    text = (ALERTS / f"teams-{payload['event_id']}.json").read_text(encoding="utf-8")
    assert "IGNORE PREVIOUS INSTRUCTIONS" in text     # displayed, not obeyed


def test_alert_that_cannot_be_saved_is_reported_as_502_and_logged_exactly_once():
    # Hide the alert folder for a moment (our own runtime folder) so saving the alert fails.
    hidden = ALERTS.with_name("dry-run-alerts-hidden-by-test")
    ALERTS.rename(hidden)
    try:
        payload = sample("problems_found")
        before = len(log_rows())
        result = send(payload)
    finally:
        hidden.rename(ALERTS)
    assert (result.delivered, result.status) == (False, 502)
    assert result.reply["logged"] is True and result.reply["alerted"] is False
    assert "could not save the dry-run alert" in result.reply["error"]
    rows = log_rows()
    assert len(rows) == before + 1 and payload["event_id"] in rows[-1]   # logged once, not three times


def test_formula_in_a_value_cannot_run_when_the_log_is_opened_in_excel():
    payload = sample("formula_in_folder_name")
    send(payload)
    row = log_rows()[-1]
    assert "'=HYPERLINK" in row                        # leading apostrophe: Excel shows it as text
