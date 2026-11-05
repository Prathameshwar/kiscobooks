"""What a design is for (designer plan P1, 2026-11-03).

A template may say which voucher kind it prints and whether its lines are products, accounts or
both. Routing honours it: a rule cannot point a kind at a design made for another, resolution
never falls back to one, and a design cannot be re-purposed while rules still print the old kind
on it. A template that never said stays routable by any kind, as before.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import canvas, publish_template
from tests.test_resolution import assign, resolve


async def designed(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    code: str,
    **context: object,
) -> dict[str, object]:
    response = await client.post(
        f"/v1/companies/{company}/templates",
        json={"name": code, "code": code, "initial_canvas": canvas(), **context},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


@pytest.mark.asyncio
async def test_a_template_records_its_kind_and_lines(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    created = await designed(
        client,
        company_id,
        auth_headers,
        "goods-bill",
        voucher_kind="PURCHASE",
        line_profile="ITEMS",
    )
    assert (created["voucher_kind"], created["line_profile"]) == ("PURCHASE", "ITEMS")
    detail = await client.get(
        f"/v1/companies/{company_id}/templates/{created['id']}", headers=auth_headers
    )
    assert (detail.json()["voucher_kind"], detail.json()["line_profile"]) == ("PURCHASE", "ITEMS")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        {"line_profile": "ITEMS"},
        {"voucher_kind": "PURCHASE", "line_profile": "BOTH"},
        {"voucher_kind": "purchase"},
    ],
)
async def test_a_line_profile_needs_its_kind_and_both_use_their_vocabulary(
    client: httpx.AsyncClient,
    company_id: uuid.UUID,
    auth_headers: dict[str, str],
    context: dict[str, object],
) -> None:
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={"name": "x", "code": "x-ctx", **context},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_listing_by_kind_keeps_designs_for_that_kind_and_unstated_ones(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    purchase = await designed(client, company_id, auth_headers, "p-bill", voucher_kind="PURCHASE")
    sales = await designed(client, company_id, auth_headers, "s-bill", voucher_kind="SALES")
    plain = await designed(client, company_id, auth_headers, "plain")
    listed = await client.get(
        f"/v1/companies/{company_id}/templates?voucher_kind=PURCHASE", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    ids = {row["id"] for row in listed.json()["items"]}
    assert ids == {purchase["id"], plain["id"]} and sales["id"] not in ids
    assert {row["voucher_kind"] for row in listed.json()["items"]} == {"PURCHASE", None}


@pytest.mark.asyncio
async def test_a_rule_cannot_route_another_kind_to_a_design_made_for_one(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    purchase = await designed(client, company_id, auth_headers, "p-only", voucher_kind="PURCHASE")
    refused = await assign(client, company_id, auth_headers, purchase["id"])
    assert refused.status_code == 422
    assert "designed for PURCHASE" in refused.text
    accepted = await assign(
        client, company_id, auth_headers, purchase["id"], voucher_kind="PURCHASE"
    )
    assert accepted.status_code == 201, accepted.text
    plain = await designed(client, company_id, auth_headers, "any-kind")
    assert (await assign(client, company_id, auth_headers, plain["id"])).status_code == 201


@pytest.mark.asyncio
async def test_resolution_never_falls_back_to_a_design_for_another_kind(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    purchase = await designed(client, company_id, auth_headers, "p-live", voucher_kind="PURCHASE")
    await publish_template(client, company_id, auth_headers, purchase)
    # The only published design is Purchase's: a sales invoice has nothing to print on.
    assert (await resolve(client, company_id, auth_headers)).status_code == 404
    found = await resolve(client, company_id, auth_headers, voucher_kind="PURCHASE")
    assert found.status_code == 200 and found.json()["template_id"] == purchase["id"]


@pytest.mark.asyncio
async def test_a_design_is_not_repurposed_while_rules_print_the_old_kind_on_it(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    plain = await designed(client, company_id, auth_headers, "repurpose")
    assert (await assign(client, company_id, auth_headers, plain["id"])).status_code == 201
    path = f"/v1/companies/{company_id}/templates/{plain['id']}"
    blocked = await client.put(path, json={"voucher_kind": "PURCHASE"}, headers=auth_headers)
    assert blocked.status_code == 409, blocked.text
    # Naming the kind its rules already print is no change of purpose.
    allowed = await client.put(
        path, json={"voucher_kind": "SALES_INVOICE", "line_profile": "MIXED"}, headers=auth_headers
    )
    assert allowed.status_code == 200, allowed.text
    assert (allowed.json()["voucher_kind"], allowed.json()["line_profile"]) == (
        "SALES_INVOICE",
        "MIXED",
    )
