from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from accounting.models.fiscal import FiscalYear
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_voucher_money import money_command


async def test_readiness_checks_owner_reconciliation_and_pending_confirmations(client, app):
    original, period, owner = await journal_setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            year_id = await db.scalar(select(FiscalYear.id))
    path = BASE + f"/fiscal-years/{year_id}/readiness"
    ready = await client.get(path, headers=ledger_headers())
    assert ready.status_code == 200 and ready.json()["ready_for_posting"]
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=ledger_headers(permissions=set()))).status_code == 403
    other = uuid7()
    assert (
        await client.get(
            path.replace(str(COMPANY), str(other)), headers=ledger_headers(company=other)
        )
    ).status_code == 403
    body = await money_command(app, original, period)
    assert (
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    ).outcome == "COMMITTED"
    pending = await client.get(path, headers=ledger_headers())
    assert pending.status_code == 200
    assert pending.json()["close_ready"] is False
    assert "OWNER_CLOSE_CHECKS_PENDING" in pending.json()["close_blockers"]
