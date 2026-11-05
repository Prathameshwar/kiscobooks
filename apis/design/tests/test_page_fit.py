"""A layout may not be bigger than the paper it prints on.

The one 1.1.0 rule that cannot live in the canvas model: it needs the template **row**, because
1.1.0 took paper size out of the tree and the row is now the only place that knows how big the
sheet is (docs/invoice-design.md §4.2 and the decision log).

What it deliberately does *not* do is police crowding. An element 2mm inside the margin is a
**warning**, and the editor lists warnings at the moment of publication where a person can
decide; a 422 cannot make that decision for them. Only a box off the edge of the sheet is
refused, because nothing can print it.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import make_template

pytestmark = pytest.mark.asyncio


def layout(
    *, element_width: float = 150.0, element_y: float = 10.0, height: float = 40.0
) -> dict[str, object]:
    return {
        "schema_version": "1.1.0",
        "sections": [
            {
                "id": "sec_body",
                "type": "ITEM_TABLE",
                "x": 10.0,
                "y": element_y,
                "width": element_width,
                "height": height,
                "elements": [
                    {
                        "id": "el_items",
                        "type": "TEXT",
                        "x": 10.0,
                        "y": element_y,
                        "width": element_width,
                        "height": height,
                        "content": "Particulars",
                    }
                ],
            }
        ],
    }


async def save(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    template_id: object,
    body: dict[str, object],
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/templates/{template_id}/versions",
        json={"layout_definition": body},
        headers=auth,
    )


async def paper(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    *,
    code: str,
    size: str,
    orientation: str = "PORTRAIT",
    width: str | None = None,
    height: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": code,
        "code": code,
        "paper_size": size,
        "page_orientation": orientation,
    }
    if width is not None:
        payload["page_width_mm"] = width
    if height is not None:
        payload["page_height_mm"] = height
    response = await client.post(f"/v1/companies/{company}/templates", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_a_layout_within_its_page_is_accepted(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await paper(client, company_id, auth_headers, code="fit-a4", size="A4")
    response = await save(client, company_id, auth_headers, template["id"], layout())
    assert response.status_code == 201, response.text


async def test_a_layout_wider_than_its_page_is_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await paper(client, company_id, auth_headers, code="wide-a4", size="A4")
    response = await save(
        client, company_id, auth_headers, template["id"], layout(element_width=240.0)
    )
    assert response.status_code == 422, response.text
    assert "fit the paper" in response.text


async def test_a_layout_longer_than_its_page_is_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await paper(client, company_id, auth_headers, code="long-a4", size="A4")
    response = await save(client, company_id, auth_headers, template["id"], layout(element_y=280.0))
    assert response.status_code == 422, response.text


async def test_an_a4_column_set_does_not_fit_an_80mm_roll(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """The failure a counter actually hits: reusing an A4 design on the receipt printer."""
    template = await paper(client, company_id, auth_headers, code="roll-80", size="THERMAL_80MM")
    assert (
        await save(client, company_id, auth_headers, template["id"], layout())
    ).status_code == 422
    narrow = layout(element_width=60.0)
    assert (await save(client, company_id, auth_headers, template["id"], narrow)).status_code == 201


async def test_a_continuous_roll_has_no_length_to_overflow(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """A receipt printer feeds as far as the content goes, so only its width is bounded."""
    template = await paper(client, company_id, auth_headers, code="roll-long", size="THERMAL_80MM")
    tall = layout(element_width=60.0, element_y=900.0)
    assert (await save(client, company_id, auth_headers, template["id"], tall)).status_code == 201


async def test_landscape_swaps_the_bound(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """260mm across is impossible on portrait A4 and ordinary on landscape."""
    portrait = await paper(client, company_id, auth_headers, code="port-a4", size="A4")
    wide = layout(element_width=260.0)
    assert (await save(client, company_id, auth_headers, portrait["id"], wide)).status_code == 422

    landscape = await paper(
        client, company_id, auth_headers, code="land-a4", size="A4", orientation="LANDSCAPE"
    )
    assert (await save(client, company_id, auth_headers, landscape["id"], wide)).status_code == 201


async def test_custom_paper_is_measured_from_the_row(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await paper(
        client,
        company_id,
        auth_headers,
        code="custom-200",
        size="CUSTOM",
        width="200.0000",
        height="150.0000",
    )
    assert (
        await save(client, company_id, auth_headers, template["id"], layout(element_width=170.0))
    ).status_code == 201
    assert (
        await save(client, company_id, auth_headers, template["id"], layout(element_width=200.0))
    ).status_code == 422


async def test_a_hair_over_is_rounding_not_a_defect(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """Layout geometry is ``float``; a tenth of a millimetre is arithmetic, not a mistake."""
    template = await paper(client, company_id, auth_headers, code="edge-a4", size="A4")
    exact = layout(element_width=200.0)  # 10mm + 200mm = 210mm, exactly A4
    assert (await save(client, company_id, auth_headers, template["id"], exact)).status_code == 201


async def test_the_rule_does_not_reach_back_into_1_0_0(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """1.0.0 is frozen in behaviour too: a layout that saved yesterday still saves today.

    A stored version is re-read on every resolve, so a new rejection applied to the old shape
    would not just block new saves — it would break reprints of already published documents.
    """
    template = await make_template(client, company_id, auth_headers, code="legacy-a4")
    oversized = {
        "schema_version": "1.0.0",
        "sections": [
            {
                "id": "sec",
                "type": "HEADER",
                "elements": [
                    {
                        "id": "el",
                        "type": "TEXT",
                        "x": 10.0,
                        "y": 10.0,
                        "width": 900.0,
                        "height": 40.0,
                        "content": "Wider than any sheet",
                    }
                ],
            }
        ],
    }
    response = await save(client, company_id, auth_headers, template["id"], oversized)
    assert response.status_code == 201, response.text


async def test_an_unprintable_first_version_rolls_the_template_back(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """The create path checks after the row exists, so the whole transaction has to unwind."""
    response = await client.post(
        f"/v1/companies/{company_id}/templates",
        json={
            "name": "born-broken",
            "code": "born-broken",
            "paper_size": "A5",
            "initial_canvas": layout(element_width=200.0),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text

    listed = await client.get(f"/v1/companies/{company_id}/templates", headers=auth_headers)
    assert listed.status_code == 200
    assert all(item["code"] != "born-broken" for item in listed.json()["items"])
