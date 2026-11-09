from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import init_db


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://demo:fixture@db.project.supabase.co:5432/postgres?sslmode=require",
    "postgresql+psycopg://demo:fixture@127.0.0.1:5432/vestinova",
    "postgresql+psycopg://demo:fixture@other.example.test:5432/vestinova_mvp",
])
def test_local_initializer_refuses_other_targets_before_connecting(monkeypatch, url):
    monkeypatch.setattr(init_db.Settings, "from_env", lambda: SimpleNamespace(database_url=url))
    connect = MagicMock()
    upgrade = MagicMock()
    monkeypatch.setattr(init_db.psycopg, "connect", connect)
    monkeypatch.setattr(init_db.command, "upgrade", upgrade)
    with pytest.raises(ValueError):
        init_db.main()
    connect.assert_not_called()
    upgrade.assert_not_called()


def test_existing_local_database_is_migrated_without_recreation(monkeypatch):
    url = "postgresql+psycopg://demo:fixture@127.0.0.1:5432/vestinova_mvp"
    monkeypatch.setattr(init_db.Settings, "from_env", lambda: SimpleNamespace(database_url=url))
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (1,)
    context = MagicMock()
    context.__enter__.return_value = connection
    connect = MagicMock(return_value=context)
    upgrade = MagicMock()
    monkeypatch.setattr(init_db.psycopg, "connect", connect)
    monkeypatch.setattr(init_db.command, "upgrade", upgrade)
    init_db.main()
    assert connect.call_args.kwargs["dbname"] == "postgres"
    assert connection.execute.call_count == 1
    assert connection.execute.call_args.args[1] == ("vestinova_mvp",)
    assert upgrade.call_args.args[1] == "head"
