"""Opening import chunks reuse native drafts and retain exact recovery checkpoints."""

import copy
import uuid

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type
from test_stock_capture import fixture

from vouchers.models.core import Voucher
from vouchers.models.stock_opening_import import StockOpeningImportClaim
from vouchers.models.unit_sources import VoucherItemUnitProjection


def auth(**changes):
    return headers(
        permissions=PERMISSIONS
        | {
            "vouchers.import.read",
            "vouchers.import.manage",
            "vouchers.import.commit",
        },
        features=frozenset({"inventory"}),
        **changes,
    )


async def document(client, prefix, app, count=3):
    original = await fixture(client, prefix, app)
    kind = await create_type(
        client,
        prefix,
        code="OPENING",
        kind="STOCK_JOURNAL",
        profile="OPENING",
        policy={
            "schema_version": 2,
            "stock": {},
            "default_mode": "ITEMS",
            "allowed_modes": ["ITEMS"],
        },
    )
    original["type_revision_id"] = kind["revision_id"]
    original["document_date"] = original["posting_date"] = original["stock_date"] = "2020-04-01"
    original["stock"].update(
        action="OPENING",
        opening_mode="COMBINED",
        stock_date="2020-04-01",
        opening_control_id=str(uuid.uuid4()),
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            unit_revision_id = await db.scalar(select(VoucherItemUnitProjection.source_id))
    result = []
    for index in range(count):
        value = copy.deepcopy(original)
        line_key = str(uuid.uuid4())
        value["lines"][0]["line_key"] = line_key
        value["stock"]["lines"][0].update(
            line_id=line_key,
            unit_ids=[str(uuid.uuid4())],
            opening={
                "source_key": f"cohort-{index}",
                "entered_unit_id": value["lines"][0]["item"]["unit_id"],
                "unit_revision_id": str(unit_revision_id),
                "entered_quantity": "1",
                "cost_mode": "VALUE",
                "history_known": False,
            },
        )
        result.append(value)
    return {"source_key": "opening-file-1", "document": {"vouchers": result}}


async def test_validate_and_commit_resume_only_remaining_native_drafts(client, prefix, app):
    body = await document(client, prefix, app)
    path = prefix + "/stock-opening-imports"
    result = await client.post(path, json=body, headers=auth())
    assert result.status_code == 201, result.text
    job = result.json()
    duplicate = await client.post(
        path, json=body | {"source_key": "same-content-new-key"}, headers=auth()
    )
    assert duplicate.status_code == 200 and duplicate.json()["id"] == job["id"]
    for expected_state in ("VALIDATING", "READY"):
        result = await client.post(
            path + f"/{job['id']}/validate",
            json={"expected_version": job["row_version"]},
            headers=auth(),
        )
        assert result.status_code == 200, result.text
        job = result.json()
        assert job["state"] == expected_state
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Voucher.id))) == 0
    for expected_state, count in (("COMMITTING", 2), ("DRAFTS_CREATED", 3)):
        request = {"expected_version": job["row_version"], "review_hash": job["review_hash"]}
        signed = auth()
        result = await client.post(path + f"/{job['id']}/commit", json=request, headers=signed)
        assert result.status_code == 200, result.text
        job = result.json()
        assert job["state"] == expected_state and job["created_chunks"] == count
        assert job["posting_required"] and job["effect_kind"] == "DRAFT_ONLY"
        replay = await client.post(path + f"/{job['id']}/commit", json=request, headers=signed)
        assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Voucher.id))) == 3
            assert await db.scalar(select(func.count(StockOpeningImportClaim.id))) == 3
    listing = await client.get(path + "?limit=1", headers=auth())
    assert listing.status_code == 200 and len(listing.json()["items"]) == 1
    ticket = await client.get(path + f"/{job['id']}/report-ticket", headers=auth())
    assert ticket.status_code == 200, ticket.text
    report = await client.get(ticket.json()["download_path"], headers=auth())
    assert report.status_code == 200 and "DRAFT" in report.text


async def test_opening_import_permissions_and_stale_reviews_fail_closed(client, prefix, app):
    body = await document(client, prefix, app, count=1)
    path = prefix + "/stock-opening-imports"
    assert (await client.post(path, json=body)).status_code == 401
    assert (await client.post(path, json=body, headers=headers())).status_code == 403
    result = await client.post(path, json=body, headers=auth())
    assert result.status_code == 201, result.text
    job = result.json()
    stale = await client.post(
        path + f"/{job['id']}/validate", json={"expected_version": 99}, headers=auth()
    )
    assert stale.status_code == 409
    denied = auth(
        policies=[
            {
                "entity_type": "vouchers.voucher_item",
                "field_key": "received_value",
                "effect": "deny",
                "access": "read",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert (await client.get(path + f"/{job['id']}", headers=denied)).status_code == 403
    assert (
        await client.post(
            path + f"/{job['id']}/cancel",
            json={"expected_version": job["row_version"]},
            headers=auth(),
        )
    ).status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "1e2"},
        {"quantity": 1},
        {"quantity": "-1"},
        {"received_value": None},
    ],
)
async def test_invalid_opening_import_values_are_rejected(client, prefix, app, change):
    body = await document(client, prefix, app, count=1)
    body["document"]["vouchers"][0]["stock"]["lines"][0].update(change)
    result = await client.post(prefix + "/stock-opening-imports", json=body, headers=auth())
    assert result.status_code == 422, result.text


async def test_partial_commit_keeps_native_receipts_and_resumes_only_failed_chunk(
    client, prefix, app, monkeypatch
):
    from billing_platform.errors import ValidationFailedError

    from vouchers.tasks import documents

    body = await document(client, prefix, app, count=3)
    path = prefix + "/stock-opening-imports"
    job = (await client.post(path, json=body, headers=auth())).json()
    for _ in range(2):
        result = await client.post(
            path + f"/{job['id']}/validate",
            json={"expected_version": job["row_version"]},
            headers=auth(),
        )
        assert result.status_code == 200, result.text
        job = result.json()
    result = await client.post(
        path + f"/{job['id']}/commit",
        json={"expected_version": job["row_version"], "review_hash": job["review_hash"]},
        headers=auth(),
    )
    assert result.status_code == 200, result.text
    job = result.json()
    assert job["created_chunks"] == 2
    original = documents.write

    async def fail_after_native_write(*args, **kwargs):
        await original(*args, **kwargs)
        raise ValidationFailedError("Synthetic failure after allocation, before checkpoint")

    monkeypatch.setattr(documents, "write", fail_after_native_write)
    failed = await client.post(
        path + f"/{job['id']}/commit",
        json={"expected_version": job["row_version"], "review_hash": job["review_hash"]},
        headers=auth(),
    )
    assert failed.status_code == 200, failed.text
    job = failed.json()
    assert (
        job["state"] == "BLOCKED" and job["created_chunks"] == 2 and job["errors"][0]["chunk"] == 3
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Voucher.id))) == 2
            assert await db.scalar(select(func.count(StockOpeningImportClaim.id))) == 2
    monkeypatch.setattr(documents, "write", original)
    result = await client.post(
        path + f"/{job['id']}/validate",
        json={"expected_version": job["row_version"]},
        headers=auth(),
    )
    assert result.status_code == 200, result.text
    job = result.json()
    result = await client.post(
        path + f"/{job['id']}/commit",
        json={"expected_version": job["row_version"], "review_hash": job["review_hash"]},
        headers=auth(),
    )
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "DRAFTS_CREATED" and result.json()["created_chunks"] == 3


@pytest.mark.parametrize("change", [{"currency": "USD"}, {"stock_date": "2020-04-02"}])
async def test_stock_header_mismatch_blocks_native_import_dry_run(client, prefix, app, change):
    body = await document(client, prefix, app, count=1)
    body["document"]["vouchers"][0].update(change)
    path = prefix + "/stock-opening-imports"
    staged = await client.post(path, json=body, headers=auth())
    if staged.status_code == 422:
        return
    assert staged.status_code == 201, staged.text
    job = staged.json()
    validated = await client.post(
        path + f"/{job['id']}/validate",
        json={"expected_version": job["row_version"]},
        headers=auth(),
    )
    assert validated.status_code == 200 and validated.json()["state"] == "BLOCKED"
