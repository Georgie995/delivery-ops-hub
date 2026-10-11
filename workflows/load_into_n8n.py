"""Load the workflow from this repo into the running n8n (Docker), keeping its credential link.

    python workflows/load_into_n8n.py

Steps:
1. build the workflow from workflows/src/;
2. find the Header Auth credential's ID (only the ID and name are read, never its secret);
3. import a copy with that credential linked; the repo copy never contains it;
4. publish the workflow;
5. restart n8n so the published version takes effect, and wait until it's ready.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "delivery-ops-hub-n8n"
WORKFLOW_ID = "deliveryOpsHub01"
sys.path.insert(0, str(ROOT / "workflows"))
from build_workflow import OUTPUT, build, link_credential  # noqa: E402


def n8n(*args):
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}  # stop Git Bash rewriting /files/... paths
    done = subprocess.run(["docker", "exec", CONTAINER, "n8n", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return done.stdout + done.stderr


def header_auth_credential():
    """Return (id, name) of the Header Auth credential. Reads the encrypted export: no secret is decrypted."""
    raw = n8n("export:credentials", "--all")
    credentials = [c for c in json.loads(raw[raw.find("["):]) if c["type"] == "httpHeaderAuth"]
    if len(credentials) != 1:
        sys.exit(f"Expected exactly one Header Auth credential in n8n, found {len(credentials)}.")
    return credentials[0]["id"], credentials[0]["name"]


def wait_until_ready(seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            request = urllib.request.Request("http://127.0.0.1:5678/webhook/delivery-check", data=b"{}",
                                             method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as error:
            if error.code == 403:  # webhook registered and refusing a request without the secret
                return True
        except OSError:
            pass
        time.sleep(2)
    return False


def main():
    OUTPUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    credential_id, credential_name = header_auth_credential()
    import_copy = ROOT / "runtime" / "import-workflow.json"
    try:
        import_copy.write_text(json.dumps(link_credential(build(), credential_id, credential_name)),
                               encoding="utf-8")
        print(n8n("import:workflow", "--input=/files/import-workflow.json").strip().splitlines()[-1])
    finally:
        import_copy.unlink(missing_ok=True)
    print(n8n("publish:workflow", f"--id={WORKFLOW_ID}").strip().splitlines()[0])
    subprocess.run(["docker", "restart", CONTAINER], capture_output=True)
    print("n8n restarted; webhook ready" if wait_until_ready() else "WARNING: webhook not ready after 90 s")


if __name__ == "__main__":
    main()
