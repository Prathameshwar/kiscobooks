"""Credit assessment guards exposure it can bound and never demands access it does not use."""

import logging
from decimal import Decimal

from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.contracts import DelegatedAuthority
from voucher_execution.transport import command_digest

from accounting.models.masters import Account
from accounting.models.subledger import OpenItem
from accounting.models.voucher_money import VoucherMoneyIntent
from tests.conftest import SECRET, TENANT
from tests.test_credit_api import policy
from tests.test_invoice_execution import fresh_invoice, invoice_command, run
from tests.test_invoice_preview import connection
from tests.test_ledger_api import LEDGER_PERMISSIONS, ledger_headers
from tests.test_purchase_allocation_targets import world

LOGGER = "accounting.voucher_execution"


def poster(*, without=(), features=None):
    """A delegated actor holding vouchers.post and every ledger permission except `without`."""
    permissions = (LEDGER_PERMISSIONS - set(without)) | {"vouchers.post", "vouchers.reverse"}
    values = ledger_headers(permissions=permissions, **({"features": features} if features else {}))
    company = verify_company_context(
        values["X-Company-Context"], values["X-Company-Signature"], SECRET.encode()
    )
    context, signature = sign_company_context(
        company.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return DelegatedAuthority(
        actor_context=values["X-Actor-Context"],
        actor_signature=values["X-Actor-Signature"],
        company_context=context,
        company_signature=signature,
    )


def as_actor(command, authority, *, fresh_identity=False):
    changes = {"authority": authority}
    if fresh_identity:
        changes |= {"operation_id": uuid7(), "execution_id": uuid7()}
    updated = command.model_copy(update=changes)
    return updated.model_copy(update={"request_hash": command_digest(updated)})


async def two_line_purchase(client, app, *, amount="1000", supplier_limit=None):
    template, invoice, transport = await world(client, app)
    if supplier_limit is not None:
        await supplier_policy(client, app, limit=supplier_limit)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rent = await db.scalar(select(Account).where(Account.code == "RENT"))
    invoice["supplies"][0]["amount"] = str(Decimal(amount) * Decimal("0.7"))
    invoice["supplies"].append(
        dict(
            invoice["supplies"][0],
            line_key=str(uuid7()),
            account_id=str(rent.id),
            account_version=rent.row_version,
            description="Office rent",
            amount=str(Decimal(amount) * Decimal("0.3")),
        )
    )
    invoice["allocations"] = []
    return await fresh_invoice(app, template, transport, kind="PURCHASE", invoice=invoice)


async def log_of(app, command, caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        result = await run(app, command)
    return result, caplog.text


async def test_plain_purchase_posts_for_a_poster_without_credit_read(client, app, caplog):
    command = await two_line_purchase(client, app)
    result, logged = await log_of(
        app, as_actor(command, poster(without={"accounting.credit.read"})), caplog
    )
    assert "PermissionDeniedError" not in logged, logged
    assert result.outcome == "COMMITTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            bill = await db.scalar(select(OpenItem))
            assert bill.direction == "DEBT" and bill.amount == Decimal("1000")
            assert await db.scalar(select(func.count(OpenItem.id))) == 1


async def plain_sale(client, app):
    template = await invoice_command(client, app, kind="SALES")
    transport = connection(client, app)
    invoice = dict(template.source_payload["invoice"]) | {
        "components": [],
        "accepted_calculation_hash": None,
    }
    return await fresh_invoice(app, template, transport, kind="SALES", invoice=invoice)


async def test_sales_debit_posts_without_credit_read_while_credit_limits_are_off(
    client, app, caplog
):
    """With the feature off every assessment ALLOWs, so posting must not demand its inputs."""
    command = await plain_sale(client, app)
    result, logged = await log_of(
        app, as_actor(command, poster(without={"accounting.credit.read"})), caplog
    )
    assert "PermissionDeniedError" not in logged, logged
    assert result.outcome == "COMMITTED", result


async def test_sales_debit_requires_credit_read_once_credit_limits_are_on(client, app, caplog):
    command = await plain_sale(client, app)
    denied = as_actor(
        command, poster(without={"accounting.credit.read"}, features={"credit_limits"})
    )
    result, logged = await log_of(app, denied, caplog)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    assert '"error_type":"PermissionDeniedError"' in logged
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherMoneyIntent.id))) == 0
            assert await db.scalar(select(func.count(OpenItem.id))) == 0
    allowed = as_actor(command, poster(features={"credit_limits"}), fresh_identity=True)
    assert (await run(app, allowed)).outcome == "COMMITTED"


async def supplier_policy(client, app, *, limit):
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            party_id = (await db.scalar(select(Account).where(Account.code == "SUPPLIER"))).party_id
    await policy(
        client, {"id": str(party_id)}, role="SUPPLIER", limit_amount=limit, enforcement="BLOCK"
    )


async def test_supplier_credit_limit_still_blocks_a_purchase_it_would_exceed(client, app, caplog):
    """A configured supplier limit is a money control: the fix must never switch it off."""
    command = await two_line_purchase(client, app, supplier_limit="500")
    full = as_actor(command, poster(features={"credit_limits"}))
    result, logged = await log_of(app, full, caplog)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    assert '"error_type":"ConflictError"' in logged
    # Without credit.read the control cannot be evaluated, so it fails closed instead of posting.
    caplog.clear()
    blind = as_actor(
        command,
        poster(without={"accounting.credit.read"}, features={"credit_limits"}),
        fresh_identity=True,
    )
    result, logged = await log_of(app, blind, caplog)
    assert result.outcome == "REJECTED" and result.rejection_code == "CONTENT_REJECTED"
    assert '"error_type":"PermissionDeniedError"' in logged
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(OpenItem.id))) == 0


async def test_supplier_credit_limit_admits_a_purchase_within_it(client, app):
    command = await two_line_purchase(client, app, supplier_limit="1500")
    result = await run(app, as_actor(command, poster(features={"credit_limits"})))
    assert result.outcome == "COMMITTED", result
