"""Outbox writer and audit payload shape.

The two invariants under test: ``emit`` does not commit (so the event and the
business change are atomic — invariant 8), and a rolled-back transaction leaves
no outbox row and therefore no audit event.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.platform_models import Outbox, ProcessedMessage
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from tests.helpers import table_of
from tests.models import TenantThing


async def _outbox_count(session: AsyncSession) -> int:
    with unfiltered():
        result = await session.execute(select(func.count()).select_from(Outbox))
    return int(result.scalar_one())


async def test_emit_stages_but_does_not_commit(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    row = emit(
        session,
        aggregate_type="company",
        aggregate_id=uuid7(),
        event_type="company.created",
        payload={"legal_name": "Acme"},
        tenant_id=tenant_a,
    )

    assert row in session.new
    assert await _outbox_count(session) == 0

    await session.commit()
    assert await _outbox_count(session) == 1


async def test_rolled_back_transaction_leaves_no_audit_row(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Invariant 8 from the other direction: no orphan event for work undone."""
    thing = TenantThing(tenant_id=tenant_a, name="acme", amount=Decimal("10.0000"))
    session.add(thing)
    emit(
        session,
        aggregate_type="tenant_thing",
        aggregate_id=uuid7(),
        event_type="tenant_thing.created",
        payload=audit_payload(
            action="create",
            entity_type="tenant_thing",
            entity_id=uuid7(),
            actor_user_id=uuid7(),
        ),
        tenant_id=tenant_a,
    )

    await session.rollback()

    assert await _outbox_count(session) == 0


async def test_each_emit_gets_a_distinct_message_id(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    aggregate_id = uuid7()
    first = emit(
        session,
        aggregate_type="company",
        aggregate_id=aggregate_id,
        event_type="company.updated",
        payload={},
        tenant_id=tenant_a,
    )
    second = emit(
        session,
        aggregate_type="company",
        aggregate_id=aggregate_id,
        event_type="company.updated",
        payload={},
        tenant_id=tenant_a,
    )
    assert first.message_id != second.message_id


async def test_platform_event_may_have_no_tenant(session: AsyncSession) -> None:
    """``outbox.tenant_id`` is nullable for platform-level events."""
    emit(
        session,
        aggregate_type="tenant",
        aggregate_id=uuid7(),
        event_type="tenant.provisioned",
        payload={},
    )
    await session.commit()

    with unfiltered():
        row = (await session.execute(select(Outbox))).scalar_one()
    assert row.tenant_id is None


async def test_new_row_is_unpublished_and_immediately_available(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    emit(
        session,
        aggregate_type="company",
        aggregate_id=uuid7(),
        event_type="company.created",
        payload={},
        tenant_id=tenant_a,
    )
    await session.commit()

    with unfiltered():
        row = (await session.execute(select(Outbox))).scalar_one()

    assert row.published_at is None
    assert row.attempt_count == 0
    assert row.available_at is not None
    assert row.schema_version == 1


@pytest.mark.parametrize("missing", ["aggregate_type", "event_type"])
async def test_emit_requires_aggregate_type_and_event_type(
    session: AsyncSession, missing: str
) -> None:
    kwargs: dict[str, object] = {
        "aggregate_type": "company",
        "aggregate_id": uuid7(),
        "event_type": "company.created",
        "payload": {},
    }
    kwargs[missing] = ""
    with pytest.raises(ValueError, match="required"):
        emit(session, **kwargs)  # type: ignore[arg-type]


async def test_consumer_dedupe_key_is_composite(session: AsyncSession) -> None:
    """Keyed on ``message_id`` alone, the second consumer of a fan-out event
    silently skips it. That bug only appears once a second consumer exists."""
    message_id = uuid7()
    session.add_all(
        [
            ProcessedMessage(consumer_name="billing.invoice", message_id=message_id),
            ProcessedMessage(consumer_name="reports.replica", message_id=message_id),
        ]
    )
    await session.commit()

    rows = (await session.execute(select(ProcessedMessage))).scalars().all()
    assert len(rows) == 2

    pk = {c.name for c in table_of(ProcessedMessage).primary_key.columns}
    assert pk == {"consumer_name", "message_id"}


async def test_redelivery_to_the_same_consumer_is_rejected_by_the_database(
    session: AsyncSession,
) -> None:
    """The other half of rule 4.4: one consumer, one effect.

    Enforced by the primary key rather than by a read-then-write check, which is
    racy under concurrent delivery of the same message to two workers.
    """
    message_id = uuid7()
    session.add(ProcessedMessage(consumer_name="billing.invoice", message_id=message_id))
    await session.commit()

    session.add(ProcessedMessage(consumer_name="billing.invoice", message_id=message_id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    assert len((await session.execute(select(ProcessedMessage))).scalars().all()) == 1


def test_audit_payload_holds_the_actor_id_and_no_pii() -> None:
    """Invariant 9: audit rows hold ``actor_user_id``, never denormalized PII."""
    actor = uuid7()
    payload = audit_payload(
        action="update",
        entity_type="identity.company",
        entity_id=uuid7(),
        actor_user_id=actor,
        category="admin",
        changes={"legal_name": {"from": "A", "to": "B"}},
        reason="rename",
    )

    assert payload["actor_user_id"] == str(actor)
    assert set(payload) == {
        "action",
        "category",
        "entity_type",
        "entity_id",
        "actor_user_id",
        "on_behalf_of_user_id",
        "changes",
        "reason",
    }


def test_audit_payload_records_impersonation() -> None:
    """Impersonation is audited at start and end, and every act in between
    names both identities (CLAUDE.md §5.5)."""
    actor, target = uuid7(), uuid7()
    payload = audit_payload(
        action="update",
        entity_type="identity.company",
        entity_id=uuid7(),
        actor_user_id=actor,
        category="security",
        on_behalf_of_user_id=target,
    )
    assert payload["actor_user_id"] == str(actor)
    assert payload["on_behalf_of_user_id"] == str(target)


def test_audit_payload_rejects_an_unknown_category() -> None:
    with pytest.raises(ValueError, match="unknown audit category"):
        audit_payload(
            action="create",
            entity_type="identity.company",
            entity_id=uuid7(),
            actor_user_id=None,
            category="whatever",
        )


def test_system_write_has_no_actor() -> None:
    payload = audit_payload(
        action="seed",
        entity_type="identity.role",
        entity_id=uuid7(),
        actor_user_id=None,
        category="system",
    )
    assert payload["actor_user_id"] is None


def test_company_audit_payload_preserves_authoritative_scope() -> None:
    company = uuid7()
    payload = audit_payload(
        action="catalog.item_group.create",
        entity_type="catalog.item_group",
        entity_id=uuid7(),
        actor_user_id=uuid7(),
        company_id=company,
    )
    assert payload["company_id"] == str(company)
