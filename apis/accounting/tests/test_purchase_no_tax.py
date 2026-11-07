"""A declared no-tax account purchase does not need an expense tax default."""

import hashlib
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.invoice import InvoicePreviewCommand
from voucher_execution.transport import command_digest

from accounting.models.fiscal import FiscalPeriod
from accounting.models.invoice import InvoiceRecord, InvoiceTaxComponent
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, AccountTaxDefault
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_invoice_preview import authority, connection, setup
from tests.test_openings_sources import party_accounts
from tests.test_voucher_execution import command
from tests.test_voucher_money import delegated
from tests.test_voucher_tax import MH, world


async def no_tax_purchase(client, app):
    original, transport, supplier = await setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            expense = await db.scalar(select(Account).where(Account.code == "NONSTOCK_PURCHASES"))
            assert await db.scalar(select(func.count(AccountTaxDefault.id))) == 0
    invoice = original.invoice.model_dump(mode="json")
    invoice.update(
        party_account_id=supplier["id"], party_account_version=supplier["row_version"],
        components=[], bill_reference="NO-TAX-TEA-500",
    )
    invoice["supplies"][0].update(
        account_id=str(expense.id), account_version=expense.row_version,
        supply_kind="ACCOUNT", description="Tea expense, supplier charged no tax", amount="500",
    )
    body = original.model_dump(mode="json")
    body.update(kind="PURCHASE", invoice=invoice, authority=authority(registrations=[MH])[0])
    return InvoicePreviewCommand.model_validate(body), transport


async def test_registered_company_previews_no_tax_purchase_without_classification(client, app):
    body, transport = await no_tax_purchase(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = await db.scalar(select(func.count(Journal.id)))
    result = await transport.preview(body)
    assert result.payable == Decimal("500") and result.tax_total == Decimal("0")
    assert isinstance(result.payable, Decimal)
    assert result.lines[0].taxes == ()
    assert result.tax_evidence[0]["default_id"] is None
    assert result.tax_evidence[0]["credit_state"] == "NOT_APPLICABLE"
    assert await transport.preview(body) == result
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == before
            assert await db.scalar(select(func.count(AccountTaxDefault.id))) == 0


@pytest.mark.parametrize("kind,supply", [("SALES", "ACCOUNT"), ("PURCHASE", "SERVICE")])
async def test_missing_classification_exception_is_only_for_purchase_account_lines(
    client, app, kind, supply
):
    body, transport = await no_tax_purchase(client, app)
    payload = body.model_dump(mode="json")
    if kind == "SALES":
        customer, income = await existing_sales_accounts(app)
        payload["invoice"].update(
            party_account_id=str(customer.id),
            party_account_version=customer.row_version,
        )
        payload["invoice"]["supplies"][0].update(
            account_id=str(income.id),
            account_version=income.row_version,
        )
    payload["kind"] = kind
    payload["invoice"]["supplies"][0]["supply_kind"] = supply
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(InvoicePreviewCommand.model_validate(payload))
    assert error.value.response.status_code == 422
    assert "statutory profile" in error.value.response.text


async def existing_sales_accounts(app):
    # Read the seeded customer/income, without provisioning a second company setup.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            customer = await db.scalar(select(Account).where(Account.party_role == "CUSTOMER"))
            income = await db.scalar(select(Account).where(Account.code == "SALES_REVENUE"))
    return customer, income


async def test_no_tax_choice_cannot_override_an_explicit_taxable_default(client, app):
    data = await world(client, app)
    _, _, supplier = await party_accounts(client)
    delegated_preview, company = authority(registrations=[MH])
    body = InvoicePreviewCommand.model_validate({
        "tenant_id": TENANT, "company_id": COMPANY, "actor_user_id": USER,
        "authority": delegated_preview, "kind": "PURCHASE", "currency": "INR",
        "document_date": "2026-04-02", "posting_date": "2026-04-02",
        "configuration_hash": "a" * 64,
        "company_configuration_hash": company.finance.configuration_hash, "policy": {},
        "invoice": {
            "party_line_key": uuid7(), "party_account_id": supplier["id"],
            "party_account_version": supplier["row_version"], "bill_reference": "TAXABLE-GUARD",
            "due_date": "2026-04-30", "tax": {"profile": "UNTAXED_ACCOUNT"},
            "supplies": [{"line_key": uuid7(), "account_id": data["rcm"]["id"],
                "account_version": data["rcm"]["row_version"], "supply_kind": "ACCOUNT",
                "description": "Explicit taxable default", "amount": "500"}],
        },
    })
    with pytest.raises(httpx.HTTPStatusError) as error:
        await connection(client, app).preview(body)
    assert error.value.response.status_code == 422
    assert "statutory profile" in error.value.response.text


async def test_registered_no_tax_purchase_posts_balanced_once_without_tax_or_defaults(client, app):
    from accounting.tasks.voucher_money_execution import dispatch

    preview, transport = await no_tax_purchase(client, app)
    evidence = {"kind": "PURCHASE", "profile": "STANDARD",
        "company_configuration_hash": preview.company_configuration_hash,
        "policy": {"invoice": preview.policy.model_dump(mode="json")}}
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    preview = preview.model_copy(update={"configuration_hash": digest})
    calculated = await transport.preview(preview)
    payload = {"mode": "ACCOUNTS", "currency": "INR", "document_date": "2026-04-02",
        "posting_date": "2026-04-02", "lines": [],
        "invoice": preview.invoice.model_dump(mode="json") | {
            "accepted_calculation_hash": calculated.calculation_hash}}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            period = await db.scalar(select(FiscalPeriod).where(FiscalPeriod.status == "OPEN"))
            before = await db.scalar(select(func.count(Journal.id)))
    request = command({"id": str(period.id), "row_version": period.row_version},
        protocol_version=2, kind="PURCHASE", source_payload=payload,
        content_hash=hashlib.sha256(canonical_json(payload)).hexdigest(),
        configuration_hash=digest, configuration_evidence=evidence | {"digest": digest},
        authority=delegated(registrations=[MH]))
    request = request.model_copy(update={"request_hash": command_digest(request)})
    async def post():
        return await dispatch(app.state.session_factory, request, secret=SECRET.encode(),
            client=app.state.posting_client, invoices_enabled=True)
    posted = await post()
    assert posted.outcome == "COMMITTED", posted
    assert await post() == posted
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Journal.id))) == before + 1
            assert await db.scalar(select(func.count(InvoiceRecord.id))) == 1
            assert await db.scalar(select(func.count(InvoiceTaxComponent.id))) == 0
            assert await db.scalar(select(func.count(AccountTaxDefault.id))) == 0
            journal = await db.scalar(select(Journal).where(Journal.kind == "VOUCHER"))
            lines = list(await db.scalars(
                select(JournalLine).where(JournalLine.journal_id == journal.id)
            ))
            assert sum(line.amount for line in lines if line.side == "DEBIT") == Decimal("500")
            assert sum(line.amount for line in lines if line.side == "CREDIT") == Decimal("500")
