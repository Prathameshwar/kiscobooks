"""Account-level GST defaults (tax-accounting plan Phase 6)."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.domain.rules import validate_account_tax_default
from accounting.models.masters import AccountTaxDefault
from tests.conftest import COMPANY, PERMISSIONS, TENANT, headers
from tests.test_catalog_tax_replica import publish_rule
from tests.test_masters import BASE, activate, post, prepare

PATH = "/account-tax-defaults"


def day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


def sale(account_id: str, rule_id: uuid.UUID | None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "account_id": account_id,
        "direction": "SALE",
        "supply_kind": "SERVICE",
        "code_system": "SAC",
        "code": "998314",
        "rule_id": None if rule_id is None else str(rule_id),
        "treatment": "TAXABLE",
        "valid_from": day(1),
    }
    return body | overrides


def purchase(account_id: str, rule_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    return (
        sale(
            account_id,
            rule_id,
            direction="PURCHASE",
            supply_kind="GOODS",
            code_system="HSN",
            code="84713010",
            itc_eligibility="ELIGIBLE",
            rcm_applicable=False,
            assessable_inclusion="GOODS",
            apportion_by="VALUE",
        )
        | overrides
    )


async def account(
    client: httpx.AsyncClient, group: str, code: str, *, kind: str = "GENERAL", active: bool = True
) -> dict[str, Any]:
    row = await post(
        client, "/accounts", {"code": code, "name": code, "group_id": group, "kind": kind}
    )
    return await activate(client, "/accounts", row) if active else row


async def setup(client: httpx.AsyncClient, app: FastAPI) -> dict[str, Any]:
    groups = await prepare(client)
    income = await account(client, groups["SALES"], "GST_SALES")
    expense = await account(client, groups["PURCHASES"], "GST_PURCHASES")
    return {
        "groups": groups,
        "income": income,
        "expense": expense,
        "service_rule": await publish_rule(app),
        "goods_rule": await publish_rule(app, item_kind="GOODS", name="GST 18% goods"),
    }


# --- domain rules: no database -------------------------------------------------------------


VALID = {
    "direction": "PURCHASE",
    "supply_kind": "SERVICE",
    "code_system": "SAC",
    "code": "998314",
    "rule_id": uuid7(),
    "treatment": "TAXABLE",
    "itc_eligibility": "ELIGIBLE",
    "rcm_applicable": True,
    "assessable_inclusion": "NONE",
    "apportion_by": None,
}


def test_domain_accepts_a_complete_purchase_default() -> None:
    validate_account_tax_default(VALID)
    validate_account_tax_default(VALID | {"treatment": "EXEMPT", "rule_id": None})
    validate_account_tax_default(
        VALID | {"code_system": "HSN", "code": "8471", "supply_kind": "GOODS"}
    )


@pytest.mark.parametrize(
    "change",
    [
        {"code": "848100"},  # a SAC code outside chapter 99
        {"code_system": "HSN", "code": "998314", "supply_kind": "GOODS"},  # HSN in chapter 99
        {"code_system": "HSN", "code": "84713", "supply_kind": "GOODS"},  # odd length
        {"code_system": "HSN", "code": "8471"},  # HSN classifies goods
        {"rule_id": None},  # taxable needs a rule
        {"treatment": "NIL_RATED", "rule_id": None},
        {"itc_eligibility": None},  # purchases state eligibility
        {"direction": "SALE"},  # sales have no ITC eligibility
        {"direction": "SALE", "itc_eligibility": None},  # nor reverse charge
        {"assessable_inclusion": "BOTH"},  # an inclusion is apportioned
        {"apportion_by": "QUANTITY"},  # and only an inclusion
    ],
)
def test_domain_rejects_inconsistent_defaults(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailedError):
        validate_account_tax_default(VALID | change)


# --- endpoints -----------------------------------------------------------------------------


async def test_create_read_list_update_export_and_audit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ctx = await setup(client, app)
    created = await post(client, PATH, sale(ctx["income"]["id"], ctx["service_rule"]))
    assert created["code"] == "998314" and created["rule_id"] == str(ctx["service_rule"])
    assert created["assessable_inclusion"] == "NONE" and created["rcm_applicable"] is False
    bought = await post(client, PATH, purchase(ctx["expense"]["id"], ctx["goods_rule"]))
    assert (bought["itc_eligibility"], bought["apportion_by"]) == ("ELIGIBLE", "VALUE")

    detail = await client.get(BASE + PATH + "/" + created["id"], headers=headers())
    assert detail.status_code == 200 and detail.json() == created

    listing = await client.get(BASE + PATH, headers=headers(), params={"direction": "SALE"})
    assert listing.status_code == 200, listing.text
    [item] = listing.json()["items"]
    assert item["id"] == created["id"]
    # The lean projection, never the detail model.
    assert "rule_id" not in item and "itc_eligibility" not in item
    dated = await client.get(BASE + PATH, headers=headers(), params={"as_of": day(0)})
    assert dated.json()["items"] == []
    by_code = await client.get(BASE + PATH, headers=headers(), params={"q": "8471"})
    assert [row["id"] for row in by_code.json()["items"]] == [bought["id"]]
    sorted_page = await client.get(BASE + PATH, headers=headers(), params={"sort": "-id"})
    assert len(sorted_page.json()["items"]) == 2
    bad_sort = await client.get(BASE + PATH, headers=headers(), params={"sort": "code"})
    assert bad_sort.status_code == 422

    fields = await client.get(BASE + PATH + "/field-set", headers=headers())
    assert fields.status_code == 200
    described = {field["key"]: field for field in fields.json()["fields"]}
    assert described["account_id"]["reference"] == "accounts"
    # Rule ids are Catalog identifiers: picked from Catalog, checked against the replica.
    assert described["rule_id"]["reference"] is None
    assert described["apportion_by"]["required"] is False

    updated = await client.patch(
        BASE + PATH + "/" + created["id"],
        json={"expected_version": created["row_version"], "valid_to": day(30)},
        headers=headers(),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["valid_to"] == day(30)

    export = await client.get(BASE + "/exports" + PATH, headers=headers())
    assert export.status_code == 200 and len(export.json()["items"]) == 2

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.aggregate_id == uuid.UUID(created["id"]))
                )
            )
    assert sorted(row.event_type for row in events) == [
        "accounting.account_tax_default.create",
        "accounting.account_tax_default.update",
    ]


async def test_authentication_permission_and_input_errors(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ctx = await setup(client, app)
    body = sale(ctx["income"]["id"], ctx["service_rule"])
    unauthenticated = await client.post(BASE + PATH, json=body)
    assert unauthenticated.status_code == 401
    readers = headers(permissions=PERMISSIONS - {"accounting.tax.manage"})
    assert (await client.post(BASE + PATH, json=body, headers=readers)).status_code == 403
    assert (await client.get(BASE + PATH, headers=readers)).status_code == 200
    blind = headers(permissions=PERMISSIONS - {"accounting.tax.read", "accounting.tax.manage"})
    assert (await client.get(BASE + PATH, headers=blind)).status_code == 403
    invalid = [
        body | {"code": "848100"},
        body | {"direction": "BOTH"},
        body | {"supply_kind": "GOODS"},
        body | {"rcm_applicable": "yes"},
        body | {"unexpected": 1},
        body | {"valid_to": day(0)},
        {key: value for key, value in body.items() if key != "code"},
    ]
    for candidate in invalid:
        response = await client.post(BASE + PATH, json=candidate, headers=headers())
        assert response.status_code == 422, (candidate, response.text)


async def test_only_general_pl_or_asset_accounts_and_matching_active_rules(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ctx = await setup(client, app)
    groups = ctx["groups"]
    liability = await account(client, groups["CURRENT_LIABILITIES"], "ACCRUALS")
    asset = await account(client, groups["FIXED_ASSETS"], "MACHINERY")
    draft = await account(client, groups["SALES"], "DRAFT_SALES", active=False)
    rule = ctx["service_rule"]
    await post(client, PATH, sale(liability["id"], rule), status=422)
    await post(client, PATH, sale(draft["id"], rule), status=409)
    await post(client, PATH, purchase(asset["id"], ctx["goods_rule"]))
    # A goods rule on a services default, and a treatment the rule does not carry.
    await post(client, PATH, sale(ctx["income"]["id"], ctx["goods_rule"]), status=422)
    await post(client, PATH, sale(ctx["income"]["id"], rule, treatment="NIL_RATED"), status=422)
    inactive = await publish_rule(app, is_active=False)
    await post(client, PATH, sale(ctx["income"]["id"], inactive), status=409)
    await post(client, PATH, sale(ctx["income"]["id"], uuid7()), status=404)


async def test_wrong_company_rule_and_object_are_forbidden(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ctx = await setup(client, app)
    other = uuid7()
    foreign_rule = await publish_rule(app, company=other)
    await post(client, PATH, sale(ctx["income"]["id"], foreign_rule), status=403)
    created = await post(client, PATH, sale(ctx["income"]["id"], ctx["service_rule"]))
    other_base = f"/v1/companies/{other}"
    other_headers = headers(company=other)
    await client.post(other_base + "/accounting-setup/initialize", json={}, headers=other_headers)
    # The object belongs to COMPANY: through another company's path it is forbidden.
    response = await client.get(other_base + PATH + "/" + created["id"], headers=other_headers)
    assert response.status_code == 403, response.text
    patch = await client.patch(
        other_base + PATH + "/" + created["id"],
        json={"expected_version": 1, "valid_to": day(9)},
        headers=headers(company=other),
    )
    assert patch.status_code == 403, patch.text
    listing = await client.get(other_base + PATH, headers=other_headers)
    assert listing.json()["items"] == []


async def test_overlap_per_account_and_direction(client: httpx.AsyncClient, app: FastAPI) -> None:
    ctx = await setup(client, app)
    income, rule = ctx["income"]["id"], ctx["service_rule"]
    first = await post(client, PATH, sale(income, rule, valid_to=day(10)))
    await post(client, PATH, sale(income, rule, valid_from=day(5)), status=409)
    # Purchase direction on the same account is a separate timeline.
    await post(client, PATH, purchase(income, ctx["goods_rule"], valid_from=day(5)))
    await post(client, PATH, sale(income, rule, valid_from=day(11)))
    stretched = await client.patch(
        BASE + PATH + "/" + first["id"],
        json={"expected_version": first["row_version"], "valid_to": day(20)},
        headers=headers(),
    )
    assert stretched.status_code == 409, stretched.text
    moved = await client.patch(
        BASE + PATH + "/" + first["id"],
        json={"expected_version": first["row_version"], "direction": "PURCHASE"},
        headers=headers(),
    )
    assert moved.status_code in {409, 422}, moved.text


async def test_idempotent_replay_has_one_effect(client: httpx.AsyncClient, app: FastAPI) -> None:
    ctx = await setup(client, app)
    h = headers(key=str(uuid.uuid4()))
    body = sale(ctx["income"]["id"], ctx["service_rule"])
    first = await client.post(BASE + PATH, json=body, headers=h)
    second = await client.post(BASE + PATH, json=body, headers=h)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    conflicting = await client.post(BASE + PATH, json=body | {"code": "998315"}, headers=h)
    assert conflicting.status_code in {409, 422}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            stored = list(await db.scalars(select(AccountTaxDefault)))
            events = list(
                await db.scalars(
                    select(Outbox).where(
                        Outbox.event_type == "accounting.account_tax_default.create"
                    )
                )
            )
    assert len(stored) == 1 and len(events) == 1


async def test_field_policy_denies_writes_and_hides_reads(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ctx = await setup(client, app)

    def policy(field: str, access: str) -> dict[str, Any]:
        return {
            "entity_type": "accounting.account_tax_default",
            "field_key": field,
            "access": access,
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }

    body = purchase(ctx["expense"]["id"], ctx["goods_rule"], rcm_applicable=True)
    denied = await client.post(
        BASE + PATH, json=body, headers=headers(policies=[policy("rcm_applicable", "write")])
    )
    assert denied.status_code == 403, denied.text
    created = await post(client, PATH, body)
    hidden = headers(policies=[policy("code", "read")])
    detail = await client.get(BASE + PATH + "/" + created["id"], headers=hidden)
    assert detail.status_code == 200 and "code" not in detail.json()
    listing = await client.get(BASE + PATH, headers=hidden)
    assert "code" not in listing.json()["items"][0]
    export = await client.get(BASE + "/exports" + PATH, headers=hidden)
    assert "code" not in export.json()["items"][0]
    # A read-denied field is no filter or search key either.
    for params in ({"code": "8471"}, {"q": "8471"}):
        response = await client.get(BASE + PATH, headers=hidden, params=params)
        assert response.status_code == 403, params


async def test_defaults_are_tenant_isolated(client: httpx.AsyncClient, app: FastAPI) -> None:
    ctx = await setup(client, app)
    mine = await post(client, PATH, sale(ctx["income"]["id"], ctx["service_rule"]))
    other_tenant = uuid7()
    theirs_h = headers(tenant=other_tenant)
    groups = await prepare(client, h=theirs_h)
    row = await post(
        client,
        "/accounts",
        {"code": "GST_SALES", "name": "Sales", "group_id": groups["SALES"], "kind": "GENERAL"},
        h=theirs_h,
    )
    row = await activate(client, "/accounts", row, h=theirs_h)
    rule = await publish_rule(app, tenant=other_tenant)
    theirs = await post(client, PATH, sale(row["id"], rule), h=theirs_h)
    for tenant, own, foreign in ((TENANT, mine, theirs), (other_tenant, theirs, mine)):
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                ids = {str(item.id) for item in await db.scalars(select(AccountTaxDefault))}
        assert ids == {own["id"]}
        h = headers(tenant=tenant)
        listed = await client.get(BASE + PATH, headers=h)
        assert [item["id"] for item in listed.json()["items"]] == [own["id"]]
        hidden = await client.get(BASE + PATH + "/" + foreign["id"], headers=h)
        assert hidden.status_code == 404
    # Another tenant's rule is invisible too, not merely another company's.
    await post(client, PATH, sale(ctx["income"]["id"], rule, valid_from=day(40)), status=404)
