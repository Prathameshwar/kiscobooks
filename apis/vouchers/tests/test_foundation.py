import datetime as dt

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import func, select

from vouchers.domain.documents import fiscal_start
from vouchers.models import core as m


async def create_type(client: httpx.AsyncClient, prefix: str, **changes):
    body = {"code": "GENERAL", "name": "General memorandum", "kind": "MEMORANDUM"} | changes
    result = await client.post(prefix + "/voucher-types", json=body, headers=headers())
    assert result.status_code == 201, result.text
    return result.json()


async def draft(client: httpx.AsyncClient, prefix: str, type_id: str, **changes):
    body = {
        "type_revision_id": type_id,
        "document_date": dt.date.today().isoformat(),
        "currency": "INR",
        "narration": "Initial evidence",
    } | changes
    result = await client.post(prefix + "/vouchers", json=body, headers=headers())
    assert result.status_code == 201, result.text
    return result.json(), body


async def test_auth_capabilities_and_validation(client, prefix, engine):
    assert (await client.get(prefix + "/voucher-capabilities")).status_code == 401
    assert (
        await client.get(prefix + "/voucher-capabilities", headers=headers(permissions=frozenset()))
    ).status_code == 403
    result = await client.get(prefix + "/voucher-capabilities", headers=headers())
    assert result.status_code == 200, result.text
    assert len(result.json()["kinds"]) == 22
    assert all(not kind["execution_ready"] for kind in result.json()["kinds"])
    result = await client.post(
        prefix + "/voucher-types",
        json={"code": "BAD", "name": "Bad", "kind": "PAYROLL"},
        headers=headers(),
    )
    assert result.status_code == 422, result.text
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == (
        200 if engine.dialect.name == "mysql" else 503
    )


@pytest.mark.parametrize(
    "namespaces",
    [frozenset(), frozenset({"vouchers"}), frozenset({"accounting"})],
)
async def test_incomplete_field_policy_context_is_rejected(client, prefix, namespaces):
    signed = headers(policy_namespaces=namespaces)
    assert (await client.get(prefix + "/voucher-capabilities", headers=signed)).status_code == 401
    created = await client.post(
        prefix + "/voucher-types",
        json={"code": "INCOMPLETE", "name": "Incomplete", "kind": "MEMORANDUM"},
        headers=signed,
    )
    assert created.status_code == 401


async def test_foreign_voucher_header_requires_company_feature(client, prefix):
    kind = await create_type(client, prefix)
    body = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": "USD",
    }
    refused = await client.post(prefix + "/vouchers", json=body, headers=headers())
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["message"] == (
        "foreign voucher currency requires multi_currency"
    )
    unlisted = await client.post(
        prefix + "/vouchers", json=body,
        headers=headers(features=frozenset({"multi_currency"})),
    )
    assert unlisted.status_code == 409, unlisted.text
    admitted = await client.post(
        prefix + "/vouchers",
        json=body,
        headers=headers(
            features=frozenset({"multi_currency"}),
            allowed_currencies=frozenset({"USD"}),
        ),
    )
    assert admitted.status_code == 201, admitted.text


async def test_draft_revision_approval_issue_idempotency(client, prefix, app):
    kind = await create_type(client, prefix)
    item, body = await draft(client, prefix, kind["revision_id"])
    result = await client.put(
        prefix + "/vouchers/" + item["id"],
        json={"expected_version": 1, "content": body | {"narration": "Changed"}},
        headers=headers(),
    )
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated["revision_id"] != item["revision_id"]
    history = await client.get(
        prefix + f'/vouchers/{item["id"]}/revisions/{item["revision_id"]}', headers=headers()
    )
    assert history.json()["narration"] == "Initial evidence"
    stale = await client.put(
        prefix + "/vouchers/" + item["id"],
        json={"expected_version": 1, "content": body},
        headers=headers(),
    )
    assert stale.status_code == 409, stale.text
    path = prefix + "/vouchers/" + item["id"]
    key = headers()
    submitted = await client.post(path + "/submit", json={"expected_version": 2}, headers=key)
    assert submitted.status_code == 200, submitted.text
    again = await client.post(path + "/submit", json={"expected_version": 2}, headers=key)
    assert again.status_code == 200 and again.headers["Idempotency-Replayed"] == "true"
    self_approval = await client.post(
        path + "/approve", json={"expected_version": 3}, headers=headers()
    )
    assert self_approval.status_code == 403, self_approval.text
    approved = await client.post(
        path + "/approve", json={"expected_version": 3}, headers=headers(user=uuid7())
    )
    assert approved.status_code == 200, approved.text
    series = await client.post(
        prefix + "/voucher-series", json={"code": "DOC", "prefix": "DOC-"}, headers=headers()
    )
    assert series.status_code == 201, series.text
    issued = await client.post(
        path + "/issue",
        json={"expected_version": 4, "series_id": series.json()["id"]},
        headers=headers(),
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["status"] == "ISSUED"
    rejected = await client.put(
        path, json={"expected_version": 5, "content": body}, headers=headers()
    )
    assert rejected.status_code == 409, rejected.text
    assert (
        await client.post(path + "/post", json={"expected_version": 5}, headers=headers())
    ).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherNumberAssignment.id))) == 1
            assert await db.scalar(select(func.count(m.VoucherRevision.id))) == 2
            assert await db.scalar(select(func.count(m.VoucherApproval.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 7


async def test_scope_fields_replays_and_atomic_rollback(client, prefix, app):
    kind = await create_type(client, prefix)
    body = {
        "type_revision_id": kind["revision_id"],
        "document_date": dt.date.today().isoformat(),
        "currency": "INR",
        "narration": "Private",
    }
    key = headers()
    created = await client.post(prefix + "/vouchers", json=body, headers=key)
    assert created.status_code == 201, created.text
    item = created.json()
    other = uuid7()
    assert (
        await client.get(
            f'/v1/companies/{other}/vouchers/{item["id"]}', headers=headers(company=other)
        )
    ).status_code == 403
    assert (
        await client.get(prefix + f'/vouchers/{item["id"]}', headers=headers(tenant=uuid7()))
    ).status_code == 404
    policy = {
        "entity_type": "vouchers.voucher",
        "field_key": "narration",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    denied_header = headers(policies=[policy], key=key["Idempotency-Key"])
    replay = await client.post(prefix + "/vouchers", json=body, headers=denied_header)
    assert replay.status_code == 201, replay.text
    assert "narration" not in replay.json()
    bad = await client.post(
        prefix + "/vouchers",
        json=body | {"custom_fields": {"cf_unknown": "value"}},
        headers=headers(),
    )
    assert bad.status_code == 422, bad.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.Voucher.id))) == 1


async def test_configuration_publication_and_stale_draft(client, prefix):
    kind = await create_type(client, prefix)
    item, _ = await draft(client, prefix, kind["revision_id"])
    config = await client.post(
        prefix + "/voucher-configurations",
        json={
            "code": "REQUIRED",
            "name": "Narration required",
            "policy": {"narration_required": True},
        },
        headers=headers(),
    )
    assert config.status_code == 201, config.text
    cid = config.json()["id"]
    published = await client.post(
        prefix + f"/voucher-configurations/{cid}/publish",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert published.status_code == 200, published.text
    bind = await client.post(
        prefix + f'/voucher-types/{kind["id"]}/configuration-bindings',
        json={
            "expected_version": 1,
            "configuration_revision_id": published.json()["revision_id"],
            "valid_from": "2020-01-01",
        },
        headers=headers(),
    )
    assert bind.status_code == 201, bind.text
    stale = await client.post(
        prefix + f'/vouchers/{item["id"]}/submit', json={"expected_version": 1}, headers=headers()
    )
    assert stale.status_code == 409, stale.text
    overlap = await client.post(
        prefix + f'/voucher-types/{kind["id"]}/configuration-bindings',
        json={
            "expected_version": 2,
            "configuration_revision_id": published.json()["revision_id"],
            "valid_from": "2020-01-01",
        },
        headers=headers(),
    )
    assert overlap.status_code == 409, overlap.text


async def test_lists_cursor_and_forbidden_sections(client, prefix):
    for i in range(3):
        await create_type(client, prefix, code=f"T{i}")
    page = await client.get(prefix + "/voucher-types?limit=2", headers=headers())
    assert page.status_code == 200, page.text
    data = page.json()
    assert len(data["items"]) == 2 and data["page"]["next_cursor"]
    second = await client.get(
        prefix + "/voucher-types",
        params={"limit": 2, "cursor": data["page"]["next_cursor"]},
        headers=headers(),
    )
    assert second.status_code == 200 and len(second.json()["items"]) == 1
    assert not {i["id"] for i in data["items"]} & {i["id"] for i in second.json()["items"]}
    assert (
        await client.get(prefix + "/voucher-types?limit=201", headers=headers())
    ).status_code == 422
    assert (
        await client.get(prefix + "/voucher-types?limit=1&limit=2", headers=headers())
    ).status_code == 422
    assert (
        await client.get(prefix + "/voucher-types?unknown=1", headers=headers())
    ).status_code == 422


def test_calendar_and_exact_quantities():
    from pydantic import ValidationError

    from vouchers.schemas.documents import ItemInput

    assert fiscal_start(dt.date(2026, 3, 31), 4, 1) == dt.date(2025, 4, 1)
    assert fiscal_start(dt.date(2026, 4, 1), 4, 1) == dt.date(2026, 4, 1)
    data = {
        "item_id": uuid7(),
        "item_version": 1,
        "unit_id": uuid7(),
        "actual_quantity": "11",
        "billed_quantity": "10",
    }
    item = ItemInput.model_validate(data)
    from decimal import Decimal

    assert isinstance(item.actual_quantity, Decimal)
    with pytest.raises(ValidationError):
        ItemInput.model_validate(data | {"actual_quantity": 1.2})
    with pytest.raises(ValidationError):
        ItemInput.model_validate(data | {"actual_quantity": "1.00001"})
