"""Signed NoStock evidence needs both Catalog transport and real lifecycle authority."""

from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from billing_platform.ids import uuid7
from pydantic import SecretStr
from voucher_execution.retirement_transport import RetirementClient, RetirementConnection
from voucher_execution.stock_retirement import ActorProof, RetirementRequest

from tests.conftest import COMPANY, TENANT, USER
from tests.test_ledger_api import ledger_headers
from tests.test_stock_ledger import item, ledger, line, warehouse


async def test_current_no_stock_is_signed_and_scope_bound(client, app):
    product, location = item(), warehouse()
    secret = SecretStr("native-retirement-accounting-test-credential" * 2)
    app.state.settings = app.state.settings.model_copy(update={"stock_retirement_secret": secret})
    proof = ledger_headers(permissions={"warehouse.deactivate"})
    body = RetirementRequest(
        check_id=uuid7(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=USER,
        warehouse_id=location.warehouse_id,
        expected_version=1,
        command_hash="a" * 64,
        authority=ActorProof(
            context=proof["X-Actor-Context"], signature=proof["X-Actor-Signature"]
        ),
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 1), product, location, value=Decimal("10"))
    transport = RetirementClient(
        "accounting",
        RetirementConnection(
            origin="http://127.0.0.1:8011",
            secret=secret,
        ),
        transport=httpx.ASGITransport(app=app),
    )
    result = await transport.check(body)
    assert result.result == "BLOCKED" and result.reason == "STOCK_ON_HAND"
    assert "quantity" not in result.model_dump() and "value" not in result.model_dump()
    wrong_company = body.model_copy(update={"company_id": uuid7(), "check_id": uuid7()})
    with pytest.raises(PermissionDeniedError):
        await transport.check(wrong_company)
    assert (
        await client.post("/internal/v1/stock-retirement", json=body.model_dump(mode="json"))
    ).status_code == 401
