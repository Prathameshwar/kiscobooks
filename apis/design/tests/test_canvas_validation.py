"""What a layout may contain.

These are the injection tests. The canvas is stored verbatim and later compiled into a
document, so anything this module lets through is something a renderer would have to
defend against — and the renderer is not the right place for that defence.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.ids import uuid7

from design.schemas.canvas import CanvasV10
from tests.conftest import canvas, make_template

pytestmark = pytest.mark.asyncio


async def save(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    auth: dict[str, str],
    template_id: object,
    layout: dict[str, object],
) -> httpx.Response:
    return await client.post(
        f"/v1/companies/{company}/templates/{template_id}/versions",
        json={"layout_definition": layout},
        headers=auth,
    )


async def test_unknown_keys_are_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    hostile = canvas()
    hostile["evil_root"] = "<script>alert(1)</script>"
    response = await save(client, company_id, auth_headers, template["id"], hostile)
    assert response.status_code == 422


async def test_unknown_style_keys_are_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    sections: list[dict[str, object]] = layout["sections"]  # type: ignore[assignment]
    elements: list[dict[str, object]] = sections[0]["elements"]  # type: ignore[assignment]
    elements[0]["style"] = {"expression": "expression(alert(1))"}
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_colour_must_be_a_hex_triple(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    layout["theme"] = {"primary_color": "url(http://169.254.169.254/)"}
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_font_family_rejects_a_stylesheet_payload(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    layout["theme"] = {"font_family": "Inter'; src: url(http://evil/f.woff2)"}
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_binding_path_must_come_from_the_allowlist(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    sections: list[dict[str, object]] = layout["sections"]  # type: ignore[assignment]
    elements: list[dict[str, object]] = sections[0]["elements"]  # type: ignore[assignment]
    elements[0]["binding_path"] = "secrets.signing_key"
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_allowed_binding_path_is_accepted(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    sections: list[dict[str, object]] = layout["sections"]  # type: ignore[assignment]
    elements: list[dict[str, object]] = sections[0]["elements"]  # type: ignore[assignment]
    elements[0] |= {"type": "FIELD_BINDING", "binding_path": "voucher.document_number"}
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 201


async def test_compiled_markup_is_not_an_accepted_field(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """The service stores no precompiled document body, so the field does not exist."""
    template = await make_template(client, company_id, auth_headers)
    response = await client.post(
        f"/v1/companies/{company_id}/templates/{template['id']}/versions",
        json={
            "layout_definition": canvas(),
            "compiled_html_template": "<script>alert(1)</script>",
            "compiled_css": "body{background:url(http://169.254.169.254/)}",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_section_and_element_counts_are_bounded(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout: dict[str, object] = {
        "schema_version": "1.0.0",
        "sections": [{"id": f"s{index}", "type": "CUSTOM", "elements": []} for index in range(41)],
    }
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_unknown_schema_version_is_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    layout["schema_version"] = "2.0.0"
    response = await save(client, company_id, auth_headers, template["id"], layout)
    assert response.status_code == 422


async def test_layout_cannot_reference_an_unknown_asset(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    response = await save(
        client, company_id, auth_headers, template["id"], canvas(asset_id=str(uuid7()))
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_layout_cannot_reference_an_unknown_component(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    response = await save(
        client, company_id, auth_headers, template["id"], canvas(component_code="absent")
    )
    assert response.status_code == 422


async def test_canvas_defaults_are_a_valid_layout() -> None:
    """The domain rule with no database at all: an empty canvas is well-formed."""
    layout = CanvasV10()
    assert layout.sections == []
    assert layout.page.size == "A4"
    assert layout.theme.primary_color.startswith("#")


async def test_free_form_property_maps_are_refused(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    """A dict with an arbitrary key set is ``extra="allow"`` under another name.

    `src`, `style` and `href` are exactly the keys a renderer may treat as structural,
    so element options are typed fields and there is no open map to put them in.
    """
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    sections: list[dict[str, object]] = layout["sections"]  # type: ignore[assignment]
    elements: list[dict[str, object]] = sections[0]["elements"]  # type: ignore[assignment]
    elements[0]["props"] = {"src": "javascript:alert(1)", "style": "background:url(http://x/)"}
    assert (await save(client, company_id, auth_headers, template["id"], layout)).status_code == 422

    layout_with_metadata = canvas()
    layout_with_metadata["metadata"] = {"note": "</style><script>fetch('http://evil')</script>"}
    rejected = await save(client, company_id, auth_headers, template["id"], layout_with_metadata)
    assert rejected.status_code == 422


async def test_typed_element_options_are_accepted(
    client: httpx.AsyncClient, company_id: uuid.UUID, auth_headers: dict[str, str]
) -> None:
    template = await make_template(client, company_id, auth_headers)
    layout = canvas()
    sections: list[dict[str, object]] = layout["sections"]  # type: ignore[assignment]
    elements: list[dict[str, object]] = sections[0]["elements"]  # type: ignore[assignment]
    elements[0] |= {"type": "QR_CODE", "symbology": "QR", "show_value": False}
    assert (await save(client, company_id, auth_headers, template["id"], layout)).status_code == 201


async def test_binding_roots_and_pattern_cannot_drift() -> None:
    """The regex is the enforcement, so it is built from the documented root list."""
    from design.schemas.canvas import BINDING_ROOTS, CanvasElement

    for root in BINDING_ROOTS:
        element = CanvasElement.model_validate(
            {
                "id": "e1",
                "type": "FIELD_BINDING",
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "binding_path": f"{root}.field_name",
            }
        )
        assert element.binding_path is not None
