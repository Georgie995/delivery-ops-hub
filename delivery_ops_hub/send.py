"""The only module that touches the network: POST a payload to the n8n webhook.

Retries are for problems that might clear up on their own (nothing answering, timeouts,
5xx server errors). A 4xx reply (wrong secret, invalid payload) won't change on retry, so
it isn't retried. A reply saying the check was already logged isn't retried either,
because a retry would log it twice.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DELAYS = (2, 4)  # seconds between attempts: 3 attempts in total (configurable default)

# No proxies: n8n runs on this PC, and a system proxy must never see the secret.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class SendResult:
    delivered: bool
    status: int | None   # HTTP status code, or None if nothing answered
    reply: dict | None
    error: str | None
    attempts: int


def post_json(url, payload, secret, timeout=10, delays=DELAYS, sleep=time.sleep):
    data = json.dumps(payload).encode("utf-8")
    result = None
    for attempt in range(len(delays) + 1):
        request = urllib.request.Request(url, data=data, method="POST", headers={
            "Content-Type": "application/json", "X-Ops-Hub-Key": secret})
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                return SendResult(True, response.status, _read_json(response.read()), None, attempt + 1)
        except urllib.error.HTTPError as error:
            reply = _read_json(error.read())
            result = SendResult(False, error.code, reply, f"n8n replied {error.code}", attempt + 1)
            if error.code < 500 or (reply or {}).get("logged") is True:
                return result  # retrying can't help, or would log the check twice
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as error:
            reason = getattr(error, "reason", error)
            timed_out = isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason)
            text = "timed out waiting for n8n" if timed_out else f"could not connect to n8n ({reason})"
            result = SendResult(False, None, None, text, attempt + 1)
        if attempt < len(delays):
            sleep(delays[attempt])
    return result


def _read_json(raw):
    try:
        value = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None
