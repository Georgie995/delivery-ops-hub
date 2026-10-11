"""Tests: posting to the webhook, against a local test server (no internet, no n8n)."""

from conftest import SECRET
from delivery_ops_hub.send import post_json

PAYLOAD = {"schema_version": 1, "event_id": "evt-1", "status": "CLEAN"}


def no_wait(seconds):
    pass  # tests don't really wait between retries


def test_delivered_on_first_try_with_the_secret_in_the_header(local_server):
    result = post_json(local_server.url, PAYLOAD, SECRET, sleep=no_wait)
    assert (result.delivered, result.status, result.attempts) == (True, 200, 1)
    assert result.reply == {"logged": True, "alerted": False, "alert_mode": "none"}
    [request] = local_server.requests
    assert request["json"] == PAYLOAD
    assert request["headers"]["X-Ops-Hub-Key"] == SECRET
    assert request["headers"]["Content-Type"] == "application/json"


def test_secret_is_only_in_the_header_never_in_the_body(local_server):
    post_json(local_server.url, PAYLOAD, SECRET, sleep=no_wait)
    assert SECRET not in str(local_server.requests[0]["json"])


def test_server_errors_are_retried_then_succeed(local_server):
    local_server.replies = [(500, {"error": "busy"}), (503, {"error": "busy"})]
    waits = []
    result = post_json(local_server.url, PAYLOAD, SECRET, sleep=waits.append)
    assert (result.delivered, result.attempts) == (True, 3)
    assert waits == [2, 4]


def test_gives_up_after_three_attempts(local_server):
    local_server.replies = [(500, {})] * 3
    result = post_json(local_server.url, PAYLOAD, SECRET, sleep=no_wait)
    assert (result.delivered, result.status, result.attempts) == (False, 500, 3)


def test_wrong_secret_or_invalid_payload_is_not_retried(local_server):
    for status in (400, 403):
        local_server.requests.clear()
        local_server.replies = [(status, {"error": "no"})]
        result = post_json(local_server.url, PAYLOAD, SECRET, sleep=no_wait)
        assert (result.delivered, result.status, result.attempts) == (False, status, 1)


def test_logged_but_alert_failed_is_not_retried(local_server):
    # Retrying would write the same check to the log twice.
    local_server.replies = [(502, {"logged": True, "alerted": False, "error": "Teams unreachable"})]
    result = post_json(local_server.url, PAYLOAD, SECRET, sleep=no_wait)
    assert (result.delivered, result.status, result.attempts) == (False, 502, 1)
    assert result.reply["logged"] is True


def test_nothing_listening_is_retried_then_reported(closed_port_url):
    result = post_json(closed_port_url, PAYLOAD, SECRET, sleep=no_wait)
    assert (result.delivered, result.status, result.attempts) == (False, None, 3)
    assert result.error


def test_slow_server_times_out(local_server):
    local_server.replies = [("hang", 1.5)] * 3
    result = post_json(local_server.url, PAYLOAD, SECRET, timeout=0.3, sleep=no_wait)
    assert (result.delivered, result.attempts) == (False, 3)
    assert "timed out" in result.error


def test_error_text_never_contains_the_secret(closed_port_url):
    result = post_json(closed_port_url, PAYLOAD, SECRET, sleep=no_wait)
    assert SECRET not in result.error
