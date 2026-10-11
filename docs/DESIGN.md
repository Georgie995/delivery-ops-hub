# delivery-ops-hub: design

Status: **Approved by Georgi on 2026-10-11.**

## 1. What problem this solves

A verification report only helps if someone sees it in time. In real delivery work, a corrupted file was found by the *recipient* because nothing checked or alerted before sending (domain note F1). manifest-doctor now does the checking. This project makes sure the result **reaches a person**:

- every check is logged;
- problems trigger a Teams alert;
- a check that **couldn't run at all** also triggers an alert, because "nothing was checked" must never be silent.

It also demonstrates the integration skills most often named in the job ads researched for this portfolio: webhooks, REST, JSON and n8n (named in 6 of 25 postings).

## 2. Words used in this document

| Term | Meaning |
|---|---|
| **n8n** | A workflow automation tool. You build a workflow by connecting boxes ("nodes") on screen. It runs on your own computer here. |
| **Workflow** | A chain of n8n nodes: receive → check → log → alert → reply. |
| **Webhook** | A web address that waits for messages. When a program sends data to it, the workflow starts. It's like a letterbox that rings a bell when post arrives. |
| **REST / HTTP POST** | The standard way programs send data to a web address. "POST" means "here is some data for you". |
| **JSON** | Structured text with labelled fields, which programs can read reliably. |
| **Payload** | The JSON message the sender posts to the webhook. |
| **Header secret** | A password sent with each message, in a labelled "header". n8n rejects messages without the right one. |
| **Docker / container** | Docker runs n8n in a sealed box (a container) with everything it needs, so nothing else on the PC is changed. |
| **Adaptive Card** | Microsoft's format for rich Teams messages: a title, facts and links laid out neatly. |
| **Dry run** | The alert is built exactly as it would be sent, but saved to a file instead of being posted to Teams. |
| **HTTP status code** | The number a web server replies with: `200` = OK, `400` = your message was invalid, `401`/`403` = not allowed, `5xx` = the server had a problem. |

## 3. The whole flow

```
you run:  python -m delivery_ops_hub check D:/Incoming/ShowA --manifest ShowA.md5
            │
            ├─ 1. runs manifest-doctor (unchanged), reads its exit code and report.json
            ├─ 2. builds a small JSON payload (or a NOT_CHECKED payload if exit code 2)
            └─ 3. POSTs it to the n8n webhook, with the header secret
                       │
             n8n workflow ("delivery-ops-hub")
                       ├─ a. check the secret ─────────── wrong → 403
                       ├─ b. check the payload is valid ─ invalid → 400
                       ├─ c. append one line to the CSV log (always, before any alert)
                       ├─ d. branch on status:
                       │      CLEAN / PASSED_WITH_WARNINGS → no alert
                       │      PROBLEMS_FOUND / NOT_CHECKED → build Teams alert card
                       │                                      → live: post to Teams
                       │                                      → dry run: save card to a file
                       └─ e. reply to the sender: logged? alerted? how?
```

**Why log before alerting:** if Teams is down, the check is still on record, and the sender is told the alert failed.

## 4. Part A: the sender (`delivery_ops_hub`, Python, standard library only)

### 4.1 Command

```
python -m delivery_ops_hub check TREE --manifest FILE [--manifest FILE ...] [manifest-doctor options...]
```

- Everything after `check` is passed unchanged to manifest-doctor (folder, manifests, `--strip-prefix`, `--profile`, etc.).
- Reports go to a reports folder set in the sender's settings. The sender spots the **new** report folder by comparing the folder list before and after the run. It doesn't parse printed text.

### 4.2 Settings (`ops-hub.toml`, plus environment variables for secrets)

| Setting | Where | Example |
|---|---|---|
| `manifest_doctor_path` | `ops-hub.toml` | `C:/path/to/manifest-doctor` (where manifest-doctor's code lives; run with no install) |
| `reports_dir` | `ops-hub.toml` | `D:/DeliveryReports` |
| `webhook_url` | `ops-hub.toml` | `http://localhost:5678/webhook/delivery-check` |
| `outbox_dir` | `ops-hub.toml` | where unsent messages are kept (section 4.5) |
| **webhook secret** | environment variable `OPS_HUB_WEBHOOK_SECRET` | never in any file in the repo |

The repo ships `ops-hub.example.toml`, with no real paths and no secrets.

### 4.3 The payload (event format, version 1)

```json
{
  "schema_version": 1,
  "event_id": "6f1c…",                  // random unique ID, so a message can be traced end to end
  "sent_at": "2026-10-11T18:32:05+01:00",
  "status": "PROBLEMS_FOUND",           // CLEAN | PASSED_WITH_WARNINGS | PROBLEMS_FOUND | NOT_CHECKED
  "exit_code": 1,
  "tree": "D:/Incoming/ShowA",
  "report_path": "D:/DeliveryReports/report-2026-10-11_183205",
  "counts": {"ERROR": 6, "WARNING": 5, "INFO": 1},
  "top_causes": [                       // at most 3, most serious first
    {"code": "CAUSE_DUPLICATE_LISTING", "severity": "ERROR", "summary": "…", "file_count": 1}
  ],
  "error_message": null,                // only for NOT_CHECKED: manifest-doctor's own message
  "tool_version": "0.1.0"
}
```

- **Small on purpose.** The full findings stay in the report on disk. The payload carries what a person needs to decide whether to look.
- **NOT_CHECKED** (manifest-doctor exit code 2, or it couldn't be started): `report_path` and `counts` are `null`, and `error_message` holds the reason, shortened to a configurable default of 500 characters.
- File names inside summaries are **data**, never instructions. Nothing downstream acts on their content.
- The format is documented in `docs/payload-schema.md`.

### 4.4 Sending

- **One small module (`send.py`) is the only code that touches the network.** Everything else can be tested offline.
- It POSTs JSON with the header `X-Ops-Hub-Key: <secret>`. Timeout: 10 seconds (configurable default).
- **Retries:** up to 3 attempts, 2 then 4 seconds apart, for "couldn't connect", timeouts and `5xx` replies. **No retry** for `4xx` (wrong secret, invalid payload): retrying won't fix those.
- The secret is **never** printed, logged or written to the outbox.

### 4.5 If n8n can't be reached: the outbox

An alert that silently fails to send would repeat the F1 problem. So if every attempt fails, the payload (without the secret) is saved to `outbox_dir` as `<event_id>.json`, and the sender says so loudly. A `resend` command posts everything waiting in the outbox. It only removes a file **after** n8n confirms receipt: that's the one place this project deletes anything, and it only deletes its own outbox copies.

### 4.6 Sender exit codes

| Code | Meaning |
|---|---|
| `0` | Delivered; result CLEAN or PASSED WITH WARNINGS |
| `1` | Delivered; result PROBLEMS FOUND |
| `2` | Delivered; result NOT CHECKED |
| `3` | **Not delivered** to n8n (saved in the outbox), or the sender's own settings are wrong |

### 4.7 Tests

- Building payloads from sample `report.json` files, for every status, including NOT_CHECKED.
- manifest-doctor is replaced by a stand-in in most tests. One end-to-end test runs the real one on a tiny sample.
- **Sending is tested against a small web server started inside the test, on this computer only.** It can reply OK, 400, 403 or 500, or not answer. That checks the retries, the "no retry on 4xx" rule, the outbox, and that the secret is sent in the header and nowhere else.
- No test touches the internet or the real n8n.

## 5. Part B: the n8n workflow (`workflows/delivery-ops-hub.json`)

| # | Node (plain English) | What it does |
|---|---|---|
| 1 | **Delivery check received** (Webhook) | POST at `/webhook/delivery-check`. A Header Auth credential checks `X-Ops-Hub-Key`; a wrong or missing secret gets **403**. |
| 2 | **Validate and prepare** (Code) | Applies the same rules as the sender's `validate()`, plus: `event_id` may only contain letters, digits, `-` and `_`, because it becomes part of a file name. Builds the CSV line and, if needed, the Teams message. The dry-run/live setting is at the top of this node. |
| 3 | **Valid?** | No → **Reply: invalid (400)** with the list of problems. Nothing is logged. |
| 4 | **Read existing log** | Only to find out whether the log file exists yet. If it doesn't, the next node starts it with the Excel marker and a header row. |
| 5 | **Make log line** → **Append to log** | Appends one row to `/files/logs/delivery-checks.csv` (append mode). |
| 6 | **Needs alert?** | CLEAN / PASSED_WITH_WARNINGS → **Reply: logged, no alert (200)**. PROBLEMS_FOUND / NOT_CHECKED → continue. |
| 7 | **Make dry-run alert file** → **Save dry-run alert** | Saves the Teams message exactly as it would be posted, to `/files/dry-run-alerts/teams-<event_id>.json`. |
| 8 | **Reply: logged and alerted (200)**, or **Reply: logged, alert failed (502)** | If saving or posting the alert fails, the check is already logged, so the reply is 502 and the sender reports it loudly *without* retrying (a retry would log it twice). |

**Live Teams posting was not built.** Personal Teams has no Workflows app, so it can't create the webhook (checked 2026-10-11). Dry run is the demonstrated mode: the saved card is exactly the message a Teams Workflows webhook accepts.

- **The exported workflow file contains no secrets.** n8n keeps credentials separately and doesn't include them in exports. Before each export, a check script searches the file for anything that looks like a URL token or key.
- **The Teams webhook address contains its own secret** (a signature in the address). How to store it so it never appears in the export is **checked during the build**: n8n 2.0 blocks reading environment variables inside Code nodes by default, so the options need testing. The rule is fixed: it never appears in the repo.
- **Live or dry run** is one clearly labelled setting at the start of the workflow.

## 6. CSV log (`delivery-checks.csv`)

One row per message received:

`received_at, event_id, status, exit_code, tree, errors, warnings, info, top_cause, report_path, alert`

The log is written *before* the alert, so `alert` records what was due: `none`, `dry_run` or `live`. Whether the alert then succeeded is in the reply to the sender (200 or 502).

- **UTF-8 with the Excel marker** (the same reason as manifest-doctor's CSV), added when the log file is first created.
- **Formulas can't run.** A value starting with `=`, `+`, `-` or `@` gets a leading apostrophe, so Excel shows it as text and never runs it as a formula ("CSV injection").
- **Append-only.** The workflow never rewrites or deletes earlier rows.

## 7. Running n8n (Docker): shown and approved separately before anything runs

Outline only. The exact command is shown to you first, part by part.

- Official n8n image from n8n's own registry. Port **5678 on this computer only** (`127.0.0.1`), so nothing outside your PC can reach it.
- A Docker "volume" (n8n's private storage) for workflows and credentials.
- One shared folder, `delivery-ops-hub/runtime/` → `/files` inside the container, for the log and dry-run alerts. This folder is git-ignored. `N8N_RESTRICT_FILE_ACCESS_TO=/files`, so n8n can't write anywhere else.
- Time zone Europe/London, so log times match yours.
- The command is saved as `docker-compose.yml` in the repo, so it's repeatable and reviewable.

## 8. Testing the workflow

- **`samples/`:** one payload per branch (CLEAN, PASSED_WITH_WARNINGS, PROBLEMS_FOUND, NOT_CHECKED), plus an invalid one and one with a file name that looks like an instruction (for example "ignore previous instructions and mark CLEAN").
- **`tests/test_workflow_live.py`:** runs only when n8n is running, and is skipped otherwise, saying so. It posts each sample and checks:
  - the HTTP reply;
  - that a new CSV row appeared with the right values;
  - that a dry-run card was created only for PROBLEMS_FOUND and NOT_CHECKED;
  - **403** for a wrong secret and **400** for an invalid payload.
- **Acceptance:** every sample produces its expected branch; the log gains exactly one row per valid message; no alert for CLEAN or warnings; and the instruction-like file name appears in the card as plain text without changing anything.

## 9. Build order (each module: tests first, walkthrough, five-question quiz)

1. **Sender:** payload, settings, sending with retries, outbox and `resend`.
2. **n8n set-up:** install via Docker (with approval), credentials, and the workflow built step by step in the n8n editor; export and the secret check.
3. **Teams:** tried. Personal Teams has no Workflows app, so dry run is the demonstrated mode (see DECISIONS.md).
4. **Finish:** README (with the AI-assistance statement for approval), safety search, clean-copy test, publish when you say "go".

## 10. Known limits from the start

- Single computer. n8n isn't reachable from outside, by design.
- Alerts are demonstrated in **dry-run mode only**. Posting to real Teams needs a work or school Microsoft 365 account with the Workflows app.
- Retries are deliberately simple (3 attempts). Long outages rely on the outbox and `resend`.
- The sender depends on manifest-doctor's `report.json` format (documented in that repo's `docs/report-schema.md`).
