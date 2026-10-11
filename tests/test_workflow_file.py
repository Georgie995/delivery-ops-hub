"""Checks on the workflow file in the repo. No n8n needed."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflows"))
from build_workflow import OUTPUT, build  # noqa: E402

COMMITTED = json.loads(OUTPUT.read_text(encoding="utf-8"))


def test_committed_file_matches_the_readable_sources():
    # If this fails, a src/*.js file changed without rebuilding: run python workflows/build_workflow.py
    assert COMMITTED == build()


def test_no_credentials_are_linked_in_the_repo_copy():
    assert all("credentials" not in node for node in COMMITTED["nodes"])


def test_nothing_that_looks_like_a_secret_or_external_address():
    text = OUTPUT.read_text(encoding="utf-8")
    assert not re.search(r"sig=|api[_-]?key|password|token", text, re.IGNORECASE)
    allowed = {"http://adaptivecards.io/schemas/adaptive-card.json"}
    assert set(re.findall(r"https?://[^\s\"'`]+", text)) <= allowed


def test_every_reply_node_is_reachable_and_the_alert_failure_has_its_own_reply():
    names = {n["name"] for n in COMMITTED["nodes"]}
    targets = {t["node"] for links in COMMITTED["connections"].values() for out in links["main"] for t in out}
    replies = {n for n in names if n.startswith("Reply:")}
    assert replies <= targets
    assert "Reply: logged, alert failed (502)" in replies
