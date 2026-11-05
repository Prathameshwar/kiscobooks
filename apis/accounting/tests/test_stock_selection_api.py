"""The browser selection route establishes tenant scope before native reads."""

from decimal import Decimal

from billing_platform.db import tenant_scope
from pydantic import SecretStr

from accounting.tasks.stock_source_client import StockSourceClient
from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import ledger_headers
from tests.test_stock_effects import source
from tests.test_stock_ledger import DAY, item, ledger, line, warehouse


async def test_selection_route_scope_and_permission(client, app, monkeypatch):
    product, location = item(), warehouse()
    app.state.settings = app.state.settings.model_copy(
        update={
            "stock_owner_url": "http://127.0.0.1:8003",
            "stock_owner_secret": SecretStr("test-source-connection-credential" * 2),
        }
    )

    async def acquire(self, request):
        return source(request, product, location).model_copy(update={"purpose": "PREVIEW"})

    monkeypatch.setattr(StockSourceClient, "acquire", acquire)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db)
            await owner.receive(line(product, location, 2), product, location, value=Decimal("10"))
    path = f"/v1/companies/{COMPANY}/stock/selection"
    body = {
        "item_id": str(product.item_id),
        "warehouse_id": str(location.warehouse_id),
        "stock_date": DAY.isoformat(),
    }
    assert (await client.post(path, json=body)).status_code == 401
    assert (await client.post(path, json=body, headers=ledger_headers())).status_code == 403
    result = await client.post(
        path,
        json=body,
        headers=ledger_headers(
            permissions={"accounting.stock.read"},
            features={"inventory"},
        ),
    )
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["quantity"] == "2.0000"
