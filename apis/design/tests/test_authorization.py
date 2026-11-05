"""Authorization: the endpoint key, and the object the key is checked against.

The highest-value tests in this module are the cross-company ones. A permission for
company A must not reach company B's template, and a company-scoped grant must not write
the tenant-wide design every company inherits (CLAUDE.md §5.2).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from billing_platform.ids import uuid7

from tests.conftest import canvas, make_template


@pytest.mark.asyncio
async def test_read_without_the_read_permission_is_403(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    unrelated = signed_headers(tenant_id, company_id, permissions=("design.asset.read",))
    response = await client.get(f"/v1/companies/{company_id}/templates", headers=unrelated)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_write_with_only_read_is_403(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    reader = signed_headers(tenant_id, company_id, permissions=("design.template.read",))
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "n", "code": "c", "initial_canvas": canvas()},
        headers=reader,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_publish_needs_its_own_permission(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    template = await make_template(client, company_id, auth_headers)
    author = signed_headers(
        tenant_id,
        company_id,
        permissions=("design.template.read", "design.template.manage"),
    )
    response = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}"
        f"/versions/{template['initial_version_id']}/publish",
        headers=author,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_grant_for_one_company_cannot_read_another(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company_a, company_b = uuid7(), uuid7()
    owner = signed_headers(tenant_id, company_a)
    template = await make_template(client, company_a, owner, code="a-design")

    intruder = signed_headers(tenant_id, company_b)
    through_own_path = await client.get(
        f"/v1/companies/{company_b}/templates/{template['id']}", headers=intruder
    )
    assert through_own_path.status_code == 404

    through_owner_path = await client.get(
        f"/v1/companies/{company_a}/templates/{template['id']}", headers=intruder
    )
    assert through_owner_path.status_code == 403


@pytest.mark.asyncio
async def test_company_grant_cannot_create_a_tenant_wide_template(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "shared", "code": "shared", "is_tenant_wide": True},
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tenant_grant_creates_a_shared_template_every_company_reads(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company_a, company_b = uuid7(), uuid7()
    tenant_admin = signed_headers(tenant_id, None, tenant_wide=True)
    shared = await make_template(
        client, company_a, tenant_admin, code="house-style", tenant_wide=True
    )
    assert shared["company_id"] == str(uuid.UUID(int=0))

    reader_b = signed_headers(tenant_id, company_b)
    visible = await client.get(
        f"/v1/companies/{company_b}/templates/{shared['id']}", headers=reader_b
    )
    assert visible.status_code == 200


@pytest.mark.asyncio
async def test_company_grant_cannot_change_a_shared_template(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company = uuid7()
    tenant_admin = signed_headers(tenant_id, None, tenant_wide=True)
    shared = await make_template(
        client, company, tenant_admin, code="house-style", tenant_wide=True
    )

    company_admin = signed_headers(tenant_id, company)
    response = await client.put(
        f"/v1/companies/{company}/templates/{shared['id']}",
        json={"name": "hijacked"},
        headers=company_admin,
    )
    assert response.status_code == 403

    archived = await client.delete(
        f"/v1/companies/{company}/templates/{shared['id']}", headers=company_admin
    )
    assert archived.status_code == 403


@pytest.mark.asyncio
async def test_recording_a_render_needs_the_render_permission(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    template = await make_template(client, company_id, auth_headers)
    designer = signed_headers(
        tenant_id,
        company_id,
        permissions=("design.template.read", "design.template.manage"),
    )
    response = await client.post(
        f"/v1/companies/{company_id}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": template["id"],
            "template_version_id": template["initial_version_id"],
            "render_channel": "PRINT",
        },
        headers=designer,
    )
    assert response.status_code == 403
