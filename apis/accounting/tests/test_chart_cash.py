"""Every company's chart can take cash: Cash in Cash-in-hand is ensured at setup (2026-11-03)."""

from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.masters import Account, AccountGroup, AccountTemplateInstallation
from accounting.tasks import templates
from tests.conftest import COMPANY, TENANT
from tests.test_masters import BASE, activate, headers, post


async def initialize(client: httpx.AsyncClient) -> None:
    await post(client, "/accounting-setup/initialize", {}, status=200)


async def without_chart(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> str:
    """A company set up before the starter chart existed: heads only. Returns its asset head."""

    async def skipped(*_: Any, **__: Any) -> None:
        return None

    with monkeypatch.context() as patch:
        patch.setattr(templates, "install_content", skipped)
        await initialize(client)
    heads = (await client.get(BASE + "/account-heads", headers=headers())).json()["items"]
    return next(row["id"] for row in heads if row["code"] == "ASSET")


async def authored_group(client: httpx.AsyncClient, head: str, code: str) -> dict[str, Any]:
    group = await post(
        client, "/account-groups", {"code": code, "name": code.title(), "head_id": head}
    )
    return await activate(client, "/account-groups", group)


async def cash(app: FastAPI) -> list[tuple[str, str, str | None, str, str | None]]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            parent = select(AccountGroup.code).where(AccountGroup.id == AccountGroup.parent_id)
            rows = await db.execute(
                select(
                    Account.code,
                    Account.status,
                    Account.system_key,
                    AccountGroup.name,
                    AccountGroup.parent_id,
                )
                .join(AccountGroup, AccountGroup.id == Account.group_id)
                .where(Account.company_id == COMPANY, Account.kind == "CASH")
            )
            result = []
            for code, status, key, group, parent_id in rows:
                parent = await db.scalar(
                    select(AccountGroup.code).where(AccountGroup.id == parent_id)
                )
                result.append((code, status, key, group, parent))
            return result


async def test_a_new_company_has_one_cash_account_in_cash_in_hand(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await initialize(client)
    await initialize(client)
    assert await cash(app) == [
        ("CASH_MAIN", "ACTIVE", "account.CASH_MAIN", "Cash-in-hand", "CURRENT_ASSETS")
    ]


async def test_a_chart_without_cash_gets_cash_and_its_groups_when_set_up_again(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = await without_chart(client, monkeypatch)
    await authored_group(client, head, "MY_ASSETS")
    await initialize(client)
    assert await cash(app) == [
        ("CASH_MAIN", "ACTIVE", "account.CASH_MAIN", "Cash-in-hand", "CURRENT_ASSETS")
    ]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            keys = set(await db.scalars(select(AccountTemplateInstallation.template_key)))
            groups = set(await db.scalars(select(AccountGroup.code)))
    # Only fixed cash/high-priority defaults are added; the authored group stays intact.
    assert keys == {"cash", "defaults.business-high"}
    assert groups == {
        "MY_ASSETS",
        "CURRENT_ASSETS",
        "CASH",
        "INDIRECT_EXPENSES",
        "INDIRECT_INCOME",
        "PURCHASES",
        "DIRECT_EXPENSES",
    }


async def test_a_chart_with_its_own_cash_account_is_left_alone(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = await without_chart(client, monkeypatch)
    group = await authored_group(client, head, "TILLS")
    till = await post(
        client,
        "/accounts",
        {"code": "TILL", "name": "Shop till", "group_id": group["id"], "kind": "CASH"},
    )
    await initialize(client)
    found = await cash(app)
    assert [row[0] for row in found] == ["TILL"] and till["kind"] == "CASH"


async def test_a_code_owned_by_another_group_never_fails_setup(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = await without_chart(client, monkeypatch)
    await authored_group(client, head, "CASH")
    await initialize(client)
    assert await cash(app) == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert set(await db.scalars(select(AccountTemplateInstallation.template_key))) == {
                "defaults.business-high"
            }
