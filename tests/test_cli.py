"""Tests: the check and resend commands, end to end, with the stand-in manifest-doctor
and the local test server."""

import json

from conftest import SECRET, sample_report
from delivery_ops_hub.cli import main


def settings_file(tmp_path, doctor_path, url):
    path = tmp_path / "ops-hub.toml"
    path.write_text(
        f'manifest_doctor_path = "{doctor_path.as_posix()}"\n'
        f'reports_dir = "{(tmp_path / "reports").as_posix()}"\n'
        f'webhook_url = "{url}"\n'
        f'outbox_dir = "{(tmp_path / "outbox").as_posix()}"\n', encoding="utf-8")
    return path


def run(tmp_path, fake_doctor, url, *args, command="check"):
    config = settings_file(tmp_path, fake_doctor.path, url)
    extra = ["D:/Incoming/ShowA", "--manifest", "m.md5"] if command == "check" else []
    return main(["--config", str(config), command, *extra, *args])


def outbox(tmp_path):
    folder = tmp_path / "outbox"
    return sorted(folder.glob("*.json")) if folder.exists() else []


def test_problems_found_is_sent_and_exits_1(tmp_path, fake_doctor, local_server, monkeypatch, capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=1, report=sample_report())
    local_server.replies = [(200, {"logged": True, "alerted": True, "alert_mode": "dry_run"})]
    assert run(tmp_path, fake_doctor, local_server.url) == 1
    assert local_server.requests[0]["json"]["status"] == "PROBLEMS_FOUND"
    out = capsys.readouterr().out
    assert "PROBLEMS_FOUND" in out and "alerted" in out


def test_clean_and_warnings_exit_0(tmp_path, fake_doctor, local_server, monkeypatch):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=0, report=sample_report("PASSED WITH WARNINGS", 0))
    assert run(tmp_path, fake_doctor, local_server.url) == 0
    assert local_server.requests[0]["json"]["status"] == "PASSED_WITH_WARNINGS"


def test_could_not_check_is_sent_as_not_checked_and_exits_2(tmp_path, fake_doctor, local_server, monkeypatch):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=2, stderr="manifest-doctor: error: D:/Incoming/ShowA: does not exist")
    assert run(tmp_path, fake_doctor, local_server.url) == 2
    sent = local_server.requests[0]["json"]
    assert sent["status"] == "NOT_CHECKED"
    assert "does not exist" in sent["error_message"]
    assert sent["tree"] == "D:/Incoming/ShowA"


def test_doctor_that_produced_no_report_is_not_checked_even_with_exit_1(tmp_path, fake_doctor, local_server,
                                                                       monkeypatch):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=1, stderr="Traceback ... something crashed")
    assert run(tmp_path, fake_doctor, local_server.url) == 2
    assert local_server.requests[0]["json"]["status"] == "NOT_CHECKED"


def test_missing_secret_stops_before_running_the_check(tmp_path, fake_doctor, local_server, monkeypatch, capsys):
    monkeypatch.delenv("OPS_HUB_WEBHOOK_SECRET", raising=False)
    fake_doctor.behave(exit_code=0, report=sample_report("CLEAN", 0))
    assert run(tmp_path, fake_doctor, local_server.url) == 3
    assert "OPS_HUB_WEBHOOK_SECRET is not set" in capsys.readouterr().err
    assert not (tmp_path / "reports").exists()  # the check never ran
    assert local_server.requests == []


def test_unreachable_n8n_saves_to_outbox_and_exits_3(tmp_path, fake_doctor, closed_port_url, monkeypatch, capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr("delivery_ops_hub.send.time.sleep", lambda s: None)
    fake_doctor.behave(exit_code=1, report=sample_report())
    assert run(tmp_path, fake_doctor, closed_port_url) == 3
    [saved] = outbox(tmp_path)
    content = saved.read_text(encoding="utf-8")
    assert json.loads(content)["status"] == "PROBLEMS_FOUND"
    assert SECRET not in content
    err = capsys.readouterr().err
    assert "NOT DELIVERED" in err and "resend" in err


def test_rejected_by_n8n_is_kept_in_outbox_and_explained(tmp_path, fake_doctor, local_server, monkeypatch, capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=0, report=sample_report("CLEAN", 0))
    local_server.replies = [(403, {"error": "wrong key"})]
    assert run(tmp_path, fake_doctor, local_server.url) == 3
    assert len(outbox(tmp_path)) == 1
    assert "403" in capsys.readouterr().err


def test_logged_but_teams_failed_is_loud_and_not_put_in_outbox(tmp_path, fake_doctor, local_server, monkeypatch,
                                                               capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    fake_doctor.behave(exit_code=1, report=sample_report())
    local_server.replies = [(502, {"logged": True, "alerted": False, "error": "Teams unreachable"})]
    assert run(tmp_path, fake_doctor, local_server.url) == 3
    assert outbox(tmp_path) == []  # already logged; resending would log it twice
    assert "TEAMS ALERT FAILED" in capsys.readouterr().err


def test_resend_delivers_waiting_messages_and_removes_only_confirmed_ones(tmp_path, fake_doctor, local_server,
                                                                         monkeypatch):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    folder = tmp_path / "outbox"
    folder.mkdir()
    for n in (1, 2):
        (folder / f"evt-{n}.json").write_text(json.dumps({"schema_version": 1, "event_id": f"evt-{n}"}),
                                              encoding="utf-8")
    (folder / "notes.txt").write_text("not ours", encoding="utf-8")
    local_server.replies = [(200, {"logged": True}), (403, {"error": "wrong key"})]
    assert run(tmp_path, fake_doctor, local_server.url, command="resend") == 3
    assert [p.name for p in outbox(tmp_path)] == ["evt-2.json"]   # the rejected one stays
    assert (folder / "notes.txt").exists()                          # never touches other files


def test_404_explains_what_it_usually_means(tmp_path, fake_doctor, local_server, monkeypatch, capsys):
    # Georgi's hands-on run: "n8n replied 404" right after starting n8n wasn't clear enough.
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    folder = tmp_path / "outbox"
    folder.mkdir()
    (folder / "evt-1.json").write_text(json.dumps({"schema_version": 1, "event_id": "evt-1"}), encoding="utf-8")
    local_server.replies = [(404, {"message": "not registered"})]
    assert run(tmp_path, fake_doctor, local_server.url, command="resend") == 3
    err = capsys.readouterr().err
    assert "n8n is still starting, or the workflow isn't published" in err
    assert "wait 20 seconds and resend" in err.lower()


def test_resend_with_empty_outbox_exits_0(tmp_path, fake_doctor, local_server, monkeypatch, capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    assert run(tmp_path, fake_doctor, local_server.url, command="resend") == 0
    assert "nothing to resend" in capsys.readouterr().out.lower()


def test_secret_never_appears_in_any_output(tmp_path, fake_doctor, local_server, closed_port_url, monkeypatch,
                                            capsys):
    monkeypatch.setenv("OPS_HUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr("delivery_ops_hub.send.time.sleep", lambda s: None)
    fake_doctor.behave(exit_code=1, report=sample_report())
    run(tmp_path, fake_doctor, local_server.url)
    run(tmp_path, fake_doctor, closed_port_url)
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
