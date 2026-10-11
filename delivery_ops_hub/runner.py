"""Run manifest-doctor as a separate program and find the report it wrote."""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    exit_code: int | None   # None if it couldn't even be started
    report_folder: Path | None
    stdout: str
    stderr: str


def run_manifest_doctor(doctor_path, args, reports_dir):
    if "--out" in args:
        raise ValueError("--out is set by delivery-ops-hub (reports_dir in ops-hub.toml); remove it")
    reports_dir = Path(reports_dir)
    before = _report_folders(reports_dir)

    env = dict(os.environ)
    # Run manifest-doctor straight from its folder, without installing it.
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(doctor_path), env.get("PYTHONPATH")]))
    env["PYTHONIOENCODING"] = "utf-8"  # so accented file names survive the trip back
    command = [sys.executable, "-m", "manifest_doctor", "check", *args, "--out", str(reports_dir)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=env)
    except OSError as error:
        return RunResult(None, None, "", f"could not start manifest-doctor: {error}")

    # Compare folder lists before and after, rather than parsing printed text that could change.
    new = sorted(_report_folders(reports_dir) - before)
    folder = new[-1] if new and (new[-1] / "report.json").exists() else None
    return RunResult(completed.returncode, folder, completed.stdout.strip(), completed.stderr.strip())


def _report_folders(reports_dir):
    if not reports_dir.exists():
        return set()
    return {p for p in reports_dir.iterdir() if p.is_dir() and p.name.startswith("report-")}
