"""Template and version lifecycle, including the bugs this service shipped with.

Each of the first five tests is a regression test for a confirmed defect: a version read
or published through the wrong template, a client-set status, a burnt code, a float page
size, and an archived template still being served.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from billing_platform.ids import uuid7

from tests.conftest import canvas, make_template, publish_template


@pytest.mark.asyncio
async def test_version_cannot_be_read_through_another_template(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company_a, company_b = uuid7(), uuid7()
    owner_a = signed_headers(tenant_id, company_a)
    owner_b = signed_headers(tenant_id, company_b)
    design_a = await make_template(client, company_a, owner_a, code="a-design")
    design_b = await make_template(client, company_b, owner_b, code="b-design")

    leaked = await client.get(
        f"/v1/companies/{company_b}/templates/{design_b['id']}"
        f"/versions/{design_a['initial_version_id']}",
        headers=owner_b,
    )
    assert leaked.status_code == 404


@pytest.mark.asyncio
async def test_version_cannot_be_published_onto_another_template(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company_a, company_b = uuid7(), uuid7()
    owner_a = signed_headers(tenant_id, company_a)
    owner_b = signed_headers(tenant_id, company_b)
    design_a = await make_template(client, company_a, owner_a, code="a-design")
    design_b = await make_template(client, company_b, owner_b, code="b-design")

    hijack = await client.post(
        f"/v1/companies/{company_b}/templates/{design_b['id']}"
        f"/versions/{design_a['initial_version_id']}/publish",
        headers=owner_b,
    )
    assert hijack.status_code == 404

    unchanged = await client.get(
        f"/v1/companies/{company_b}/templates/{design_b['id']}", headers=owner_b
    )
    assert unchanged.json()["current_version_id"] is None
    assert unchanged.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_status_is_not_client_writable(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers, with_canvas=False)
    response = await client.put(
        f"/v1/companies/{company_id}/templates/{template['id']}",
        json={"status": "PUBLISHED"},
        headers=auth_headers,
    )
    assert response.status_code == 422

    still_draft = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    assert still_draft.json()["status"] == "DRAFT"
    assert still_draft.json()["current_version_id"] is None


@pytest.mark.asyncio
async def test_archiving_releases_the_code_for_reuse(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    first = await make_template(client, company_id, auth_headers, code="gst-invoice")
    archived = await client.delete(
        f"/v1/companies/{company_id}/templates/{first['id']}", headers=auth_headers
    )
    assert archived.status_code == 204

    again = await make_template(client, company_id, auth_headers, code="gst-invoice")
    assert again["id"] != first["id"]


@pytest.mark.asyncio
async def test_duplicate_live_code_is_409(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    await make_template(client, company_id, auth_headers, code="dup")
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "dup", "code": "dup"},
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_page_geometry_round_trips_as_decimal(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """Driver float coercion is silent, so the type is asserted, not just the value."""
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={
            "name": "thermal",
            "code": "thermal",
            "paper_size": "CUSTOM",
            "page_width_mm": "80.5000",
            "page_height_mm": "297.0000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["page_width_mm"]) == Decimal("80.5")


@pytest.mark.asyncio
async def test_custom_paper_requires_both_dimensions(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "c", "code": "c", "paper_size": "CUSTOM", "page_width_mm": "80.0"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_archived_template_is_gone_from_reads_and_writes(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await client.delete(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )

    detail = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    assert detail.status_code == 404

    listing = await client.get(f"/v1/companies/{company_id}/templates", headers=auth_headers)
    assert [row["id"] for row in listing.json()["items"]] == []

    # History survives: the versions of an archived design remain readable, because a
    # document printed from one has to stay explainable.
    history = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions", headers=auth_headers
    )
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1


@pytest.mark.asyncio
async def test_version_numbering_is_sequential_and_publishing_is_explicit(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    second = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(content="REVISED"), "change_summary": "second"},
        headers=auth_headers,
    )
    assert second.status_code == 201
    assert second.json()["version_number"] == 2
    assert second.json()["published_at"] is None

    # Saving a revision does not change what prints.
    unchanged = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    assert unchanged.json()["current_version_id"] is None

    published = await publish_template(
        client, company_id, auth_headers, template, second.json()["id"]
    )
    assert published["status"] == "PUBLISHED"
    assert published["current_version_id"] == second.json()["id"]

    stamped = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions/{second.json()['id']}",
        headers=auth_headers,
    )
    assert stamped.json()["published_at"] is not None


@pytest.mark.asyncio
async def test_layout_digest_is_stable_and_differs_per_layout(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    same = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas()},
        headers=auth_headers,
    )
    different = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(content="OTHER")},
        headers=auth_headers,
    )
    first = await client.get(
        f"/v1/companies/{company_id}/templates/{template['id']}"
        f"/versions/{template['initial_version_id']}",
        headers=auth_headers,
    )
    assert same.json()["layout_digest"] == first.json()["layout_digest"]
    assert different.json()["layout_digest"] != first.json()["layout_digest"]


@pytest.mark.asyncio
async def test_empty_update_is_rejected(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    response = await client.put(
        f"/v1/companies/{company_id}/templates/{template['id']}", json={}, headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_changes_metadata_only(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    response = await client.put(
        f"/v1/companies/{company_id}/templates/{template['id']}",
        json={"name": "Renamed", "page_orientation": "LANDSCAPE"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["page_orientation"] == "LANDSCAPE"
    assert response.json()["code"] == template["code"]


@pytest.mark.asyncio
async def test_unknown_template_is_404(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/v1/companies/{company_id}/templates/{uuid7()}", headers=auth_headers
    )
    assert response.status_code == 404
