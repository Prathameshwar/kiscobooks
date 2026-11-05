"""A company created with inventory gets its standard stock accounts with its books (2026-11-03)."""

import datetime as dt
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.masters import Account, AccountGroup, AccountHead
from accounting.models.stock import StockAccountPolicy
from accounting.tasks.stock_policy import ACCOUNT_NATURES, STANDARD_ACCOUNTS
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import BASE, finance_headers
from tests.test_masters import prepare

CODES = set(STANDARD_ACCOUNTS.values())


async def books(client: httpx.AsyncClient, *, features: set[str], key: str | None = None) -> None:
    result = await client.post(
        BASE + "/financial-setup/initialize",
        json={},
        headers=finance_headers(features=features, key=key or str(uuid.uuid4())),
    )
    assert result.status_code == 200, result.text


async def stock_state(app: FastAPI) -> tuple[list[StockAccountPolicy], dict[str, tuple[str, str]]]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            policies = list(await db.scalars(select(StockAccountPolicy)))
            rows = await db.execute(
                select(Account.code, Account.status, AccountHead.nature)
                .join(AccountGroup, AccountGroup.id == Account.group_id)
                .join(AccountHead, AccountHead.id == AccountGroup.head_id)
                .where(Account.company_id == COMPANY, Account.code.in_(CODES))
            )
            return policies, {code: (status, nature) for code, status, nature in rows}


async def test_books_with_inventory_map_the_five_standard_stock_accounts_from_books_begin(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    await books(client, features={"inventory"})
    policies, accounts = await stock_state(app)
    assert len(policies) == 1
    policy = policies[0]
    assert policy.valid_from == dt.date(2026, 4, 1) and policy.valid_to is None
    assert accounts == {
        STANDARD_ACCOUNTS[field]: ("ACTIVE", nature) for field, nature in ACCOUNT_NATURES.items()
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            mapped = {
                field: await db.scalar(
                    select(Account.code).where(Account.id == getattr(policy, field))
                )
                for field in ACCOUNT_NATURES
            }
            published = await db.scalar(
                select(func.count(Outbox.id)).where(
                    Outbox.event_type == "accounting.stock_account_policy.publish"
                )
            )
    assert mapped == STANDARD_ACCOUNTS
    assert published == 1
    # The read API names the same policy the stock screens and purchase bills use.
    listed = await client.get(
        BASE + "/stock/account-policies?limit=50",
        headers=finance_headers(permissions={"accounting.stock.read"}, features={"inventory"}),
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [str(policy.id)]


async def test_books_without_inventory_add_no_stock_accounts(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    await books(client, features=set())
    assert await stock_state(app) == ([], {})


async def test_a_replayed_or_repeated_setup_keeps_one_policy(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    key = str(uuid.uuid4())
    await books(client, features={"inventory"}, key=key)
    await books(client, features={"inventory"}, key=key)
    await books(client, features={"inventory"})
    policies, accounts = await stock_state(app)
    assert len(policies) == 1 and len(accounts) == 5


async def test_books_set_up_before_inventory_catch_up_when_set_up_again(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await prepare(client)
    await books(client, features=set())
    await books(client, features={"inventory"})
    policies, accounts = await stock_state(app)
    assert len(policies) == 1 and len(accounts) == 5


async def test_a_code_owned_by_another_account_never_blocks_the_books_or_half_creates_them(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    taken = await client.post(
        BASE + "/accounts",
        json={
            "code": "STOCK_VARIANCE",
            "name": "My variance",
            "group_id": groups["INDIRECT_EXPENSES"],
            "kind": "GENERAL",
        },
        headers=finance_headers(),
    )
    assert taken.status_code == 201, taken.text
    await books(client, features={"inventory"})
    policies, accounts = await stock_state(app)
    assert policies == []
    # Only the account the person made: none of the standard four were left behind.
    assert set(accounts) == {"STOCK_VARIANCE"}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "accounting.stock_account_policy.publish"
                    )
                )
                == 0
            )
