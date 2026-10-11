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
