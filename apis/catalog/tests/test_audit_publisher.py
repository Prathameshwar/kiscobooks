"""Catalog's supervisor supplies only the explicit audit contracts and authority."""

from __future__ import annotations

import asyncio
import runpy
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from billing_platform.publisher import PublisherConfig
from pydantic import SecretStr

from catalog.events.audit_contract import AUDIT_EVENTS, audit_event
from catalog.tasks import audit_publisher


def settings() -> audit_publisher.AuditPublisherSettings:
    return audit_publisher.AuditPublisherSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        audit_broker_url=SecretStr("amqp://ephemeral.invalid"),
        audit_broker_user="catalog_audit",
        audit_event_secret=SecretStr("ephemeral-catalog-audit-secret" * 2),
        audit_batch_limit=10,
        audit_timeout_seconds=2,
    )


def test_unregistered_audit_route_is_rejected_at_the_emitter() -> None:
    with pytest.raises(ValueError, match="unregistered Catalog audit event"):
        audit_event("catalog.item_group", "unregistered_action")
    assert audit_event("catalog.item_group", "move") in AUDIT_EVENTS


async def test_catalog_publisher_contract_is_explicit_and_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[PublisherConfig] = []

    async def run(config: PublisherConfig) -> None:
        captured.append(config)

    monkeypatch.setattr(audit_publisher, "run_publisher", run)
    config = settings()
    await audit_publisher.run(config)
    assert len(captured) == 1
    value = captured[0]
    assert value.database_url == config.database_url
    assert value.broker_url == config.audit_broker_url.get_secret_value()
    assert value.broker_user == "catalog_audit" and value.exchange == "platform.audit"
    assert value.key.issuer == "catalog" and value.key.audience == "audit"
    assert value.key.operations == AUDIT_EVENTS
    assert {
        "catalog.custom_field_adoption.adopt",
        "catalog.item_price.publish",
        "catalog.tax_release.publish",
        "catalog.bulk_job.update",
    } <= value.key.operations
    assert all(name.startswith("catalog.") and "*" not in name for name in value.key.operations)
    assert value.batch_limit == 10 and value.timeout_seconds == 2
    assert "identity.catalog_context.changed" not in value.key.operations
    assert "catalog.product.published" not in value.key.operations
    assert config.audit_event_secret.get_secret_value() not in repr(value)


def test_catalog_publisher_environment_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["catalog-publisher"])
    config = settings()
    values = {
        "DATABASE_URL": config.database_url,
        "AUDIT_BROKER_URL": config.audit_broker_url.get_secret_value(),
        "AUDIT_BROKER_USER": config.audit_broker_user,
        "AUDIT_EVENT_SECRET": config.audit_event_secret.get_secret_value(),
    }
    for key, value in values.items():
        monkeypatch.setenv("CATALOG_" + key, value)
    called = 0

    def run(coroutine: Coroutine[Any, Any, None]) -> None:
        nonlocal called
        called += 1
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run)
    audit_publisher.main()
    runpy.run_path(str(Path(audit_publisher.__file__)), run_name="__main__")
    assert called == 2
    monkeypatch.setenv("CATALOG_AUDIT_EVENT_SECRET", "short")
    with pytest.raises(SystemExit, match="ValidationError"):
        audit_publisher.main()


def test_operations_dispatch_and_safe_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    config = settings()
    monkeypatch.setattr(audit_publisher, "AuditPublisherSettings", lambda **kwargs: config)
    operation = AsyncMock()
    monkeypatch.setattr(audit_publisher, "operate", operation)
    monkeypatch.setattr(
        audit_publisher,
        "arguments",
        lambda _: SimpleNamespace(status=True, retry=None, dead_letters=None, env_file=None),
    )
    audit_publisher.main()
    assert operation.await_count == 1
    operation.side_effect = RuntimeError("private broker password")
    with pytest.raises(SystemExit, match="RuntimeError") as error:
        audit_publisher.main()
    assert "password" not in str(error.value)
