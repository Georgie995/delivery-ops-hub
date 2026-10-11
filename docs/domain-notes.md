# Domain notes

The real-world reasons this project exists, from Georgi's work in ingest, tape archive and delivery. They are written generically, with no client, project or product details.

| # | What happened | Why it matters here | What delivery-ops-hub does |
|---|---|---|---|
| F1 | A file that wasn't fully ingested was sent without a verify step. Nothing looked wrong, and the recipient found the problem. | A check is only useful if its result reaches someone before sending. | Every check is logged; problems raise a Teams alert. |
| F1 (by extension) | "Nothing was checked" looks exactly like "nothing went wrong" if nobody is told. | A tool error must never be silent. | manifest-doctor exit code 2 becomes a NOT_CHECKED alert. |
| F6 | A verify tool listed *everything* as failed without saying which files or why. | An alert must say what to look at. | The alert carries the top probable causes and the path to the full report. |
| F9 | Tape software reported error *counts* but not *which files*, then stalled and crashed. | Partial or failed runs must leave a clear record. | The log keeps one row per check, append-only. Undeliverable messages go to an outbox rather than vanishing. |
