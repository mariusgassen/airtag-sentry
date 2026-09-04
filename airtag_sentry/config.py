"""Configuration loading: config.yaml (app behavior) + .env (secrets/infra)."""

from __future__ import annotations

import dataclasses
import logging
import os
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when config.yaml / the environment is missing or inconsistent."""


@dataclasses.dataclass
class AnisetteConfig:
    mode: str
    libs_path: str
    remote_url: str | None


@dataclasses.dataclass
class AppleConfig:
    store_path: str
    anisette: AnisetteConfig


@dataclasses.dataclass
class AirtagConfig:
    id: str
    name: str
    accessory_json_path: str | None
    private_key_b64: str | None


@dataclasses.dataclass
class PollingConfig:
    interval_minutes: int


@dataclasses.dataclass
class MovementConfig:
    distance_threshold_meters: float
    stillstand_hours: float
    stillstand_movement_meters: float
    alert_on_backfill: bool


@dataclasses.dataclass
class WebConfig:
    host: str
    port: int


@dataclasses.dataclass
class AuthConfig:
    github_client_id: str
    github_client_secret: str
    allowed_login: str
    session_secret_key: str


@dataclasses.dataclass
class NtfyConfig:
    topic_url: str


@dataclasses.dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclasses.dataclass
class WebPushConfig:
    public_key: str
    private_key: str
    subject: str


@dataclasses.dataclass
class NotificationsConfig:
    ntfy: NtfyConfig | None
    telegram: TelegramConfig | None
    webpush: WebPushConfig | None


@dataclasses.dataclass
class Config:
    apple: AppleConfig
    airtags: list[AirtagConfig]
    polling: PollingConfig
    movement: MovementConfig
    web: WebConfig
    auth: AuthConfig
    database_url: str
    notifications: NotificationsConfig


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"{path} not found. Copy config.example.yaml to {path} and adjust it.")
    raw = yaml.safe_load(path.read_text()) or {}

    apple_raw = raw.get("apple", {}) or {}
    anisette_raw = apple_raw.get("anisette", {}) or {}
    apple = AppleConfig(
        store_path=apple_raw.get("store_path", "data/account.json"),
        anisette=AnisetteConfig(
            mode=anisette_raw.get("mode", "local"),
            libs_path=anisette_raw.get("libs_path", "data/ani_libs.bin"),
            remote_url=anisette_raw.get("remote_url"),
        ),
    )

    airtags_raw = raw.get("airtags") or []
    if not airtags_raw:
        raise ConfigError("config.yaml must define at least one entry under 'airtags:'.")

    airtags: list[AirtagConfig] = []
    seen_ids: set[str] = set()
    seen_env_suffixes: dict[str, str] = {}
    for entry in airtags_raw:
        airtag_id = str((entry or {}).get("id") or "").strip()
        if not airtag_id:
            raise ConfigError("Every entry in airtags: must have a non-empty 'id'.")
        if airtag_id in seen_ids:
            raise ConfigError(f"Duplicate airtag id '{airtag_id}' in airtags:.")
        seen_ids.add(airtag_id)

        suffix = re.sub(r"[^A-Za-z0-9]", "_", airtag_id).upper()
        if suffix in seen_env_suffixes:
            raise ConfigError(
                f"airtag ids '{seen_env_suffixes[suffix]}' and '{airtag_id}' both map to "
                f"the same env var AIRTAG_PRIVATE_KEY_B64_{suffix} - use more distinct ids."
            )
        seen_env_suffixes[suffix] = airtag_id

        accessory_json_path = entry.get("accessory_json_path")
        env_name = f"AIRTAG_PRIVATE_KEY_B64_{suffix}"
        private_key_b64 = _env(env_name)
        if bool(accessory_json_path) == bool(private_key_b64):
            raise ConfigError(
                f"airtags[id={airtag_id}]: set exactly one of accessory_json_path "
                f"(config.yaml) or {env_name} (.env) as this AirTag's key source."
            )
        airtags.append(
            AirtagConfig(
                id=airtag_id,
                name=entry.get("name", airtag_id),
                accessory_json_path=accessory_json_path,
                private_key_b64=private_key_b64,
            )
        )

    polling_raw = raw.get("polling", {}) or {}
    polling = PollingConfig(interval_minutes=int(polling_raw.get("interval_minutes", 15)))

    movement_raw = raw.get("movement", {}) or {}
    movement = MovementConfig(
        distance_threshold_meters=float(movement_raw.get("distance_threshold_meters", 100)),
        stillstand_hours=float(movement_raw.get("stillstand_hours", 24)),
        stillstand_movement_meters=float(movement_raw.get("stillstand_movement_meters", 15)),
        alert_on_backfill=bool(movement_raw.get("alert_on_backfill", False)),
    )

    web_raw = raw.get("web", {}) or {}
    web = WebConfig(host=web_raw.get("host", "0.0.0.0"), port=int(web_raw.get("port", 8000)))

    github_client_id = _env("GITHUB_CLIENT_ID")
    github_client_secret = _env("GITHUB_CLIENT_SECRET")
    allowed_login = _env("GITHUB_ALLOWED_LOGIN")
    session_secret_key = _env("SESSION_SECRET_KEY")
    missing_auth = [
        name
        for name, value in [
            ("GITHUB_CLIENT_ID", github_client_id),
            ("GITHUB_CLIENT_SECRET", github_client_secret),
            ("GITHUB_ALLOWED_LOGIN", allowed_login),
            ("SESSION_SECRET_KEY", session_secret_key),
        ]
        if not value
    ]
    if missing_auth:
        raise ConfigError(
            "Missing required dashboard-login env var(s): " + ", ".join(missing_auth)
        )
    auth = AuthConfig(
        github_client_id=github_client_id,
        github_client_secret=github_client_secret,
        allowed_login=allowed_login,
        session_secret_key=session_secret_key,
    )

    database_url = _env("DATABASE_URL")
    if not database_url:
        raise ConfigError("DATABASE_URL is not set. Copy .env.example to .env and adjust it.")

    ntfy_url = _env("NTFY_TOPIC_URL")
    ntfy = NtfyConfig(topic_url=ntfy_url) if ntfy_url else None

    tg_token = _env("TELEGRAM_BOT_TOKEN")
    tg_chat = _env("TELEGRAM_CHAT_ID")
    telegram = TelegramConfig(bot_token=tg_token, chat_id=tg_chat) if tg_token and tg_chat else None

    vapid_public = _env("VAPID_PUBLIC_KEY")
    vapid_private = _env("VAPID_PRIVATE_KEY")
    vapid_subject = _env("VAPID_SUBJECT")
    webpush = (
        WebPushConfig(public_key=vapid_public, private_key=vapid_private, subject=vapid_subject)
        if vapid_public and vapid_private and vapid_subject
        else None
    )

    notifications = NotificationsConfig(ntfy=ntfy, telegram=telegram, webpush=webpush)
    if not any([ntfy, telegram, webpush]):
        logger.warning(
            "No notifier configured (ntfy/telegram/webpush) - movement alerts will "
            "only show up in the logs and the dashboard's alert list."
        )

    return Config(
        apple=apple,
        airtags=airtags,
        polling=polling,
        movement=movement,
        web=web,
        auth=auth,
        database_url=database_url,
        notifications=notifications,
    )
