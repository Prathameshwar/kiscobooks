"""Native physical sections round-trip independently from posting/availability."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type
from unit_source_factories import unit_masters
from voucher_execution.stock import StockPolicy

from vouchers.domain.configuration import intersect
from vouchers.models import core as m
from vouchers.models.stock import VoucherStockContext, VoucherStockDetail, VoucherStockUnit
from vouchers.schemas.configuration import Policy
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


def auth(**changes):
    return headers(features=frozenset({"inventory"}), **changes)


async def fixture(client, prefix, app, *, kind_code="RECEIPT_NOTE"):
    kind = await create_type(
        client,
        prefix,
        kind=kind_code,
        policy={
            "schema_version": 2,
            # A v2 type that omits this keeps the schema default (approval required, no
            # self-approval), applied by explicit_approval_controls. These tests exercise the
            # two-person path, so they state it explicitly.
            "approval_required": True,
            "stock": {},
            "default_mode": "ITEMS",
            "allowed_modes": ["ITEMS"],
        },
    )
    item, unit, line, warehouse, serial = (uuid7() for _ in range(5))
    masters = [
        *unit_masters(item, unit),
        {
            "entity_type": "item_transaction_policy",
            "source_id": str(item),
            "source_version": 1,
            "status": "ACTIVE",
            "facts": {
                "kind": "GOODS",
                "inventory_mode": "STOCK",
                "item_version": 1,
                "sellable": True,
                "purchasable": True,
            },
        },
    ]
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": masters,
            }
        ),
        "catalog",
    )
    today = dt.date.today().isoformat()
    return {
        "type_revision_id": kind["revision_id"],
        "document_date": today,
        "posting_date": today,
        "stock_date": today,
        "currency": "INR",
        "mode": "ITEMS",
        "narration": "Receive prepared stock",
        "lines": [
            {
                "line_key": str(line),
                "item": {
                    "item_id": str(item),
                    "item_version": 1,
                    "unit_id": str(unit),
                    "actual_quantity": "1",
                    "billed_quantity": "0",
                },
            }
        ],
        "stock": {
            "action": "RECEIPT",
            "stock_date": today,
            "currency": "INR",
            "reason": "Reviewed inward goods",
            "lines": [
                {
                    "line_id": str(line),
                    "item_id": str(item),
                    "warehouse_id": str(warehouse),
                    "quantity": "1",
                    "received_value": "12.50",
                    "unit_ids": [str(serial)],
                }
            ],
        },
    }


@pytest.mark.parametrize("entered", [False, True])
async def test_native_stock_capture_round_trip_canonical_money_and_history(
    client, prefix, app, entered
):
    body = await fixture(client, prefix, app)
    if entered:
        from vouchers.models.unit_sources import VoucherItemUnitProjection

        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                source_id = await db.scalar(select(VoucherItemUnitProjection.source_id))
        body["stock"]["lines"][0]["quantity_entry"] = {
            "unit_revision_id": str(source_id),
            "entered_unit_id": body["lines"][0]["item"]["unit_id"],
            "entered_quantity": "1",
        }
    response = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["stock"]["lines"][0]["received_value"] == "12.5000"
    assert row["stock"]["lines"][0]["quantity"] == "1.0000"
    assert row["stock"]["lines"][0]["unit_ids"] == body["stock"]["lines"][0]["unit_ids"]
    if entered:
        assert row["stock"]["lines"][0]["quantity_entry"]["entered_quantity"] == "1.0000"
    detail = await client.get(prefix + "/vouchers/" + row["id"], headers=auth())
    assert detail.status_code == 200 and detail.json() == row
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(VoucherStockContext.id))) == 1
            assert await db.scalar(select(func.count(VoucherStockDetail.id))) == 1
            assert await db.scalar(select(func.count(VoucherStockUnit.id))) == 1
            stored = await db.scalar(select(VoucherStockDetail))
            stored.received_value = 99
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()


async def test_denied_stock_value_hides_aggregate_and_hash_and_blocks_creation(client, prefix, app):
    body = await fixture(client, prefix, app)
    row = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert row.status_code == 201, row.text
    rule = {
        "entity_type": "vouchers.voucher_item",
        "field_key": "received_value",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "access": "read",
    }
    masked = await client.get(
        prefix + "/vouchers/" + row.json()["id"], headers=auth(policies=[rule])
    )
    assert masked.status_code == 200, masked.text
    assert masked.json().get("stock") is None and masked.json().get("content_hash") is None
    denied = await client.post(
        prefix + "/vouchers", json=body, headers=auth(policies=[rule | {"access": "write"}])
    )
    assert denied.status_code == 403, denied.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.Voucher.id))) == 1


async def test_stock_capture_requires_inventory_and_same_common_quantity(client, prefix, app):
    body = await fixture(client, prefix, app)
    off = await client.post(prefix + "/vouchers", json=body, headers=headers())
    assert off.status_code == 409, off.text
    body["stock"]["lines"][0]["quantity"] = "2"
    refused = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert refused.status_code == 422, refused.text


def test_inherited_stock_controls_cannot_widen_parent():
    parent = Policy(
        schema_version=2,
        stock=StockPolicy(allow_zero_value_receipts=False, opening_gl_mode="LINKED_GL"),
    )
    child = Policy(schema_version=2, stock=StockPolicy(allow_zero_value_receipts=True))
    merged = intersect(parent, child)
    assert merged.stock.allow_zero_value_receipts is False
    assert merged.stock.opening_gl_mode == "LINKED_GL"


async def test_stock_field_metadata_respects_shared_item_and_header_denies(client, prefix, app):
    body = await fixture(client, prefix, app)
    from vouchers.models.core import VoucherTypeRevision

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revision = await db.get(VoucherTypeRevision, uuid.UUID(body["type_revision_id"]))
            type_id = revision.type_id
    rules = [
        {
            "entity_type": "vouchers.voucher_item",
            "field_key": "received_value",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        },
        {
            "entity_type": "vouchers.voucher_item",
            "field_key": "unit_ids",
            "access": "write",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        },
    ]
    result = await client.get(
        prefix + f"/voucher-types/{type_id}/field-set?date=" + body["document_date"],
        headers=auth(policies=rules),
    )
    assert result.status_code == 200, result.text
    stock = result.json()["native"]["properties"]["stock"]["anyOf"][0]
    properties = stock["properties"]["lines"]["items"]["properties"]
    assert "received_value" not in properties
    assert properties["unit_ids"]["readOnly"] is True


async def approved_stock(client, prefix, app):
    from test_money_posting import authority_headers

    body = await fixture(client, prefix, app)
    row = await client.post(prefix + "/vouchers", json=body, headers=auth())
    assert row.status_code == 201, row.text
    path = prefix + "/vouchers/" + row.json()["id"]
    submitted = await client.post(path + "/submit", json={"expected_version": 1}, headers=auth())
    assert submitted.status_code == 200, submitted.text
    approved = await client.post(
        path + "/approve", json={"expected_version": 2}, headers=auth(user=uuid7())
    )
    assert approved.status_code == 200, approved.text
    series = await client.post(
        prefix + "/voucher-series", json={"code": "STOCK", "prefix": "STK-"}, headers=auth()
    )
    assert series.status_code == 201, series.text
    issued = await client.post(
        path + "/issue",
        json={"expected_version": 3, "series_id": series.json()["id"]},
        headers=auth(),
    )
    assert issued.status_code == 200, issued.text
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {
                            "start_date": body["posting_date"],
                            "end_date": body["posting_date"],
                        },
                    }
                ],
            }
        ),
        "accounting",
    )
    return path, authority_headers(features=frozenset({"inventory"}))


async def test_stock_post_has_independent_gate_both_dates_and_one_durable_attempt(
    client, prefix, app
):
    from voucher_execution import ExecutionCommand
    from voucher_execution.transport import command_digest

    path, authority = await approved_stock(client, prefix, app)
    app.state.settings.money_execution_enabled = True
    denied = await client.post(path + "/post", json={"expected_version": 4}, headers=authority)
    assert denied.status_code == 409, denied.text
    app.state.settings.money_execution_enabled = False
    app.state.settings.stock_execution_enabled = True
    accepted = await client.post(path + "/post", json={"expected_version": 4}, headers=authority)
    assert accepted.status_code == 202, accepted.text
    retry = await client.post(path + "/post", json={"expected_version": 4}, headers=authority)
    assert retry.status_code == 202 and retry.json() == accepted.json()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.get(m.VoucherOperation, uuid.UUID(accepted.json()["operation_id"]))
            command = ExecutionCommand.model_validate(operation.command)
            assert command.request_hash == command_digest(command)
            assert command.stock_date == command.posting_date == dt.date.today()
            assert len(command.period_versions) == 1
            assert command.source_payload["stock"]["lines"][0]["received_value"] == "12.5000"


async def test_stock_delivery_discovers_company_and_reconciles_lost_response(client, prefix, app):
    import secrets

    import httpx
    from billing_platform.db.types import utcnow
    from billing_platform.idempotency import canonical_json
    from billing_platform.service_auth import service_request_bytes, service_response_bytes
    from voucher_execution import ExecutionCommand, ExecutionResult
    from voucher_execution.transport import StockExecutionClient, verify
    from voucher_execution.transport import headers as signed_headers

    from vouchers.tasks.execution_worker import deliver, deliver_stock_page, stock_companies

    path, authority = await approved_stock(client, prefix, app)
    app.state.settings.stock_execution_enabled = True
    accepted = await client.post(path + "/post", json={"expected_version": 4}, headers=authority)
    assert accepted.status_code == 202, accepted.text
    operation = uuid.UUID(accepted.json()["operation_id"])
    companies = await stock_companies(app.state.session_factory, None)
    assert len(companies) == 1 and companies[0][1:] == (TENANT, COMPANY)
    secret, key = secrets.token_bytes(32), "stock.current"
    result, posts = None, 0

    async def owner(request):
        nonlocal result, posts
        status = request.url.path.endswith("/status")
        purpose = "stock.execution.status" if status else "stock.execution.command"
        framed = service_request_bytes(
            method=request.method, path=request.url.path, query="", body=request.content
        )
        verify(secret, key, purpose, framed, request.headers)
        command = ExecutionCommand.model_validate_json(request.content)
        assert command.operation_id == operation and command.company_id == COMPANY
        assert command.voucher_number, "native stock commands retain their issued number"
        if status and result is None:
            return httpx.Response(404)
        if not status:
            posts += 1
            result = ExecutionResult(
                protocol_version=2,
                tenant_id=TENANT,
                company_id=COMPANY,
                operation_id=operation,
                execution_id=command.execution_id,
                content_hash=command.content_hash,
                configuration_hash=command.configuration_hash,
                request_hash=command.request_hash,
                outcome="COMMITTED",
                committed_at=utcnow(),
                committed_generation=1,
                effects=(
                    {"owner": "accounting", "effect_kind": "STOCK", "effect_id": uuid7()},
                    {"owner": "accounting", "effect_kind": "SOURCE_RECEIPT", "effect_id": uuid7()},
                ),
            )
            raise httpx.ReadTimeout("Simulated lost committed response", request=request)
        raw = canonical_json(result.model_dump(mode="json"))
        return httpx.Response(
            200,
            content=raw,
            headers=signed_headers(
                secret,
                key,
                purpose + ".response",
                service_response_bytes(request_bytes=framed, response_body=raw),
                response=True,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as http:
        transport = StockExecutionClient(http, "http://127.0.0.1", key, secret)
        assert not await deliver(app.state.session_factory, transport, TENANT, COMPANY, operation)
        assert await deliver_stock_page(app.state.session_factory, transport, None) is None
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                row = await db.get(m.VoucherOperation, operation)
                assert row.status == "PENDING" and row.attempt_count == 1
        await deliver_stock_page(app.state.session_factory, transport, None)
        await deliver_stock_page(app.state.session_factory, transport, None)
    assert posts == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(m.VoucherOperation, operation)
            assert row.status == "COMMITTED" and row.attempt_count == 2
