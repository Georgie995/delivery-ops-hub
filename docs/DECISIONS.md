# Decisions

Each entry records the decision, the alternatives considered and why this one was chosen.

## 2026-10-11: Replace the planned ingest-watch with an n8n-first hub

- **Why:** carried over from the portfolio research. The original ingest-watch was estimated at more than 30 hours, mostly code to defend line by line. This project covers webhooks, REST, JSON and n8n with far less code.

## 2026-10-11: Alerts in Teams, log in a local CSV file

- **Decision:** Georgi chose both. The CSV opens in Excel.

## 2026-10-11: Never use the employer's Teams

- **Why:** posting portfolio test alerts into a work tenant would mix the project with the employer. Georgi will use a personal Teams account.
- **Fallback:** if personal Teams can't create a Workflows webhook, alerts run in "dry run" mode (cards saved to files), and the README says which mode was demonstrated.

## 2026-10-11: Teams via a Workflows webhook, not the old connectors

- **Why:** Office 365 connector webhooks in Teams were retired in May 2026 (Microsoft message center MC1181996; Microsoft 365 Developer Blog, "Retirement of Office 365 connectors within Microsoft Teams"). The replacement is a webhook created with the Workflows app.

## 2026-10-11: n8n runs in Docker

- **Decision:** run n8n in Docker.
- **Alternatives:** install Node.js and n8n through npm.
- **Why:** Docker was already installed, and Node.js wasn't. A container keeps n8n sealed off from the rest of the PC and is easy to remove completely.

## 2026-10-11: The sender pushes reports; n8n doesn't run manifest-doctor

- **Why:** n8n 2.0 disables the Execute Command and Local File Trigger nodes by default for security (n8n v2.0 breaking changes). Pushing to a webhook keeps n8n's permissions minimal, keeps manifest-doctor unchanged and network-free, and is exactly the webhook skill the project demonstrates.

## 2026-10-11: A check-and-send command

- **Decision:** one command runs manifest-doctor and sends the result (Georgi's choice).
- **Alternatives:** send an existing report.
- **Finding the report:** the sender finds the new report folder by comparing folder lists before and after, not by parsing printed text, which could change.

## 2026-10-11: Warnings are logged, not alerted

- **Why:** Georgi's choice. Alerts stay rare, so people don't learn to ignore them.

## 2026-10-11: "Couldn't check" raises an alert

- **Decision:** manifest-doctor exit code 2 produces a NOT_CHECKED message and a Teams alert (Georgi's choice).
- **Why:** this is the F1 lesson: "nothing was checked" must never be silent.

## 2026-10-11: Webhook protected by a header secret

- **Decision:** Georgi's choice. The secret lives in an environment variable and in n8n's credential store, never in the repo.

## 2026-10-11: Small payload

- **Decision:** the payload carries the result, counts and the top 3 causes, not every finding.
- **Why:** a person needs enough to decide whether to look; the full detail stays in the report on disk. It also keeps Teams messages short.

## 2026-10-11: Log first, then alert

- **Why:** if Teams fails, the check is still on record, and the sender is told the alert failed (HTTP 502).

## 2026-10-11: An outbox for messages that can't be delivered

- **Why:** if n8n is unreachable, a silent failure would repeat F1. The message is saved and the sender says so loudly.
- **Deleting:** `resend` deletes an outbox file only after n8n confirms receipt, and only its own files.

## 2026-10-11: The exercise from project 1 is waived

- **Decision:** Georgi chose to skip the hands-on "change this behaviour" exercise for manifest-doctor and move on to this project.

## 2026-10-11: Design approved with the defaults as written

- **Outbox:** copies are deleted only after n8n confirms receipt.
- **Error messages:** NOT_CHECKED messages are capped at 500 characters (configurable default).
- **Teams address:** how to store the Teams webhook address is decided during the build. It must never appear in the repo.

## 2026-10-11: Sender details (module 1)

- **Tests use project 1's pytest.** They run with the pytest already installed for manifest-doctor (`../delivery-verify/.venv`), so nothing new was installed.
- **manifest-doctor runs from its own folder** (via `PYTHONPATH`) as a separate program, without installing it. Its output is read as UTF-8, so accented file names survive.
- **Exit code 1 isn't trusted on its own.** It only counts as "problems found" if a new report really exists. Python also exits with 1 when it can't find manifest-doctor at all, and that must become NOT_CHECKED, not a fake result.
- **Secret checked first.** A missing secret stops the sender *before* the check runs, so a long check isn't wasted.
- **"Logged but Teams failed" (HTTP 502 with `logged: true`)** is reported loudly. It isn't retried and isn't put in the outbox, because that would log the same check twice.
- **Rejected messages go to the outbox.** A message rejected by n8n (4xx, e.g. wrong secret) is saved there, so it isn't lost once the settings are fixed.
- **No proxies:** the sender talks to n8n directly, so a system proxy never sees the secret.
- **Slow tests on Windows:** the tests that simulate "n8n switched off" take about 2 seconds per attempt on Windows (the time Windows takes to report that nothing is listening). The total test run is under a minute.
