"""History immutability and invalid stored-source regressions."""

import datetime as dt
import uuid
from types import SimpleNamespace

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ItemGroup, ProductFamily
from catalog.models.tax import TaxClassification, TaxRate, TaxRateComponent
from catalog.schemas.tax import ComponentInput
from catalog.tasks import activation, pricing_commands, tax_history, tax_integrity
from catalog.tasks.tax_validation import stored_components, stored_match
from tests.pricing_factories import create, guard
from tests.tax_factories import EVIDENCE, components, query, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_rule_applicability_is_frozen_after_first_binding(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body = {
        "rule_id": str(ids["tax_rule"]),
        "code_system": "HSN",
        "code": "5678",
        "match_kind": "EXACT",
    }
    blocked = await client.post(
        root + "/tax-rule-applicabilities", headers=command_headers(auth), json=body
    )
    assert blocked.status_code == 409, blocked.text
    rule = await create(
        client,
        root,
        auth,
        "/tax-rules",
        {
            **EVIDENCE,
            "code": "UNUSED",
            "name": "Unbound reviewed rule",
            "item_kind": "GOODS",
            "treatment": "TAXABLE",
            "tax_category_id": str(ids["tax_category"]),
        },
    )
    body["rule_id"] = rule["id"]
    value = await create(client, root, auth, "/tax-rule-applicabilities", body)
    found = await client.get(root + "/tax-rule-applicabilities/" + value["id"], headers=auth)
    assert found.status_code == 200 and found.json()["code"] == "5678", found.text


async def test_withdrawal_excludes_future_rows_and_preserves_readable_evidence(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(
        pricing_commands, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC)
    )
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    blocked = await client.post(
        root + "/tax-withdrawals",
        headers=command_headers(auth),
        json={
            **guard(current.json()),
            "resource": "tax_rate",
            "target_id": str(ids["rate_INTER_STATE"]),
            "expected_version": 1,
            "reason": "Cannot withdraw today",
        },
    )
    assert blocked.status_code == 409, blocked.text
    future = await create(
        client,
        root,
        auth,
        "/tax-classifications",
        {
            **guard(current.json()),
            **EVIDENCE,
            "code_system": "HSN",
            "code": "5678",
            "item_kind": "GOODS",
            "description": "Future draft",
            "valid_from": "2091-01-01",
        },
    )
    body = {
        **guard(future),
        "resource": "tax_classification",
        "target_id": future["id"],
        "expected_version": 1,
        "reason": "Retain abandoned future evidence",
    }
    request = command_headers(auth)
    result = await client.post(root + "/tax-withdrawals", headers=request, json=body)
    assert result.status_code == 201, result.text
    replay = await client.post(root + "/tax-withdrawals", headers=request, json=body)
    assert (
        replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    detail = await client.get(root + "/tax-classifications/" + future["id"], headers=auth)
    assert (
        detail.status_code == 200
        and detail.json()["source_reference"] == EVIDENCE["source_reference"]
    )
    listed = await client.get(
        root + "/tax-classifications", headers=auth, params={"as_of": "2091-01-01"}
    )
    assert listed.status_code == 200 and future["id"] not in {
        entry["id"] for entry in listed.json()["items"]
    }
    again = await client.post(
        root + "/tax-withdrawals",
        headers=command_headers(auth),
        json={**body, **guard(result.json()), "expected_version": 2},
    )
    assert again.status_code == 409, again.text


def test_invalid_persisted_components_and_applicability_raise_controlled_conflicts() -> None:
    valid = [ComponentInput.model_validate(entry) for entry in components("INTER_STATE")]
    assert stored_components("INTER_STATE", "TAXABLE", valid) == valid
    invalid = valid[0].model_copy(update={"percentage": "untrusted"})
    with pytest.raises(ConflictError, match="correction"):
        stored_components("INTER_STATE", "TAXABLE", [invalid])
    with pytest.raises(ConflictError, match="correction"):
        stored_components("INTRA_STATE", "TAXABLE", valid)
    assert (
        stored_match(SimpleNamespace(code_system="HSN", code="1234", match_kind="EXACT")).code
        == "1234"
    )
    with pytest.raises(ConflictError, match="correction"):
        stored_match(SimpleNamespace(code_system="HSN", code="", match_kind="PREFIX"))


async def test_withdrawal_cannot_leave_an_active_product_without_future_tax(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(
        pricing_commands, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC)
    )
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            item = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            previous = await db.get(TaxRate, ids["rate_INTER_STATE"])
            assert item is not None and family is not None and previous is not None
            item.status = family.status = "ACTIVE"
            previous.valid_to = dt.date(2090, 12, 31)
            future = TaxRate(
                tenant_id=tenant_a,
                company_id=company,
                row_version=1,
                series_id=ids["series_INTER_STATE"],
                supersedes_id=previous.id,
                valid_from=dt.date(2091, 1, 1),
                valid_to=None,
                **EVIDENCE,
            )
            db.add(future)
            await db.flush()
            target = future.id
            db.add(
                TaxRateComponent(
                    tenant_id=tenant_a,
                    company_id=company,
                    row_version=1,
                    rate_id=target,
                    **components("INTER_STATE")[0],
                )
            )
    current = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    result = await client.post(
        root + "/tax-withdrawals",
        headers=command_headers(auth),
        json={
            **guard(current.json()),
            "resource": "tax_rate",
            "target_id": str(target),
            "expected_version": 1,
            "reason": "Must not strand active products",
            "restore_predecessor": False,
        },
    )
    assert result.status_code == 409 and "active product" in result.text, result.text
    resolved = await client.post(
        root + "/tax-configurations/resolve", headers=auth, json=query(ids, as_of="2091-01-01")
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "COMPLETE", resolved.text


async def test_group_impact_and_bounds_never_report_an_unchecked_subset(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    scope = await create(
        client,
        root,
        auth,
        "/tax-scopes",
        {"owner_kind": "GROUP", "group_id": str(ids["item_group"])},
    )
    body = {"resource": "catalog_tax_scope", "target_id": scope["id"], "as_of": "2090-01-01"}
    result = await client.post(root + "/tax-impact-previews", headers=auth, json=body)
    assert result.status_code == 200 and result.json()["affected_item_ids"] == [
        str(ids["item"])
    ], result.text
    for module, name in (
        (tax_history, "MAX_ROWS"),
        (tax_integrity, "MAX_ITEMS"),
        (tax_integrity, "MAX_DATES"),
        (tax_integrity, "MAX_CHECKS"),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(module, name, 0)
            result = await client.post(root + "/tax-impact-previews", headers=auth, json=body)
            assert result.status_code == 409, (name, result.text)


async def test_empty_service_group_rejects_goods_tax_rule(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            group = ItemGroup(
                tenant_id=tenant_a,
                company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                code="SERVICE_ONLY",
                name="Service only",
                allowed_kind="SERVICE",
                is_active=True,
                row_version=1,
            )
            db.add(group)
            await db.flush()
            group_id = group.id
    scope = await create(
        client, root, auth, "/tax-scopes", {"owner_kind": "GROUP", "group_id": str(group_id)}
    )
    result = await client.post(
        root + "/tax-bindings",
        headers=command_headers(auth),
        json={
            **guard(scope),
            "scope_id": scope["id"],
            "valid_from": "2091-01-01",
            "direction": "SALE",
            "bundle": "RULE",
            "mode": "OVERRIDE",
            "rule_id": str(ids["tax_rule"]),
        },
    )
    assert result.status_code == 422, result.text


async def test_unrelated_classifications_do_not_exhaust_product_review_capacity(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            for number in range(7):
                db.add(
                    TaxClassification(
                        tenant_id=tenant_a,
                        company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                        row_version=1,
                        jurisdiction="IN",
                        code_system="HSN",
                        code=str(9000 + number),
                        item_kind="GOODS",
                        description="Unrelated future classification",
                        valid_from=dt.date(2091, 1, 1),
                        valid_to=None,
                        **EVIDENCE,
                    )
                )
    monkeypatch.setattr(tax_history, "MAX_ROWS", 6)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    result = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=auth,
        json={"as_of": "2090-01-01"},
    )
    assert result.status_code == 200 and result.json()["eligible"], result.text


async def test_activation_without_commercial_directions_needs_no_tax_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db, db.begin():
            item = await db.get(Item, ids["item"])
            assert item is not None
            item.sellable = item.purchasable = False
    monkeypatch.setattr(tax_history, "MAX_ROWS", 0)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    result = await client.post(
        root + "/items/" + str(ids["item"]) + "/activation-preview",
        headers=auth,
        json={"as_of": "2090-01-01"},
    )
    assert result.status_code == 200 and result.json()["eligible"], result.text
