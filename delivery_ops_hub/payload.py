"""Build the small JSON message ("payload") sent to n8n. Format: docs/payload-schema.md.

The full findings stay in the report on disk. The message carries only what a person
needs to decide whether to look. File names in summaries are data, never instructions.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
STATUSES = ("CLEAN", "PASSED_WITH_WARNINGS", "PROBLEMS_FOUND", "NOT_CHECKED")
_FROM_REPORT = {"CLEAN": "CLEAN", "PASSED WITH WARNINGS": "PASSED_WITH_WARNINGS",
                "PROBLEMS FOUND": "PROBLEMS_FOUND"}
MAX_CAUSES = 3


def build_from_report(report_folder, now=None, event_id=None):
    report_folder = Path(report_folder)
    report = json.loads((report_folder / "report.json").read_text(encoding="utf-8"))
    header = report["header"]
    return _envelope(
        now, event_id,
        status=_FROM_REPORT[header["result"]],
        exit_code=header["exit_code"],
        tree=header["tree"],
        report_path=str(report_folder),
        counts=header["counts"],
        top_causes=[{"code": c["code"], "severity": c["severity"], "summary": c["summary"],
                     "file_count": len(c["paths"])} for c in report["causes"][:MAX_CAUSES]],
        error_message=None,
        tool_version=header.get("version"),
    )


def build_not_checked(tree, reason, exit_code, max_chars=500, now=None, event_id=None):
    """manifest-doctor couldn't check: there's no report, only a reason."""
    reason = reason.strip() or "manifest-doctor stopped without saying why"
    if len(reason) > max_chars:
        reason = reason[:max_chars - 1] + "…"  # shortened, and visibly so
    return _envelope(now, event_id, status="NOT_CHECKED", exit_code=exit_code, tree=str(tree),
                     report_path=None, counts=None, top_causes=[], error_message=reason, tool_version=None)


def _envelope(now, event_id, **fields):
    now = now or datetime.now().astimezone()
    return {"schema_version": SCHEMA_VERSION,
            "event_id": event_id or uuid.uuid4().hex,
            "sent_at": now.isoformat(timespec="seconds"),
            **fields}


def validate(payload):
    """Return a list of problems (empty means valid). n8n applies the same rules."""
    problems = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(payload.get("event_id"), str) or not payload.get("event_id"):
        problems.append("event_id is missing")
    if payload.get("status") not in STATUSES:
        problems.append(f"status must be one of {', '.join(STATUSES)}")
    for key in ("sent_at", "tree"):
        if not payload.get(key):
            problems.append(f"{key} is missing")
    if payload.get("status") == "NOT_CHECKED":
        if not payload.get("error_message"):
            problems.append("error_message is required for NOT_CHECKED")
    elif payload.get("status") in STATUSES:
        if not isinstance(payload.get("counts"), dict):
            problems.append("counts is missing")
        if not payload.get("report_path"):
            problems.append("report_path is missing")
    if not isinstance(payload.get("top_causes", []), list):
        problems.append("top_causes must be a list")
    return problems
