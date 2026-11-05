"""Field policy, tenant layout and bounded-query enforcement, all server-side.

A hidden or renamed field is layout; a blocked field is policy. These are separate mechanisms
and the API must keep them separate: layout never denies, policy never renders.
"""

import datetime as dt
from typing import Any

import httpx

from tests.conftest import COMPANY, headers
from tests.test_masters import BASE, new_party, party, prepare


def policy(
    field_key: Any,
    access: Any = "read",
    effect: Any = "deny",
    condition: Any = None,
    entity: str = "accounting.party",
) -> dict[str, Any]:
    return {
        "entity_type": entity,
        "field_key": field_key,
        "access": access,
        "effect": effect,
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": condition,
    }


def layout(field_key: str, **overrides: Any) -> dict[str, Any]:
    return {"entity_type": "accounting.party", "field_key": field_key} | overrides


async def test_read_deny_removes_the_field_from_detail_list_and_field_set(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    abc = await party(client)
    h = headers(policies=[policy("legal_name")])

    detail = await client.get(BASE + f'/parties/{abc["id"]}', headers=h)
    assert detail.status_code == 200 and "legal_name" not in detail.json()
    described = await client.get(BASE + "/parties/field-set", headers=h)
    fields = {row["key"]: row for row in described.json()["fields"]}
    assert fields["legal_name"]["readable"] is False
    assert fields["legal_name"]["writable"] is True


async def test_write_deny_blocks_the_changed_field_only(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    h = headers(policies=[policy("name", access="write")])

    blocked = await client.patch(
        BASE + f'/parties/{abc["id"]}',
        json={"expected_version": abc["row_version"], "name": "Renamed"},
        headers=h,
    )
    assert blocked.status_code == 403, blocked.text
    # An untouched denied field must not block an otherwise permitted edit.
    allowed = await client.patch(
        BASE + f'/parties/{abc["id"]}',
        json={"expected_version": abc["row_version"], "notes": "reviewed"},
        headers=h,
    )
    assert allowed.status_code == 200, allowed.text
    described = await client.get(BASE + "/parties/field-set", headers=h)
    fields = {row["key"]: row for row in described.json()["fields"]}
    assert fields["name"]["writable"] is False and fields["name"]["readable"] is True


async def test_denying_structural_identity_fails_closed(client: httpx.AsyncClient) -> None:
    """A resource whose identity is unreadable cannot be rendered at all, so the read is
    refused rather than answered with a row missing its own primary key."""
    await prepare(client)
    result = await client.get(BASE + "/parties", headers=headers(policies=[policy("id")]))
    assert result.status_code == 403, result.text


async def test_a_policy_naming_an_unknown_field_or_effect_is_refused(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    await party(client)
    for broken in (
        policy("not_a_field"),
        policy("legal_name", access="execute"),
        policy("legal_name", effect="maybe"),
    ):
        result = await client.get(BASE + "/parties", headers=headers(policies=[broken]))
        assert result.status_code == 403, result.text
    # A policy for another entity is not this resource's business. Read it from the detail
    # endpoint, since the lean list item never carries legal_name in the first place.
    other = policy("legal_name", entity="accounting.account")
    abc = (await client.get(BASE + "/parties", headers=headers())).json()["items"][0]
    result = await client.get(BASE + f'/parties/{abc["id"]}', headers=headers(policies=[other]))
    assert result.status_code == 200, result.text
    assert "legal_name" in result.json()


async def test_a_policy_carrying_a_non_string_value_fails_closed(client: httpx.AsyncClient) -> None:
    """Every shape check here is a membership or parse test, and both raise on a value of the
    wrong type. An unevaluable policy must deny with the error envelope, never surface a 500."""
    await prepare(client)
    await party(client)
    broken = (
        policy(["legal_name"]),
        policy("legal_name", access={"read": True}),
        policy("legal_name", effect=["deny"]),
        policy("legal_name") | {"scope_type": ["company"]},
        policy("legal_name") | {"scope_id": 7},
        policy("legal_name") | {"scope_id": "not-a-uuid"},
        {"entity_type": "accounting.party", "field_key": "legal_name"},
    )
    for candidate in broken:
        result = await client.get(BASE + "/parties", headers=headers(policies=[candidate]))
        assert result.status_code == 403, (candidate, result.text)
        assert set(result.json()) == {"error"}, result.text


async def test_a_conditional_deny_applies_only_to_matching_rows(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    condition = {"field": "party_type", "cmp": "eq", "value": "PERSON"}
    h = headers(policies=[policy("legal_name", condition=condition)])
    # The seeded party is an organisation, so the condition does not match and the field shows.
    detail = await client.get(BASE + f'/parties/{abc["id"]}', headers=h)
    assert detail.status_code == 200 and "legal_name" in detail.json()

    matching = {"field": "party_type", "cmp": "eq", "value": "ORGANISATION"}
    hidden = await client.get(
        BASE + f'/parties/{abc["id"]}',
        headers=headers(policies=[policy("legal_name", condition=matching)]),
    )
    assert hidden.status_code == 200 and "legal_name" not in hidden.json()


async def test_a_conditional_allow_cannot_be_evaluated_without_row_values(
    client: httpx.AsyncClient,
) -> None:
    """Listing has no single row to test a condition against, so a conditional allow is skipped
    and a conditional deny still applies — the safe direction in both cases."""
    await prepare(client)
    await party(client)
    condition = {"field": "party_type", "cmp": "eq", "value": "PERSON"}
    granted = headers(policies=[policy("legal_name", effect="allow", condition=condition)])
    result = await client.get(BASE + "/parties", headers=granted)
    assert result.status_code == 200, result.text

    denied = headers(policies=[policy("code", condition=condition)])
    result = await client.get(BASE + "/parties", headers=denied)
    assert result.status_code == 200 and "code" not in result.json()["items"][0]


async def test_layout_marks_a_field_required_and_renames_it_without_denying_it(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    layouts = [layout("notes", is_required=True, label_override="Internal note")]
    described = await client.get(BASE + "/parties/field-set", headers=headers(layouts=layouts))
    fields = {row["key"]: row for row in described.json()["fields"]}
    assert fields["notes"]["required"] is True
    assert fields["notes"]["label"] == "Internal note"

    body = {
        "code": "NOTE",
        "name": "Note",
        "legal_name": "Note Ltd",
        "country_code": "IN",
        "role": "SUPPLIER",
    }
    missing = await client.post(
        BASE + "/parties/create-with-details", json=body, headers=headers(layouts=layouts)
    )
    assert missing.status_code == 422, missing.text
    assert "a configured required field is missing" in missing.text
    # The same party with the required note is accepted, so the 422 above was the layout's.
    filled = await client.post(
        BASE + "/parties/create-with-details",
        json=body | {"notes": "present"},
        headers=headers(layouts=layouts),
    )
    assert filled.status_code == 201, filled.text


async def test_a_hidden_field_is_layout_not_authorization(client: httpx.AsyncClient) -> None:
    """§6.15: hiding a field is presentation. The API still accepts it and still returns it."""
    await prepare(client)
    layouts = [layout("notes", is_visible=False)]
    described = await client.get(BASE + "/parties/field-set", headers=headers(layouts=layouts))
    fields = {row["key"]: row for row in described.json()["fields"]}
    assert fields["notes"]["visible"] is False and fields["notes"]["writable"] is True

    created = await new_party(
        client,
        code="HID",
        name="Hidden",
        legal_name="Hidden Ltd",
        notes="still stored",
        h=headers(layouts=layouts),
    )
    assert created["notes"] == "still stored"


async def test_list_filters_search_and_sort_stay_within_the_resource(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    await party(client)
    h = headers()
    # A filter the resource does not define is rejected rather than silently ignored.
    unsupported = await client.get(BASE + "/accounting-setup?status=ACTIVE", headers=h)
    assert unsupported.status_code == 422, unsupported.text
    # Neither is a text search on a resource with nothing indexed to search.
    unsearchable = await client.get(BASE + "/accounting-setup?q=any", headers=h)
    assert unsearchable.status_code == 422, unsearchable.text

    hit = await client.get(BASE + "/parties?q=ABC", headers=h)
    assert hit.status_code == 200 and len(hit.json()["items"]) == 1
    miss = await client.get(BASE + "/parties?q=ZZZ", headers=h)
    assert miss.status_code == 200 and miss.json()["items"] == []

    # Search reads the indexed columns, so denying one of them must deny the search.
    denied = await client.get(BASE + "/parties?q=ABC", headers=headers(policies=[policy("name")]))
    assert denied.status_code == 403, denied.text

    sorted_page = await client.get(BASE + "/parties?sort=-name", headers=h)
    assert sorted_page.status_code == 200, sorted_page.text
    unsortable = await client.get(BASE + "/parties?sort=notes", headers=h)
    assert unsortable.status_code == 422, unsortable.text


async def test_read_denies_hold_in_exports_and_history(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    h = headers(policies=[policy("legal_name")])
    export = await client.get(BASE + "/exports/parties", headers=h)
    assert export.status_code == 200 and "legal_name" not in export.json()["items"][0]
    assert export.headers["cache-control"] == "no-store"

    unknown = await client.get(BASE + "/exports/not-a-resource", headers=headers())
    assert unknown.status_code == 404, unknown.text
    unknown = await client.get(BASE + f'/history/not-a-resource/{abc["id"]}', headers=headers())
    assert unknown.status_code == 404, unknown.text

    without_scope = headers(permissions={"accounting.party.read", "accounting.party.manage"})
    assert (await client.get(BASE + "/exports/parties", headers=without_scope)).status_code == 403
    history = BASE + f'/history/parties/{abc["id"]}'
    assert (await client.get(history, headers=without_scope)).status_code == 403


async def test_history_pages_by_signed_cursor(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    await client.patch(
        BASE + f'/parties/{abc["id"]}',
        json={"expected_version": abc["row_version"], "notes": "amended"},
        headers=headers(),
    )
    first = await client.get(BASE + f'/history/parties/{abc["id"]}?limit=1', headers=headers())
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 1 and first.json()["page"]["has_more"] is True
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        BASE + f'/history/parties/{abc["id"]}?limit=1&cursor={cursor}', headers=headers()
    )
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
    entries = {row["action"] for row in second.json()["items"]}
    assert entries <= {"create", "update", "activate", "deactivate"}
    assert dt.date.fromisoformat(second.json()["items"][0]["created_at"][:10]) <= dt.date.today()
