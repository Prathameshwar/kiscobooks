"""Actual commands retain safe before/after evidence without private business labels."""

import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from tests.test_api import headers
from tests.test_unit_api import UNIT_BODY, seed_context


async def test_unit_changes_keep_exact_values_and_request_attribution(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, request_id = uuid7(), uuid7(), uuid7()
    await seed_context(factory, tenant_a, company, user)
    auth = headers(company, tenant=tenant_a, user=user, permission="unit.manage")
    auth.update(
        {"Idempotency-Key": "create", "X-Trace-Id": "a" * 32, "X-Request-Id": str(request_id)}
    )
    response = await client.post(
        f"/v1/companies/{company}/units",
        headers=auth,
        json=UNIT_BODY | {"name": "Private unit label"},
    )
    assert response.status_code == 201, response.text
    body = {"expected_version": 1, "quantity_increment": "2", "name": "Other private label"}
    for _ in range(2):
        response = await client.patch(
            response.headers.get(
                "location", f"/v1/companies/{company}/units/{response.json()['id']}"
            ),
            headers=auth | {"Idempotency-Key": "update"},
            json=body,
        )
        assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(await db.scalars(select(Outbox).order_by(Outbox.occurred_at, Outbox.id)))
    assert len(events) == 2
    evidence = events[-1].payload
    assert Decimal(evidence["changes"]["quantity_increment"]["from"]) == Decimal("1")
    assert evidence["changes"]["quantity_increment"]["to"] == "2.0000"
    assert evidence["changes"]["name"] == {"changed": True}
    assert "private" not in str(evidence).lower()
    assert evidence["request_id"] == str(request_id)
    assert events[-1].trace_id == "a" * 32
    assert evidence["actor_type"] == "user"
    assert evidence["actor_user_id"] == str(user)


async def test_report_access_is_transactional_and_repeated_downloads_are_distinct(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.bulk_factories import post, setup, unit_row

    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    ticket = await client.get(root + "/" + job["id"] + "/report-ticket", headers=auth)
    assert ticket.status_code == 200, ticket.text
    for _ in range(2):
        response = await client.get(ticket.json()["download_path"], headers=auth)
        assert response.status_code == 200, response.text

    async def failed_commit(db: AsyncSession) -> None:
        raise RuntimeError("test storage failure before commit")

    # A prepared file must not escape if its access event cannot be committed.
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", failed_commit)
        response = await client.get(ticket.json()["download_path"], headers=auth)
        assert response.status_code == 500
    assert (await client.get(ticket.json()["download_path"])).status_code == 401
    assert (await client.get(ticket.json()["download_path"] + "x", headers=auth)).status_code != 200
    with tenant_scope(tenant_a):
        async with factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "catalog.bulk_job.export")
                )
            )
    assert len(events) == 2
    assert all(
        row.aggregate_id == uuid.UUID(job["id"]) and row.payload["company_id"] == str(company)
        for row in events
    )
    assert all(
        row.payload["category"] == "access"
        and row.payload["context"] == {"count": 1, "format": "CSV"}
        for row in events
    )
    assert ticket.json()["download_path"] not in str([row.payload for row in events])


async def test_pricing_publication_records_exact_money_and_safe_currency(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    stable_product_source_clock: None,
) -> None:
    from tests.pricing_factories import foundation, publish_price, setup_pricing

    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, price = await publish_price(
        client, root, auth, setup, amount="0.1234", price_basis_quantity="1000"
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            event = await db.scalar(
                select(Outbox).where(
                    Outbox.aggregate_id == uuid.UUID(price["id"]),
                    Outbox.event_type == "catalog.item_price.create",
                )
            )
    assert event is not None
    assert event.payload["category"] == "money"
    assert event.payload["changes"]["amount"] == {"from": None, "to": "0.1234"}
    assert event.payload["changes"]["currency"]["to"] == "INR"
    assert "Reviewed commercial rate" not in str(event.payload)


def test_unknown_values_markers_and_deleted_values_are_distinct() -> None:
    from catalog.events.evidence import changes

    fields = frozenset({"amount", "source_reference"})
    assert changes("catalog.item_price", fields) == {
        "amount": {"changed": True},
        "source_reference": {"changed": True},
    }
    assert changes(
        "catalog.item_price", fields, before={"amount": Decimal("900719925474099.1234")}, after={}
    )["amount"] == {"from": "900719925474099.1234", "to": None}
    assert changes(
        "catalog.item_price",
        fields,
        after={"amount": Decimal("1.2345"), "source_reference": "Private"},
        creating=True,
    ) == {"amount": {"from": None, "to": "1.2345"}, "source_reference": {"changed": True}}


async def test_index_cleanup_has_explicit_system_attribution() -> None:
    from catalog.models.field_indexes import FieldRebuildJob
    from catalog.tasks.index_rebuilds import audit

    async with AsyncSession() as db:
        for actor_id, actor_type, category in (
            (None, "system", "system"),
            (uuid7(), "user", "admin"),
        ):
            audit(db, uuid7(), uuid7(), FieldRebuildJob(id=uuid7()), "cleanup", actor_id=actor_id)
            event = next(row for row in db.new if isinstance(row, Outbox))
            assert event.payload["actor_type"] == actor_type
            assert event.payload["category"] == category
            assert event.payload["actor_user_id"] == (str(actor_id) if actor_id else None)
            db.expunge_all()
