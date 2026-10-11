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
