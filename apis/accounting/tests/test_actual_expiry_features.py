"""Actual optional expiry participates in the durable first-use reservation."""

import datetime as dt
import hashlib

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from voucher_execution.transport import command_digest

from accounting.api.auth import delegated_access
from accounting.models.stock_tracking import StockLot
from accounting.schemas.stock_tracking import TrackingSource
from accounting.tasks.stock_effects import apply
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import authority, captured, configure, intent, source
from tests.test_stock_ledger import item, values, warehouse


@pytest.mark.parametrize("enabled", [True, False])
async def test_optional_declared_expiry_is_reserved_or_rejected(app, client, enabled):
    _, period, _ = await journal_setup(client, app)
    await configure(app)
    product = item(tracking=True).model_copy(
        update={
            "serial_tracking": False,
            "expiry_required": False,
            "manufacture_date_required": False,
            "issue_strategy": "FIFO",
        }
    )
    location = warehouse()
    lot_values = values()
    lot = StockLot(
        **lot_values,
        item_id=product.item_id,
        code="OPTIONAL-EXPIRY",
        normalized_code="optional-expiry",
        namespace_key="ITEM:" + str(product.item_id),
        status="ACTIVE",
        is_held=False,
        manufactured_on=None,
        expires_on=dt.date(2028, 1, 1),
        source_facts=TrackingSource(
            company_id=COMPANY,
            item_id=product.item_id,
            as_of=dt.date(2026, 4, 2),
            profile_revision_id=product.profile_revision_id,
            lot_tracking=True,
            serial_tracking=False,
            expiry_required=False,
            manufacture_date_required=False,
            source_digest="a" * 64,
        ).model_dump(mode="json"),
    )
    features = {"inventory", "batch_tracking"}
    if enabled:
        features.add("expiry_tracking")
    request = captured(period, product, location)
    payload = request.source_payload
    stock = payload["stock"]
    payload = payload | {
        "stock": stock
        | {
            "lines": [
                stock["lines"][0]
                | {
                    "lot_id": str(lot.id),
                }
            ]
        }
    }
    request = request.model_copy(
        update={
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            "authority": authority(features=frozenset(features)),
        }
    )
    request = request.model_copy(update={"request_hash": command_digest(request)})
    current = delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            db.add(lot)
            await db.flush()
            if enabled:
                effects = await apply(
                    db,
                    current,
                    request,
                    await intent(db, request),
                    source(request, product, location),
                )
                assert "expiry_tracking" in effects.features
            else:
                with pytest.raises(ConflictError, match="expiry"):
                    await apply(
                        db,
                        current,
                        request,
                        await intent(db, request),
                        source(request, product, location),
                    )
