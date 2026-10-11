"""Messages that couldn't be delivered wait here, one JSON file each, named by event ID.

The payload never contains the webhook secret, so nothing secret is written to disk.
"""

import json
from pathlib import Path


def save(outbox_dir, payload):
    outbox_dir = Path(outbox_dir)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{payload['event_id']}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def pending(outbox_dir):
    outbox_dir = Path(outbox_dir)
    return sorted(outbox_dir.glob("*.json")) if outbox_dir.exists() else []


def remove_after_confirmed(path):
    """Only called once n8n has confirmed receipt, and only for our own outbox files."""
    Path(path).unlink()
