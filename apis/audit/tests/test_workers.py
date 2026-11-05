import asyncio
import secrets
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from audit.config import Settings, SourceCredential
from audit.tasks import consume, publish


def settings(**values):
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr(secrets.token_hex(32)),
        cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        **values,
    )


def test_source_event_allowlist_accepts_environment_json_arrays(monkeypatch):
    import json

    monkeypatch.setenv(
        "AUDIT_SOURCE_CREDENTIALS",
        json.dumps(
            {
                "identity.current": {
                    "issuer": "identity",
                    "broker_user": "test",
                    "secret": secrets.token_hex(32),
                    "event_types": [
                        "platform.account_decision_completed",
                        "platform.accounts_read",
                    ],
                }
            }
        ),
    )
    assert settings().source_credentials["identity.current"].event_types == frozenset(
        {"platform.account_decision_completed", "platform.accounts_read"}
    )


async def test_consumer_requires_credentials_and_reconnects_without_logging_secrets(
    monkeypatch, factory, caplog
):
    with pytest.raises(ValueError):
        await consume.run_consumer(settings(), factory)
    configuration = settings(
        broker_url="amqp://isolated.invalid",
        source_credentials={
            "current": SourceCredential(
                issuer="accounting",
                broker_user="test",
                secret=SecretStr(secrets.token_hex(32)),
                event_types=frozenset({"accounting.party.update"}),
            )
        },
    )

    @asynccontextmanager
    async def disconnected(url):
        raise RuntimeError("private connection details")
        yield  # pragma: no cover -- makes an async context manager that fails on entry

    monkeypatch.setattr(consume, "confirmed_channel", disconnected)
    monkeypatch.setattr(consume.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await consume.run_consumer(configuration, factory)
    assert "private connection details" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_export_publisher_has_its_own_identity_and_operations(monkeypatch):
    secret = secrets.token_hex(32)
    values = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "BROKER_URL": "amqp://isolated.invalid",
        "BROKER_USER": "audit",
        "EVENT_SECRET": secret,
    }
    for key, value in values.items():
        monkeypatch.setenv("AUDIT_PUBLISHER_" + key, value)
    config = publish.PublisherSettings().configuration()
    assert config.key.issuer == "audit"
    assert config.key.operations == frozenset({"audit.exported"})
    assert secret not in repr(config)
    monkeypatch.setattr(sys, "argv", ["audit-publisher", "--status"])
    calls = []

    def run(coroutine):
        calls.append(coroutine.cr_code.co_name)
        coroutine.close()

    monkeypatch.setattr(publish.asyncio, "run", run)
    publish.main()
    assert calls == ["operate"]


def test_worker_boot_errors_do_not_disclose_credentials(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["audit-publisher"])

    def fail(**kwargs):
        raise RuntimeError("private connection details")

    monkeypatch.setattr(publish, "PublisherSettings", fail)
    with pytest.raises(SystemExit, match="RuntimeError") as error:
        publish.main()
    assert "private connection" not in str(error.value)
