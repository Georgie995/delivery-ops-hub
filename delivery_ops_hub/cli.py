"""The sender's commands.

    python -m delivery_ops_hub check TREE --manifest FILE [other manifest-doctor options]
    python -m delivery_ops_hub resend

Exit codes: 0 delivered (clean or warnings), 1 delivered (problems found),
2 delivered (not checked), 3 not delivered, or the sender's own settings are wrong.
"""

import argparse
import json
import sys

from . import outbox
from .payload import build_from_report, build_not_checked
from .runner import run_manifest_doctor
from .send import post_json
from .settings import SettingsError, get_secret, load_settings

EXIT_FOR_STATUS = {"CLEAN": 0, "PASSED_WITH_WARNINGS": 0, "PROBLEMS_FOUND": 1, "NOT_CHECKED": 2}
NOT_DELIVERED = 3


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = _parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        secret = get_secret()  # checked first, so a long check isn't wasted on a missing secret
        if args.command == "check":
            return _check(args, settings, secret)
        return _resend(settings, secret)
    except (SettingsError, ValueError) as error:
        print(f"delivery-ops-hub: error: {error}", file=sys.stderr)
        return NOT_DELIVERED


def _parser():
    parser = argparse.ArgumentParser(prog="delivery-ops-hub",
                                     description="Check a delivery with manifest-doctor and send the result to n8n.")
    parser.add_argument("--config", default="ops-hub.toml", help="settings file (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="run manifest-doctor and send the result")
    check.add_argument("tree", help="the folder to check")
    check.add_argument("doctor_args", nargs=argparse.REMAINDER, help="passed unchanged to manifest-doctor")
    commands.add_parser("resend", help="send messages waiting in the outbox")
    return parser


def _check(args, settings, secret):
    run = run_manifest_doctor(settings["manifest_doctor_path"], [args.tree, *args.doctor_args],
                              settings["reports_dir"])
    if run.stdout:
        print(run.stdout)
    if run.exit_code in (0, 1) and run.report_folder is not None:
        payload = build_from_report(run.report_folder)
    else:
        # Exit code 2, a crash, or "finished" without writing a report: nothing was verified.
        reason = run.stderr
        if run.exit_code != 2:
            reason = f"manifest-doctor ended with exit code {run.exit_code} and wrote no report. {run.stderr}"
        payload = build_not_checked(args.tree, reason, run.exit_code, settings["max_error_chars"])
    return _deliver(payload, settings, secret)


def _deliver(payload, settings, secret):
    result = post_json(settings["webhook_url"], payload, secret, timeout=settings["timeout_seconds"])
    status = payload["status"]
    if result.delivered:
        reply = result.reply or {}
        print(f"{status}: delivered to n8n (logged: {reply.get('logged')}, alerted: {reply.get('alerted')}, "
              f"alert mode: {reply.get('alert_mode')})")
        return EXIT_FOR_STATUS[status]
    if result.status == 502 and (result.reply or {}).get("logged") is True:
        detail = (result.reply or {}).get("error", "no detail")
        print(f"{status}: LOGGED, BUT TEAMS ALERT FAILED ({detail}). Tell the team directly.", file=sys.stderr)
        return NOT_DELIVERED
    path = outbox.save(settings["outbox_dir"], payload)
    print(f"{status}: NOT DELIVERED to n8n ({_why(result)}). Saved to {path}. "
          "Run 'python -m delivery_ops_hub resend' once n8n is reachable.", file=sys.stderr)
    return NOT_DELIVERED


def _why(result):
    """The error, plus what it usually means when that isn't obvious."""
    if result.status == 404:
        # Seen in Georgi's hands-on run: resending straight after starting n8n.
        return (f"{result.error}: n8n is still starting, or the workflow isn't published. "
                "Wait 20 seconds and resend")
    return result.error


def _resend(settings, secret):
    waiting = outbox.pending(settings["outbox_dir"])
    if not waiting:
        print("Nothing to resend: the outbox is empty.")
        return 0
    sent = 0
    for path in waiting:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = post_json(settings["webhook_url"], payload, secret, timeout=settings["timeout_seconds"])
        logged = result.delivered or (result.status == 502 and (result.reply or {}).get("logged") is True)
        if logged:
            outbox.remove_after_confirmed(path)
            sent += 1
        else:
            print(f"Still not delivered: {path.name} ({_why(result)})", file=sys.stderr)
    print(f"Resent {sent} of {len(waiting)} message(s).")
    return 0 if sent == len(waiting) else NOT_DELIVERED
