"""Opening lookup uses posted native journals and exact remaining bridge value."""

from decimal import Decimal

from billing_platform.db import tenant_scope
from sqlalchemy import select

from accounting.api.auth import delegated_access
from accounting.models.ledger import JournalLine
from accounting.tasks.stock_effects import bridge_opening
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_ledger_api import BASE, journal_setup, ledger_headers
from tests.test_openings_sources import post_source
from tests.test_stock_effects import authority, configure
from tests.test_stock_ledger import item, ledger, line, warehouse


async def test_opening_options_are_authorized_posted_unreversed_and_net_of_claims(app, client):
    body, _, _ = await journal_setup(client, app, zero_opening=False)
    accounts = await configure(app, finalize_zero=False)
    body["lines"][0]["account_id"] = str(accounts["inventory_account_id"])
    body["lines"][1]["account_id"] = str(accounts["opening_offset_account_id"])
    created = await client.post(
        BASE + "/opening-batches",
        json={
            "posting_date": "2026-04-01",
            "description": "Inventory opening",
            "lines": body["lines"],
        },
        headers=ledger_headers(),
    )
    assert created.status_code == 201, created.text
    path = BASE + "/stock/opening-lines?stock_date=2026-04-01"
    allowed = ledger_headers(
        permissions={"accounting.stock.read", "ledger.read"}, features={"inventory"}
    )
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=ledger_headers())).status_code == 403
    assert (await client.get(path, headers=allowed)).json()["items"] == []
    posted = await post_source(client, created.json())
    assert posted.status_code == 200, posted.text
    page = await client.get(path, headers=allowed)
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 1
    choice = page.json()["items"][0]
    assert Decimal(choice["remaining_value"]) == Decimal("100.25")
    assert choice["currency"] == "INR" and choice["number"]
    assert (
        await client.get(path.replace("2026-04-01", "2026-04-02"), headers=allowed)
    ).status_code == 422
    denied = ledger_headers(
        permissions={"accounting.stock.read", "ledger.read"},
        features={"inventory"},
        policies=[
            {
                "entity_type": "accounting.journal_line",
                "field_key": "base_amount",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ],
    )
    assert (await client.get(path, headers=denied)).status_code == 403
    from accounting.models.stock import StockAccountPolicy

    proof = authority()
    current = delegated_access(
        proof, SECRET.encode(), tenant_id=TENANT, company_id=COMPANY, actor_user_id=USER
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            product, location = item(), warehouse()
            owner = await ledger(db, action="OPENING")
            received = await owner.receive(
                line(product, location, 1), product, location, value=Decimal("12.50")
            )
            opening_line = await db.scalar(
                select(JournalLine).where(
                    JournalLine.account_id == accounts["inventory_account_id"]
                )
            )
            policy = await db.scalar(select(StockAccountPolicy))
            await bridge_opening(
                owner, current, received, opening_line.id, Decimal("12.50"), policy
            )
    following = await client.get(path, headers=allowed)
    assert following.status_code == 200, following.text
    assert Decimal(following.json()["items"][0]["remaining_value"]) == Decimal("87.75")
