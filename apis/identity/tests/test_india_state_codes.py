"""India's public administration codes are statutory; internal references stay stable."""

import pytest
from billing_platform.reference.seed import seed_reference
from sqlalchemy import select

from identity.domain.india_states import gst_state_codes
from identity.models import ReferenceRevision, State
from tests.test_platform_setup import signed
from tests.test_reference_crud import ready

pytest_plugins = ["tests.test_platform_setup"]


async def test_indian_state_code_is_assigned_searchable_and_permanent(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    data = {
        "kind": "state",
        "code": "IN-MH",
        "country_code": "IN",
        "name": "Maharashtra",
        "subdivision_type": "State",
    }
    created = await client.post("/v1/platform/references/states", headers=signed(key), json=data)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["code"] == "IN-MH" and row["display_code"] == "27"
    assert row["data"]["tax_jurisdiction_code"] == "27"
    found = await client.get(
        "/v1/platform/references/states?q=27&country_code=IN", headers=signed(key)
    )
    assert found.status_code == 200 and [
        item["display_code"] for item in found.json()["items"]
    ] == ["27"]
    assert "data" not in found.json()["items"][0]
    wrong = await client.patch(
        "/v1/platform/references/states/IN-MH",
        headers=signed(key),
        json={"version": 1, "data": {**row["data"], "tax_jurisdiction_code": "29"}},
    )
    assert wrong.status_code == 422
    async with factory() as db, db.begin():
        await seed_reference(db, managed=True)
        assert (await db.get(State, "IN-MH")).tax_jurisdiction_code == "27"
        revision = await db.scalar(
            select(ReferenceRevision).where(
                ReferenceRevision.kind == "state", ReferenceRevision.code == "IN-MH"
            )
        )
        assert revision.payload["tax_jurisdiction_code"] == "27"


@pytest.mark.parametrize(
    "code,tax", [("IN-MH", "29"), ("IN-AP", "28"), ("IN-DH", "25"), ("IN-ZZZ", "39")]
)
async def test_unassigned_or_incorrect_indian_codes_are_rejected(
    setup_app, client, factory, code, tax
):
    key, _ = await ready(setup_app, client, factory)
    response = await client.post(
        "/v1/platform/references/states",
        headers=signed(key),
        json={
            "kind": "state",
            "code": code,
            "country_code": "IN",
            "name": "Invalid mapping",
            "subdivision_type": "State",
            "tax_jurisdiction_code": tax,
        },
    )
    assert response.status_code == 422


async def test_other_countries_keep_their_original_state_codes(setup_app, client, factory):
    from tests.factories import build_country

    key, _ = await ready(setup_app, client, factory)
    async with factory() as db, db.begin():
        db.add(build_country(code="US", iso3="USA", numeric_code="840"))
    response = await client.post(
        "/v1/platform/references/states",
        headers=signed(key),
        json={
            "kind": "state",
            "code": "US-CA",
            "country_code": "US",
            "name": "California",
            "subdivision_type": "State",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["display_code"] == "US-CA"
    assert response.json()["data"]["tax_jurisdiction_code"] is None


def test_all_indian_defaults_have_unique_two_digit_current_gst_codes():
    codes = gst_state_codes()
    assert len(codes) == len(set(codes.values())) == 36
    assert codes["IN-JK"] == "01" and codes["IN-DH"] == "26"
    assert codes["IN-MH"] == "27" and codes["IN-AP"] == "37" and codes["IN-LA"] == "38"
    assert all(len(code) == 2 and code.isdigit() for code in codes.values())
