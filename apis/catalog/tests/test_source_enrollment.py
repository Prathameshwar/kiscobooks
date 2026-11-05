"""Dynamic enrollment is authenticated, bounded and fail closed on discovery errors."""

from typing import Any

import pytest
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr, ValidationError

from catalog.tasks import identity_source, source_worker
from tests.source_factories import change
from tests.test_identity_source_client import settings


async def test_discovery_downloads_all_pages_and_rejects_cycles_and_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7())
    second = CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7())
    responses = [
        {"scopes": [first.model_dump(mode="json")], "next_cursor": "page2"},
        {"scopes": [second.model_dump(mode="json")], "next_cursor": None},
    ]
    calls: list[dict[str, Any]] = []

    async def request(*args: Any, **kwargs: Any) -> bytes:
        calls.append(kwargs)
        return canonical_json(responses[min(len(calls) - 1, 1)])

    monkeypatch.setattr(identity_source, "_request", request)
    assert await identity_source.fetch_enrollments(settings()) == (first, second)
    assert len(calls) == 2
    assert calls[0]["request_operation"] == "catalog.enrollment.read"
    assert calls[0]["response_operation"] == "catalog.enrollment.response"
    assert b'"cursor":"page2"' in calls[1]["body"]
    calls.clear()
    responses[1] = {"scopes": [second.model_dump(mode="json")], "next_cursor": "page2"}
    with pytest.raises(identity_source.IdentitySourceUnavailableError):
        await identity_source.fetch_enrollments(settings())
    assert len(calls) == 2
    calls.clear()
    responses[1] = {"scopes": [first.model_dump(mode="json")], "next_cursor": None}
    with pytest.raises(identity_source.IdentitySourceUnavailableError):
        await identity_source.fetch_enrollments(settings())


def worker_settings(**kwargs: Any) -> source_worker.WorkerSettings:
    return source_worker.WorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        identity_source=settings(),
        source_broker_url=SecretStr("amqp://ephemeral.invalid"),
        source_broker_user="identity",
        source_event_secret=SecretStr("ephemeral-test-event-key" * 3),
        **kwargs,
    )


def test_worker_requires_explicit_static_or_dynamic_enrollment() -> None:
    with pytest.raises(ValidationError):
        worker_settings()
    assert worker_settings(source_discovery=True).source_subscriptions == ()


async def test_discovery_failure_never_renews_and_revocation_replaces_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7())
    new = CompanyServiceScope(tenant_id=uuid7(), company_id=uuid7())
    registry = source_worker.EnrollmentRegistry((old,))
    renewals = []
    config = worker_settings(source_discovery=True)

    async def discover(*args: Any) -> tuple[CompanyServiceScope, ...]:
        return (new,)

    async def fetch(*args: Any, **kwargs: Any) -> None:
        renewals.append(kwargs["company_id"])
        raise identity_source.IdentitySourceUnavailableError("offline")

    monkeypatch.setattr(source_worker, "fetch_enrollments", discover)
    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    await source_worker.refresh_once(None, config, registry)
    assert renewals == [new.company_id] and registry.scopes == (new,)

    async def failure(*args: Any) -> tuple[CompanyServiceScope, ...]:
        raise identity_source.IdentitySourceUnavailableError("offline")

    monkeypatch.setattr(source_worker, "fetch_enrollments", failure)
    renewals.clear()
    await source_worker.refresh_once(None, config, registry)
    assert renewals == [] and registry.scopes == (new,)


async def test_not_yet_enrolled_event_grants_no_authority_and_keeps_validation(
    factory, tenant_a
) -> None:
    event = MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant_a,
        event_type=source_worker.EVENT_TYPE,
        schema_version=1,
        occurred_at=utcnow(),
        payload=change(tenant_a, 2).model_dump(mode="json"),
    )
    async with factory.begin() as db:
        with pytest.raises(ValidationFailedError):
            await source_worker.handle_change(db, event, allowed_tenants=frozenset())
        await source_worker.handle_change(
            db, event, allowed_tenants=frozenset(), ignore_unenrolled=True
        )
        with pytest.raises(ValidationFailedError):
            await source_worker.handle_change(
                db,
                event.model_copy(update={"schema_version": 2}),
                allowed_tenants=frozenset(),
                ignore_unenrolled=True,
            )
