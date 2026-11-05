"""Money and audit remain atomic under malformed inputs, denied fields and competing work."""

import asyncio

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.models.ledger import DocumentSequence, Journal
from accounting.models.subledger import Allocation, OpenItem
from accounting.models.voucher_money import BankInstrument, VoucherMoneyIntent
from accounting.tasks.journal_posting import PostingDependencyError
from accounting.tasks.voucher_money_execution import dispatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_money_profiles import revise
from tests.test_openings_sources import party_accounts, post_source, source
from tests.test_voucher_money import delegated, money_command


@pytest.mark.parametrize(
    "case", ["tracking", "amount", "field_write", "field_read", "namespace", "disabled"]
)
async def test_owner_rejections_leave_no_posted_money(client, app, case):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    financial = body.source_payload["financial"]
    if case == "tracking":
        financial["accounts"][1]["tracking"] = "ADVANCE"
    if case == "amount":
        financial["accounts"][1]["amount"] = "1.23456"
    if case in {"tracking", "amount"}:
        body = revise(body, financial=financial)
    if case.startswith("field_"):
        body = body.model_copy(
            update={
                "authority": delegated(
                    policies=[
                        {
                            "entity_type": "accounting.account"
                            if case == "field_read"
                            else "accounting.journal_line",
                            "field_key": "currency" if case == "field_read" else "amount",
                            "effect": "deny",
                            "access": "write" if case == "field_write" else "read",
                            "scope_type": "company",
                            "scope_id": str(COMPANY),
                        }
                    ]
                )
            }
        )
    if case == "namespace":
        from billing_platform.company_context import sign_company_context, verify_company_context

        authority = body.authority
        context = verify_company_context(
            authority.company_context, authority.company_signature, SECRET.encode()
        )
        raw, signature = sign_company_context(
            context.model_copy(update={"policy_namespaces": frozenset({"vouchers"})}),
            SECRET.encode(),
        )
        body = body.model_copy(
            update={
                "authority": authority.model_copy(
                    update={"company_context": raw, "company_signature": signature}
                )
            }
        )
    body = body.model_copy(update={"request_hash": command_digest(body)})
    result = await dispatch(
        app.state.session_factory,
        body,
        secret=SECRET.encode(),
        client=owner,
        enabled=case != "disabled",
    )
    assert result.outcome == "REJECTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 0
            )
            assert await db.scalar(select(func.count(BankInstrument.id))) == 0
            assert await db.scalar(select(func.count(DocumentSequence.id))) == 0


async def test_multi_bill_failure_rolls_back_journal_open_item_allocation_and_bank_evidence(
    client, app
):
    original, period, owner = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    invoice = await source(client, customer, original["lines"][1]["account_id"])
    assert (await post_source(client, invoice)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            debt = await db.scalar(select(OpenItem))
            debt_id = str(debt.id)
    original["lines"][1]["account_id"] = customer["id"]
    body = await money_command(app, original, period)
    financial = body.source_payload["financial"]
    financial["accounts"][1]["tracking"] = "ON_ACCOUNT"
    financial["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"item_id": debt_id},
            "credit": {"line_key": financial["accounts"][1]["line_key"]},
            "currency": "INR",
            "amount": "60",
        }
        for _ in range(2)
    ]
    body = revise(body, kind="RECEIPT", financial=financial)
    result = await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    assert result.outcome == "REJECTED", result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 1
            )
            assert await db.scalar(select(func.count(OpenItem.id))) == 1
            assert await db.scalar(select(func.count(Allocation.id))) == 0
            assert await db.scalar(select(func.count(BankInstrument.id))) == 0
            assert (await db.scalar(select(VoucherMoneyIntent))).status == "CANCELLED"


async def test_disabled_profile_cancels_prepared_work_after_dependency_outage(client, app):
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    owner.fail = True
    with pytest.raises(PostingDependencyError):
        await dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
    result = await dispatch(
        app.state.session_factory, body, secret=SECRET.encode(), client=owner, enabled=False
    )
    assert result.outcome == "REJECTED" and result.rejection_code == "UNSUPPORTED_PROFILE"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (await db.scalar(select(VoucherMoneyIntent))).status == "CANCELLED"
            assert (await db.scalar(select(Journal))).status == "VOID"


@pytest.mark.mysql
async def test_duplicate_native_deliveries_commit_one_number_and_effect_set(client, app):
    if app.state.engine.dialect.name != "mysql":
        pytest.skip("requires native row locks")
    original, period, owner = await journal_setup(client, app)
    body = await money_command(app, original, period)
    outcomes = await asyncio.gather(
        *(
            dispatch(app.state.session_factory, body, secret=SECRET.encode(), client=owner)
            for _ in range(2)
        )
    )
    assert outcomes[0] == outcomes[1] and outcomes[0].outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == 1
            assert (await db.scalar(select(DocumentSequence))).next_value == 2
            assert await db.scalar(select(func.count(BankInstrument.id))) == 1
