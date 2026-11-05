"""Multiple states, explicit registrations and default replacement through public APIs."""

import datetime as dt
from typing import Any

import httpx

from tests.conftest import headers
from tests.test_integrity_regressions import address_and_registration, day
from tests.test_masters import BASE, activate, post, prepare


async def address(client: httpx.AsyncClient, party_id: str, state: str) -> dict[str, Any]:
    row = await post(
        client,
        "/party-addresses",
        {
            "party_id": party_id,
            "label": state,
            "mailing_name": "Trading",
            "line1": "Sample address",
            "city": "Sample city",
            "country_code": "IN",
            "state_code": state,
            "postal_code": "400001",
        },
    )
    return await activate(client, "/party-addresses", row)


async def test_general_and_registration_defaults_coexist_and_replace_safely(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    party, office, registration = await address_and_registration(client, day(-10), None)
    general = {
        "party_id": party["id"],
        "address_id": office["id"],
        "purpose": "BILLING",
        "is_default": True,
    }
    old = await activate(
        client, "/party-address-uses", await post(client, "/party-address-uses", general)
    )
    scoped = await post(
        client, "/party-address-uses", general | {"registration_id": registration["id"]}
    )
    await activate(client, "/party-address-uses", scoped)
    delivery = await address(client, party["id"], "IN-KA")
    replacement = await post(
        client, "/party-address-uses", general | {"address_id": delivery["id"]}
    )
    denied = await client.post(
        BASE + "/party-address-uses/" + replacement["id"] + "/activate",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert denied.status_code == 409, denied.text
    await post(
        client,
        "/party-address-uses/" + old["id"] + "/deactivate",
        {"expected_version": old["row_version"]},
        status=200,
    )
    assert (await activate(client, "/party-address-uses", replacement))["status"] == "ACTIVE"
    # An interstate delivery remains a general address; no registration is inferred.
    assert replacement["registration_id"] is None


async def test_registration_links_require_matching_state_and_preserve_it(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    party, office, registration = await address_and_registration(client, day(-10), None)
    delivery = await address(client, party["id"], "IN-KA")
    link = {
        "party_id": party["id"],
        "registration_id": registration["id"],
        "address_id": delivery["id"],
        "valid_from": day(0),
    }
    denied = await client.post(BASE + "/party-registration-addresses", json=link, headers=headers())
    assert denied.status_code == 422, denied.text
    denied = await client.post(
        BASE + "/party-address-uses",
        json={
            "party_id": party["id"],
            "registration_id": registration["id"],
            "address_id": delivery["id"],
            "purpose": "REGISTERED",
        },
        headers=headers(),
    )
    assert denied.status_code == 422, denied.text
    await post(client, "/party-registration-addresses", link | {"address_id": office["id"]})
    denied = await client.patch(
        BASE + "/party-addresses/" + office["id"],
        json={"expected_version": office["row_version"], "state_code": "IN-KA"},
        headers=headers(),
    )
    assert denied.status_code == 409, denied.text


async def test_registration_address_lookup_is_explicit_and_date_bounded(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    party, office, registration = await address_and_registration(client, day(-10), None)
    link = await post(
        client,
        "/party-registration-addresses",
        {
            "party_id": party["id"],
            "registration_id": registration["id"],
            "address_id": office["id"],
            "valid_from": day(1),
            "valid_to": day(10),
        },
    )
    for offset, expected in [(0, []), (1, [link["id"]]), (10, [link["id"]]), (11, [])]:
        response = await client.get(
            BASE + "/party-registration-addresses",
            params={
                "address_id": office["id"],
                "registration_id": registration["id"],
                "as_of": day(offset),
            },
            headers=headers(),
        )
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()["items"]] == expected
    unsupported = await client.get(
        BASE + "/parties", params={"as_of": dt.date.today().isoformat()}, headers=headers()
    )
    assert unsupported.status_code == 422
