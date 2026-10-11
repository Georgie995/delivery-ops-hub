"""Tests: running manifest-doctor and finding its new report."""

from pathlib import Path

import pytest

from conftest import sample_report
from delivery_ops_hub.runner import run_manifest_doctor

REAL_DOCTOR = Path(__file__).resolve().parents[2] / "delivery-verify"


def test_passes_arguments_through_and_adds_the_reports_folder(fake_doctor, tmp_path):
    fake_doctor.behave(exit_code=0, report=sample_report("CLEAN", 0))
    run_manifest_doctor(fake_doctor.path, ["D:/Incoming/ShowA", "--manifest", "m.md5"], tmp_path / "reports")
    assert fake_doctor.received_args == ["check", "D:/Incoming/ShowA", "--manifest", "m.md5",
                                         "--out", str(tmp_path / "reports")]


def test_finds_the_new_report_folder(fake_doctor, tmp_path):
    (tmp_path / "reports" / "report-2020-01-01_000000").mkdir(parents=True)  # an old one: must be ignored
    fake_doctor.behave(exit_code=1, report=sample_report())
    result = run_manifest_doctor(fake_doctor.path, ["D:/x", "--manifest", "m"], tmp_path / "reports")
    assert result.exit_code == 1
    assert result.report_folder.name == "report-2026-10-11_183205"


def test_exit_code_2_has_no_report_and_keeps_the_error_text(fake_doctor, tmp_path):
    fake_doctor.behave(exit_code=2, stderr="manifest-doctor: error: D:/x: does not exist")
    result = run_manifest_doctor(fake_doctor.path, ["D:/x", "--manifest", "m"], tmp_path / "reports")
    assert (result.exit_code, result.report_folder) == (2, None)
    assert "does not exist" in result.stderr


def test_wrong_manifest_doctor_path_is_reported_not_mistaken_for_problems(tmp_path):
    # Python exits 1 when a module can't be found, the same number as "problems found".
    # With no new report, the result must not be treated as a real check.
    result = run_manifest_doctor(tmp_path / "no_such_folder", ["D:/x", "--manifest", "m"], tmp_path / "reports")
    assert result.report_folder is None
    assert "No module named" in result.stderr


def test_out_option_in_the_arguments_is_refused(fake_doctor, tmp_path):
    with pytest.raises(ValueError, match="--out"):
        run_manifest_doctor(fake_doctor.path, ["D:/x", "--out", "elsewhere"], tmp_path / "reports")


@pytest.mark.skipif(not (REAL_DOCTOR / "manifest_doctor").exists(), reason="manifest-doctor repo not next to this one")
def test_works_with_the_real_manifest_doctor(tmp_path):
    import hashlib
    tree = tmp_path / "delivery"
    tree.mkdir()
    (tree / "a.mov").write_bytes(b"aaa")
    manifest = tmp_path / "m.md5"
    manifest.write_text(f"{hashlib.md5(b'aaa').hexdigest()}  a.mov\n", encoding="utf-8")
    result = run_manifest_doctor(REAL_DOCTOR, [str(tree), "--manifest", str(manifest)], tmp_path / "reports")
    assert result.exit_code == 0
    assert (result.report_folder / "report.json").exists()
