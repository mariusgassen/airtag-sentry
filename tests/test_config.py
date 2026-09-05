import pytest

from airtag_sentry.config import ConfigError, database_url_from_env, load_config


@pytest.fixture()
def postgres_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "airtag")
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    monkeypatch.setenv("POSTGRES_DB", "airtag_sentry")
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)


def test_database_url_derived_with_defaults(postgres_env):
    assert (
        database_url_from_env()
        == "postgresql://airtag:change-me@localhost:5432/airtag_sentry"
    )


def test_database_url_honors_host_and_port_overrides(postgres_env, monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    assert (
        database_url_from_env()
        == "postgresql://airtag:change-me@postgres:5433/airtag_sentry"
    )


def test_database_url_escapes_special_characters(postgres_env, monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/w:rd?")
    url = database_url_from_env()
    assert url == "postgresql://airtag:p%40ss%2Fw%3Ard%3F@localhost:5432/airtag_sentry"


def test_database_url_requires_postgres_vars(monkeypatch):
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    with pytest.raises(ConfigError, match="POSTGRES_USER"):
        database_url_from_env()


@pytest.fixture()
def required_env(postgres_env, monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GITHUB_ALLOWED_LOGIN", "octocat")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-secret")
    monkeypatch.setenv(
        "AIRTAG_KEY_ENCRYPTION_KEY",
        "PTx2A3nrHR9wKR_hqK0YtxHZgHqEeZOo8VvV3XwZjxA=",
    )
    for name in (
        "APPLE_STORE_PATH",
        "ANISETTE_MODE",
        "ANISETTE_LIBS_PATH",
        "ANISETTE_REMOTE_URL",
        "WEB_HOST",
        "WEB_PORT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_load_config_defaults(required_env):
    cfg = load_config()

    assert cfg.apple.store_path == "data/account.json"
    assert cfg.apple.anisette.mode == "local"
    assert cfg.apple.anisette.libs_path == "data/ani_libs.bin"
    assert cfg.apple.anisette.remote_url is None
    assert cfg.web.host == "0.0.0.0"
    assert cfg.web.port == 8000


def test_load_config_honors_overrides(required_env, monkeypatch):
    monkeypatch.setenv("ANISETTE_MODE", "remote")
    monkeypatch.setenv("ANISETTE_REMOTE_URL", "http://anisette:6969")
    monkeypatch.setenv("WEB_PORT", "9000")

    cfg = load_config()

    assert cfg.apple.anisette.mode == "remote"
    assert cfg.apple.anisette.remote_url == "http://anisette:6969"
    assert cfg.web.port == 9000
