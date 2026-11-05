"""Print reads reuse committed owner facts without recalculating posted money."""

from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.printing import PurchasePrintCommand

from accounting.models.masters import Account
from accounting.tasks.invoice_execution import request_for
from tests.conftest import COMPANY, TENANT
from tests.test_invoice_execution import invoice_command, run
from tests.test_invoice_preview import authority, connection


async def test_purchase_print_preview_then_immutable_posted_facts_and_field_denies(client, app):
    execution = await invoice_command(client, app, kind="PURCHASE")
    transport = connection(client, app)
    preview = request_for(execution).model_copy(update={"authority": authority()[0]})
    command = PurchasePrintCommand(
        preview=preview, revision_id=execution.revision_id, require_posted=False
    )
    draft = await transport.purchase_print(command)
    assert draft.source == "PREVIEW" and isinstance(draft.calculation.payable, Decimal)
    result = await run(app, execution)
    assert result.outcome == "COMMITTED", result
    posted = command.model_copy(update={"require_posted": True})
    original = await transport.purchase_print(posted)
    assert original.source == "POSTED"
    assert original.calculation.model_dump(exclude={"allocations", "tax_evidence"}) == (
        draft.calculation.model_dump(exclude={"allocations", "tax_evidence"})
    )
    # Master version drift breaks a fresh calculation, but cannot alter a posted print.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            account = await db.scalar(select(Account).where(Account.code == "NONSTOCK_PURCHASES"))
            account.row_version += 1
    assert await transport.purchase_print(posted) == original
    denied, _ = authority(
        policies=[
            {
                "entity_type": "accounting.invoice_record",
                "field_key": "payable",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.purchase_print(
            posted.model_copy(
                update={
                    "preview": preview.model_copy(update={"authority": denied}),
                }
            )
        )
    assert error.value.response.status_code == 403
    with pytest.raises(httpx.HTTPStatusError) as error:
        await transport.purchase_print(posted.model_copy(update={"revision_id": uuid7()}))
    assert error.value.response.status_code == 409
    unsigned = await client.post(
        "/internal/v1/purchase-print-facts", json=command.model_dump(mode="json")
    )
    assert unsigned.status_code == 401
