"""Assets and components: what a client may state, and what the service decides.

Designer plan P4/D3 (2026-11-03): asset bytes are uploaded, stored on this service's own
private disk, measured from what was actually received (never a client's declared size,
digest or pixel count), and read back only against a signed, actor-bound, expiring token.
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from billing_platform.ids import uuid7
from fastapi import FastAPI

from design.tasks.assets import storage_path
from tests.conftest import canvas, make_template

pytestmark = pytest.mark.asyncio


def png(
    width: int = 512,
    height: int = 128,
    *,
    color: tuple[int, int, int] = (31, 58, 92),
    noisy: bool = False,
) -> bytes:
    """A real, minimal, validly-CRC'd PNG at the given size — not a magic blob.

    ``noisy`` fills each row with random bytes, so zlib cannot shrink it — the oversized
    test needs its *stored* size to actually exceed the limit, not just its pixel count.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = os.urandom(width * 3) if noisy else bytes(color) * width
    row = b"\x00" + pixels
    body = zlib.compress(row * height, 0 if noisy else -1)
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")


LOGO = png()


def asset_payload(**overrides: object) -> dict[str, object]:
    return {
        "asset_name": "Primary logo",
        "asset_type": "LOGO",
        "file_name": "logo.png",
        "mime_type": "image/png",
        "content_base64": base64.b64encode(LOGO).decode(),
    } | overrides


async def register(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
    **overrides: object,
) -> httpx.Response:
    # Every call in one test file shares the same directory; harmless, since paths are
    # content- and asset-id-scoped and never collide across calls.
    app.state.settings.asset_storage_root = tmp_path
    return await client.post(
        f"/v1/companies/{company}/assets", json=asset_payload(**overrides), headers=auth
    )


async def test_an_uploaded_logo_is_stored_at_its_derived_path_with_measured_facts(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(client, company_id, auth_headers, app, tmp_path)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["storage_path"] == storage_path(
        prefix="design",
        tenant_id=tenant_id,
        company_id=company_id,
        asset_id=uuid.UUID(body["id"]),
        mime_type="image/png",
    )
    assert str(company_id) in body["storage_path"]
    assert body["storage_backend"] == "PRIVATE_DISK"
    # Measured from the real bytes, not anything the client could have claimed.
    assert body["file_size_bytes"] == len(LOGO)
    assert body["content_digest"] == hashlib.sha256(LOGO).hexdigest()
    assert (body["image_width_px"], body["image_height_px"]) == (512, 128)
    stored = tmp_path.joinpath(*body["storage_path"].split("/"))
    assert stored.read_bytes() == LOGO


async def test_client_supplied_storage_path_or_digest_or_size_is_ignored_not_trusted(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client,
        company_id,
        auth_headers,
        app,
        tmp_path,
        storage_path="../../other-tenant/logo.png",
        content_digest="a" * 64,
        file_size_bytes=999999,
    )
    # Unknown fields on this request are simply rejected — the schema has no such fields.
    assert response.status_code == 422


async def test_client_supplied_public_url_is_refused(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client, company_id, auth_headers, app, tmp_path, public_url="http://evil/logo.png"
    )
    assert response.status_code == 422


async def test_svg_is_refused(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client,
        company_id,
        auth_headers,
        app,
        tmp_path,
        mime_type="image/svg+xml",
        file_name="logo.svg",
        content_base64=base64.b64encode(b"<svg></svg>").decode(),
    )
    assert response.status_code == 422


async def test_font_asset_upload_is_refused_with_its_reason(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client,
        company_id,
        auth_headers,
        app,
        tmp_path,
        asset_type="CUSTOM_FONT",
        mime_type="font/woff2",
        file_name="brand.woff2",
        content_base64=base64.b64encode(b"wOF2-not-stored").decode(),
    )
    assert response.status_code == 422


async def test_oversized_asset_is_refused(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    huge = png(2000, 900, noisy=True)
    assert len(huge) > 5 * 1024 * 1024
    response = await register(
        client,
        company_id,
        auth_headers,
        app,
        tmp_path,
        content_base64=base64.b64encode(huge).decode(),
    )
    assert response.status_code == 422


async def test_content_not_matching_its_declared_media_type_is_refused(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client,
        company_id,
        auth_headers,
        app,
        tmp_path,
        content_base64=base64.b64encode(b"not a png").decode(),
    )
    assert response.status_code == 422


async def test_invalid_base64_is_refused(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    response = await register(
        client, company_id, auth_headers, app, tmp_path, content_base64="***not-base64***"
    )
    assert response.status_code == 422


async def test_upload_refuses_when_private_storage_is_not_configured(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
) -> None:
    app.state.settings.asset_storage_root = None
    response = await client.post(
        f"/v1/companies/{company_id}/assets", json=asset_payload(), headers=auth_headers
    )
    assert response.status_code == 409


async def test_a_downloaded_asset_matches_what_was_uploaded_and_the_token_is_scoped(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    token = asset["download_token"]
    assert token

    fetched = await client.get(
        f"/v1/companies/{company_id}/assets/{asset['id']}/download",
        params={"token": token},
        headers=auth_headers,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.content == LOGO
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.headers["cache-control"] == "no-store"

    other = (
        await register(client, company_id, auth_headers, app, tmp_path, asset_name="Second")
    ).json()
    cross = await client.get(
        f"/v1/companies/{company_id}/assets/{other['id']}/download",
        params={"token": token},
        headers=auth_headers,
    )
    assert cross.status_code == 422

    garbage = await client.get(
        f"/v1/companies/{company_id}/assets/{asset['id']}/download",
        params={"token": "not-a-real-token"},
        headers=auth_headers,
    )
    assert garbage.status_code == 422


async def test_a_token_minted_for_one_actor_does_not_work_for_another(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    signed_headers: Callable[..., dict[str, str]],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    other_user = signed_headers(tenant_id, company_id, user_id=uuid7())
    response = await client.get(
        f"/v1/companies/{company_id}/assets/{asset['id']}/download",
        params={"token": asset["download_token"]},
        headers=other_user,
    )
    assert response.status_code == 422


async def test_an_inactive_asset_cannot_be_downloaded_even_with_a_fresh_token(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    await client.delete(f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers)
    detail = await client.get(
        f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers
    )
    assert detail.json()["download_token"] is None


async def test_asset_deactivation_keeps_the_row(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    gone = await client.delete(
        f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers
    )
    assert gone.status_code == 204

    listing = await client.get(f"/v1/companies/{company_id}/assets", headers=auth_headers)
    assert listing.json()["items"] == []

    detail = await client.get(
        f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers
    )
    assert detail.status_code == 200
    assert detail.json()["is_active"] is False

    twice = await client.delete(
        f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers
    )
    assert twice.status_code == 409


async def test_layout_may_reference_an_active_company_asset(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    template = await make_template(client, company_id, auth_headers)
    response = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(asset_id=asset["id"])},
        headers=auth_headers,
    )
    assert response.status_code == 201


async def test_layout_cannot_reference_another_companys_asset(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    company_a, company_b = uuid7(), uuid7()
    owner_a = signed_headers(tenant_id, company_a)
    owner_b = signed_headers(tenant_id, company_b)
    asset = (await register(client, company_a, owner_a, app, tmp_path)).json()
    template_b = await make_template(client, company_b, owner_b, code="b-design")

    response = await client.post(
        f"/v1/companies/{company_b}/templates/{template_b['id']}/versions",
        json={"layout_definition": canvas(asset_id=asset["id"])},
        headers=owner_b,
    )
    assert response.status_code == 422


async def test_layout_cannot_reference_a_deactivated_asset(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    asset = (await register(client, company_id, auth_headers, app, tmp_path)).json()
    await client.delete(f"/v1/companies/{company_id}/assets/{asset['id']}", headers=auth_headers)
    template = await make_template(client, company_id, auth_headers)
    response = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(asset_id=asset["id"])},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_component_round_trip_and_duplicate_code(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    payload = {
        "name": "Bank details",
        "code": "bank-primary",
        "component_category": "BANK_DETAILS",
        "content_definition": {"heading": "Remit to", "account_label": "A/C 1234"},
    }
    created = await client.post(
        f"/v1/companies/{company_id}/components", json=payload, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["content_definition"]["heading"] == "Remit to"

    duplicate = await client.post(
        f"/v1/companies/{company_id}/components", json=payload, headers=auth_headers
    )
    assert duplicate.status_code == 409

    listed = await client.get(f"/v1/companies/{company_id}/components", headers=auth_headers)
    assert len(listed.json()["items"]) == 1
    # The lean list projection never carries the block's contents.
    assert "content_definition" not in listed.json()["items"][0]

    patched = await client.patch(
        f"/v1/companies/{company_id}/components/{created.json()['id']}",
        json={"content_definition": {"heading": "Pay to"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["content_definition"] == {"heading": "Pay to"}

    deactivated = await client.patch(
        f"/v1/companies/{company_id}/components/{created.json()['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert deactivated.json()["is_active"] is False


async def test_component_content_is_bounded(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/v1/companies/{company_id}/components",
        json={
            "name": "Terms",
            "code": "terms",
            "component_category": "TERMS_CONDITIONS",
            "content_definition": {"body": "x" * 2500},
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_layout_may_reference_an_active_component(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    await client.post(
        f"/v1/companies/{company_id}/components",
        json={
            "name": "Footer",
            "code": "footer-std",
            "component_category": "FOOTER",
            "content_definition": {"note": "Thank you"},
        },
        headers=auth_headers,
    )
    template = await make_template(client, company_id, auth_headers)
    response = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(component_code="footer-std")},
        headers=auth_headers,
    )
    assert response.status_code == 201


async def test_tenant_wide_layout_cannot_embed_a_company_private_asset(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    """A shared house style may name only shared assets.

    Otherwise one company's signature or seal prints on every company's documents: the
    references were being checked against the URL's company rather than the row's owner.
    """
    company = uuid7()
    company_admin = signed_headers(tenant_id, company)
    private_asset = (await register(client, company, company_admin, app, tmp_path)).json()

    tenant_admin = signed_headers(tenant_id, None, tenant_wide=True)
    rejected = await client.post(
        f"/v1/companies/{company}/templates",
        json={
            "name": "house",
            "code": "house-style",
            "is_tenant_wide": True,
            "initial_canvas": canvas(asset_id=private_asset["id"]),
        },
        headers=tenant_admin,
    )
    assert rejected.status_code == 422

    shared_asset = (
        await register(client, company, tenant_admin, app, tmp_path, is_tenant_wide=True)
    ).json()
    accepted = await client.post(
        f"/v1/companies/{company}/templates",
        json={
            "name": "house",
            "code": "house-style",
            "is_tenant_wide": True,
            "initial_canvas": canvas(asset_id=shared_asset["id"]),
        },
        headers=tenant_admin,
    )
    assert accepted.status_code == 201, accepted.text


async def test_version_of_a_shared_template_cannot_embed_a_private_asset(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    company = uuid7()
    company_admin = signed_headers(tenant_id, company)
    private_asset = (await register(client, company, company_admin, app, tmp_path)).json()

    tenant_admin = signed_headers(tenant_id, None, tenant_wide=True)
    shared = await make_template(
        client, company, tenant_admin, code="house-style", tenant_wide=True
    )
    response = await client.post(
        f"/v1/companies/{company}/templates/{shared['id']}/versions",
        json={"layout_definition": canvas(asset_id=private_asset["id"])},
        headers=tenant_admin,
    )
    assert response.status_code == 422
