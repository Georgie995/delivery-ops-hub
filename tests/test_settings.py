"""Tests: sender settings and the webhook secret."""

import pytest

from delivery_ops_hub.settings import SettingsError, get_secret, load_settings

GOOD = """
manifest_doctor_path = "D:/tools/manifest-doctor"
reports_dir = "D:/DeliveryReports"
webhook_url = "http://localhost:5678/webhook/delivery-check"
outbox_dir = "D:/DeliveryReports/outbox"
"""


def write(tmp_path, text):
    path = tmp_path / "ops-hub.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_settings_are_read_with_defaults(tmp_path):
    settings = load_settings(write(tmp_path, GOOD))
    assert settings["webhook_url"] == "http://localhost:5678/webhook/delivery-check"
    assert settings["timeout_seconds"] == 10
    assert settings["max_error_chars"] == 500


@pytest.mark.parametrize("text, problem", [
    (GOOD.replace('reports_dir = "D:/DeliveryReports"\n', ""), "reports_dir"),
    (GOOD + 'colour = "blue"\n', "colour"),
    (GOOD + "timeout_seconds = -1\n", "timeout_seconds"),
    (GOOD.replace("http://localhost:5678", "ftp://localhost:5678"), "webhook_url"),
    ("this is not toml = = =", "TOML"),
])
def test_mistakes_in_settings_are_reported_clearly(tmp_path, text, problem):
    with pytest.raises(SettingsError, match=problem):
        load_settings(write(tmp_path, text))


def test_missing_settings_file_is_reported(tmp_path):
    with pytest.raises(SettingsError, match="not found"):
        load_settings(tmp_path / "nope.toml")


def test_secret_comes_from_the_environment():
    assert get_secret({"OPS_HUB_WEBHOOK_SECRET": "abc"}) == "abc"


@pytest.mark.parametrize("env", [{}, {"OPS_HUB_WEBHOOK_SECRET": ""}, {"OPS_HUB_WEBHOOK_SECRET": "   "}])
def test_missing_secret_stops_with_a_message_that_does_not_guess(env):
    with pytest.raises(SettingsError, match="OPS_HUB_WEBHOOK_SECRET is not set"):
        get_secret(env)
