"""Verified VM-local bytes, immutable revision references and fresh disclosure authority."""

import base64
import hashlib
from pathlib import Path

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from conftest import COMPANY, TENANT, headers
from test_foundation import create_type, draft

from vouchers.domain import supporting_files as disk

DATA = b"%PDF-1.7\nPurchase supporting evidence\n%%EOF"


async def setup(client, prefix, app, tmp_path):
    app.state.settings.supporting_file_root = tmp_path
    kind = await create_type(client, prefix, kind="PURCHASE", name="Purchase")
    saved, body = await draft(client, prefix, kind["revision_id"])
    path = prefix + "/vouchers/" + saved["id"]
    upload = {
        "expected_version": saved["row_version"],
        "filename": "Supplier bill.pdf",
        "media_type": "application/pdf",
        "content_base64": base64.b64encode(DATA).decode(),
    }
    return saved, body, path, upload


async def test_upload_link_download_and_historical_retention(client, prefix, app, tmp_path):
    saved, body, path, upload = await setup(client, prefix, app, tmp_path)
    key = headers()
    result = await client.post(path + "/supporting-files", json=upload, headers=key)
    assert result.status_code == 201, result.text
    file = result.json()
    assert file["content_hash"] == hashlib.sha256(DATA).hexdigest()
    assert file["size_bytes"] == len(DATA)
    assert file["download_token"] is None  # staged bytes are not saved bill evidence
    replay = await client.post(path + "/supporting-files", json=upload, headers=key)
    assert replay.status_code == 201 and replay.json()["id"] == file["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert (await client.get(path + "/supporting-files", headers=headers())).json() == []
    reference = {
        name: file[name] for name in ("object_key", "content_hash", "media_type", "size_bytes")
    }
    linked = await client.put(
        path,
        json={
            "expected_version": saved["row_version"],
            "content": body | {"attachments": [reference]},
        },
        headers=headers(),
    )
    assert linked.status_code == 200, linked.text
    revision = linked.json()["revision_id"]
    listing = await client.get(path + "/supporting-files", headers=headers())
    assert listing.status_code == 200, listing.text
    token = listing.json()[0]["download_token"]
    url = path + "/supporting-files/" + file["id"] + "/download"
    download = await client.get(url, params={"token": token}, headers=headers())
    assert download.status_code == 200 and download.content == DATA
    assert download.headers["Cache-Control"] == "no-store"
    assert "attachment" in download.headers["Content-Disposition"]
    removed = await client.put(
        path,
        json={
            "expected_version": linked.json()["row_version"],
            "content": body | {"attachments": []},
        },
        headers=headers(),
    )
    assert removed.status_code == 200, removed.text
    assert (await client.get(url, params={"token": token}, headers=headers())).status_code == 403
    historic = await client.get(
        url, params={"token": token, "revision_id": revision}, headers=headers()
    )
    assert historic.status_code == 200 and historic.content == DATA


async def test_unverified_and_tampered_references_are_refused(client, prefix, app, tmp_path):
    saved, body, path, upload = await setup(client, prefix, app, tmp_path)
    file = (await client.post(path + "/supporting-files", json=upload, headers=headers())).json()
    reference = {
        name: file[name] for name in ("object_key", "content_hash", "media_type", "size_bytes")
    }
    for changed in (
        {"content_hash": "a" * 64},
        {"size_bytes": len(DATA) + 1},
        {"object_key": f"{TENANT}/{COMPANY}/unverified"},
    ):
        result = await client.put(
            path,
            json={
                "expected_version": saved["row_version"],
                "content": body | {"attachments": [reference | changed]},
            },
            headers=headers(),
        )
        assert result.status_code == 422, result.text


async def test_large_upload_identity_is_hash_bound_not_a_base64_receipt(
    client, prefix, app, tmp_path
):
    _, _, path, upload = await setup(client, prefix, app, tmp_path)
    data = b"Private supplier text\n" * 60000
    result = await client.post(
        path + "/supporting-files",
        json=upload
        | {
            "filename": "supplier.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(data).decode(),
        },
        headers=headers(),
    )
    assert result.status_code == 201, result.text
    assert result.json()["size_bytes"] == len(data)
    assert (
        disk.read(tmp_path, result.json()["object_key"], result.json()["content_hash"], len(data))
        == data
    )


async def test_files_cannot_cross_tenants_companies_or_vouchers(client, prefix, app, tmp_path):
    from billing_platform.ids import uuid7

    saved, body, path, upload = await setup(client, prefix, app, tmp_path)
    file = (await client.post(path + "/supporting-files", json=upload, headers=headers())).json()
    other, _ = await draft(client, prefix, body["type_revision_id"])
    reference = {
        name: file[name] for name in ("object_key", "content_hash", "media_type", "size_bytes")
    }
    cross = await client.put(
        prefix + "/vouchers/" + other["id"],
        json={
            "expected_version": other["row_version"],
            "content": body | {"attachments": [reference]},
        },
        headers=headers(),
    )
    assert cross.status_code == 422, cross.text
    company = uuid7()
    assert (
        await client.get(
            f"/v1/companies/{company}/vouchers/{saved['id']}/supporting-files",
            headers=headers(company=company),
        )
    ).status_code == 403
    assert (
        await client.get(path + "/supporting-files", headers=headers(tenant=uuid7()))
    ).status_code == 404


async def test_storage_and_upload_permission_fail_closed(client, prefix, app, tmp_path):
    saved, _, path, upload = await setup(client, prefix, app, tmp_path)
    app.state.settings.supporting_file_root = None
    assert (
        await client.post(path + "/supporting-files", json=upload, headers=headers())
    ).status_code == 409
    app.state.settings.supporting_file_root = tmp_path
    assert (
        await client.post(
            path + "/supporting-files",
            json=upload,
            headers=headers(permissions=frozenset({"vouchers.read"})),
        )
    ).status_code == 403
    policy = {
        "entity_type": "vouchers.voucher",
        "field_key": "attachments",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.post(
            path + "/supporting-files", json=upload, headers=headers(policies=[policy])
        )
    ).status_code == 403
    assert not list(tmp_path.rglob("*"))
    assert (
        await client.post(
            path + "/supporting-files",
            json=upload | {"expected_version": saved["row_version"] + 1},
            headers=headers(),
        )
    ).status_code == 409


async def test_download_rechecks_field_scope_token_and_integrity(client, prefix, app, tmp_path):
    saved, body, path, upload = await setup(client, prefix, app, tmp_path)
    file = (await client.post(path + "/supporting-files", json=upload, headers=headers())).json()
    reference = {
        name: file[name] for name in ("object_key", "content_hash", "media_type", "size_bytes")
    }
    linked = await client.put(
        path,
        json={
            "expected_version": saved["row_version"],
            "content": body | {"attachments": [reference]},
        },
        headers=headers(),
    )
    assert linked.status_code == 200, linked.text
    token = (await client.get(path + "/supporting-files", headers=headers())).json()[0][
        "download_token"
    ]
    url = path + "/supporting-files/" + file["id"] + "/download"
    assert (
        await client.get(url, params={"token": "tampered"}, headers=headers())
    ).status_code == 422
    policy = {
        "entity_type": "vouchers.voucher",
        "field_key": "attachments",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.get(url, params={"token": token}, headers=headers(policies=[policy]))
    ).status_code == 403
    disk.location(tmp_path, file["object_key"]).write_bytes(b"corrupt")
    assert (await client.get(url, params={"token": token}, headers=headers())).status_code == 409


@pytest.mark.parametrize(
    "media,data",
    [
        ("application/pdf", b"fake"),
        ("image/png", DATA),
        ("text/plain", b"\x00"),
        ("text/plain", b"\xff"),
        ("image/svg+xml", b"<svg />"),
    ],
)
def test_content_type_and_empty_files_are_refused(media, data):
    with pytest.raises(ValidationFailedError):
        disk.decode(base64.b64encode(data).decode(), media)


def test_disk_traversal_and_missing_root_are_refused(tmp_path):
    with pytest.raises(ValidationFailedError):
        disk.location(tmp_path, "../escape")
    with pytest.raises(ConflictError):
        disk.location(Path("relative"), "../escape")


async def test_registrations_are_immutable_and_retained(client, prefix, app, tmp_path):
    import uuid

    from billing_platform.db import tenant_scope

    from vouchers.models.supporting_files import PurchaseSupportingFile

    _, _, path, upload = await setup(client, prefix, app, tmp_path)
    file = (await client.post(path + "/supporting-files", json=upload, headers=headers())).json()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(PurchaseSupportingFile, uuid.UUID(file["id"]))
            row.content_hash = "b" * 64
            with pytest.raises(ConflictError, match="immutable"):
                await db.flush()
        async with app.state.session_factory() as db:
            row = await db.get(PurchaseSupportingFile, uuid.UUID(file["id"]))
            await db.delete(row)
            with pytest.raises(ConflictError, match="never deleted"):
                await db.flush()


async def test_each_download_is_audited_before_bytes_and_a_refusal_is_not(
    client, prefix, app, tmp_path
):
    from billing_platform.db import tenant_scope
    from billing_platform.db.platform_models import Outbox
    from sqlalchemy import select

    async def downloads():
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                return list(
                    await db.scalars(
                        select(Outbox).where(
                            Outbox.event_type == "vouchers.supporting_file.download"
                        )
                    )
                )

    saved, body, path, upload = await setup(client, prefix, app, tmp_path)
    file = (await client.post(path + "/supporting-files", json=upload, headers=headers())).json()
    reference = {
        name: file[name] for name in ("object_key", "content_hash", "media_type", "size_bytes")
    }
    linked = await client.put(
        path,
        json={
            "expected_version": saved["row_version"],
            "content": body | {"attachments": [reference]},
        },
        headers=headers(),
    )
    assert linked.status_code == 200, linked.text
    token = (await client.get(path + "/supporting-files", headers=headers())).json()[0][
        "download_token"
    ]
    url = path + "/supporting-files/" + file["id"] + "/download"
    assert (await client.get(url, params={"token": token}, headers=headers())).status_code == 200
    events = await downloads()
    assert len(events) == 1
    assert str(events[0].aggregate_id) == file["id"]
    assert "Supplier bill" not in str(events[0].payload)  # references only, never the filename
    disk.location(tmp_path, file["object_key"]).write_bytes(b"corrupt")
    assert (await client.get(url, params={"token": token}, headers=headers())).status_code == 409
    assert len(await downloads()) == 1
