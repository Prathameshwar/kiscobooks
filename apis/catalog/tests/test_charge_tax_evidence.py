"""Phase 5: Catalog's version-two charge-tax evidence producer (no route; task and domain)."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.money import RoundingMode
from billing_platform.permissions import CATALOG_PERMISSIONS
from billing_platform.service_auth import ServiceKey, verify_service_body
from billing_platform.tax_calc import (
    BuyerType,
    ComponentCode,
    ComponentKind,
    ComponentRounding,
    SupplyKind,
    TaxComponent,
    Treatment,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain import charge_tax as domain
from catalog.models import tax as m
from catalog.models.tax_governance import TaxHistoryAction
from catalog.tasks.charge_tax import assess_charge_tax, evidence
from catalog.tasks.configuration_access import ConfigurationAccess
from tests.json_schema import assert_valid, errors, load
from tests.tax_factories import seed_tax

SCHEMA = "catalog-tax-computation-v2.schema.json"
POSTING = dt.date(2090, 6, 1)
REGULAR: dict[str, Any] = {
    "id": str(uuid.uuid4()),
    "tax_system": "gst_in",
    "regime": "regular",
    "registration_class": "supplier",
    "jurisdiction_code": "IN-MH",
    "valid_from": "2090-01-01",
    "valid_to": None,
}
#: Coexisting registrations that must never be chosen as the charging one.
ISD = REGULAR | {"id": str(uuid.uuid4()), "regime": "isd", "registration_class": "isd"}
MISLABELED = REGULAR | {"id": str(uuid.uuid4()), "registration_class": "tds_deductor"}
OTHER_STATE = REGULAR | {"id": str(uuid.uuid4()), "jurisdiction_code": "IN-KA"}
ENDED = REGULAR | {"id": str(uuid.uuid4()), "valid_to": "2090-05-31"}
COMPOSITION = REGULAR | {"id": str(uuid.uuid4()), "regime": "composition"}
CONTEXT: list[dict[str, Any]] = [
    REGULAR,
    ISD,
    MISLABELED,
    OTHER_STATE,
    ENDED,
    {"tax_system": "vat_x"},
]
FACTS = domain.CompanyFacts("IN", "MH", "INR", 2, RoundingMode.HALF_UP)


def percent(code: str, value: str, position: int) -> TaxComponent:
    return TaxComponent(
        component=ComponentCode(code),
        kind=ComponentKind.PERCENT,
        rounding_mode=ComponentRounding.HALF_UP,
        position=position,
        percentage=Decimal(value),
    )


INTRA = (percent("CGST", "9", 0), percent("SGST", "9", 1))
INTER = (percent("IGST", "18", 0), percent("CESS", "1", 1))


def charge(**changes: Any) -> domain.ChargeTaxInput:
    values: dict[str, Any] = {
        "tenant_id": uuid.UUID(int=1),
        "company_id": uuid.UUID(int=2),
        "assessment_id": uuid.UUID(int=3),
        "input_hash": "a" * 64,
        "posting_date": POSTING,
        "currency": "INR",
        "net_amount": Decimal("100.00"),
        "supply_kind": SupplyKind.SERVICE,
        "treatment": Treatment.TAXABLE,
        "place_of_supply_state": "MH",
        "buyer_type": BuyerType.REGULAR,
    }
    return domain.ChargeTaxInput(**(values | changes))


def build(
    request: domain.ChargeTaxInput,
    components: tuple[TaxComponent, ...] = INTRA,
    registrations: list[dict[str, Any]] = CONTEXT,
) -> dict[str, Any]:
    determination = domain.determine(request, FACTS, utgst_states=frozenset({"CH"}))
    return domain.statement(request, FACTS, determination, components, registrations)


def accounting_round_trip(value: dict[str, Any]) -> dict[str, Any]:
    """What Accounting re-serialises before verifying: decimals via ``str(Decimal)``."""
    return value | {
        "net_amount": str(Decimal(value["net_amount"])),
        "gross_amount": str(Decimal(value["gross_amount"])),
        "components": [
            entry | {"amount": str(Decimal(entry["amount"]))} for entry in value["components"]
        ],
    }


def test_intra_state_statement_matches_the_v2_contract() -> None:
    value = build(charge())
    assert_valid(load(SCHEMA), value)
    assert value["company_registration_id"] == REGULAR["id"]
    assert value["components"] == [
        {"code": "CGST", "amount": "9.00"},
        {"code": "SGST", "amount": "9.00"},
    ]
    assert value["net_amount"] == "100.00" and value["gross_amount"] == "118.00"
    total = sum((Decimal(entry["amount"]) for entry in value["components"]), Decimal(0))
    assert Decimal(value["net_amount"]) + total == Decimal(value["gross_amount"])
    assert accounting_round_trip(value) == value
    assert value["version"] == 2 and value["posting_date"] == "2090-06-01"


def test_inter_state_statement_carries_igst_and_cess() -> None:
    value = build(charge(place_of_supply_state="IN-KA", net_amount=Decimal("33.33")), INTER)
    assert_valid(load(SCHEMA), value)
    assert value["components"] == [
        {"code": "IGST", "amount": "6.00"},
        {"code": "CESS", "amount": "0.33"},
    ]
    assert value["gross_amount"] == "39.66"


def test_intra_ut_uses_utgst_from_configured_states() -> None:
    request = charge(place_of_supply_state="CH")
    facts = domain.CompanyFacts("IN", "IN-CH", "INR", 2, RoundingMode.HALF_UP)
    determination = domain.determine(request, facts, utgst_states=frozenset({"IN-CH"}))
    assert determination.context.value == "INTRA_UT"
    registration = REGULAR | {"jurisdiction_code": "IN-CH"}
    value = domain.statement(
        request,
        facts,
        determination,
        (percent("CGST", "9", 0), percent("UTGST", "9", 1)),
        [registration],
    )
    assert [entry["code"] for entry in value["components"]] == ["CGST", "UTGST"]
    assert_valid(load(SCHEMA), value)


def test_export_is_zero_rated_and_untaxed() -> None:
    value = build(charge(buyer_type=BuyerType.OVERSEAS, place_of_supply_state=None), INTER)
    assert value["components"] == [] and value["gross_amount"] == value["net_amount"]
    assert value["company_registration_id"] == REGULAR["id"]
    assert_valid(load(SCHEMA), value)


def test_composition_registration_issues_an_untaxed_statement() -> None:
    value = build(charge(), INTRA, [COMPOSITION])
    assert value["components"] == [] and value["gross_amount"] == "100.00"
    assert value["company_registration_id"] == COMPOSITION["id"]
    assert_valid(load(SCHEMA), value)


@pytest.mark.parametrize(
    "registrations",
    [[], [ISD], [MISLABELED], [OTHER_STATE], [ENDED], [{"tax_system": "vat_x"}]],
)
def test_taxed_statement_needs_a_supplier_registration_valid_on_the_date(
    registrations: list[dict[str, Any]],
) -> None:
    with pytest.raises(ValidationFailedError, match="registration"):
        build(charge(), INTRA, registrations)
    # Untaxed treatments never need one.
    value = build(charge(treatment=Treatment.EXEMPT), (), registrations)
    assert value["company_registration_id"] is None and value["components"] == []
    assert_valid(load(SCHEMA), value)


def test_registration_resolves_by_posting_date_not_today() -> None:
    later = REGULAR | {"id": str(uuid.uuid4()), "valid_from": "2090-06-01"}
    assert build(charge(), INTRA, [ENDED, later])["company_registration_id"] == later["id"]
    early = charge(posting_date=dt.date(2090, 5, 31))
    assert build(early, INTRA, [ENDED, later])["company_registration_id"] == ENDED["id"]


def test_ambiguous_and_malformed_registrations_fail_closed() -> None:
    twin = REGULAR | {"id": str(uuid.uuid4())}
    with pytest.raises(ConflictError):
        build(charge(), INTRA, [REGULAR, twin])
    with pytest.raises(ValidationFailedError, match="malformed"):
        build(charge(), INTRA, [{"tax_system": "gst_in", "id": "nope"}])


def test_amounts_must_be_exact_company_currency_decimals() -> None:
    with pytest.raises(ValidationFailedError):
        build(charge(net_amount=Decimal("100.001")))
    with pytest.raises(ValidationFailedError, match="company currency"):
        build(charge(currency="USD"))
    with pytest.raises(ValidationFailedError):
        domain.amount_string(Decimal(0), 2)
    with pytest.raises(ValidationFailedError):
        domain.amount_string(1.5, 2)  # type: ignore[arg-type]  # the float is the refused case


def test_provider_id_is_deterministic_per_inputs() -> None:
    first, second = build(charge()), build(charge())
    assert first == second
    other = build(charge(assessment_id=uuid.UUID(int=4)))
    assert other["provider_id"] != first["provider_id"]
    without = {key: value for key, value in first.items() if key != "provider_id"}
    assert first["provider_id"] == str(domain.provider_id(without))


def test_contract_rejects_drifted_statements() -> None:
    schema = load(SCHEMA)
    value = build(charge())
    assert errors(schema, value | {"net_amount": "1.00001"})
    assert errors(schema, value | {"gross_amount": "0"})
    assert errors(schema, value | {"version": 1})
    assert errors(schema, value | {"accounts": {}})
    assert errors(schema, value | {"components": [{"code": "GST", "amount": "1"}]})


def test_evidence_signature_verifies_for_accounting() -> None:
    secret = b"s" * 32
    value = build(charge())
    now = int(time.time())
    signed = evidence(value, secret=secret, key_id="catalog.test", timestamp=now)
    assert set(signed) == {"key_id", "timestamp", "computation", "signature"}
    keys = {
        "catalog.test": ServiceKey("catalog", "accounting", frozenset({domain.OPERATION}), secret)
    }
    principal = verify_service_body(
        keys,
        key_id="catalog.test",
        issuer="catalog",
        audience="accounting",
        operation="catalog.accounting_tax.assessed",
        timestamp=str(now),
        signature=signed["signature"],
        body=canonical_json(accounting_round_trip(value)),
        now=now,
        maximum_age=300,
    )
    assert principal.issuer == "catalog"
    tampered = value | {"gross_amount": "118.01"}
    with pytest.raises(Exception, match="service authentication failed"):
        verify_service_body(
            keys,
            key_id="catalog.test",
            issuer="catalog",
            audience="accounting",
            operation=domain.OPERATION,
            timestamp=str(now),
            signature=signed["signature"],
            body=canonical_json(tampered),
            now=now,
            maximum_age=300,
        )


def actor(tenant: uuid.UUID, company: uuid.UUID, user: uuid.UUID, *, drop: str = "") -> Actor:
    permissions = frozenset(key for key in CATALOG_PERMISSIONS if key != drop)
    return Actor(
        tenant, user, grants=(Grant(permissions, Scope("company", company), dt.date(2000, 1, 1)),)
    )


async def assess(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    root: str,
    ids: dict[str, uuid.UUID],
    *,
    drop: str = "",
    **changes: Any,
) -> dict[str, Any]:
    company = uuid.UUID(root.rsplit("/", 1)[1])
    values: dict[str, Any] = {
        "assessment_id": uuid.UUID(int=9),
        "input_hash": "b" * 64,
        "posting_date": POSTING,
        "currency": "INR",
        "net_amount": Decimal("250.00"),
        "rule_id": ids["tax_rule"],
        "place_of_supply_state": "MH",
        "buyer_type": "REGULAR",
        "registrations": [REGULAR],
        "utgst_states": frozenset({"CH"}),
    } | changes
    with tenant_scope(tenant):
        async with factory() as db:
            current = actor(tenant, company, ids["actor_user"], drop=drop)
            access = ConfigurationAccess(db, current, company)
            return await assess_charge_tax(access, **values)


async def test_task_uses_the_rate_effective_on_the_posting_date(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a)
    value = await assess(factory, tenant_a, root, ids)
    assert_valid(load(SCHEMA), value)
    # The seeded synthetic intra-state rate is 5%, split 2.5% + 2.5%.
    assert value["components"] == [
        {"code": "CGST", "amount": "6.25"},
        {"code": "SGST", "amount": "6.25"},
    ]
    assert value["gross_amount"] == "262.50"
    assert value["tenant_id"] == str(tenant_a)
    inter = await assess(factory, tenant_a, root, ids, place_of_supply_state="KA")
    assert inter["components"] == [{"code": "IGST", "amount": "12.50"}]
    # Before the rate starts there is no rate: refused, never a silent zero.
    with pytest.raises(ConflictError, match="no tax rate"):
        await assess(factory, tenant_a, root, ids, posting_date=dt.date(2089, 12, 31))


async def test_task_skips_withdrawn_rates(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                TaxHistoryAction(
                    tenant_id=tenant_a,
                    company_id=company,
                    row_version=1,
                    resource="tax_rate",
                    target_id=ids["rate_INTRA_STATE"],
                    action="WITHDRAW",
                    previous_id=None,
                    previous_valid_to=None,
                    release_id=None,
                    reason="Synthetic withdrawal",
                    business_date=dt.date(2089, 1, 1),
                )
            )
    with pytest.raises(ConflictError, match="no tax rate"):
        await assess(factory, tenant_a, root, ids)


async def test_task_needs_read_authority_and_an_active_rule(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a)
    with pytest.raises(PermissionDeniedError):
        await assess(factory, tenant_a, root, ids, drop="tax_rule.read")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            rule = await db.get(m.TaxRule, ids["tax_rule"])
            assert rule is not None
            rule.is_active = False
    with pytest.raises(ConflictError, match="inactive"):
        await assess(factory, tenant_a, root, ids)


async def test_task_cannot_reach_another_tenants_rule(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    root_a, _, ids_a = await seed_tax(factory, tenant_a)
    _, _, ids_b = await seed_tax(factory, tenant_b)
    with pytest.raises(Exception) as caught:
        await assess(factory, tenant_a, root_a, ids_a, rule_id=ids_b["tax_rule"])
    assert getattr(caught.value, "status_code", None) in {403, 404}


@pytest.mark.parametrize("treatment", ["EXEMPT", "NIL_RATED"])
async def test_untaxed_rules_produce_untaxed_statements(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, treatment: str
) -> None:
    root, _, ids = await seed_tax(factory, tenant_a, treatment=treatment)
    value = await assess(factory, tenant_a, root, ids, registrations=[])
    assert value["components"] == [] and value["gross_amount"] == "250.00"
    assert value["company_registration_id"] is None
    assert_valid(load(SCHEMA), value)
