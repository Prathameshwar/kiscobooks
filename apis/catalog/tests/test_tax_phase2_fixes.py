"""Phase 2 tax regressions: history, rounding, code systems, previews, audit and company scope."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.tax_publication import RATE_EVENT, TAX_PUBLICATION_EVENTS
from catalog.models import Outbox
from catalog.tasks import pricing_commands
from tests.pricing_factories import guard
from tests.tax_factories import EVIDENCE, components, query, seed_tax
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def on(monkeypatch: pytest.MonkeyPatch, day: dt.date) -> None:
    moment = dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.UTC)
    monkeypatch.setattr(pricing_commands, "utcnow", lambda: moment)


def rate(ids: dict[str, uuid.UUID], context: str, valid_from: str, **extra: Any) -> dict[str, Any]:
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


async def events(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    object_id: str,
    *,
    publications: bool = False,
) -> list[str]:
    """Audit events of one object; Accounting publications only when asked for (Phase 5)."""
    with tenant_scope(tenant):
        async with factory() as db:
            found = await db.scalars(
                select(Outbox.event_type).where(
                    Outbox.tenant_id == tenant, Outbox.aggregate_id == uuid.UUID(object_id)
                )
            )
            return sorted(
                event for event in found if (event in TAX_PUBLICATION_EVENTS) == publications
            )


async def test_same_day_supersession_cannot_shorten_a_rate_in_force(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    on(monkeypatch, dt.date(2090, 6, 1))
    body = rate(ids, "INTER_STATE", "2090-06-01")
    result = await client.post(root + "/tax-rates", headers=command_headers(auth), json=body)
    assert result.status_code == 409, result.text
    assert "future" in result.text
    preview = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert preview.status_code == 409, preview.text
    # A strictly future supersession of the same predecessor stays allowed.
    body["valid_from"] = "2090-06-02"
    result = await client.post(root + "/tax-rates", headers=command_headers(auth), json=body)
    assert result.status_code == 201, result.text


async def test_brand_new_history_may_start_today(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    on(monkeypatch, dt.date(2090, 6, 1))
    result = await client.post(
        root + "/tax-classifications",
        headers=command_headers(auth),
        json={
            "expected_generation": 1,
            "expected_source_version": 2,
            **EVIDENCE,
            "code_system": "HSN",
            "code": "5678",
            "item_kind": "GOODS",
            "description": "Synthetic same-day start",
            "valid_from": "2090-06-01",
        },
    )
    assert result.status_code == 201, result.text


async def test_split_gst_components_must_share_rounding(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body = rate(ids, "INTRA_STATE", "2091-01-01")
    body["components"][1]["rounding_mode"] = "DOWN"
    for path, request in (("/tax-rate-previews", auth), ("/tax-rates", command_headers(auth))):
        result = await client.post(root + path, headers=request, json=body)
        assert result.status_code == 422, result.text
        assert "rounding" in result.text


async def test_cross_context_rounding_must_agree(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body = rate(ids, "INTER_STATE", "2091-01-01")
    body["components"][0]["rounding_mode"] = "DOWN"
    result = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert result.status_code == 409, result.text


@pytest.mark.parametrize("code", ["9901", "990123", "99012345"])
async def test_goods_classification_rejects_chapter_99(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    code: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    result = await client.post(
        root + "/tax-classifications",
        headers=command_headers(auth),
        json={
            "expected_generation": 1,
            "expected_source_version": 2,
            **EVIDENCE,
            "code_system": "HSN",
            "code": code,
            "item_kind": "GOODS",
            "description": "Services chapter",
            "valid_from": "2091-01-01",
        },
    )
    assert result.status_code == 422, result.text
    result = await client.post(
        root + "/tax-rule-applicabilities",
        headers=command_headers(auth),
        json={"rule_id": str(ids["tax_rule"]), "code_system": "HSN", "code": code[:4]},
    )
    assert result.status_code == 422, result.text


async def test_sac_must_start_with_99(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a, kind="SERVICE")
    result = await client.post(
        root + "/tax-classifications",
        headers=command_headers(auth),
        json={
            "expected_generation": 1,
            "expected_source_version": 2,
            **EVIDENCE,
            "code_system": "SAC",
            "code": "981234",
            "item_kind": "SERVICE",
            "description": "Not a services code",
            "valid_from": "2091-01-01",
        },
    )
    assert result.status_code == 422, result.text


async def test_previews_check_permission_before_validation(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    denied = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"tax_rule.publish"}),
    )
    invalid = rate(ids, "INTRA_STATE", "2091-01-01", components=components("INTER_STATE"))
    allowed = await client.post(root + "/tax-rate-previews", headers=auth, json=invalid)
    assert allowed.status_code == 422, allowed.text
    result = await client.post(root + "/tax-rate-previews", headers=denied, json=invalid)
    assert result.status_code == 403, result.text
    stale = rate(ids, "INTER_STATE", "2091-01-01", expected_generation=99)
    result = await client.post(root + "/tax-rate-previews", headers=denied, json=stale)
    assert result.status_code == 403, result.text


@pytest.mark.parametrize(
    "path", ["/tax-rate-previews", "/tax-release-previews", "/tax-impact-previews"]
)
async def test_previews_are_rate_limited(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    app: FastAPI,
    path: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    key = "tax:" + tenant_a.hex + company.hex + ids["actor_user"].hex
    for _ in range(120):
        assert app.state.pricing_limiter.allow(key, limit=120)
    result = await client.post(root + path, headers=auth, json={})
    assert result.status_code == 429, result.text


async def test_publish_commands_audit_as_publish_and_withdrawal_audits_target(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    result = await client.post(
        root + "/tax-rates",
        headers=command_headers(auth),
        json=rate(ids, "INTER_STATE", "2091-01-01"),
    )
    assert result.status_code == 201, result.text
    published = result.json()
    assert await events(factory, tenant_a, published["id"]) == ["catalog.tax_rate.publish"]
    # The same command also publishes the rate to Accounting, once, in its transaction.
    assert await events(factory, tenant_a, published["id"], publications=True) == [RATE_EVENT]
    # The shortened predecessor records an update of its window.
    assert await events(factory, tenant_a, str(ids["rate_INTER_STATE"])) == [
        "catalog.tax_rate.update"
    ]
    binding = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **guard(published),
            "scope_id": str(ids["catalog_tax_scope"]),
            "direction": "SALE",
            "bundle": "TREATMENT",
            "mode": "OVERRIDE",
            "treatment": "TAXABLE",
            "tax_category_id": str(ids["tax_category"]),
            "valid_from": "2091-01-01",
            "supersedes_id": str(ids["binding_SALE_TREATMENT"]),
            "expected_previous_version": 1,
        },
    )
    assert binding.status_code == 201, binding.text
    assert await events(factory, tenant_a, binding.json()["id"]) == [
        "catalog.catalog_tax_binding.publish"
    ]
    withdrawal = await client.post(
        root + "/tax-withdrawals",
        headers=command_headers(auth),
        json={
            **guard(binding.json()),
            "resource": "catalog_tax_binding",
            "target_id": binding.json()["id"],
            "expected_version": 1,
            "reason": "Synthetic abandoned binding",
        },
    )
    assert withdrawal.status_code == 201, withdrawal.text
    assert await events(factory, tenant_a, binding.json()["id"]) == [
        "catalog.catalog_tax_binding.publish",
        "catalog.catalog_tax_binding.withdraw",
    ]
    assert await events(factory, tenant_a, withdrawal.json()["id"]) == [
        "catalog.tax_history_action.create"
    ]


async def test_body_references_to_another_company_are_rejected(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    _, _, foreign = await seed_tax(factory, tenant_a)
    generation = {"expected_generation": 1, "expected_source_version": 2}
    binding = {
        **generation,
        "scope_id": str(ids["catalog_tax_scope"]),
        "direction": "SALE",
        "valid_from": "2091-01-01",
        "mode": "OVERRIDE",
    }
    fixed_cess = {
        "component_key": "CESS",
        "component": "CESS",
        "kind": "FIXED_PER_UNIT",
        "amount": "1",
        "currency": "INR",
        "basis_quantity": "1",
        "unit_id": str(foreign["unit_of_measure"]),
        "rounding_mode": "HALF_UP",
        "position": 1,
    }
    cases: list[tuple[str, str, dict[str, Any]]] = [
        (
            "POST",
            "/tax-rules",
            {
                **EVIDENCE,
                "code": "NEW",
                "name": "New",
                "item_kind": "GOODS",
                "treatment": "TAXABLE",
                "tax_category_id": str(foreign["tax_category"]),
            },
        ),
        (
            "POST",
            "/tax-rate-series",
            {"rule_id": str(foreign["tax_rule"]), "applicability": "INTER_STATE"},
        ),
        ("POST", "/tax-rates", rate(foreign, "INTER_STATE", "2091-01-01")),
        (
            "POST",
            "/tax-rates",
            rate(
                ids,
                "INTER_STATE",
                "2091-01-01",
                components=[*components("INTER_STATE"), fixed_cess],
            ),
        ),
        ("POST", "/tax-scopes", {"owner_kind": "GROUP", "group_id": str(foreign["item_group"])}),
        (
            "POST",
            "/tax-scopes",
            {"owner_kind": "FAMILY", "family_id": str(foreign["product_family"])},
        ),
        ("POST", "/tax-scopes", {"owner_kind": "SKU", "item_id": str(foreign["item"])}),
        (
            "POST",
            "/tax-bindings",
            {
                **binding,
                "bundle": "TREATMENT",
                "treatment": "TAXABLE",
                "tax_category_id": str(ids["tax_category"]),
                "scope_id": str(foreign["catalog_tax_scope"]),
            },
        ),
        (
            "POST",
            "/tax-bindings",
            {
                **binding,
                "bundle": "CLASSIFICATION",
                "classification_id": str(foreign["tax_classification"]),
            },
        ),
        (
            "POST",
            "/tax-bindings",
            {**binding, "bundle": "RULE", "rule_id": str(foreign["tax_rule"])},
        ),
        (
            "POST",
            "/tax-bindings",
            {
                **binding,
                "bundle": "TREATMENT",
                "treatment": "TAXABLE",
                "tax_category_id": str(foreign["tax_category"]),
            },
        ),
        (
            "PATCH",
            "/tax-rules/" + str(foreign["tax_rule"]),
            {"expected_version": 1, "name": "Changed", "is_active": True},
        ),
        (
            "PATCH",
            "/tax-categories/" + str(foreign["tax_category"]),
            {"expected_version": 1, "name": "Changed", "is_active": True},
        ),
    ]
    for method, path, body in cases:
        result = await client.request(method, root + path, headers=command_headers(auth), json=body)
        assert result.status_code in {403, 404}, (path, body, result.text)
    resolved = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids)
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "COMPLETE", resolved.text
