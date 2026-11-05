"""Reviewed India drug licences belong to one party and exact trading address."""

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from sqlalchemy import select

from accounting.api.voucher_sources import facts as voucher_facts
from accounting.domain.pharmacy_licences import required_form
from accounting.models.masters import PartyDrugLicence
from accounting.tasks.pharmacy_licences import effective_dealer_licence
from tests.conftest import COMPANY, TENANT, USER, headers
from tests.test_masters import BASE, activate, party, post, prepare


@pytest.mark.parametrize(
    ("operation", "licence_class", "form"),
    [
        ("RETAIL", "OTHER_THAN_C_C1_X", "20"),
        ("RETAIL", "C_C1_EXCLUDING_X", "21"),
        ("WHOLESALE", "OTHER_THAN_C_C1_X", "20B"),
        ("WHOLESALE", "C_C1_EXCLUDING_X", "21B"),
    ],
)
def test_dealer_form_matrix(operation, licence_class, form):
    assert required_form(operation, licence_class) == form


def test_schedule_x_dealer_form_is_unavailable():
    with pytest.raises(ConflictError):
        required_form("WHOLESALE", "SCHEDULE_X")


async def test_party_drug_licence_review_address_history_and_replay(client: httpx.AsyncClient, app):
    await prepare(client)
    owner = await party(client)
    address = await post(
        client,
        "/party-addresses",
        {
            "party_id": owner["id"],
            "label": "Trading premises",
            "mailing_name": "ABC",
            "line1": "1 Example Road",
            "city": "Mumbai",
            "country_code": "IN",
            "state_code": "IN-MH",
        },
    )
    address = await activate(client, "/party-addresses", address)
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    body = {
        "party_id": owner["id"],
        "address_id": address["id"],
        "licence_form": "20B",
        "licence_number": "MH-TEST-20B-001",
        "valid_from": tomorrow.isoformat(),
        "source_reference": "Reviewed licensing authority record",
        "source_sha256": "a" * 64,
    }
    route = BASE + "/party-drug-licences"
    assert (await client.post(route, json=body)).status_code == 401
    denied = headers(permissions=frozenset({"accounting.party.read"}))
    assert (await client.post(route, json=body, headers=denied)).status_code == 403
    assert (
        await client.post(route, json={**body, "licence_form": "20F"}, headers=headers())
    ).status_code == 422
    auth = headers()
    created = await client.post(route, json=body, headers=auth)
    assert created.status_code == 201, created.text
    detail = created.json()
    assert detail["reviewed_by"] == str(USER)
    assert detail["address_id"] == address["id"]
    assert detail["licence_form"] == "20B"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            snapshot, cursor = await voucher_facts(
                db, TENANT, COMPANY, "party_drug_licence", None, 1
            )
    assert cursor is None
    assert snapshot["masters"][0]["source_id"] == detail["id"]
    assert snapshot["masters"][0]["facts"]["address_id"] == address["id"]
    moved_premises = await client.patch(
        BASE + "/party-addresses/" + address["id"],
        json={"expected_version": address["row_version"], "line1": "99 Different Road"},
        headers=headers(),
    )
    assert moved_premises.status_code == 409
    replay = await client.post(route, json=body, headers=auth)
    assert replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    listing = await client.get(
        route + "?party_id=" + owner["id"] + "&as_of=" + tomorrow.isoformat(), headers=headers()
    )
    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["items"]] == [detail["id"]]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            selected = await effective_dealer_licence(
                db,
                company_id=COMPANY,
                party_id=uuid.UUID(owner["id"]),
                address_id=uuid.UUID(address["id"]),
                operation="WHOLESALE",
                licence_class="OTHER_THAN_C_C1_X",
                as_of=tomorrow,
            )
            assert selected.id == uuid.UUID(detail["id"])
            with pytest.raises(ConflictError):
                await effective_dealer_licence(
                    db,
                    company_id=COMPANY,
                    party_id=uuid.UUID(owner["id"]),
                    address_id=uuid.UUID(address["id"]),
                    operation="WHOLESALE",
                    licence_class="C_C1_EXCLUDING_X",
                    as_of=tomorrow,
                )
    overlap = await client.post(
        route,
        json={**body, "licence_number": "MH-TEST-20B-002"},
        headers=headers(),
    )
    assert overlap.status_code == 409
    closed = await client.patch(
        route + "/" + detail["id"],
        json={
            "expected_version": detail["row_version"],
            "valid_to": tomorrow.isoformat(),
            "closure_reason": "Verified licence withdrawal",
        },
        headers=headers(),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["valid_to"] == tomorrow.isoformat()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            with pytest.raises(ConflictError):
                await effective_dealer_licence(
                    db,
                    company_id=COMPANY,
                    party_id=uuid.UUID(owner["id"]),
                    address_id=uuid.UUID(address["id"]),
                    operation="WHOLESALE",
                    licence_class="OTHER_THAN_C_C1_X",
                    as_of=tomorrow + dt.timedelta(days=1),
                )
    again = await client.patch(
        route + "/" + detail["id"],
        json={
            "expected_version": closed.json()["row_version"],
            "valid_to": tomorrow.isoformat(),
            "closure_reason": "Second closure",
        },
        headers=headers(),
    )
    assert again.status_code == 409
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db, db.begin():
            assert list(await db.scalars(select(PartyDrugLicence))) == []


async def test_party_drug_licence_rejects_wrong_company_scope(client: httpx.AsyncClient):
    await prepare(client)
    response = await client.get(
        f"/v1/companies/{uuid.uuid4()}/party-drug-licences", headers=headers()
    )
    assert response.status_code == 401
