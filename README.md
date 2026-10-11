# delivery-ops-hub

Makes sure the result of a delivery check **reaches a person**. Every check is logged; problems, and checks that couldn't run at all, raise an alert. An n8n workflow receives each result by webhook.

Built on [manifest-doctor](https://github.com/Georgie995/manifest-doctor), which does the checking.

## The problem

A verification tool only helps if someone sees the result in time. In real delivery work, a corrupted file was found by the *recipient* because nothing checked or alerted before sending. Two quieter failures are just as dangerous:

- **"Nothing was checked" looks exactly like "nothing went wrong"** if nobody is told.
- **An alert that silently fails to send** is the same as no alert.

## How it works

```
python -m delivery_ops_hub check <folder> --manifest <file>
   │
   ├─ runs manifest-doctor, finds its new report
   ├─ builds a small JSON message (or NOT_CHECKED, with the reason)
   └─ POSTs it to n8n, with a secret header ──────────►  n8n workflow
                                                          ├─ wrong secret → 403
                                                          ├─ invalid      → 400
                                                          ├─ append one row to a CSV log
                                                          ├─ problems or not checked → build a Teams alert card
                                                          └─ reply: logged? alerted?
```

- **The sender** (`delivery_ops_hub/`, Python standard library only) runs manifest-doctor unchanged, then sends its result.
  - It retries only problems that can clear up on their own: nothing answering, timeouts, 5xx errors.
  - If n8n can't be reached, the message waits in an **outbox** until `resend` delivers it.
  - Only one module (`send.py`) touches the network.
- **The workflow** (`workflows/`) checks a header secret and validates the message. It **writes the log row first**, then builds the alert.
  - If the alert fails after logging, it replies **502**, so the sender reports it without retrying. A retry would log the check twice.
- **Alerts run in dry-run mode.** Each alert is saved as the exact Adaptive Card that a Microsoft Teams *Workflows* webhook accepts. Posting to real Teams needs a work or school Microsoft 365 account with the Workflows app. Personal Teams doesn't have it, and a work tenant is deliberately not used for a portfolio project (see [DECISIONS](docs/DECISIONS.md)).

## Example run (real output, synthetic data)

```
> python -m delivery_ops_hub check ..\practice\messy_delivery --manifest ..\practice\messy_manifest.md5
RESULT: PROBLEMS FOUND (6 errors, 5 warnings, 1 info)
  ERROR: 1 path is listed more than once in a manifest with different checksums. ...
  ...
PROBLEMS_FOUND: delivered to n8n (logged: True, alerted: True, alert mode: dry_run)

> python -m delivery_ops_hub check ..\practice\no_such_folder --manifest ..\practice\messy_manifest.md5
NOT_CHECKED: delivered to n8n (logged: True, alerted: True, alert mode: dry_run)

> docker compose stop
> python -m delivery_ops_hub check ..\practice\tidy_delivery --manifest ...
PASSED_WITH_WARNINGS: NOT DELIVERED to n8n (could not connect to n8n ...). Saved to ...\hub-outbox\90c68f40....json.
Run 'python -m delivery_ops_hub resend' once n8n is reachable.

> docker compose start
> python -m delivery_ops_hub resend
Resent 1 of 1 message(s).
```

## Exit codes (sender)

| Code | Meaning |
|---|---|
| `0` | Delivered; clean or warnings only |
| `1` | Delivered; problems found |
| `2` | Delivered; **not checked** (manifest-doctor couldn't run the check) |
| `3` | **Not delivered** (saved in the outbox), alert failed after logging, or the sender's own settings are wrong |

## Set-up

Requires Python 3.11+, Docker, and [manifest-doctor](https://github.com/Georgie995/manifest-doctor) checked out locally.

1. **Start n8n:**
   ```
   mkdir -p runtime/logs runtime/dry-run-alerts
   docker compose up -d
   ```
   - This uses n8n 2.42.6, reachable only from this PC (`127.0.0.1:5678`), and writing only to `runtime/`.
   - n8n doesn't create folders itself, so create them before the first run.
2. **Create the owner account** at http://localhost:5678.
3. **Create a webhook secret.**
   - Set the environment variable `OPS_HUB_WEBHOOK_SECRET` to a long random value.
   - In n8n, create a **Header Auth** credential with Name `X-Ops-Hub-Key` and the same value.
4. **Load the workflow:**
   ```
   python workflows/load_into_n8n.py
   ```
   This builds the workflow from `workflows/src/`, links the credential by ID, publishes it and restarts n8n.
5. **Configure the sender:** copy `ops-hub.example.toml` to `ops-hub.toml` and set the paths. The secret never goes in this file.

## Tests

```
python -m pytest -m "not live"     # sender and workflow-file tests: no n8n needed
python -m pytest                   # also the live tests, against the running n8n
```

- **Sender tests** use a tiny web server inside the test (on this PC only) and a stand-in manifest-doctor.
- **Live tests** post every sample in `samples/` to the real workflow and check:
  - the reply, the CSV row and the alert file;
  - **400** for an invalid message and **403** for a wrong secret;
  - **502** with exactly one log row when the alert can't be saved;
  - that an instruction-like file name is shown as plain text;
  - that a formula in a folder name can't run when the log is opened in Excel.

## Why not just…?

| Alternative | Why this project doesn't |
|---|---|
| **Let n8n run manifest-doctor itself** | n8n 2.0 disables its "run a command" and "watch a folder" nodes by default for security. Pushing results to a webhook keeps n8n's permissions minimal and is the standard integration pattern. |
| **Have manifest-doctor send alerts directly** | It would put network code into a tool that's deliberately offline and read-only. The sender keeps that in one small, separately tested module. |
| **Zapier or Make instead of n8n** | Both are cloud services: delivery results would leave the PC. n8n can be self-hosted. It's under the [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) (fair-code, not OSI open source), which allows free use for internal business purposes. |
| **Email alerts** | Teams was the target. Email would need a mail server and its own credentials. |

## Known limits

- **Dry-run alerts only.** Not tested with real Teams (see above).
- **Teams formatting:** card text supports basic Markdown, so a file name containing `_` or `*` might render partly in italics or bold in Teams.
- **Log reads:** the workflow reads the whole log on every message (only to see whether it exists yet).
- **Folders:** the two `runtime/` folders must exist before the first run.
- **Retries:** deliberately simple (3 attempts, 2 and 4 seconds apart). Longer outages rely on the outbox and `resend`.
- **Tested on Windows 11 only,** with Python 3.13, Docker Desktop and n8n 2.42.6.

## Documentation

- [DESIGN.md](docs/DESIGN.md): how it works, with a glossary.
- [DECISIONS.md](docs/DECISIONS.md): every choice and why, including what went wrong during set-up.
- [walkthrough.md](docs/walkthrough.md): plain-English explanation of each module, with interview-style questions.
- [payload-schema.md](docs/payload-schema.md): the message format.
- [domain-notes.md](docs/domain-notes.md): the real-world failures behind it.

All data is synthetic. No client names, project or tape codes, hostnames or internal paths appear anywhere.

## AI assistance

> **DRAFT. Georgi to confirm or correct before publishing.**

The code and workflow in this repository were built with an AI coding assistant (Claude, by Anthropic). I did not write the Python or JavaScript by hand.

What I did:

- **Specified it** from delivery failures I've handled. The key one was a problem found by the recipient because nothing checked or alerted before sending. I chose:
  - Teams alerts and a CSV log;
  - warnings logged but not alerted;
  - "couldn't check" raising an alert;
  - a secret on the webhook;
  - never using my employer's Teams.
- **Approved the design** before any code was written. The decisions are logged in `docs/DECISIONS.md`.
- **Set it up and ran it myself:** installed n8n in Docker, created the secret and the n8n credential, and ran the whole chain by hand. That included switching n8n off to watch a result wait in the outbox, then resending it.
- **Found and fixed problems through use:**
  - A credential set-up mistake was caught by the "wrong secret is refused" test.
  - My hands-on run showed a bare "404" message wasn't clear enough, so it now explains what it usually means.
- **Checked Teams myself** and decided not to fake a "live" mode that couldn't be tested for real.
- **Learned how it works** through a written walkthrough and quiz for each module.

## Licence

[MIT](LICENSE) © 2026 Georgi Stoyanov
