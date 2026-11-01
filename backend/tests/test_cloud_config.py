import pytest

from app.config import Settings, validate_supabase_database_url


VALID_URL = (
    "postgresql+psycopg://postgres.project:password@"
    "aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
)


def test_supabase_session_pooler_accepts_tls():
    validate_supabase_database_url(VALID_URL)


def test_supabase_direct_accepts_tls():
    validate_supabase_database_url(
        "postgresql+psycopg://postgres:password@db.project.supabase.co:"
        "5432/postgres?sslmode=require"
    )


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://postgres:password@localhost:5432/postgres?sslmode=require",
    "postgresql+psycopg://postgres:password@example.com:5432/postgres?sslmode=require",
    "postgresql+psycopg://postgres:password@db.project.supabase.co:5432/postgres",
    "postgresql+psycopg://postgres:password@db.project.supabase.co:6543/postgres?sslmode=require",
    "postgresql+psycopg://postgres:password@db.project.supabase.co:5432/postgres?sslmode=disable",
    "postgresql+psycopg://postgres:password@db.project.supabase.co:5432/postgres?sslmode=require&host=localhost",
    "postgresql+psycopg://postgres:password@db.project.supabase.co:5432/other?sslmode=require",
    "not-a-url",
])
def test_supabase_rejects_unsafe_or_wrong_database(url):
    with pytest.raises(ValueError) as error:
        validate_supabase_database_url(url)
    assert "password" not in str(error.value)


def test_production_mode_uses_supabase(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("JWT_SECRET", "test_secret_of_at_least_32_characters")
    assert Settings.from_env().database_url == VALID_URL


def test_local_mode_still_rejects_remote(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("JWT_SECRET", "test_secret_of_at_least_32_characters")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_production_requires_valid_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "other")
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("JWT_SECRET", "test_secret_of_at_least_32_characters")
    with pytest.raises(ValueError):
        Settings.from_env()
