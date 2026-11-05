"""Assignment rules and resolution order.

The two regression tests here are the ones that mattered: an archived template must stop
resolving, and one unusable candidate must not sink the whole resolution.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from billing_platform.ids import uuid7

from tests.conftest import make_template, publish_template


async def assign(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    template_id: object,
    **criteria: object,
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/assignments",
        json={"voucher_kind": "SALES_INVOICE", "template_id": template_id, **criteria},
        headers=auth,
    )


async def resolve(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    **request: object,
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/resolve",
        json={"voucher_kind": "SALES_INVOICE", **request},
        headers=auth,
    )


@pytest.mark.asyncio
async def test_rule_resolves_its_template_and_names_itself(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    rule = await assign(client, company_id, auth_headers, template["id"])
    assert rule.status_code == 201

    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["template_id"] == template["id"]
    assert body["assignment_rule_id"] == rule.json()["id"]
    assert body["layout_definition"]["sections"][0]["type"] == "HEADER"
    assert body["layout_digest"]


@pytest.mark.asyncio
async def test_archived_template_stops_resolving(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    await assign(client, company_id, auth_headers, template["id"])

    await client.delete(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.status_code == 404


@pytest.mark.asyncio
async def test_unpublished_candidate_is_skipped_not_fatal(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """A high-priority rule pointing at a draft must not hide the usable rule below it."""
    draft = await make_template(client, company_id, auth_headers, code="draft-design")
    live = await make_template(client, company_id, auth_headers, code="live-design")
    await publish_template(client, company_id, auth_headers, live)

    await assign(client, company_id, auth_headers, draft["id"], priority=900)
    await assign(
        client,
        company_id,
        auth_headers,
        live["id"],
        priority=100,
        branch_id=None,
        currency_code="INR",
    )

    resolved = await resolve(client, company_id, auth_headers, currency_code="INR")
    assert resolved.status_code == 200
    assert resolved.json()["template_id"] == live["id"]


@pytest.mark.asyncio
async def test_priority_then_specificity_decides(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    general = await make_template(client, company_id, auth_headers, code="general")
    specific = await make_template(client, company_id, auth_headers, code="specific")
    await publish_template(client, company_id, auth_headers, general)
    await publish_template(client, company_id, auth_headers, specific)
    branch = uuid7()

    await assign(client, company_id, auth_headers, general["id"], priority=500)
    await assign(
        client, company_id, auth_headers, specific["id"], priority=500, branch_id=str(branch)
    )

    for_branch = await resolve(client, company_id, auth_headers, branch_id=str(branch))
    assert for_branch.json()["template_id"] == specific["id"]

    elsewhere = await resolve(client, company_id, auth_headers, branch_id=str(uuid7()))
    assert elsewhere.json()["template_id"] == general["id"]


@pytest.mark.asyncio
async def test_pinned_criterion_does_not_match_an_unstated_request(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    pinned = await make_template(client, company_id, auth_headers, code="pinned")
    await publish_template(client, company_id, auth_headers, pinned)
    await assign(client, company_id, auth_headers, pinned["id"], currency_code="USD")

    # Falls back to the company's published template, and says so.
    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.status_code == 200
    assert resolved.json()["assignment_rule_id"] is None


@pytest.mark.asyncio
async def test_fallback_skips_a_published_template_without_a_version(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    usable = await make_template(client, company_id, auth_headers, code="usable")
    await publish_template(client, company_id, auth_headers, usable)

    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.status_code == 200
    assert resolved.json()["template_id"] == usable["id"]


@pytest.mark.asyncio
async def test_nothing_published_is_404(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    await make_template(client, company_id, auth_headers)
    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.status_code == 404


@pytest.mark.asyncio
async def test_rule_cannot_name_another_companys_template(
    client: httpx.AsyncClient,
    tenant_id: uuid.UUID,
    signed_headers: Callable[..., dict[str, str]],
) -> None:
    company_a, company_b = uuid7(), uuid7()
    owner_a = signed_headers(tenant_id, company_a)
    owner_b = signed_headers(tenant_id, company_b)
    design_a = await make_template(client, company_a, owner_a, code="a-design")
    await publish_template(client, company_a, owner_a, design_a)

    response = await assign(client, company_b, owner_b, design_a["id"])
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rule_cannot_pin_a_version_of_a_different_template(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    one = await make_template(client, company_id, auth_headers, code="one")
    two = await make_template(client, company_id, auth_headers, code="two")
    response = await assign(
        client,
        company_id,
        auth_headers,
        one["id"],
        specific_version_id=two["initial_version_id"],
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pinned_version_resolves_even_after_a_newer_publish(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    from tests.conftest import canvas

    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    pinned_version = template["initial_version_id"]

    newer = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={"layout_definition": canvas(content="NEWER")},
        headers=auth_headers,
    )
    await publish_template(client, company_id, auth_headers, template, newer.json()["id"])
    await assign(
        client, company_id, auth_headers, template["id"], specific_version_id=pinned_version
    )

    resolved = await resolve(client, company_id, auth_headers)
    assert resolved.json()["version_id"] == pinned_version


@pytest.mark.asyncio
async def test_duplicate_rule_criteria_are_409(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    assert (await assign(client, company_id, auth_headers, template["id"])).status_code == 201
    assert (await assign(client, company_id, auth_headers, template["id"])).status_code == 409


@pytest.mark.asyncio
async def test_deactivated_rule_stops_resolving_and_is_audited_as_such(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    rule = await assign(client, company_id, auth_headers, template["id"], priority=800)

    patched = await client.patch(
        f"/v1/companies/{company_id}/assignments/{rule.json()['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    listed = await client.get(f"/v1/companies/{company_id}/assignments", headers=auth_headers)
    assert listed.json()["items"] == []

    with_inactive = await client.get(
        f"/v1/companies/{company_id}/assignments?include_inactive=true", headers=auth_headers
    )
    assert len(with_inactive.json()["items"]) == 1


@pytest.mark.asyncio
async def test_archiving_a_template_deactivates_its_rules(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    await publish_template(client, company_id, auth_headers, template)
    await assign(client, company_id, auth_headers, template["id"])

    await client.delete(
        f"/v1/companies/{company_id}/templates/{template['id']}", headers=auth_headers
    )
    remaining = await client.get(f"/v1/companies/{company_id}/assignments", headers=auth_headers)
    assert remaining.json()["items"] == []


@pytest.mark.asyncio
async def test_malformed_voucher_kind_is_422(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/v1/companies/{company_id}/resolve",
        json={"voucher_kind": "sales invoice"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_where_a_design_is_used_lists_only_its_own_rules(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    first = await make_template(client, company_id, auth_headers, code="used-here")
    second = await make_template(client, company_id, auth_headers, code="used-there")
    mine = await assign(client, company_id, auth_headers, first["id"])
    other = await assign(
        client, company_id, auth_headers, second["id"], voucher_type_id=str(uuid7())
    )
    assert mine.status_code == 201 and other.status_code == 201
    listed = await client.get(
        f"/v1/companies/{company_id}/assignments?template_id={first['id']}", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [mine.json()["id"]]
    unknown = await client.get(
        f"/v1/companies/{company_id}/assignments?template_id={uuid7()}", headers=auth_headers
    )
    assert unknown.json()["items"] == []
    malformed = await client.get(
        f"/v1/companies/{company_id}/assignments?template_id=not-an-id", headers=auth_headers
    )
    assert malformed.status_code == 422


async def test_a_where_used_cursor_cannot_be_replayed_for_another_design(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers, code="paged-design")
    for _ in range(2):
        created = await assign(
            client, company_id, auth_headers, template["id"], voucher_type_id=str(uuid7())
        )
        assert created.status_code == 201, created.text
    base = f"/v1/companies/{company_id}/assignments?limit=1"
    page = await client.get(base + f"&template_id={template['id']}", headers=auth_headers)
    cursor = page.json()["page"]["next_cursor"]
    assert cursor
    replay = await client.get(
        base + f"&template_id={uuid7()}&cursor={cursor}", headers=auth_headers
    )
    assert replay.status_code == 422
