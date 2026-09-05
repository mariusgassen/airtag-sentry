import pytest

from airtag_sentry.config import ConfigError, database_url_from_env


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
