"""Shared invoice acceptance must refuse over-allocation before posting is requested."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.invoice import InvoicePreviewCommand

from accounting.models.masters import Account
from accounting.models.subledger import OpenItem
from tests.conftest import TENANT
from tests.test_invoice_preview import setup
from tests.test_openings_sources import post_source, source


@pytest.mark.parametrize("advance,payment", [("900.0001", "0"), ("500", "400.0001")])
async def test_invoice_preview_rejects_advance_allocations_above_payable(
    client, app, advance, payment
):
    original, transport, _ = await setup(client, app)
    payload = original.model_dump(mode="json")
    customer_id = payload["invoice"]["party_account_id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cash = await db.scalar(select(Account).where(Account.kind == "CASH"))
            assert cash is not None
    # A real advance receipt is the credit the invoice may draw on; posting it versions the party.
    receipt = await source(client, {"id": customer_id}, str(cash.id), kind="RECEIPT", amount="1000")
    assert (await post_source(client, receipt)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            credit = await db.scalar(select(OpenItem).where(OpenItem.direction == "CREDIT"))
            assert credit is not None
            payload["invoice"]["party_account_version"] = (
                await db.get(Account, uuid.UUID(customer_id))
            ).row_version
            cash = await db.get(Account, cash.id)
    payload["invoice"]["allocations"] = [
        {
            "allocation_key": str(uuid7()),
            "debt": {"line_key": str(original.invoice.party_line_key)},
            "credit": {"item_id": str(uuid7())},
            "currency": "INR",
            "amount": advance,
        }
    ]
    if payment != "0":
        payload["invoice"]["tenders"] = [
            {
                "account_id": str(cash.id),
                "account_version": cash.row_version,
                "tender": {
                    "tender_key": str(uuid7()),
                    "line_key": str(uuid7()),
                    "mode": "CASH",
                    "amount": payment,
                    "currency": "INR",
                },
            }
        ]
    with pytest.raises(httpx.HTTPStatusError) as refused:
        await transport.preview(InvoicePreviewCommand.model_validate(payload))
    assert refused.value.response.status_code == 422
    assert "settlements exceed" in refused.value.response.text
    payload["invoice"]["allocations"][0]["amount"] = "900.0000"
    payload["invoice"]["tenders"] = []
    with pytest.raises(httpx.HTTPStatusError) as unknown:
        await transport.preview(InvoicePreviewCommand.model_validate(payload))
    assert unknown.value.response.status_code == 422
    assert "does not exist" in unknown.value.response.text
    payload["invoice"]["allocations"][0]["credit"] = {"item_id": str(credit.id)}
    accepted = await transport.preview(InvoicePreviewCommand.model_validate(payload))
    assert str(accepted.payable) == "900.0000"
