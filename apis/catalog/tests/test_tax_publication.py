"""Phase 5: Catalog GST publications for Accounting's replica, in the command transaction."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.tax_publication import (
    CLASSIFICATION_EVENT,
    RATE_EVENT,
    RULE_EVENT,
    TAX_PUBLICATION_EVENTS,
    decimal_string,
    stronger,
)
from catalog.models import Outbox
from catalog.models import tax as m
from catalog.models.classification import CatalogPolicyState
from catalog.tasks import accounting_publisher, tax_publication
from catalog.tasks.tax_backfill import backfill
from tests.json_schema import assert_valid, errors, load
from tests.pricing_factories import create, guard
from tests.tax_factories import EVIDENCE, components, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")

SCHEMAS = {
    CLASSIFICATION_EVENT: ("catalog-tax-classification-changed-v1.schema.json", "classification"),
    RULE_EVENT: ("catalog-tax-rule-changed-v1.schema.json", "rule"),
    RATE_EVENT: ("catalog-tax-rate-changed-v1.schema.json", "rate"),
}
#: Accounting's replica rules (apis/accounting/src/accounting/domain/tax_replica.py).
MUTABLE = {
    "classification": {"valid_to", "description"},
    "rule": {"name", "is_active"},
    "rate": {"valid_to"},
}


def company_of(root: str) -> uuid.UUID:
    return uuid.UUID(root.rsplit("/", 1)[1])


async def published(factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID) -> list[Outbox]:
    with tenant_scope(tenant):
        async with factory() as db:
            return list(
                await db.scalars(
                    select(Outbox)
                    # The outbox is a platform table, not tenant-filtered: scope explicitly.
                    .where(
                        Outbox.event_type.in_(TAX_PUBLICATION_EVENTS), Outbox.tenant_id == tenant
                    )
                    .order_by(Outbox.id)
                )
            )


async def generation(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> int:
    with tenant_scope(tenant):
        async with factory() as db:
            value = await db.scalar(
                select(CatalogPolicyState.generation).where(
                    CatalogPolicyState.company_id == company
                )
            )
            return 1 if value is None else int(value)


def check_contract(rows: list[Outbox]) -> None:
    """Every payload matches its JSON schema and Accounting's replica would accept the
    sequence: versions strictly increase per object and only mutable fields change."""
    history: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        name, key = SCHEMAS[row.event_type]
        assert_valid(load(name), row.payload)
        payload = row.payload
        body = payload[key]
        assert row.aggregate_id == uuid.UUID(body["id"]) and row.schema_version == 1
        assert row.tenant_id == uuid.UUID(payload["tenant_id"])
        if "valid_to" in body and body["valid_to"] is not None:
            assert body["valid_to"] >= body["valid_from"]
        if payload["action"] == "WITHDRAW":
            assert body.get("valid_to") is not None if key != "rule" else not body["is_active"]
        previous = history.get(row.aggregate_id)
        if previous is not None and payload["source_version"] > previous["source_version"]:
            before = previous[key]
            changed = {field for field in body if body[field] != before[field]}
            assert changed <= MUTABLE[key], (key, changed)
        if previous is None or payload["source_version"] > previous["source_version"]:
            history[row.aggregate_id] = payload


def rate_body(
    ids: dict[str, uuid.UUID], context: str, valid_from: str, **extra: Any
) -> dict[str, Any]:
    return {
        "expected_generation": 1,
        "expected_source_version": 2,
        **EVIDENCE,
        "series_id": str(ids["series_" + context]),
        "valid_from": valid_from,
        "supersedes_id": str(ids["rate_" + context]),
        "expected_previous_version": 1,
        "components": components(context),
        **extra,
    }


def classification_body(result: dict[str, Any] | None = None, code: str = "5678") -> dict[str, Any]:
    return {
        **(guard(result) if result else {"expected_generation": 1, "expected_source_version": 2}),
        **EVIDENCE,
        "code_system": "HSN",
        "code": code,
        "item_kind": "GOODS",
        "description": "Synthetic future classification",
        "valid_from": "2091-01-01",
    }


async def test_publish_update_withdraw_events_match_the_contracts(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    assert await published(factory, tenant_a) == []
    # Rate supersession: the new rate publishes, the predecessor's window shortens.
    superseding = await create(
        client, root, auth, "/tax-rates", rate_body(ids, "INTER_STATE", "2091-01-01")
    )
    rows = await published(factory, tenant_a)
    by_id = {(row.aggregate_id, row.payload["source_version"]): row.payload for row in rows}
    new_rate = by_id[uuid.UUID(superseding["id"]), superseding["policy_generation"]]
    old_rate = by_id[ids["rate_INTER_STATE"], superseding["policy_generation"]]
    assert superseding["policy_generation"] == 2
    assert new_rate["action"] == "PUBLISH" and old_rate["action"] == "UPDATE"
    assert new_rate["rate"]["supersedes_id"] == str(ids["rate_INTER_STATE"])
    assert new_rate["rate"]["rule_id"] == str(ids["tax_rule"])
    assert new_rate["rate"]["applicability"] == "INTER_STATE"
    assert old_rate["rate"]["valid_to"] == "2090-12-31"
    component = new_rate["rate"]["components"][0]
    assert component["percentage"] == "5.0000" and isinstance(component["percentage"], str)
    # Withdrawing the future rate restores the predecessor's open end.
    withdrawn_rate = await create(
        client,
        root,
        auth,
        "/tax-withdrawals",
        {
            **guard(superseding),
            "resource": "tax_rate",
            "target_id": superseding["id"],
            "expected_version": 1,
            "reason": "Synthetic abandoned rate",
        },
    )
    # A future classification, then its withdrawal.
    classification = await create(
        client, root, auth, "/tax-classifications", classification_body(withdrawn_rate)
    )
    withdrawn_class = await create(
        client,
        root,
        auth,
        "/tax-withdrawals",
        {
            **guard(classification),
            "resource": "tax_classification",
            "target_id": classification["id"],
            "expected_version": 1,
            "reason": "Synthetic abandoned classification",
        },
    )
    # A rule publishes, is renamed, then retires.
    category = await create(client, root, auth, "/tax-categories", {"code": "SPARE", "name": "S"})
    rule = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            **EVIDENCE,
            "code": "SPARE",
            "name": "Spare",
            "item_kind": "GOODS",
            "treatment": "EXEMPT",
            "tax_category_id": category["id"],
        },
    )
    renamed = await client.patch(
        root + "/tax-rules/" + rule["id"],
        headers=command_headers(auth),
        json={"name": "Renamed", "expected_version": 1, "is_active": True},
    )
    assert renamed.status_code == 200, renamed.text
    retired = await client.patch(
        root + "/tax-rules/" + rule["id"],
        headers=command_headers(auth),
        json={"name": "Renamed", "expected_version": 2, "is_active": False},
    )
    assert retired.status_code == 200, retired.text

    rows = await published(factory, tenant_a)
    check_contract(rows)
    actions = {
        (row.aggregate_id, row.payload["source_version"]): row.payload["action"] for row in rows
    }
    assert actions[uuid.UUID(superseding["id"]), withdrawn_rate["policy_generation"]] == "WITHDRAW"
    assert actions[ids["rate_INTER_STATE"], withdrawn_rate["policy_generation"]] == "UPDATE"
    assert actions[uuid.UUID(classification["id"]), classification["policy_generation"]] == (
        "PUBLISH"
    )
    assert actions[uuid.UUID(classification["id"]), withdrawn_class["policy_generation"]] == (
        "WITHDRAW"
    )
    assert actions[uuid.UUID(rule["id"]), rule["policy_generation"]] == "PUBLISH"
    assert actions[uuid.UUID(rule["id"]), renamed.json()["policy_generation"]] == "UPDATE"
    assert actions[uuid.UUID(rule["id"]), retired.json()["policy_generation"]] == "WITHDRAW"
    payloads = {(row.aggregate_id, row.payload["source_version"]): row.payload for row in rows}
    restored = payloads[ids["rate_INTER_STATE"], withdrawn_rate["policy_generation"]]
    assert restored["rate"]["valid_to"] is None
    gone = payloads[uuid.UUID(superseding["id"]), withdrawn_rate["policy_generation"]]
    # Contract v1 can only express withdrawal as the shortest window (see open items).
    assert gone["rate"]["valid_to"] == gone["rate"]["valid_from"] == "2091-01-01"
    # source_version is the generation after the bump, shared by one command's events.
    assert {row.payload["source_version"] for row in rows} == {
        superseding["policy_generation"],
        withdrawn_rate["policy_generation"],
        classification["policy_generation"],
        withdrawn_class["policy_generation"],
        rule["policy_generation"],
        renamed.json()["policy_generation"],
        retired.json()["policy_generation"],
    }
    assert retired.json()["policy_generation"] == await generation(
        factory, tenant_a, company_of(root)
    )
    # Category is Catalog-only; bindings are not replicated either.
    assert {row.aggregate_type for row in rows} == {
        "catalog.tax_rate",
        "catalog.tax_classification",
        "catalog.tax_rule",
    }


async def test_versions_strictly_increase_per_object(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    rule_id = str(ids["tax_rule"])
    versions = []
    for index, name in enumerate(("First", "Second", "Third"), start=1):
        result = await client.patch(
            root + "/tax-rules/" + rule_id,
            headers=command_headers(auth),
            json={"name": name, "expected_version": index, "is_active": True},
        )
        assert result.status_code == 200, result.text
        versions.append(result.json()["policy_generation"])
    rows = [row for row in await published(factory, tenant_a) if row.event_type == RULE_EVENT]
    assert [row.payload["source_version"] for row in rows] == versions
    assert versions == sorted(set(versions)) and versions[0] == 2
    assert [row.payload["rule"]["name"] for row in rows] == ["First", "Second", "Third"]
    check_contract(rows)


async def test_rollback_leaves_no_publication(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            before = len(list(await db.scalars(select(Outbox.id))))
    original = tax_publication.emit_publications
    staged: list[int] = []

    async def failing(*args: Any) -> int:
        staged.append(await original(*args))
        raise ConflictError("synthetic failure after staging")

    monkeypatch.setattr(tax_publication, "emit_publications", failing)
    result = await client.post(
        root + "/tax-classifications", headers=command_headers(auth), json=classification_body()
    )
    assert result.status_code == 409, result.text
    assert staged == [1]
    assert await published(factory, tenant_a) == []
    with tenant_scope(tenant_a):
        async with factory() as db:
            missing = select(m.TaxClassification).where(m.TaxClassification.code == "5678")
            assert await db.scalar(missing) is None
            # Neither the publication nor the command's audit event survives the rollback.
            assert len(list(await db.scalars(select(Outbox.id)))) == before
    assert await generation(factory, tenant_a, company_of(root)) == 1


async def test_previews_publish_nothing(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    preview = await client.post(
        root + "/tax-rate-previews", headers=auth, json=rate_body(ids, "INTER_STATE", "2091-01-01")
    )
    assert preview.status_code == 200, preview.text
    assert await published(factory, tenant_a) == []


async def test_publications_are_tenant_scoped(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    root_a, auth_a, _ = await seed_tax(factory, tenant_a)
    root_b, auth_b, _ = await seed_tax(factory, tenant_b)
    await create(client, root_a, auth_a, "/tax-classifications", classification_body())
    await create(client, root_b, auth_b, "/tax-classifications", classification_body(code="8765"))
    rows_a, rows_b = await published(factory, tenant_a), await published(factory, tenant_b)
    assert [row.payload["classification"]["code"] for row in rows_a] == ["5678"]
    assert [row.payload["classification"]["code"] for row in rows_b] == ["8765"]
    assert {row.tenant_id for row in rows_a} == {tenant_a}
    assert {row.payload["company_id"] for row in rows_a} == {str(company_of(root_a))}
    # The backfill of one tenant never stages the other's rows.
    await backfill(
        factory, [CompanyServiceScope(tenant_id=tenant_a, company_id=company_of(root_a))]
    )
    assert {row.tenant_id for row in await published(factory, tenant_a)} == {tenant_a}
    assert len(await published(factory, tenant_b)) == 1


async def test_backfill_is_idempotent_and_contract_valid(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = company_of(root)
    scope = [CompanyServiceScope(tenant_id=tenant_a, company_id=company)]
    first = (await backfill(factory, scope))[tenant_a, company]
    assert first.generation == 1 and first.skipped == 0
    assert first.staged == {"tax_classification": 1, "tax_rule": 1, "tax_rate": 3}
    rows = await published(factory, tenant_a)
    check_contract(rows)
    assert {row.payload["action"] for row in rows} == {"PUBLISH"}
    assert {row.payload["source_version"] for row in rows} == {1}
    second = (await backfill(factory, scope))[tenant_a, company]
    assert sum(second.staged.values()) == 0 and second.skipped == 5
    assert len(await published(factory, tenant_a)) == 5
    # After a command, a rerun republishes at the new generation, skipping what the command
    # already published at it; withdrawn rows go out as WITHDRAW.
    future = await create(client, root, auth, "/tax-classifications", classification_body())
    withdrawal = await create(
        client,
        root,
        auth,
        "/tax-withdrawals",
        {
            **guard(future),
            "resource": "tax_classification",
            "target_id": future["id"],
            "expected_version": 1,
            "reason": "Synthetic abandoned classification",
        },
    )
    third = (await backfill(factory, scope))[tenant_a, company]
    assert third.generation == withdrawal["policy_generation"] == 3
    assert third.skipped == 1 and sum(third.staged.values()) == 5
    rows = await published(factory, tenant_a)
    check_contract(rows)
    latest = {row.aggregate_id: row.payload for row in rows if row.payload["source_version"] == 3}
    assert latest[uuid.UUID(future["id"])]["action"] == "WITHDRAW"
    assert latest[ids["tax_rule"]]["action"] == "PUBLISH"
    assert sum((await backfill(factory, scope))[tenant_a, company].staged.values()) == 0


async def test_backfill_publishes_an_inactive_rule_as_withdrawn(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            rule = await db.get(m.TaxRule, ids["tax_rule"])
            assert rule is not None
            rule.is_active = False
    company = company_of(root)
    await backfill(factory, [CompanyServiceScope(tenant_id=tenant_a, company_id=company)])
    rows = [row for row in await published(factory, tenant_a) if row.event_type == RULE_EVENT]
    assert [row.payload["action"] for row in rows] == ["WITHDRAW"]
    check_contract(rows)


def test_decimal_strings_are_exact_and_never_float() -> None:
    assert decimal_string(Decimal("2.5")) == "2.5000"
    assert decimal_string(Decimal(0)) == "0.0000"
    assert decimal_string(None) is None
    for bad in (Decimal("0.00001"), Decimal(-1), Decimal("1e16"), Decimal("NaN"), 2.5):
        with pytest.raises(ValueError):
            decimal_string(bad)  # type: ignore[arg-type]  # the float is the refused case


def test_one_command_keeps_the_strongest_action() -> None:
    assert stronger(None, "UPDATE") == "UPDATE"
    assert stronger("PUBLISH", "UPDATE") == "PUBLISH"
    assert stronger("UPDATE", "WITHDRAW") == "WITHDRAW"
    assert stronger("WITHDRAW", "PUBLISH") == "WITHDRAW"


def test_contract_validator_rejects_drift() -> None:
    schema = load("catalog-tax-rule-changed-v1.schema.json")
    value: dict[str, Any] = {
        "schema_version": 1,
        "tenant_id": str(uuid.uuid4()),
        "company_id": str(uuid.uuid4()),
        "source_version": 2,
        "action": "PUBLISH",
        "rule": {
            "id": str(uuid.uuid4()),
            "code": "X",
            "name": "X",
            "tax_system": "gst_in",
            "jurisdiction": "IN",
            "item_kind": "GOODS",
            "treatment": "TAXABLE",
            "tax_category_id": str(uuid.uuid4()),
            "is_active": True,
            "source_reference": "r",
            "source_sha256": "ab" * 32,
        },
    }
    assert errors(schema, value) == []
    assert errors(schema, value | {"extra": 1})
    assert errors(schema, value | {"source_version": 0})
    assert errors(schema, value | {"rule": value["rule"] | {"source_url": "https://x"}})


async def test_accounting_publisher_is_scoped_to_tax_publications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import SecretStr

    captured: list[Any] = []

    async def run(config: Any) -> None:
        captured.append(config)

    monkeypatch.setattr(accounting_publisher, "run_publisher", run)
    settings = accounting_publisher.AccountingPublisherSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        source_broker_url=SecretStr("amqp://ephemeral.invalid"),
        source_broker_user="catalog_sources",
        accounting_event_secret=SecretStr("ephemeral-catalog-accounting-secret" * 2),
    )
    await accounting_publisher.run(settings)
    (value,) = captured
    assert value.exchange == "platform.sources"
    assert value.key.issuer == "catalog" and value.key.audience == "accounting"
    assert value.key.operations == TAX_PUBLICATION_EVENTS
    assert value.broker_user == "catalog_sources"


def test_withdrawal_window_is_documented_shortest() -> None:
    # Guard the documented representation: a withdrawn dated row ends on its first day.
    from types import SimpleNamespace

    from catalog.events.tax_publication import classification_payload

    row = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        jurisdiction="IN",
        code_system="HSN",
        code="1234",
        item_kind="GOODS",
        description="d",
        valid_from=dt.date(2091, 1, 1),
        valid_to=None,
        source_reference="r",
        source_sha256="ab" * 32,
    )
    payload = classification_payload(row, 3, "WITHDRAW")
    assert payload["classification"]["valid_to"] == "2091-01-01"
    assert_valid(load("catalog-tax-classification-changed-v1.schema.json"), payload)
    with pytest.raises(ValueError):
        classification_payload(row, 0, "PUBLISH")
    with pytest.raises(ValueError):
        classification_payload(row, 2, "DELETE")
