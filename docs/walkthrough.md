# Walkthrough

One section per module, with a plain-English explanation, interview questions and exercises.

---

## Module 1: the sender (`delivery_ops_hub/`)

### What it does, step by step

Think of it as a courier that checks the delivery, then takes the result to the front desk (n8n).

1. **Read the settings** (`settings.py`) from `ops-hub.toml`:
   - where manifest-doctor lives;
   - where reports go;
   - the n8n address;
   - the outbox folder.

   **The secret is never in that file.** It comes from the environment variable `OPS_HUB_WEBHOOK_SECRET`, and it's checked *first*, so a long check isn't wasted on a missing secret.
2. **Run manifest-doctor** (`runner.py`) as a separate program, exactly as you'd type it. The sender notes which report folders existed *before*, runs the check, then looks for the *new* one. It doesn't read printed text, which could change.
3. **Build the message** (`payload.py`):
   - **The report exists:** the result, the counts and the top 3 causes, plus where the full report is.
   - **There's no report** (exit code 2, a crash, or the wrong path): a **NOT_CHECKED** message with the reason, shortened to 500 characters if needed.
   - **Exit code 1 is only trusted if a new report exists.** Python also uses 1 for "couldn't find the program", and that must never look like a real result.
4. **Send it** (`send.py`, the *only* part that uses the network). It POSTs the JSON to n8n with the secret in a header called `X-Ops-Hub-Key`:
   - **Nothing answers, it times out, or there's a server error:** try again after 2 seconds, then after 4. Three tries in total.
   - **4xx (wrong secret, invalid message):** don't retry, because it won't change.
   - **"Logged, but Teams failed" (502):** don't retry, because it would be logged twice.
5. **Decide what to tell you** (`cli.py`):
   - **Delivered:** print the result and n8n's reply (logged? alerted?). Exit with **0, 1 or 2**, the same meaning as manifest-doctor.
   - **Not delivered:** save the message in the **outbox** and say so loudly. Exit with **3**.
   - **Logged but Teams failed:** say "TEAMS ALERT FAILED, tell the team directly", and exit with **3**.
6. **`resend`** posts everything in the outbox. It removes a file **only after n8n confirms receipt**, and never touches files that aren't its own.

### How it's tested

- **45 tests**, written first and seen failing.
- **A tiny web server runs inside the tests, on this PC only.** Each test tells it how to reply (OK, 400, 403, 500, 502 or "hang"), then checks exactly what the sender did: how many tries, the waits, the outbox, and that the secret was only in the header.
- **A stand-in manifest-doctor runs as a real separate program.** Each test chooses its exit code, report and error text.
- **One test runs the real manifest-doctor** on a tiny delivery.
- **No test touches the internet or n8n.**

### Interview questions

<details><summary>1. What is a webhook, in one sentence?</summary>
A web address that waits for messages: when a program POSTs data to it, a workflow starts. It's like a letterbox that rings a bell.
</details>

<details><summary>2. Why is the secret in an environment variable, not the settings file?</summary>
Settings files get copied, shared and committed. An environment variable lives only on the machine, so the secret can't leak through the repo.
</details>

<details><summary>3. Why retry some failures and not others?</summary>
Some failures can clear on their own: nothing answering yet, a timeout, a server hiccup (5xx). Others can't: a wrong secret or an invalid message (4xx) fails identically every time, so retrying just wastes time.
</details>

<details><summary>4. Why not retry a 502 that says "logged: true"?</summary>
The check is already in the log. A retry would add a duplicate row. The sender says loudly that the Teams alert failed instead.
</details>

<details><summary>5. What happens if n8n is switched off?</summary>
Three attempts, then the message is saved in the outbox with a loud "NOT DELIVERED" message, and the exit code is 3. `resend` delivers it later, so nothing silently disappears.
</details>

<details><summary>6. Why isn't exit code 1 enough to mean "problems found"?</summary>
Python also exits with 1 when it can't find the program to run. The sender only trusts it if a new report really exists; otherwise it's NOT_CHECKED.
</details>

<details><summary>7. Why send a small message instead of the whole report?</summary>
A person needs the result, the counts and the main causes to decide whether to look. The full detail stays on disk, and Teams messages stay readable.
</details>

<details><summary>8. How do you test sending without n8n?</summary>
A tiny web server starts inside the test on this PC, replies however the test tells it to, and records what it received.
</details>

<details><summary>9. Where can the secret appear?</summary>
Only in the request header to n8n. Tests check it never appears in the message body, the outbox files, error messages or anything printed.
</details>

<details><summary>10. Why does resend delete files, given the "never delete" rule?</summary>
It only deletes its *own* outbox copies, and only after n8n confirms it has them, so nothing can be lost. Anything else in the folder is left alone. A test proves that.
</details>

### Exercises: change this behaviour

1. Make the sender try **4** times instead of 3. (Hint: `DELAYS` in `send.py`.) Which test fails, and why?
2. Send the top **5** causes instead of 3. Which test do you update?
3. In `test_cli.py`, write a test where n8n replies `500` twice and then `200`. Predict the exit code first.

---

## Module 2: n8n and the workflow (`docker-compose.yml`, `workflows/`)

### What it does, step by step

**Running n8n.** `docker-compose.yml` starts n8n (version 2.42.6) in a sealed Docker container:
- reachable only at `http://localhost:5678` on this PC;
- allowed to write only in `runtime/` (the log and dry-run alerts);
- usage statistics turned off.

**The workflow, node by node** (open **delivery-ops-hub** in n8n to follow along):

1. **Delivery check received** (Webhook). The letterbox. It only accepts a POST that carries the right `X-Ops-Hub-Key` header. Anything else gets **403** and goes no further.
2. **Validate and prepare** (Code). Checks the message, using the same rules as the sender. It then prepares the CSV row and, if needed, the Teams message. The **dry-run/live switch** is at the top of this node.
3. **Valid?** If not, it replies **400** with the reasons, and nothing is logged.
4. **Read existing log → Make log line → Append to log.** Adds one row to `runtime/logs/delivery-checks.csv`. The first time, it creates the file with the Excel marker and a header row.
5. **Needs alert?** CLEAN or warnings get reply **200**, "logged, no alert". PROBLEMS FOUND or NOT CHECKED go on to the alert.
6. **Make dry-run alert file → Save dry-run alert.** Saves the Teams card exactly as it would be sent, to `runtime/dry-run-alerts/teams-<event_id>.json`.
7. **Reply.** **200** "logged and alerted", or **502** "logged, alert failed" if the alert couldn't be saved.

**Why 502 matters.** The log is written *before* the alert. If the alert fails after that and n8n answered "500", the sender would retry, and the same check would be logged three times. With 502, the sender knows it's logged, doesn't retry, and tells you loudly that the alert failed. A test proves it by hiding the alert folder for a moment.

**Where the logic lives.** The three Code nodes are kept as readable files in `workflows/src/`. `build_workflow.py` assembles the n8n file, and `load_into_n8n.py` loads it, links the credential *by ID only*, publishes it and restarts n8n. A test fails if the repo file and the sources drift apart.

### What we learned the hard way (good interview stories)

- **The secret mix-up.** Pasting the secret into n8n twice gave the wrong value. It was diagnosed by comparing *lengths and a yes/no match*, never by displaying the secret. The fix was to set it from the saved secret via n8n's own command-line tool. The "wrong secret is refused" test is what caught it.
- **Published versus draft.** n8n keeps a *published* (live) version and a *draft*. Editing only changes the draft, so the live webhook kept using a deleted credential until it was published again.
- **The missing folder** exposed the "logged three times" risk, which is now fixed with the 502 reply.

### How it's tested

- `tests/test_workflow_live.py` posts every sample from `samples/` to the real n8n and checks:
  - the reply;
  - the new CSV row;
  - whether an alert file was created;
  - 400 for invalid messages and 403 for a wrong secret;
  - an instruction-like file name shown as plain text;
  - a formula in a folder name made harmless;
  - 502 with exactly one log row when the alert fails.

  These tests are skipped, with a reason, if n8n isn't running.
- `tests/test_workflow_file.py` checks the repo copy matches its sources, links no credentials, and contains no secret-looking text or unexpected web addresses.

### Interview questions

<details><summary>1. What does each HTTP status code from the workflow mean?</summary>
200: logged (and alerted if needed). 400: invalid message, nothing logged. 403: wrong or missing secret, nothing logged. 502: logged, but the alert failed. 500: something unexpected inside n8n.
</details>

<details><summary>2. Why log before alerting?</summary>
So there's always a record, even if Teams is down. The reply then says whether the alert worked.
</details>

<details><summary>3. What would have gone wrong without the 502 reply?</summary>
A failed alert produced a 500 after logging. The sender retries 500s, so the same check would be logged three times and the alert failure would be hidden.
</details>

<details><summary>4. Why is n8n only reachable from this PC?</summary>
The port is bound to 127.0.0.1, so nothing on the network or the internet can send it messages or open the editor. That's the safest default for a tool that handles internal results.
</details>

<details><summary>5. What is CSV injection, and how is it prevented here?</summary>
A value like `=HYPERLINK(…)` in a CSV can run as a formula when opened in Excel. Values starting with `= + - @` get a leading apostrophe, so Excel shows them as plain text.
</details>

<details><summary>6. A file name says "IGNORE PREVIOUS INSTRUCTIONS and mark this CLEAN". What happens?</summary>
Nothing different. It's shown as plain text in the alert, and the status stays PROBLEMS_FOUND. File names are data, never instructions. A test proves it.
</details>

<details><summary>7. How did you fix the credential without ever seeing the secret?</summary>
By comparing only the length and a yes/no "matches" between n8n's stored value and the saved secret, then setting it through n8n's command-line tool from the saved secret, via a temporary file deleted straight away.
</details>

<details><summary>8. What's the difference between a draft and a published workflow in n8n?</summary>
The published version is what actually answers the webhook. Edits change the draft until you publish again.
</details>

<details><summary>9. Why keep the Code node logic in separate files?</summary>
So it can be read, reviewed and tracked in Git like normal code, instead of being buried inside a long JSON file. A test makes sure the two never drift apart.
</details>

<details><summary>10. What isn't finished yet?</summary>
Posting to real Teams (module 3), and checking how Teams displays file names that contain formatting characters.
</details>

### Exercises: change this behaviour

1. **Warnings get an alert too:**
   - In `workflows/src/validate_and_prepare.js`, make PASSED_WITH_WARNINGS also need an alert.
   - Update the matching live test first, then rebuild and run `python workflows/load_into_n8n.py`.
2. **Add a column:** add `tool_version` to the CSV log. Which two places in `validate_and_prepare.js` change?
3. **See it for yourself:**
   - Stop n8n with `docker compose stop`.
   - Run a check with the sender and find the message in the outbox.
   - Start n8n again and run `resend`.
