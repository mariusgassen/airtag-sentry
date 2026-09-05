"""Configuration loading: config.yaml (app behavior) + .env (secrets/infra)."""

from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet
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
    polling: PollingConfig
    movement: MovementConfig
    web: WebConfig
    auth: AuthConfig
    database_url: str
    key_encryption_key: str
    notifications: NotificationsConfig


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def database_url_from_env() -> str:
    """Build the Postgres connection URL from POSTGRES_* env vars.

    Standalone (not folded into load_config) so alembic/env.py can call it
    without needing the rest of the app's config (GitHub OAuth, encryption
    key) just to run a migration.
    """
    postgres_user = _env("POSTGRES_USER")
    postgres_password = _env("POSTGRES_PASSWORD")
    postgres_db = _env("POSTGRES_DB")
    missing_postgres = [
        name
        for name, value in [
            ("POSTGRES_USER", postgres_user),
            ("POSTGRES_PASSWORD", postgres_password),
            ("POSTGRES_DB", postgres_db),
        ]
        if not value
    ]
    if missing_postgres:
        raise ConfigError("Missing required Postgres env var(s): " + ", ".join(missing_postgres))
    postgres_host = _env("POSTGRES_HOST") or "localhost"
    postgres_port = _env("POSTGRES_PORT") or "5432"
    return (
        f"postgresql://{quote(postgres_user, safe='')}:{quote(postgres_password, safe='')}"
        f"@{postgres_host}:{postgres_port}/{quote(postgres_db, safe='')}"
    )


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

    database_url = database_url_from_env()

    key_encryption_key = _env("AIRTAG_KEY_ENCRYPTION_KEY")
    if not key_encryption_key:
        raise ConfigError(
            "AIRTAG_KEY_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        Fernet(key_encryption_key.encode())
    except ValueError as exc:
        raise ConfigError(f"AIRTAG_KEY_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc

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
        polling=polling,
        movement=movement,
        web=web,
        auth=auth,
        database_url=database_url,
        key_encryption_key=key_encryption_key,
        notifications=notifications,
    )
