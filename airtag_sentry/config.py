"""Configuration loading: everything comes from the environment (.env)."""

from __future__ import annotations

import dataclasses
import logging
import os
from urllib.parse import quote

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing or inconsistent."""


@dataclasses.dataclass
class AnisetteConfig:
    mode: str
    libs_path: str
    remote_url: str | None


@dataclasses.dataclass
class AppleConfig:
    store_path: str
    anisette: AnisetteConfig
    owner_session_dir: str


@dataclasses.dataclass
class WebConfig:
    host: str
    port: int


@dataclasses.dataclass
class AuthConfig:
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_allowed_username: str
    session_secret_key: str


@dataclasses.dataclass
class WebPushConfig:
    public_key: str
    private_key: str
    subject: str


@dataclasses.dataclass
class NotificationsConfig:
    # Telegram is not here: it's entered via the dashboard's Settings panel
    # and stored encrypted in Postgres (see db.get_telegram_credentials),
    # not read from the environment at startup - same treatment owner-
    # tracking's Apple password got.
    webpush: WebPushConfig | None


@dataclasses.dataclass
class Config:
    apple: AppleConfig
    web: WebConfig
    auth: AuthConfig
    database_url: str
    key_encryption_key: str
    notifications: NotificationsConfig


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _env_str(name: str, default: str) -> str:
    return _env(name) or default


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value is not None else default


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


def load_config() -> Config:
    apple = AppleConfig(
        store_path=_env_str("APPLE_STORE_PATH", "data/account.json"),
        anisette=AnisetteConfig(
            mode=_env_str("ANISETTE_MODE", "local"),
            libs_path=_env_str("ANISETTE_LIBS_PATH", "data/ani_libs.bin"),
            remote_url=_env("ANISETTE_REMOTE_URL"),
        ),
        owner_session_dir=_env_str("APPLE_OWNER_SESSION_PATH", "data/pyicloud_session"),
    )

    web = WebConfig(host=_env_str("WEB_HOST", "0.0.0.0"), port=_env_int("WEB_PORT", 8000))

    oidc_issuer = _env("OIDC_ISSUER")
    oidc_client_id = _env("OIDC_CLIENT_ID")
    oidc_client_secret = _env("OIDC_CLIENT_SECRET")
    oidc_allowed_username = _env("OIDC_ALLOWED_USERNAME")
    session_secret_key = _env("SESSION_SECRET_KEY")
    missing_auth = [
        name
        for name, value in [
            ("OIDC_ISSUER", oidc_issuer),
            ("OIDC_CLIENT_ID", oidc_client_id),
            ("OIDC_CLIENT_SECRET", oidc_client_secret),
            ("OIDC_ALLOWED_USERNAME", oidc_allowed_username),
            ("SESSION_SECRET_KEY", session_secret_key),
        ]
        if not value
    ]
    if missing_auth:
        raise ConfigError(
            "Missing required dashboard-login env var(s): " + ", ".join(missing_auth)
        )
    auth = AuthConfig(
        oidc_issuer=oidc_issuer,
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_allowed_username=oidc_allowed_username,
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

    vapid_public = _env("VAPID_PUBLIC_KEY")
    vapid_private = _env("VAPID_PRIVATE_KEY")
    vapid_subject = _env("VAPID_SUBJECT")
    webpush = (
        WebPushConfig(public_key=vapid_public, private_key=vapid_private, subject=vapid_subject)
        if vapid_public and vapid_private and vapid_subject
        else None
    )

    notifications = NotificationsConfig(webpush=webpush)
    if not webpush:
        logger.warning(
            "VAPID web push is not configured, and Telegram is set up separately "
            "in the dashboard's Settings panel - movement alerts may only show up "
            "in the logs and the dashboard's alert list."
        )

    return Config(
        apple=apple,
        web=web,
        auth=auth,
        database_url=database_url,
        key_encryption_key=key_encryption_key,
        notifications=notifications,
    )
