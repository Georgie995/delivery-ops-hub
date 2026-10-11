"""Shared test helpers.

- `local_server`: a tiny web server inside the test, on this PC only (127.0.0.1). Each test
  queues the replies it wants and checks what was received. No internet, no n8n.
- `fake_doctor`: a stand-in manifest-doctor whose exit code, report and error text each
  test chooses. It runs as a real separate program, exactly like the real one.
- `make_report`: writes a report folder with a report.json like manifest-doctor's.
"""

import json
import socket
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SECRET = "test-secret-1234567890"


class Server:
    def __init__(self):
        self.replies = []    # queued (status, body) or ("hang", seconds)
        self.requests = []   # what was received: {"path", "headers", "json"}

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/webhook/delivery-check"


@pytest.fixture
def local_server():
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            state.requests.append({"path": self.path, "headers": dict(self.headers),
                                   "json": json.loads(body) if body else None})
            reply = state.replies.pop(0) if state.replies else (200, {"logged": True, "alerted": False,
                                                                      "alert_mode": "none"})
            if reply[0] == "hang":
                time.sleep(reply[1])
                reply = (200, {"logged": True})
            status, payload = reply
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass  # keep test output quiet

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture
def closed_port_url():
    """A local address where nothing is listening, like n8n being switched off."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/webhook/delivery-check"


def sample_report(result="PROBLEMS FOUND", exit_code=1, counts=None, causes=None, tree="D:/Incoming/ShowA"):
    if counts is None:
        counts = {"ERROR": 2, "WARNING": 1, "INFO": 0} if exit_code == 1 else {"ERROR": 0, "WARNING": 0, "INFO": 0}
    if causes is None:
        causes = [
            {"code": "CAUSE_DUPLICATE_LISTING", "severity": "ERROR", "summary": "1 path is listed more than once.",
             "paths": ["ShowA/a.mov"], "note": "Probable cause, not a verdict."},
            {"code": "CAUSE_WRAPPER_FOLDER", "severity": "WARNING", "summary": "3 files only match once...",
             "paths": ["W/a", "W/b", "W/c"], "note": "Probable cause, not a verdict."},
        ]
    return {"header": {"tool": "manifest-doctor", "version": "0.1.0", "run_at": "2026-10-11T18:32:05+01:00",
                       "tree": tree, "result": result, "exit_code": exit_code, "counts": counts},
            "causes": causes, "findings": []}


@pytest.fixture
def make_report(tmp_path):
    def make(name="report-2026-10-11_183205", **kwargs):
        folder = tmp_path / "reports" / name
        folder.mkdir(parents=True)
        (folder / "report.json").write_text(json.dumps(sample_report(**kwargs)), encoding="utf-8")
        return folder
    return make


@pytest.fixture
def fake_doctor(tmp_path, monkeypatch):
    """Create a stand-in manifest_doctor package. Configure it per test with behave(...)."""
    root = tmp_path / "fake_doctor"
    package = root / "manifest_doctor"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(textwrap.dedent('''
        import json, os, sys
        from pathlib import Path
        behaviour = json.loads(os.environ["FAKE_DOCTOR"])
        args = sys.argv[1:]
        out = Path(args[args.index("--out") + 1])
        Path(os.environ["FAKE_DOCTOR_ARGS"]).write_text(json.dumps(args), encoding="utf-8")
        if behaviour.get("report"):
            folder = out / "report-2026-10-11_183205"
            folder.mkdir(parents=True)
            (folder / "report.json").write_text(json.dumps(behaviour["report"]), encoding="utf-8")
        if behaviour.get("stderr"):
            print(behaviour["stderr"], file=sys.stderr)
        sys.exit(behaviour["exit_code"])
    '''), encoding="utf-8")
    args_file = tmp_path / "fake_doctor_args.json"
    monkeypatch.setenv("FAKE_DOCTOR_ARGS", str(args_file))

    class Doctor:
        path = root

        def behave(self, exit_code, report=None, stderr=""):
            monkeypatch.setenv("FAKE_DOCTOR", json.dumps({"exit_code": exit_code, "report": report,
                                                          "stderr": stderr}))

        @property
        def received_args(self):
            return json.loads(args_file.read_text(encoding="utf-8"))

    return Doctor()
