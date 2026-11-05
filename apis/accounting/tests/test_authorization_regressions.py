"""Field policy must see the full record on every read and write entry point."""

from typing import Any

import httpx
import pytest

from tests.conftest import headers
from tests.test_field_policy import layout, policy
from tests.test_masters import BASE, activate, new_party, post, prepare


@pytest.mark.parametrize(
    "path,permissions",
    [
        ("parties", {"accounting.party.read"}),
        ("account-heads", {"accounting.head.read", "accounting.head.manage"}),
    ],
)
async def test_field_set_does_not_offer_unavailable_writes(
    client: httpx.AsyncClient, path: str, permissions: set[str] | frozenset[str]
) -> None:
    response = await client.get(
        BASE + f"/{path}/field-set", headers=headers(permissions=permissions)
    )
    assert response.status_code == 200, response.text
    assert response.json()["fields"]
    assert all(not field["writable"] for field in response.json()["fields"])


async def review_party(client: httpx.AsyncClient) -> dict[str, Any]:
    """An active party with its role and account: a party is never created as a draft any more."""
    await prepare(client)
    return await new_party(
        client, code="REVIEW", name="Review", legal_name="Review", notes="Present"
    )


async def draft_address(client: httpx.AsyncClient) -> dict[str, Any]:
    """A DRAFT address of the review party: parties have no draft step left, addresses still do."""
    party = await review_party(client)
    return await post(
        client,
        "/party-addresses",
        {
            "party_id": party["id"],
            "label": "Office",
            "mailing_name": "Review",
            "line1": "1 Road",
            "city": "Mumbai",
            "country_code": "IN",
            "state_code": "IN-MH",
            "postal_code": "400001",
        },
    )


async def test_active_record_write_condition_cannot_be_bypassed(client: httpx.AsyncClient) -> None:
    row = await review_party(client)
    h = headers(
        policies=[
            policy(
                "notes",
                access="write",
                condition={
                    "field": "status",
                    "cmp": "eq",
                    "value": "ACTIVE",
                },
            )
        ]
    )
    result = await client.patch(
        BASE + f'/parties/{row["id"]}',
        headers=h,
        json={"expected_version": row["row_version"], "notes": "Denied"},
    )
    assert result.status_code == 403, result.text
    current = (await client.get(BASE + f'/parties/{row["id"]}', headers=headers())).json()
    assert current["notes"] == "Present" and current["row_version"] == row["row_version"]


async def test_transition_condition_has_non_status_fields(client: httpx.AsyncClient) -> None:
    # A party is created active, so the draft-to-active transition is exercised on an address.
    row = await draft_address(client)
    result = await client.post(
        BASE + f'/party-addresses/{row["id"]}/activate',
        json={"expected_version": row["row_version"]},
        headers=headers(
            policies=[
                policy(
                    "status",
                    access="write",
                    entity="accounting.party_address",
                    condition={
                        "field": "country_code",
                        "cmp": "eq",
                        "value": "IN",
                    },
                )
            ]
        ),
    )
    assert result.status_code == 403, result.text
    # Without the policy the same transition is allowed, so the 403 above was the policy's.
    assert (await activate(client, "/party-addresses", row))["status"] == "ACTIVE"


async def test_uuid_condition_holds_in_detail_and_replay(client: httpx.AsyncClient) -> None:
    party = await review_party(client)
    h = headers()
    contact = await post(
        client,
        "/party-contacts",
        {
            "party_id": party["id"],
            "name": "Contact",
            "email": "contact@example.test",
        },
        h=h,
    )
    denied = headers(
        key=h["Idempotency-Key"],
        policies=[
            policy(
                "email",
                condition={
                    "field": "party_id",
                    "cmp": "eq",
                    "value": party["id"],
                },
                entity="accounting.party_contact",
            )
        ],
    )
    detail = await client.get(BASE + f'/party-contacts/{contact["id"]}', headers=denied)
    assert detail.status_code == 200 and "email" not in detail.json(), detail.text
    replay = await client.post(
        BASE + "/party-contacts",
        headers=denied,
        json={
            "party_id": party["id"],
            "name": "Contact",
            "email": "contact@example.test",
        },
    )
    assert replay.status_code == 201 and "email" not in replay.json(), replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"


async def test_required_layout_uses_complete_record_on_activation(
    client: httpx.AsyncClient,
) -> None:
    # The activation request carries only the expected version, so the required `line1` can only
    # be seen on the stored record. A party is created active, so the draft is an address.
    row = await draft_address(client)
    required = layout("line1", is_required=True) | {"entity_type": "accounting.party_address"}
    activated = await activate(client, "/party-addresses", row, h=headers(layouts=[required]))
    assert activated["status"] == "ACTIVE" and activated["line1"] == "1 Road"


async def test_chart_initialization_cannot_bypass_status_write_policy(
    client: httpx.AsyncClient,
) -> None:
    result = await client.post(
        BASE + "/accounting-setup/initialize",
        json={},
        headers=headers(policies=[policy("status", access="write", entity="accounting.account")]),
    )
    assert result.status_code == 403, result.text
    assert not (await client.get(BASE + "/accounts", headers=headers())).json()["items"]
    assert not (await client.get(BASE + "/account-groups", headers=headers())).json()["items"]


async def test_history_enforces_identity_and_changed_field_read_denies(
    client: httpx.AsyncClient,
) -> None:
    row = await review_party(client)
    url = BASE + f'/history/parties/{row["id"]}'
    denied = await client.get(url, headers=headers(policies=[policy("id")]))
    assert denied.status_code == 403, denied.text
    filtered = await client.get(url, headers=headers(policies=[policy("notes")]))
    assert filtered.status_code == 200, filtered.text
    assert all("notes" not in revision["changed_fields"] for revision in filtered.json()["items"])


async def test_decimal_membership_policy_ignores_storage_scale(client: httpx.AsyncClient) -> None:
    await post(client, "/accounting-setup/initialize", {}, status=200)
    term = await post(client, "/payment-terms", {"code": "P", "name": "Payment"})
    line = await post(
        client,
        "/payment-term-lines",
        {
            "payment_term_id": term["id"],
            "sequence": 1,
            "percentage": "100",
            "days": 30,
        },
    )
    response = await client.get(
        BASE + f'/payment-term-lines/{line["id"]}',
        headers=headers(
            policies=[
                policy(
                    "days",
                    entity="accounting.payment_term_line",
                    condition={"field": "percentage", "cmp": "in", "value": ["100"]},
                )
            ]
        ),
    )
    assert response.status_code == 200 and "days" not in response.json(), response.text


async def test_pattern_policy_uses_pattern_as_pattern(client: httpx.AsyncClient) -> None:
    row = await review_party(client)
    response = await client.get(
        BASE + f'/parties/{row["id"]}',
        headers=headers(
            policies=[
                policy(
                    "notes", condition={"field": "status", "cmp": "matches", "value": "ACT[A-Z]{3}"}
                )
            ]
        ),
    )
    assert response.status_code == 200 and "notes" not in response.json(), response.text


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "unknown", "cmp": "eq", "value": "x"},
        {"field": "status", "cmp": "eq", "value": {"invalid": True}},
    ],
)
async def test_malformed_policy_fails_with_an_error_envelope(
    client: httpx.AsyncClient, condition: Any
) -> None:
    row = await review_party(client)
    response = await client.get(
        BASE + f'/parties/{row["id"]}',
        headers=headers(policies=[policy("notes", condition=condition)]),
    )
    assert response.status_code == 403, response.text
    assert set(response.json()) == {"error"}


async def test_initialization_honours_user_field_denies(client: httpx.AsyncClient) -> None:
    response = await client.post(
        BASE + "/accounting-setup/initialize",
        json={},
        headers=headers(
            policies=[policy("base_currency", access="write", entity="accounting.accounting_setup")]
        ),
    )
    assert response.status_code == 403, response.text
    assert not (await client.get(BASE + "/accounting-setup", headers=headers())).json()["items"]


async def test_template_condition_sees_its_system_key(client: httpx.AsyncClient) -> None:
    response = await client.post(
        BASE + "/accounting-setup/initialize",
        json={},
        headers=headers(
            policies=[
                policy(
                    "name",
                    access="write",
                    entity="accounting.account",
                    condition={"field": "system_key", "cmp": "eq", "value": "account.CASH_MAIN"},
                )
            ]
        ),
    )
    assert response.status_code == 403, response.text


async def test_create_condition_does_not_evaluate_a_nonexistent_prior_record(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    row = await new_party(
        client,
        code="INDIAN",
        name="Indian",
        legal_name="Indian",
        h=headers(
            policies=[
                policy(
                    "name",
                    access="write",
                    condition={"field": "country_code", "cmp": "ne", "value": "IN"},
                )
            ]
        ),
    )
    assert row["country_code"] == "IN"
