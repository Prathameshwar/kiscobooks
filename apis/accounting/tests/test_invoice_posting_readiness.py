"""A calculation that posting would refuse is never offered for acceptance (review 2026-11-02)."""

import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import insert, select, update

from accounting.domain.invoice_readiness import posting_problem
from accounting.models.masters import Account, PartyRole
from tests.conftest import TENANT
from tests.test_invoice_preview import setup

DOCUMENT = dt.date(2026, 4, 2)


def calculated(*, payable="100", rounding="0", taxes=(), credit_state="ELIGIBLE", mappings=()):
    line = uuid7()
    return SimpleNamespace(
        payable=Decimal(payable),
        rounding=Decimal(rounding),
        lines=[SimpleNamespace(key=line, taxes=list(taxes))],
        tax_evidence=[
            {
                "line_key": str(line),
                "credit_state": credit_state,
                "posting_mappings": list(mappings),
            }
        ],
    )


def invoice(*, due=DOCUMENT, rounding_account=None):
    return SimpleNamespace(due_date=due, rounding_account_id=rounding_account)


def test_ready_untaxed_bill_has_no_problem():
    assert posting_problem("PURCHASE", DOCUMENT, invoice(), calculated()) is None


@pytest.mark.parametrize(
    "bill,result,message",
    [
        (invoice(), calculated(payable="0"), "positive consideration"),
        (invoice(due=DOCUMENT - dt.timedelta(days=1)), calculated(), "due date"),
        (invoice(), calculated(rounding="-0.0100"), "rounding requires"),
        (
            invoice(),
            calculated(
                taxes=[SimpleNamespace(code="IGST", supplier_charged=False)],
                mappings=[{"purpose": "RCM_IGST", "ready": False}],
            ),
            "mapping",
        ),
        (
            invoice(),
            calculated(
                taxes=[SimpleNamespace(code="CGST", supplier_charged=True)],
                credit_state="PENDING_EVIDENCE",
            ),
            "mapping",
        ),
    ],
)
def test_posting_refusals_are_known_at_calculation(bill, result, message):
    assert message in posting_problem("PURCHASE", DOCUMENT, bill, result)


def test_rounding_with_its_account_and_ready_mappings_are_postable():
    bill = invoice(rounding_account=uuid7())
    result = calculated(
        rounding="0.0100",
        taxes=[SimpleNamespace(code="IGST", supplier_charged=False)],
        mappings=[{"purpose": "RCM_IGST", "ready": True}],
    )
    assert posting_problem("PURCHASE", DOCUMENT, bill, result) is None


async def purchase(client, app):
    command, transport, supplier = await setup(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            expense = await db.scalar(select(Account).where(Account.code == "NONSTOCK_PURCHASES"))
            body = command.invoice.model_dump(mode="json")
            body["party_account_id"] = supplier["id"]
            body["party_account_version"] = supplier["row_version"]
            body["supplies"][0]["account_id"] = str(expense.id)
            body["supplies"][0]["account_version"] = expense.row_version
            body["components"] = []
    return command.model_copy(update={"kind": "PURCHASE"}), transport, supplier, body


def refused(error: pytest.ExceptionInfo[httpx.HTTPStatusError], text: str) -> None:
    assert error.value.response.status_code in {409, 422}, error.value.response.text
    assert text in error.value.response.text


async def test_preview_refuses_zero_payable_and_early_due_date(client, app):
    command, transport, _, body = await purchase(client, app)
    accepted = await transport.preview(
        command.model_copy(update={"invoice": type(command.invoice).model_validate(body)})
    )
    assert accepted.payable == 1000
    zero = body | {"supplies": [body["supplies"][0] | {"amount": "0"}]}
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(
            command.model_copy(update={"invoice": type(command.invoice).model_validate(zero)})
        )
    refused(error, "positive consideration")
    early = body | {"due_date": "2026-04-01"}
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(
            command.model_copy(update={"invoice": type(command.invoice).model_validate(early)})
        )
    refused(error, "due date")


async def test_preview_refuses_a_supplier_with_two_ledgers_or_an_inactive_role(client, app):
    command, transport, supplier, body = await purchase(client, app)
    request = command.model_copy(update={"invoice": type(command.invoice).model_validate(body)})
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            ledger = await db.get(Account, uuid.UUID(supplier["id"]))
            values = {
                column.key: getattr(ledger, column.key)
                for column in Account.__table__.columns
                if column.key not in {"id", "code", "name"}
                and not column.computed
                and getattr(ledger, column.key) is not None
            }
            # A legacy second ledger for the same supplier role (created before PL-D03).
            with unfiltered():
                await db.execute(
                    insert(Account).values(
                        values | {"id": uuid7(), "code": "LEGACY-SUPP", "name": "Legacy supplier"}
                    )
                )
            await db.commit()
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(request)
    refused(error, "more than one ledger")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            with unfiltered():
                await db.execute(
                    update(Account).where(Account.code == "LEGACY-SUPP").values(status="INACTIVE")
                )
                await db.execute(
                    update(PartyRole)
                    .where(PartyRole.party_id == ledger.party_id, PartyRole.role == "SUPPLIER")
                    .values(status="INACTIVE")
                )
            await db.commit()
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.preview(request)
    refused(error, "role for this invoice is not active")
