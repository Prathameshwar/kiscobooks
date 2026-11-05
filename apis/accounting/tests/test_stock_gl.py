"""Inventory GL accounts cannot bypass quantity/value authority."""

from tests.test_ledger_api import BASE, journal_setup, ledger_headers
from tests.test_stock_effects import configure


async def test_manual_inventory_journal_cannot_be_prepared(client, app):
    body, period, authority = await journal_setup(client, app)
    mapping = await configure(app)
    body["lines"][0]["account_id"] = str(mapping["inventory_account_id"])
    created = await client.post(BASE + "/journals", json=body, headers=ledger_headers())
    assert created.status_code == 201, created.text
    row = created.json()
    denied = await client.post(
        BASE + "/journals/" + row["id"] + "/post",
        json={"expected_version": row["row_version"]},
        headers=ledger_headers(),
    )
    assert denied.status_code == 409, denied.text
    assert "stock" in denied.json()["error"]["message"].lower()
    assert authority.calls == 0


async def test_financial_inventory_opening_cannot_bypass_finalized_physical_cutover(client, app):
    import datetime as dt

    import pytest
    from billing_platform.db import tenant_scope
    from billing_platform.errors import ConflictError

    from accounting.models.ledger import Journal, JournalLine
    from accounting.tasks.stock_gl import guard_journal
    from tests.conftest import COMPANY, TENANT

    await journal_setup(client, app)
    mapping = await configure(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            with pytest.raises(ConflictError, match="stock openings"):
                await guard_journal(
                    db,
                    Journal(company_id=COMPANY, kind="OPENING", posting_date=dt.date(2026, 4, 1)),
                    [JournalLine(account_id=mapping["inventory_account_id"])],
                )
