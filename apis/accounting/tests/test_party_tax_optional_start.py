"""Open-start party registrations retain effective history and overlap protection."""

import datetime as dt
from typing import Any

import httpx
import pytest
from billing_platform.errors import ConflictError, ValidationFailedError

from accounting.domain.rules import (
    guard_effective_edit,
    overlapping,
    require_contained_interval,
    validate_values,
)
from tests.conftest import headers
from tests.test_integrity_regressions import day
from tests.test_masters import BASE, party, post, prepare
from tests.test_party_creation import draft


@pytest.mark.parametrize("explicit_null", [False, True])
async def test_aggregate_accepts_unspecified_tax_start(
    client: httpx.AsyncClient, explicit_null: bool
) -> None:
    await prepare(client)
    body = draft()
    body["tax_registration"] = {
        "scheme": "GST_IN", "registration_type": "UNREGISTERED",
        "country_code": "IN", "state_code": "IN-MH",
    }
    if explicit_null:
        body["tax_registration"]["valid_from"] = None
    await post(client, "/parties/create-with-details", body)
    rows = (await client.get(BASE + "/party-tax-registrations", headers=headers())).json()["items"]
    assert len(rows) == 1 and rows[0]["valid_from"] is None


@pytest.mark.parametrize("open_first", [False, True])
async def test_native_open_start_overlap_asof_and_history(
    client: httpx.AsyncClient, open_first: bool
) -> None:
    await prepare(client)
    owner = await party(client)
    values: dict[str, Any] = {
        "party_id": owner["id"], "scheme": "VAT", "country_code": "IN",
        "registration_number": "VAT-OPEN", "valid_to": "2099-12-31",
    }
    dated = values | {"valid_from": "2030-01-01"}
    first = await post(client, "/party-tax-registrations", values if open_first else dated)
    await post(client, "/party-tax-registrations", dated if open_first else values, status=409)
    if not open_first:
        return
    for date, count in [("1000-01-01", 1), ("2099-12-31", 1), ("2100-01-01", 0)]:
        result = await client.get(
            BASE + "/party-tax-registrations", headers=headers(), params={"as_of": date}
        )
        assert result.status_code == 200, result.text
        assert len(result.json()["items"]) == count
    metadata = await client.get(
        BASE + "/configuration/party-tax-registrations/field-set",
        headers=headers(), params={"operation": "update", "object_id": first["id"]},
    )
    assert metadata.status_code == 200, metadata.text
    fields = {field["key"]: field for field in metadata.json()["fields"]}
    assert not fields["valid_from"]["editable"]
    assert fields["valid_to"]["editable"]
    result = await client.patch(
        BASE + "/party-tax-registrations/" + first["id"], headers=headers(),
        json={"expected_version": first["row_version"], "registration_number": "CHANGED"},
    )
    assert result.status_code == 409, result.text
    result = await client.patch(
        BASE + "/party-tax-registrations/" + first["id"], headers=headers(),
        json={"expected_version": first["row_version"], "valid_to": "2098-12-31"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["valid_from"] is None


async def test_start_metadata_is_optional(client: httpx.AsyncClient) -> None:
    result = await client.get(
        BASE + "/configuration/party-tax-registrations/field-set?operation=create",
        headers=headers(),
    )
    assert result.status_code == 200, result.text
    field = next(field for field in result.json()["fields"] if field["key"] == "valid_from")
    assert field["required"] is False
    assert field["control"]["nullable"] is True


async def test_open_registration_contains_links_and_preserves_their_end(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    body = draft()
    body["tax_registration"] = {
        "scheme": "GST_IN", "registration_type": "UNREGISTERED",
        "country_code": "IN", "state_code": "IN-MH", "valid_to": day(30),
    }
    owner = await post(client, "/parties/create-with-details", body)
    regs = (await client.get(BASE + "/party-tax-registrations", headers=headers())).json()["items"]
    offices = (await client.get(BASE + "/party-addresses", headers=headers())).json()["items"]
    registration = regs[0]
    await post(client, "/party-registration-addresses", {
        "party_id": owner["id"], "registration_id": registration["id"],
        "address_id": offices[0]["id"], "valid_from": day(-365), "valid_to": day(20),
    })
    result = await client.patch(
        BASE + "/party-tax-registrations/" + registration["id"], headers=headers(),
        json={"expected_version": registration["row_version"], "valid_to": day(10)},
    )
    assert result.status_code == 409, result.text


def test_open_start_interval_rules() -> None:
    today = dt.date(2026, 10, 31)
    assert overlapping(None, None, today, None)
    assert overlapping(today, None, None, today)
    assert not overlapping(None, today, dt.date(2026, 11, 1), None)
    require_contained_interval(today, today, None, today)
    with pytest.raises(ConflictError):
        require_contained_interval(today, None, None, today)
    with pytest.raises(ConflictError):
        guard_effective_edit(None, None, {"valid_from"}, None, today=today)
    guard_effective_edit(None, None, {"valid_to"}, today, today=today)
    base = {"scheme": "VAT", "registration_number": "VAT-1", "valid_from": None}
    validate_values("party_tax_registration", base)
    with pytest.raises(ValidationFailedError):
        validate_values("party_tax_registration", base | {"valid_to": dt.date(999, 1, 1)})
    with pytest.raises(ValidationFailedError):
        validate_values("party_identifier", {"valid_from": None})
