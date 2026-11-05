"""Catalog GST publications into the Accounting replica (tax-accounting plan Phase 5)."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.delivery import consume_once
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import func, select

from accounting.domain.tax_replica import (
    decide,
    effective_on,
    immutable_changes,
    next_action,
    same_components,
)
from accounting.models.tax_replica import (
    TAX_REPLICA_MODELS,
    TaxClassificationReplica,
    TaxRateComponentReplica,
    TaxRateReplica,
    TaxRuleReplica,
)
from accounting.schemas.catalog_tax_events import (
    CLASSIFICATION_EVENT,
    RATE_EVENT,
    RULE_EVENT,
    RateChanged,
)
from accounting.tasks.catalog_tax_replica import CONSUMER, handle_catalog_tax
from accounting.tasks.catalog_tax_worker import CatalogTaxWorkerSettings, broker_source
from tests.conftest import COMPANY, TENANT

SHA = "a" * 64


def envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    tenant: uuid.UUID = TENANT,
    message_id: uuid.UUID | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id or uuid7(),
        tenant_id=tenant,
        event_type=event_type,
        schema_version=1,
        occurred_at=dt.datetime.now(dt.UTC),
        payload=payload,
    )


def change(
    version: int, action: str, tenant: uuid.UUID, company: uuid.UUID, **entity: Any
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tenant_id": str(tenant),
        "company_id": str(company),
        "source_version": version,
        "action": action,
        **entity,
    }


def rule_event(
    rule_id: uuid.UUID,
    version: int,
    *,
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
    action: str = "PUBLISH",
    item_kind: str = "SERVICE",
    treatment: str = "TAXABLE",
    is_active: bool = True,
    name: str = "GST 18% services",
    message_id: uuid.UUID | None = None,
) -> MessageEnvelope:
    rule = {
        "id": str(rule_id),
        "code": "R" + rule_id.hex[-12:].upper(),
        "name": name,
        "tax_system": "gst_in",
        "jurisdiction": "IN",
        "item_kind": item_kind,
        "treatment": treatment,
        "tax_category_id": str(uuid.UUID(int=rule_id.int ^ 1)),
        "is_active": is_active,
        "source_reference": "CBIC notification 11/2017-CT(Rate)",
        "source_sha256": SHA,
    }
    return envelope(
        RULE_EVENT,
        change(version, action, tenant, company, rule=rule),
        tenant=tenant,
        message_id=message_id,
    )


def classification_event(
    classification_id: uuid.UUID,
    version: int,
    *,
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
    action: str = "PUBLISH",
    code: str = "998314",
    code_system: str = "SAC",
    item_kind: str = "SERVICE",
    valid_to: str | None = None,
    description: str = "IT design and development services",
) -> MessageEnvelope:
    body = {
        "id": str(classification_id),
        "jurisdiction": "IN",
        "code_system": code_system,
        "code": code,
        "item_kind": item_kind,
        "description": description,
        "valid_from": "2017-07-01",
        "valid_to": valid_to,
        "source_reference": "CBIC SAC schedule",
        "source_sha256": SHA,
    }
    return envelope(
        CLASSIFICATION_EVENT,
        change(version, action, tenant, company, classification=body),
        tenant=tenant,
    )


def component(key: str, kind: str, percentage: str, position: int) -> dict[str, Any]:
    return {
        "id": str(uuid7()),
        "component_key": key,
        "component": kind,
        "kind": "PERCENT",
        "percentage": percentage,
        "rounding_mode": "HALF_UP",
        "position": position,
    }


def rate_event(
    rate_id: uuid.UUID,
    rule_id: uuid.UUID,
    version: int,
    *,
    tenant: uuid.UUID = TENANT,
    company: uuid.UUID = COMPANY,
    action: str = "PUBLISH",
    valid_to: str | None = None,
    components: list[dict[str, Any]] | None = None,
    applicability: str = "INTRA_STATE",
) -> MessageEnvelope:
    body = {
        "id": str(rate_id),
        "rule_id": str(rule_id),
        "series_id": str(uuid.UUID(int=rate_id.int ^ 1)),
        "applicability": applicability,
        "valid_from": "2017-07-01",
        "valid_to": valid_to,
        "supersedes_id": None,
        "source_reference": "CBIC notification 11/2017-CT(Rate)",
        "source_sha256": SHA,
        "components": components
        if components is not None
        else [component("CGST", "CGST", "9.0000", 0), component("SGST", "SGST", "9", 1)],
    }
    return envelope(RATE_EVENT, change(version, action, tenant, company, rate=body), tenant=tenant)


async def deliver(app: FastAPI, message: MessageEnvelope) -> bool:
    return await consume_once(
        app.state.session_factory, message, handle_catalog_tax, consumer_name=CONSUMER
    )


async def publish_rule(app: FastAPI, **kwargs: Any) -> uuid.UUID:
    """A published active rule in the replica; returns its Catalog identifier."""
    rule_id = uuid7()
    assert await deliver(app, rule_event(rule_id, 1, **kwargs))
    return rule_id


async def rows(app: FastAPI, model: Any, tenant: uuid.UUID = TENANT) -> list[Any]:
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            return list(await db.scalars(select(model).order_by(model.id)))


# --- pure rules: no database ---------------------------------------------------------------


def test_generation_ordering_is_strict() -> None:
    assert decide(None, 1) == "insert"
    assert decide(3, 4) == "update"
    assert decide(3, 3) == "ignore"
    assert decide(3, 2) == "ignore"


def test_only_listed_fields_may_change_between_generations() -> None:
    current = {"name": "A", "code": "X", "is_active": True}
    assert immutable_changes(current, current | {"name": "B"}, {"name"}) == frozenset()
    assert immutable_changes(current, current | {"code": "Y"}, {"name"}) == {"code"}


def test_withdrawn_rows_are_never_effective_and_withdrawal_is_sticky() -> None:
    start = dt.date(2027, 4, 1)
    # Catalog publishes a withdrawn future row with valid_to == valid_from.
    assert not effective_on("WITHDRAW", start, start, start)
    assert not effective_on("WITHDRAW", start, None, dt.date(2030, 1, 1))
    assert effective_on("PUBLISH", start, start, start)
    assert effective_on("UPDATE", start, None, dt.date(2030, 1, 1))
    assert not effective_on("PUBLISH", start, None, start - dt.timedelta(days=1))
    assert not effective_on("PUBLISH", start, start, start + dt.timedelta(days=1))
    assert next_action(None, "PUBLISH") == "PUBLISH"
    assert next_action("PUBLISH", "WITHDRAW") == "WITHDRAW"
    assert next_action("WITHDRAW", "UPDATE") == "WITHDRAW"


def test_components_compare_by_decimal_value_not_scale_or_order() -> None:
    first = {"key": "CGST", "percentage": Decimal("9.0000")}
    second = {"key": "SGST", "percentage": Decimal("9")}
    assert same_components([first, second], [second | {"percentage": Decimal("9.00")}, first])
    assert not same_components([first], [first | {"percentage": Decimal("9.5")}])


@pytest.mark.parametrize(
    "mutation",
    [
        {"percentage": 9.0},  # a JSON number is never a rate
        {"percentage": "9.00001"},
        {"percentage": "-1"},
        {"percentage": "101"},
        {"percentage": None},
        {"kind": "FIXED_PER_UNIT"},
        {"unexpected": True},
    ],
)
def test_payload_rejects_floats_bad_scale_and_shape(mutation: dict[str, Any]) -> None:
    payload = rate_event(uuid7(), uuid7(), 1).payload
    payload["rate"]["components"][0] |= mutation
    with pytest.raises(ValidationError):
        RateChanged.model_validate(payload)


def test_payload_parses_rates_as_decimal() -> None:
    parsed = RateChanged.model_validate(rate_event(uuid7(), uuid7(), 1).payload)
    assert isinstance(parsed.rate.components[0].percentage, Decimal)
    assert parsed.rate.components[0].percentage == Decimal("9")


def test_payload_rejects_withdrawal_without_end_and_duplicate_components() -> None:
    with pytest.raises(ValidationError):
        RateChanged.model_validate(rate_event(uuid7(), uuid7(), 2, action="WITHDRAW").payload)
    twin = component("CGST", "CGST", "9", 0)
    with pytest.raises(ValidationError):
        RateChanged.model_validate(rate_event(uuid7(), uuid7(), 1, components=[twin, twin]).payload)


def test_worker_trusts_only_catalog_signing_for_accounting() -> None:
    settings = CatalogTaxWorkerSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        catalog_broker_url="amqp://localhost",  # type: ignore[arg-type]  # coerced by pydantic
        catalog_broker_user="catalog",
        catalog_event_secret="s" * 32,  # type: ignore[arg-type]  # coerced by pydantic
    )
    key = broker_source(settings).key
    assert (key.issuer, key.audience) == ("catalog", "accounting")
    assert key.operations == {CLASSIFICATION_EVENT, RULE_EVENT, RATE_EVENT}
    assert settings.catalog_tax_queue == CONSUMER


# --- consumer against the database ---------------------------------------------------------


async def test_rate_round_trips_decimal_and_redelivery_has_one_effect(app: FastAPI) -> None:
    rule_id = await publish_rule(app)
    rate_id = uuid7()
    message = rate_event(rate_id, rule_id, 1)
    assert await deliver(app, message)
    assert not await deliver(app, message)
    [rate] = await rows(app, TaxRateReplica)
    assert (rate.id, rate.rule_id, rate.source_version) == (rate_id, rule_id, 1)
    assert rate.source_message_id == message.message_id
    components = await rows(app, TaxRateComponentReplica)
    assert len(components) == 2
    for row in components:
        assert isinstance(row.percentage, Decimal)
        assert row.percentage == Decimal("9")
        assert row.rate_id == rate_id


async def test_out_of_order_generations_are_ignored(app: FastAPI) -> None:
    rule_id = uuid7()
    assert await deliver(app, rule_event(rule_id, 5, name="Current name"))
    # A late older generation and an equal one are consumed but change nothing.
    assert await deliver(app, rule_event(rule_id, 4, name="Stale name", is_active=False))
    assert await deliver(app, rule_event(rule_id, 5, name="Same generation"))
    [rule] = await rows(app, TaxRuleReplica)
    assert (rule.name, rule.is_active, rule.source_version) == ("Current name", True, 5)
    assert await deliver(app, rule_event(rule_id, 6, action="UPDATE", name="Renamed"))
    [rule] = await rows(app, TaxRuleReplica)
    assert (rule.name, rule.source_version) == ("Renamed", 6)


async def test_withdrawals_mirror_catalog_lifecycle(app: FastAPI) -> None:
    rule_id = await publish_rule(app)
    rate_id, classification_id = uuid7(), uuid7()
    published = [component("CGST", "CGST", "9", 0), component("SGST", "SGST", "9", 1)]
    assert await deliver(app, rate_event(rate_id, rule_id, 2, components=published))
    assert await deliver(app, classification_event(classification_id, 2))
    assert await deliver(app, rule_event(rule_id, 3, action="WITHDRAW", is_active=False))
    withdrawn = rate_event(
        rate_id, rule_id, 3, action="WITHDRAW", valid_to="2026-03-31", components=published
    )
    assert await deliver(app, withdrawn)
    assert await deliver(
        app, classification_event(classification_id, 3, action="WITHDRAW", valid_to="2026-03-31")
    )
    [rule] = await rows(app, TaxRuleReplica)
    [rate] = await rows(app, TaxRateReplica)
    [classification] = await rows(app, TaxClassificationReplica)
    assert rule.is_active is False
    assert rate.valid_to == classification.valid_to == dt.date(2026, 3, 31)
    # Nothing is deleted: the withdrawn rate keeps its components.
    assert len(await rows(app, TaxRateComponentReplica)) == 2


async def test_history_rewrites_and_scope_mismatches_are_dead_lettered(app: FastAPI) -> None:
    rule_id = await publish_rule(app)
    rate_id = uuid7()
    assert await deliver(app, rate_event(rate_id, rule_id, 2))
    rewrites = [
        rule_event(rule_id, 3, treatment="EXEMPT"),
        rate_event(rate_id, rule_id, 3, components=[component("IGST", "IGST", "18", 0)]),
        rule_event(rule_id, 4, company=uuid7()),
        # A payload naming another tenant than its authenticated envelope.
        envelope(RULE_EVENT, rule_event(uuid7(), 1, tenant=uuid7()).payload),
        envelope("catalog.tax_series.changed", rule_event(uuid7(), 1).payload),
        envelope(RULE_EVENT, rule_event(uuid7(), 1).payload | {"source_version": 0}),
    ]
    for message in rewrites:
        with pytest.raises(ValidationFailedError):
            await deliver(app, message)
    # The failed handler leaves no inbox marker, so a corrected redelivery still applies.
    [rule] = await rows(app, TaxRuleReplica)
    assert (rule.treatment, rule.source_version) == ("TAXABLE", 1)
    assert len(await rows(app, TaxRateComponentReplica)) == 2


async def test_unsupported_schema_version_is_refused(app: FastAPI) -> None:
    message = rule_event(uuid7(), 1).model_copy(update={"schema_version": 2})
    with pytest.raises(ValidationFailedError):
        await deliver(app, message)


async def test_every_replica_table_is_tenant_isolated(app: FastAPI) -> None:
    other_tenant, other_company = uuid7(), uuid7()
    for tenant, company in ((TENANT, COMPANY), (other_tenant, other_company)):
        rule_id = uuid7()
        assert await deliver(app, rule_event(rule_id, 1, tenant=tenant, company=company))
        assert await deliver(app, rate_event(uuid7(), rule_id, 1, tenant=tenant, company=company))
        assert await deliver(app, classification_event(uuid7(), 1, tenant=tenant, company=company))
    for model in TAX_REPLICA_MODELS:
        mine = await rows(app, model)
        theirs = await rows(app, model, other_tenant)
        assert mine and theirs
        assert {row.tenant_id for row in mine} == {TENANT}
        assert {row.company_id for row in mine} == {COMPANY}
        assert {row.tenant_id for row in theirs} == {other_tenant}
        assert not {row.id for row in mine} & {row.id for row in theirs}
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                total = await db.scalar(select(func.count(model.id)))
        assert total == len(mine)


async def test_withdrawal_of_a_future_row_records_its_action_and_stays_withdrawn(
    app: FastAPI,
) -> None:
    rule_id = await publish_rule(app)
    rate_id, classification_id = uuid7(), uuid7()
    published = [component("IGST", "IGST", "18", 0)]
    assert await deliver(app, rate_event(rate_id, rule_id, 2, components=published))
    assert await deliver(app, classification_event(classification_id, 2))
    [rate] = await rows(app, TaxRateReplica)
    [classification] = await rows(app, TaxClassificationReplica)
    assert rate.source_action == classification.source_action == "PUBLISH"
    # Catalog withdraws an unstarted row by ending it on its own start date.
    assert await deliver(
        app,
        rate_event(
            rate_id, rule_id, 3, action="WITHDRAW", valid_to="2017-07-01", components=published
        ),
    )
    assert await deliver(
        app, classification_event(classification_id, 3, action="WITHDRAW", valid_to="2017-07-01")
    )
    for model in (TaxRateReplica, TaxClassificationReplica):
        [row] = await rows(app, model)
        assert row.source_action == "WITHDRAW"
        assert row.valid_to == row.valid_from == dt.date(2017, 7, 1)
        assert not effective_on(row.source_action, row.valid_from, row.valid_to, row.valid_from)
    # A later generation may still change permitted fields but cannot revive the row.
    assert await deliver(
        app,
        classification_event(
            classification_id, 4, action="UPDATE", valid_to="2017-07-01", description="Renamed"
        ),
    )
    [classification] = await rows(app, TaxClassificationReplica)
    assert (classification.description, classification.source_action) == ("Renamed", "WITHDRAW")
