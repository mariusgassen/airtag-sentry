"""Configuration loading: config.yaml (app behavior) + .env (secrets/infra)."""

from __future__ import annotations

import dataclasses
import logging
import os
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
    airtag: AirtagConfig
    polling: PollingConfig
    movement: MovementConfig
    web: WebConfig
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

    airtag_raw = raw.get("airtag", {}) or {}
    accessory_json_path = airtag_raw.get("accessory_json_path")
    private_key_b64 = _env("AIRTAG_PRIVATE_KEY_B64")
    if bool(accessory_json_path) == bool(private_key_b64):
        raise ConfigError(
            "Set exactly one of airtag.accessory_json_path (config.yaml) or "
            "AIRTAG_PRIVATE_KEY_B64 (.env) as the AirTag's key source."
        )
    airtag = AirtagConfig(
        name=airtag_raw.get("name", "AirTag"),
        accessory_json_path=accessory_json_path,
        private_key_b64=private_key_b64,
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
        airtag=airtag,
        polling=polling,
        movement=movement,
        web=web,
        database_url=database_url,
        notifications=notifications,
    )
