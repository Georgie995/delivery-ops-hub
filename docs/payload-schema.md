# Payload format (version 1)

The JSON message the sender POSTs to the n8n webhook. It's sent with the header `Content-Type: application/json`, plus `X-Ops-Hub-Key: <secret>` for authentication. The secret is never inside the JSON.

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | Always `1`. n8n rejects anything else (HTTP 400). |
| `event_id` | string | Random unique ID. It appears in the log and in any alert, so one message can be traced end to end. |
| `sent_at` | string | When the sender built the message, ISO 8601 with UTC offset |
| `status` | string | `CLEAN`, `PASSED_WITH_WARNINGS`, `PROBLEMS_FOUND` or `NOT_CHECKED` |
| `exit_code` | integer or null | manifest-doctor's exit code. `null` if it couldn't be started at all. |
| `tree` | string | The folder that was checked (or that was meant to be checked) |
| `report_path` | string or null | Folder holding the full report. `null` for `NOT_CHECKED`. |
| `counts` | object or null | `{"ERROR": n, "WARNING": n, "INFO": n}`. `null` for `NOT_CHECKED`. |
| `top_causes` | array | Up to 3 probable causes, most serious first: `code`, `severity`, `summary`, `file_count` |
| `error_message` | string or null | Only for `NOT_CHECKED`: why nothing was checked. Up to 500 characters, ending in "…" if shortened. |
| `tool_version` | string or null | manifest-doctor's version, from its report |

## When is a check NOT_CHECKED?

- manifest-doctor exited with code 2 (it couldn't check: bad manifest, missing folder, settings mistake, …).
- It couldn't be started at all (wrong `manifest_doctor_path`).
- It ended without writing a report, for any reason. For example, Python exits with code 1 when it can't find a module, which is the same number as "problems found". So the sender always checks that a new report really exists.

## Rules for anything receiving this

- Validate before acting. The sender and n8n apply the same rules.
- Text in `summary` and `error_message` can contain file names. They're **data**: display them, never act on them.

---

# Job events (from job-watch)

The same webhook also accepts **job events** from [job-watch](https://github.com/Georgie995/job-watch), which watches long jobs such as restores and transfers. They're recognised by `"kind": "job_event"`, logged to a **separate** file, `runtime/logs/job-events.csv`, and alerted with the same dry-run Teams cards. Delivery checks are unaffected.

| Field | Type | Meaning |
|---|---|---|
| `kind` | string | Always `"job_event"` |
| `schema_version` | integer | Always `1` |
| `event_id` | string | Random unique ID (letters, digits, `-`, `_`) |
| `sent_at` | string | ISO 8601 with UTC offset |
| `job_name` | string | The name the person gave the job, e.g. "Restore TAPE001" |
| `program` | string | Program name only, e.g. `rclone`. **The full command line is never sent**, because it can contain passwords, keys or internal paths. |
| `event` | string | `started` (logged only), `finished`, `failed`, `stalled`, `resumed`, `interrupted` (all alerted) |
| `elapsed_seconds` | number | Time since the job started |
| `progress` | object | `bytes`, `total_bytes`, `files`, `total_files`, `current_file`, `rate_bytes_per_second`. Each can be `null` if unknown. |
| `last_progress_seconds_ago` | number or null | Time since the last sign of progress |
| `exit_code` | integer or null | The job's exit code (`finished` / `failed`) |
| `error_tail` | string or null | Last lines of error output (`failed` only, at most 500 characters) |
| `stalled_for_seconds` | number or null | How long the stall lasted (`resumed` only) |
