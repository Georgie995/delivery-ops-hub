"""Assemble workflows/delivery-ops-hub.json from the readable JavaScript in workflows/src/.

The JavaScript files are the source of truth. If a Code node is changed in the n8n editor,
copy the change back into src/ and rebuild, so the repo and n8n never drift apart.

    python workflows/build_workflow.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "delivery-ops-hub.json"
PREP = "Validate and prepare"


def code(name):
    return (HERE / "src" / name).read_text(encoding="utf-8")


def node(id_, name, type_, version, position, parameters, **extra):
    return {"id": id_, "name": name, "type": type_, "typeVersion": version,
            "position": position, "parameters": parameters, **extra}


def if_true(id_, name, position, expression):
    return node(id_, name, "n8n-nodes-base.if", 2.2, position, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{"id": f"{id_}-c1", "leftValue": expression, "rightValue": "",
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and",
        },
        "options": {},
    })


def reply(id_, name, position, status, body_expression):
    return node(id_, name, "n8n-nodes-base.respondToWebhook", 1.1, position, {
        "respondWith": "json", "responseBody": body_expression, "options": {"responseCode": status}})


def build():
    event_id = f"$('{PREP}').first().json.event_id"
    nodes = [
        node("a1", "Delivery check received", "n8n-nodes-base.webhook", 2, [0, 300], {
            "httpMethod": "POST", "path": "delivery-check", "authentication": "headerAuth",
            "responseMode": "responseNode", "options": {}},
            webhookId="5f6f2b1e-6a43-4c7e-9a0b-0d8e1c2a7b10"),
        node("a2", PREP, "n8n-nodes-base.code", 2, [240, 300],
             {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": code("validate_and_prepare.js")}),
        if_true("a3", "Valid?", [480, 300], "={{ $json.valid }}"),
        reply("a4", "Reply: invalid (400)", [720, 520], 400,
              "={{ { error: 'invalid payload', problems: $json.problems } }}"),
        node("a5", "Read existing log", "n8n-nodes-base.readWriteFile", 1.1, [720, 200],
             {"operation": "read", "fileSelector": "/files/logs/delivery-checks.csv", "options": {}},
             alwaysOutputData=True, onError="continueRegularOutput"),
        node("a6", "Make log line", "n8n-nodes-base.code", 2, [960, 200],
             {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": code("make_log_line.js")}),
        node("a7", "Append to log", "n8n-nodes-base.readWriteFile", 1.1, [1200, 200],
             {"operation": "write", "fileName": "/files/logs/delivery-checks.csv", "dataPropertyName": "data",
              "options": {"append": True}}),
        if_true("a8", "Needs alert?", [1440, 200], f"={{{{ $('{PREP}').first().json.needs_alert }}}}"),
        reply("a9", "Reply: logged, no alert", [1680, 360], 200,
              f"={{{{ {{ logged: true, alerted: false, alert_mode: 'none', event_id: {event_id} }} }}}}"),
        node("a10", "Make dry-run alert file", "n8n-nodes-base.code", 2, [1680, 100],
             {"mode": "runOnceForAllItems", "language": "javaScript", "jsCode": code("make_card_file.js")}),
        # If the alert can't be saved, the check is already logged: reply 502 so the sender says
        # so loudly and does NOT retry (a retry would write the same check to the log again).
        node("a11", "Save dry-run alert", "n8n-nodes-base.readWriteFile", 1.1, [1920, 100],
             {"operation": "write", "fileName": "={{ $json.path }}", "dataPropertyName": "data", "options": {}},
             onError="continueErrorOutput"),
        reply("a12", "Reply: logged and alerted", [2160, 0], 200,
              f"={{{{ {{ logged: true, alerted: true, alert_mode: 'dry_run', event_id: {event_id} }} }}}}"),
        reply("a13", "Reply: logged, alert failed (502)", [2160, 200], 502,
              f"={{{{ {{ logged: true, alerted: false, alert_mode: 'dry_run', "
              f"error: 'could not save the dry-run alert: ' + ($json.error?.message ?? 'unknown error'), "
              f"event_id: {event_id} }} }}}}"),
    ]

    def to(target):
        return [{"node": target, "type": "main", "index": 0}]

    connections = {
        "Delivery check received": {"main": [to(PREP)]},
        PREP: {"main": [to("Valid?")]},
        "Valid?": {"main": [to("Read existing log"), to("Reply: invalid (400)")]},
        "Read existing log": {"main": [to("Make log line")]},
        "Make log line": {"main": [to("Append to log")]},
        "Append to log": {"main": [to("Needs alert?")]},
        "Needs alert?": {"main": [to("Make dry-run alert file"), to("Reply: logged, no alert")]},
        "Make dry-run alert file": {"main": [to("Save dry-run alert")]},
        "Save dry-run alert": {"main": [to("Reply: logged and alerted"), to("Reply: logged, alert failed (502)")]},
    }
    # A fixed ID, so re-importing updates the same workflow instead of creating copies.
    return {"id": "deliveryOpsHub01", "name": "delivery-ops-hub", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "active": False, "pinData": {}}


def link_credential(workflow, credential_id, credential_name):
    """For loading into n8n only: point the Webhook node at an existing Header Auth credential.
    The credential's ID and name aren't secret, but they're specific to one n8n install,
    so the repo copy never includes them."""
    for n in workflow["nodes"]:
        if n["type"] == "n8n-nodes-base.webhook":
            n["credentials"] = {"httpHeaderAuth": {"id": credential_id, "name": credential_name}}
    return workflow


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--import-copy", metavar="PATH", help="also write a copy for importing into n8n")
    parser.add_argument("--credential-id", help="link this Header Auth credential in the import copy")
    parser.add_argument("--credential-name", default="Header Auth account")
    args = parser.parse_args()
    OUTPUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    if args.import_copy:
        workflow = build()
        if args.credential_id:
            link_credential(workflow, args.credential_id, args.credential_name)
        Path(args.import_copy).write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote import copy {args.import_copy}")
