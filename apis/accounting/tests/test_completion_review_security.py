"""Second review: derived workflow responses must preserve field authorization."""

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from tests.conftest import TENANT, headers
from tests.test_field_policy import policy
from tests.test_masters import BASE, post, prepare


async def test_preview_and_install_replay_do_not_infer_denied_classification(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    original_headers = headers()
    body = {"business_accounts": False}
    await post(client, "/accounting-setup/install", body, h=original_headers, status=200)
    for entity, field in [
        ("account_group", "parent_id"),
        ("account_group", "head_id"),
        ("account_group", "affects_gross_profit"),
        ("account", "kind"),
        ("account", "used_at"),
        ("account_head", "nature"),
        ("account_template_installation", "template_version"),
    ]:
        rule = policy(field, entity="accounting." + entity)
        if entity == "account":
            rule["condition"] = {"field": "status", "cmp": "eq", "value": "ACTIVE"}
        h = headers(policies=[rule], key=original_headers["Idempotency-Key"])
        for action in ("preview", "install"):
            response = await client.post(BASE + "/accounting-setup/" + action, json=body, headers=h)
            assert response.status_code == 403, (entity, field, action, response.text)


async def test_history_rejects_filters_it_does_not_apply(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    url = BASE + "/history/account-groups/" + groups["SALES"]
    for query in ("q=missing", "status=INACTIVE", "as_of=2000-01-01", "code=missing"):
        response = await client.get(url + "?" + query, headers=headers())
        assert response.status_code == 422, (query, response.text)
    response = await client.get(url + "?limit=1&sort=-id", headers=headers())
    assert response.status_code == 200 and len(response.json()["items"]) == 1


async def test_template_evidence_respects_write_denies_and_rolls_back(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await post(client, "/accounting-setup/initialize", {}, status=200)
    for entity, field in [
        ("account_template_installation", "template_key"),
        ("account_template_binding", "object_id"),
        ("accounting_setup", "template_version"),
    ]:
        if entity == "accounting_setup":
            # Isolated fixture: model a legacy setup version so this install
            # actually changes the denied field, rather than testing a no-op.
            with tenant_scope(TENANT):
                async with app.state.session_factory() as db, db.begin():
                    setup = await db.scalar(select(m.AccountingSetup))
                    assert setup is not None
                    setup.template_version = "legacy-test"
        paths = ("template-installations", "template-bindings", "account-groups", "accounts")
        before = {
            path: (await client.get(BASE + "/" + path + "?limit=200", headers=headers())).json()
            for path in paths
        }
        result = await client.post(
            BASE + "/accounting-setup/install",
            json={"business_accounts": False},
            headers=headers(
                policies=[policy(field, access="write", entity="accounting." + entity)]
            ),
        )
        assert result.status_code == 403, (entity, result.text)
        for path in paths:
            after = await client.get(BASE + "/" + path + "?limit=200", headers=headers())
            assert after.status_code == 200, after.text
            assert after.json() == before[path], path
        if entity == "accounting_setup":
            with tenant_scope(TENANT):
                async with app.state.session_factory() as db:
                    setup = await db.scalar(select(m.AccountingSetup))
                    assert setup is not None and setup.template_version == "legacy-test"


async def test_currency_replica_change_is_protected_audited_and_used_currency_is_fixed(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await prepare(client)
    body = {
        "code": "CURRENCY_SYNC",
        "name": "Sync",
        "legal_name": "Sync",
        "country_code": "IN",
        "role": "SUPPLIER",
    }
    denied = await client.post(
        BASE + "/parties/create-with-details",
        json=body,
        headers=headers(
            base_currency="USD",
            policies=[
                policy("base_currency", access="write", entity="accounting.accounting_setup")
            ],
        ),
    )
    assert denied.status_code == 403, denied.text
    await post(client, "/parties/create-with-details", body, h=headers(base_currency="USD"))
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            setup = await db.scalar(select(m.AccountingSetup))
            assert setup is not None and setup.base_currency == "USD" and setup.row_version == 3
            audits = list(
                await db.scalars(
                    select(MasterRevision).where(
                        MasterRevision.entity_type == "accounting_setup",
                        MasterRevision.action == "update",
                    )
                )
            )
            assert [row.changed_fields for row in audits] == [
                ["template_version"],
                ["base_currency"],
            ]
            account = await db.scalar(select(m.Account))
            assert account is not None
            account.used_at = utcnow()
    result = await client.post(
        BASE + "/parties/create-with-details",
        json=body | {"code": "USED_CURRENCY"},
        headers=headers(base_currency="INR"),
    )
    assert result.status_code == 409, result.text
