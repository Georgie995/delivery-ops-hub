"""Sender settings from ops-hub.toml. The webhook secret comes only from the environment,
so it can never end up in a settings file that gets shared or committed."""

import os
import tomllib
from pathlib import Path

REQUIRED = ("manifest_doctor_path", "reports_dir", "webhook_url", "outbox_dir")
DEFAULTS = {"timeout_seconds": 10, "max_error_chars": 500}  # configurable defaults
SECRET_VARIABLE = "OPS_HUB_WEBHOOK_SECRET"


class SettingsError(Exception):
    """The sender can't run with these settings (exit code 3)."""


def load_settings(path):
    path = Path(path)
    if not path.exists():
        raise SettingsError(f"settings file {path} not found (copy ops-hub.example.toml to start)")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"settings file {path} is not valid TOML: {error}") from error

    unknown = set(data) - set(REQUIRED) - set(DEFAULTS)
    if unknown:
        raise SettingsError(f"{path}: unknown setting(s): {', '.join(sorted(unknown))}")
    missing = [key for key in REQUIRED if not data.get(key)]
    if missing:
        raise SettingsError(f"{path}: missing setting(s): {', '.join(missing)}")
    if not str(data["webhook_url"]).startswith(("http://", "https://")):
        raise SettingsError(f"{path}: webhook_url must start with http:// or https://")

    settings = {**DEFAULTS, **data}
    if not isinstance(settings["timeout_seconds"], (int, float)) or settings["timeout_seconds"] <= 0:
        raise SettingsError(f"{path}: timeout_seconds must be a positive number")
    if not isinstance(settings["max_error_chars"], int) or settings["max_error_chars"] < 50:
        raise SettingsError(f"{path}: max_error_chars must be a whole number of at least 50")
    return settings


def get_secret(env=None):
    env = os.environ if env is None else env
    secret = env.get(SECRET_VARIABLE, "").strip()
    if not secret:
        raise SettingsError(f"{SECRET_VARIABLE} is not set. Set it to the same secret stored in n8n's "
                            "Header Auth credential.")
    return secret
