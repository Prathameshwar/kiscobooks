"""Cross-tenant isolation per table, paging, and the audit/outbox invariants.

The isolation test is the highest-value test in the service: seed two tenants, read as
one, assert the other's rows are absent — for every table this service owns
(CLAUDE.md §7).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from design.models.template import (
    InvoiceRenderSnapshot,
    InvoiceTemplate,
    InvoiceTemplateAsset,
    InvoiceTemplateAssignment,
    InvoiceTemplateComponent,
    InvoiceTemplateVersion,
)
from tests.conftest import canvas, make_template, publish_template

pytestmark = pytest.mark.asyncio

DIGEST = hashlib.sha256(b"logo").hexdigest()
#: A real, minimal, validly-CRC'd 1x1 PNG, base64 — not a magic blob (plan P4, 2026-11-03).
LOGO_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


async def _seed(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    *,
    code: str,
) -> dict[str, object]:
    """One row in every table this service owns."""
    template = await make_template(client, company, auth, code=code)
    await publish_template(client, company, auth, template)
    await client.post(
        f"/v1/companies/{company}/assignments",
        json={"voucher_kind": "SALES_INVOICE", "template_id": template["id"]},
        headers=auth,
    )
    uploaded = await client.post(
        f"/v1/companies/{company}/assets",
        json={
            "asset_name": f"{code}-logo",
            "asset_type": "LOGO",
            "file_name": "logo.png",
            "mime_type": "image/png",
            "content_base64": LOGO_PNG_BASE64,
        },
        headers=auth,
    )
    assert uploaded.status_code == 201, uploaded.text
    await client.post(
        f"/v1/companies/{company}/components",
        json={
            "name": f"{code}-bank",
            "code": f"{code}-bank",
            "component_category": "BANK_DETAILS",
            "content_definition": {"heading": "Remit"},
        },
        headers=auth,
    )
    await client.post(
        f"/v1/companies/{company}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": template["id"],
            "template_version_id": template["initial_version_id"],
            "render_channel": "PDF_DOWNLOAD",
        },
        headers=auth,
    )
    return template


async def test_every_table_is_tenant_isolated(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    signed_headers: Callable[..., dict[str, str]],
    app: FastAPI,
    tmp_path: Path,
) -> None:
    app.state.settings.asset_storage_root = tmp_path
    tenant_a, tenant_b = uuid7(), uuid7()
    company_a, company_b = uuid7(), uuid7()
    await _seed(client, company_a, signed_headers(tenant_a, company_a), code="a-design")
    await _seed(client, company_b, signed_headers(tenant_b, company_b), code="b-design")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    models = (
        InvoiceTemplate,
        InvoiceTemplateVersion,
        InvoiceTemplateAssignment,
        InvoiceTemplateAsset,
        InvoiceTemplateComponent,
        InvoiceRenderSnapshot,
    )
    async with factory() as db:
        for model in models:
            # Both tenants wrote a row: proven through the audited escape hatch, which is
            # the only way to see across tenants at all.
            with unfiltered():
                rows = (await db.execute(select(model.tenant_id))).scalars().all()
            assert set(rows) == {tenant_a, tenant_b}, model.__tablename__

            # Reading as one tenant returns only that tenant's row.
            with tenant_scope(tenant_a):
                scoped = (await db.execute(select(model.tenant_id))).scalars().all()
            assert set(scoped) == {tenant_a}, model.__tablename__

    # And through the API, tenant B sees none of tenant A's rows.
    reader_b = signed_headers(tenant_b, company_a)
    through_api = await client.get(f"/v1/companies/{company_a}/templates", headers=reader_b)
    assert through_api.status_code == 200
    assert through_api.json()["items"] == []


async def test_guarded_session_filters_by_the_ambient_tenant(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    """The filter is session-level, not per-query discipline (CLAUDE.md §5.3)."""
    from billing_platform.db import create_session_factory

    tenant_a, tenant_b = uuid7(), uuid7()
    company = uuid7()
    await make_template(client, company, signed_headers(tenant_a, company), code="a")
    await make_template(client, company, signed_headers(tenant_b, company), code="b")

    guarded: async_sessionmaker[AsyncSession] = create_session_factory(engine, guarded=True)
    with tenant_scope(tenant_a):
        async with guarded() as db:
            visible = (await db.execute(select(InvoiceTemplate.code))).scalars().all()
    assert list(visible) == ["a"]


async def test_every_state_change_stages_one_audit_event(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    # ``outbox`` is deliberately exempt from the tenant filter: its poller reads across
    # every tenant (``billing_platform.db.platform_models.Outbox``).
    async with factory() as db:
        events = (await db.execute(select(Outbox.event_type).order_by(Outbox.id))).scalars().all()
    assert list(events) == [
        "design.invoice_template.create",
        "design.invoice_template_version.create",
        "design.invoice_template_version.publish",
        "design.invoice_template.publish",
    ]


async def test_audit_payload_names_the_actor_and_never_the_layout(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    actor = uuid7()
    auth = signed_headers(tenant_id, company_id, user_id=actor)
    await make_template(client, company_id, auth)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        row = (
            await db.execute(
                select(Outbox).where(Outbox.event_type == "design.invoice_template.create")
            )
        ).scalar_one()
    assert row.payload["actor_user_id"] == str(actor)
    assert row.payload["entity_type"] == "design.invoice_template"
    assert row.payload["company_id"] == str(company_id)
    assert row.payload["source_service"] == "design"
    assert "layout_definition" not in str(row.payload)
    assert row.tenant_id == tenant_id
    assert row.message_id is not None


async def test_a_rejected_request_leaves_no_audit_row(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
) -> None:
    """The event and the row commit together, so a failed write claims nothing."""
    template = await make_template(client, company_id, auth_headers)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        before = (await db.execute(select(func.count()).select_from(Outbox))).scalar_one()

    rejected = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(asset_id=str(uuid7()))},
        headers=auth_headers,
    )
    assert rejected.status_code == 422

    with unfiltered():
        async with factory() as db:
            after = (await db.execute(select(func.count()).select_from(Outbox))).scalar_one()
            versions = (
                await db.execute(select(func.count()).select_from(InvoiceTemplateVersion))
            ).scalar_one()
    assert after == before
    assert versions == 1


async def test_audit_contract_refuses_an_undeclared_event() -> None:
    from design.events.audit_contract import AUDIT_EVENTS, audit_event

    assert audit_event("invoice_template", "publish") == "design.invoice_template.publish"
    assert "design.invoice_template.delete" not in AUDIT_EVENTS
    with pytest.raises(ValueError, match="undeclared"):
        audit_event("invoice_template", "delete")


async def test_pages_are_keyset_paginated_and_the_cursor_is_scoped(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    for index in range(3):
        await make_template(client, company_id, auth_headers, code=f"design-{index}")

    first = await client.get(f"/v1/companies/{company_id}/templates?limit=2", headers=auth_headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert first.json()["page"]["has_more"] is True
    cursor = first.json()["page"]["next_cursor"]
    assert cursor

    second = await client.get(
        f"/v1/companies/{company_id}/templates?limit=2&cursor={cursor}", headers=auth_headers
    )
    assert len(second.json()["items"]) == 1
    assert second.json()["page"]["has_more"] is False
    assert {row["id"] for row in first.json()["items"]} & {
        row["id"] for row in second.json()["items"]
    } == set()

    # A cursor minted for one actor's authority is not usable by another.
    other_actor = signed_headers(tenant_id, company_id, user_id=uuid7())
    reused = await client.get(
        f"/v1/companies/{company_id}/templates?limit=2&cursor={cursor}", headers=other_actor
    )
    assert reused.status_code == 422


async def test_limit_ceiling_is_enforced(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/v1/companies/{company_id}/templates?limit=500", headers=auth_headers
    )
    assert response.status_code == 422


async def test_render_history_filters_by_document(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    voucher, other = uuid7(), uuid7()
    for subject in (voucher, voucher, other):
        recorded = await client.post(
            f"/v1/companies/{company_id}/renders",
            json={
                "voucher_id": str(subject),
                "template_id": template["id"],
                "template_version_id": template["initial_version_id"],
                "render_channel": "PRINT",
                "checksum_sha256": DIGEST,
            },
            headers=auth_headers,
        )
        assert recorded.status_code == 201, recorded.text

    # A reprint is a second row, never an overwrite.
    for_voucher = await client.get(
        f"/v1/companies/{company_id}/renders?voucher_id={voucher}", headers=auth_headers
    )
    assert len(for_voucher.json()["items"]) == 2

    everything = await client.get(f"/v1/companies/{company_id}/renders", headers=auth_headers)
    assert len(everything.json()["items"]) == 3


async def test_snapshot_cannot_claim_a_foreign_version(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    one = await make_template(client, company_id, auth_headers, code="one")
    two = await make_template(client, company_id, auth_headers, code="two")
    response = await client.post(
        f"/v1/companies/{company_id}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": one["id"],
            "template_version_id": two["initial_version_id"],
            "render_channel": "PRINT",
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_an_archived_design_can_still_be_recorded_as_printed(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await client.delete(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    response = await client.post(
        f"/v1/companies/{company_id}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": template["id"],
            "template_version_id": template["initial_version_id"],
            "render_channel": "EMAIL",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201


async def test_render_artifact_path_is_derived_not_supplied(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
    auth_headers: dict[str, str],
) -> None:
    """`design.render.record` is held by a clerk, so the body is user input.

    A free-form key let one company's print record name another tenant's object, in the
    one record meant to be trustworthy.
    """
    from design.tasks.snapshots import artifact_path

    template = await make_template(client, company_id, auth_headers)
    forged = await client.post(
        f"/v1/companies/{company_id}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": template["id"],
            "template_version_id": template["initial_version_id"],
            "render_channel": "PRINT",
            "storage_path": f"design/assets/{uuid7()}/{uuid7()}/stolen.png",
        },
        headers=auth_headers,
    )
    assert forged.status_code == 422

    recorded = await client.post(
        f"/v1/companies/{company_id}/renders",
        json={
            "voucher_id": str(uuid7()),
            "template_id": template["id"],
            "template_version_id": template["initial_version_id"],
            "render_channel": "PRINT",
        },
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    body = recorded.json()
    assert body["storage_path"] == artifact_path(
        prefix="design",
        tenant_id=tenant_id,
        company_id=company_id,
        snapshot_id=uuid.UUID(body["id"]),
        output_format="PDF",
    )
    assert str(tenant_id) in body["storage_path"] and ".." not in body["storage_path"]


async def test_component_content_change_is_still_named_in_the_audit_row(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
) -> None:
    """The value is withheld; the fact that it changed is not (docs/audit.md §5.2)."""
    created = await client.post(
        f"/v1/companies/{company_id}/components",
        json={
            "name": "Terms",
            "code": "terms-std",
            "component_category": "TERMS_CONDITIONS",
            "content_definition": {"body": "Payable in 30 days"},
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    patched = await client.patch(
        f"/v1/companies/{company_id}/components/{created.json()['id']}",
        json={"content_definition": {"body": "Payable in 15 days"}},
        headers=auth_headers,
    )
    assert patched.status_code == 200

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        row = (
            await db.execute(
                select(Outbox).where(
                    Outbox.event_type == "design.invoice_template_component.update"
                )
            )
        ).scalar_one()
    assert row.payload["changes"] == {"content_definition": {"changed": True}}
