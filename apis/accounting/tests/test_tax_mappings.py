"""Tax posting purposes, registration regime windows and party GST registrations."""

import datetime as dt
from typing import Any

import httpx
from billing_platform.ids import uuid7

from tests.conftest import headers
from tests.test_masters import BASE, activate, party, post, prepare


def day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


REGULAR = {
    "id": str(uuid7()),
    "tax_system": "gst_in",
    "regime": "regular",
    "jurisdiction_code": "IN-MH",
    "valid_from": day(-30),
    "valid_to": None,
}
COMPOSITION = REGULAR | {"id": str(uuid7()), "regime": "composition", "jurisdiction_code": "IN-KA"}
#: A composition period that has ended, followed by a regular row: Identity never edits a
#: row's regime, so a regime change is two rows and each is judged on its own window.
FORMER = REGULAR | {
    "id": str(uuid7()),
    "regime": "composition",
    "jurisdiction_code": "IN-GJ",
    "valid_from": day(-90),
    "valid_to": day(-31),
}
CONTEXT = [REGULAR, COMPOSITION, FORMER]


def h(**kwargs: Any) -> dict[str, str]:
    return headers(registrations=CONTEXT, **kwargs)


async def tax_account(
    client: httpx.AsyncClient, group: str, code: str, profile: dict[str, Any]
) -> dict[str, Any]:
    account = await post(
        client, "/accounts", {"code": code, "name": code, "group_id": group, "kind": "TAX"}, h=h()
    )
    await post(client, "/account-tax-profiles", {"account_id": account["id"]} | profile, h=h())
    return await activate(client, "/accounts", account, h=h())


def gst(component: str, purpose: str, registration: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_registration_id": registration["id"],
        "scheme": "GST_IN",
        "component": component,
        "duty_type": "CESS" if component == "CESS" else "GST",
        "purpose": purpose,
    }


def withheld(duty: str, purpose: str) -> dict[str, Any]:
    return {"scheme": "OTHER", "component": "OTHER", "duty_type": duty, "purpose": purpose}


async def mapping(
    client: httpx.AsyncClient,
    purpose: str,
    account: dict[str, Any],
    registration: dict[str, Any] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "purpose": purpose,
        "account_id": account["id"],
        "currency": "INR",
        "valid_from": day(1),
    }
    if registration is not None:
        body["company_registration_id"] = registration["id"]
    return await client.post(BASE + "/posting-mappings", json=body, headers=h())


async def test_cess_reverse_charge_and_withholding_purposes(client: httpx.AsyncClient) -> None:
    groups = await prepare(client, h=h())
    payable, recoverable = groups["TAX_PAYABLE"], groups["ADVANCES"]
    out_cess = await tax_account(
        client, payable, "OUT_CESS", gst("CESS", "OUTPUT_PAYABLE", REGULAR)
    )
    in_cess = await tax_account(
        client, recoverable, "IN_CESS", gst("CESS", "INPUT_RECOVERABLE", REGULAR)
    )
    out_igst = await tax_account(
        client, payable, "OUT_IGST", gst("IGST", "OUTPUT_PAYABLE", REGULAR)
    )
    rcm = await tax_account(client, payable, "RCM_IGST", gst("IGST", "RCM_PAYABLE", COMPOSITION))
    tds = await tax_account(client, payable, "TDS_PAY", withheld("TDS", "OUTPUT_PAYABLE"))
    tcs = await tax_account(client, recoverable, "TCS_REC", withheld("TCS", "INPUT_RECOVERABLE"))
    accepted = [
        ("OUTPUT_CESS", out_cess, REGULAR),
        ("INPUT_CESS", in_cess, REGULAR),
        # Reverse charge is owed whatever the recipient's regime, so composition may map it.
        ("RCM_IGST", rcm, COMPOSITION),
        ("TDS_PAYABLE", tds, None),
        ("TCS_RECEIVABLE", tcs, None),
    ]
    for purpose, account, registration in accepted:
        response = await mapping(client, purpose, account, registration)
        assert response.status_code == 201, (purpose, response.text)
        assert response.json()["purpose"] == purpose
    refused = [
        # The purpose table, not a name suffix, decides the component.
        ("OUTPUT_CESS", out_igst, REGULAR),
        ("OUTPUT_IGST", out_cess, REGULAR),
        # The duty is part of the rule: a TCS account is no TDS liability.
        ("TDS_PAYABLE", tcs, None),
        ("TCS_PAYABLE", tds, None),
        # The mapping's registration must be the profile's.
        ("RCM_IGST", rcm, REGULAR),
        # GST purposes need a registration.
        ("OUTPUT_IGST", out_igst, None),
    ]
    for purpose, account, registration in refused:
        response = await mapping(client, purpose, account, registration)
        assert response.status_code == 422, (purpose, response.text)
    # Recoverable heads must be assets.
    wrong_head = await mapping(client, "TDS_RECEIVABLE", tds)
    assert wrong_head.status_code == 422, wrong_head.text


async def test_regime_is_judged_on_each_registration_window(client: httpx.AsyncClient) -> None:
    groups = await prepare(client, h=h())
    payable, recoverable = groups["TAX_PAYABLE"], groups["ADVANCES"]
    for profile, group in [
        (gst("CGST", "OUTPUT_PAYABLE", COMPOSITION), payable),
        (gst("CGST", "INPUT_RECOVERABLE", COMPOSITION), recoverable),
        (gst("CGST", "OUTPUT_PAYABLE", FORMER), payable),
    ]:
        account = await post(
            client,
            "/accounts",
            {"code": "T" + str(uuid7())[-6:], "name": "Tax", "group_id": group, "kind": "TAX"},
            h=h(),
        )
        response = await client.post(
            BASE + "/account-tax-profiles",
            json={"account_id": account["id"]} | profile,
            headers=h(),
        )
        assert response.status_code == 422, response.text
        assert "regime" in response.text or "regular registration" in response.text
    # The current regular row is unaffected by the earlier composition row.
    account = await tax_account(client, payable, "OUT_CGST", gst("CGST", "OUTPUT_PAYABLE", REGULAR))
    assert (await mapping(client, "OUTPUT_CGST", account, REGULAR)).status_code == 201


async def test_template_refuses_an_ended_registration(client: httpx.AsyncClient) -> None:
    await post(client, "/accounting-setup/initialize", {}, h=h(), status=200)
    for registration in (FORMER, COMPOSITION):
        response = await client.post(
            BASE + "/accounting-setup/preview",
            json={
                "business_accounts": True,
                "gst_registration_id": registration["id"],
                "local_component": "SGST",
            },
            headers=h(),
        )
        assert response.status_code == 422, response.text


async def test_overdraft_bank_account_may_receive(client: httpx.AsyncClient) -> None:
    bank_id = uuid7()

    def hb() -> dict[str, str]:
        return headers(bank_ids={bank_id})

    groups = await prepare(client, h=hb())
    bank = await post(
        client,
        "/accounts",
        {"code": "OD", "name": "Overdraft", "group_id": groups["BANK_OD"], "kind": "BANK"},
        h=hb(),
    )
    await post(
        client,
        "/account-bank-profiles",
        {"account_id": bank["id"], "company_bank_id": str(bank_id)},
        h=hb(),
    )
    bank = await activate(client, "/accounts", bank, h=hb())
    body = {"purpose": "BANK_RECEIPT", "account_id": bank["id"], "currency": "INR"}
    response = await client.post(
        BASE + "/posting-mappings", json=body | {"valid_from": day(1)}, headers=hb()
    )
    assert response.status_code == 201, response.text
    # A liability account that is not a bank is still refused.
    general = await post(
        client,
        "/accounts",
        {"code": "LOAN", "name": "Loan", "group_id": groups["SECURED_LOANS"], "kind": "GENERAL"},
        h=hb(),
    )
    general = await activate(client, "/accounts", general, h=hb())
    response = await client.post(
        BASE + "/posting-mappings",
        json=body | {"account_id": general["id"], "valid_from": day(400)},
        headers=hb(),
    )
    assert response.status_code == 422, response.text


async def register(
    client: httpx.AsyncClient, party_id: str, values: dict[str, Any]
) -> httpx.Response:
    body = {"party_id": party_id, "scheme": "GST_IN", "country_code": "IN"} | values
    return await client.post(BASE + "/party-tax-registrations", json=body, headers=headers())


async def test_party_registration_types_and_overlaps(client: httpx.AsyncClient) -> None:
    await prepare(client)
    pid = (await party(client))["id"]
    start, later = day(1), day(100)
    created: list[dict[str, Any]] = [
        # An unregistered buyer records only its state, for place of supply.
        {"registration_type": "UNREGISTERED", "state_code": "IN-MH", "valid_from": start},
        {"registration_type": "UNREGISTERED", "state_code": "IN-KA", "valid_from": start},
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F1Z6",
            "state_code": "IN-GJ",
            "valid_from": start,
            "valid_to": day(50),
        },
        # A successor registration that does not overlap.
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F2Z5",
            "state_code": "IN-GJ",
            "valid_from": later,
        },
        # An SEZ unit holds its own GSTIN beside the regular one.
        {
            "registration_type": "SEZ_UNIT",
            "registration_number": "24ABCDE1234F3Z4",
            "state_code": "IN-GJ",
            "valid_from": start,
        },
        {
            "registration_type": "OVERSEAS",
            "country_code": "US",
            "state_code": None,
            "valid_from": start,
        },
    ]
    for values in created:
        response = await register(client, pid, values)
        assert response.status_code == 201, (values, response.text)
        assert response.json()["registration_type"] == values["registration_type"]
    conflicts: list[dict[str, Any]] = [
        # At most one unregistered row per party and state.
        {"registration_type": "UNREGISTERED", "state_code": "IN-MH", "valid_from": later},
        # A regular registration overlapping the unregistered status in the same state.
        {
            "registration_type": "REGULAR",
            "registration_number": "27ABCDE1234F1Z0",
            "state_code": "IN-MH",
            "valid_from": later,
        },
        # Two overlapping regular registrations for one party and state.
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F3Z4",
            "state_code": "IN-GJ",
            "valid_from": day(10),
            "valid_to": day(20),
        },
    ]
    for values in conflicts:
        response = await register(client, pid, values)
        assert response.status_code == 409, (values, response.text)
    invalid: list[dict[str, Any]] = [
        {"registration_type": "UNREGISTERED", "registration_number": "27ABCDE1234F1Z0"},
        {
            "registration_type": "REGULAR",
            "registration_number": "27ABCDE1234F1Z0",
            "state_code": None,
        },
        {"registration_type": "UNREGISTERED", "state_code": None},
        {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F1Z5"},
        {"registration_type": "REGULAR", "registration_number": "27ABCDE1234F0Z1"},
        {"registration_type": "REGULAR", "registration_number": "29ABCDE1234F1ZW"},
        {"registration_type": "SEZ_DEVELOPER"},
        {"registration_type": "NOT_A_TYPE", "registration_number": "27ABCDE1234F1Z0"},
    ]
    for values in invalid:
        response = await register(
            client, pid, {"state_code": "IN-MH", "valid_from": day(500)} | values
        )
        assert response.status_code == 422, (values, response.text)


async def test_party_registration_endpoint_contract(client: httpx.AsyncClient) -> None:
    await prepare(client)
    pid = (await party(client))["id"]
    body = {
        "party_id": pid,
        "scheme": "GST_IN",
        "country_code": "IN",
        "registration_type": "UNREGISTERED",
        "state_code": "IN-MH",
        "valid_from": day(1),
    }
    path = BASE + "/party-tax-registrations"
    anonymous = {key: value for key, value in headers().items() if not key.startswith("X-Actor")}
    assert (await client.post(path, json=body, headers=anonymous)).status_code == 401
    denied = headers(permissions=frozenset())
    assert (await client.post(path, json=body, headers=denied)).status_code == 403
    # The caller holds another company: this company's party is out of its scope.
    other = uuid7()
    initialized = await client.post(
        f"/v1/companies/{other}/accounting-setup/initialize",
        json={},
        headers=headers(company=other),
    )
    assert initialized.status_code == 200, initialized.text
    wrong = await client.post(
        f"/v1/companies/{other}/party-tax-registrations", json=body, headers=headers(company=other)
    )
    assert wrong.status_code in {403, 404}, wrong.text
    invalid = body | {"registration_type": "NOT_A_TYPE"}
    assert (await client.post(path, json=invalid, headers=headers())).status_code == 422
    first = await client.post(path, json=body, headers=headers(key="unregistered-mh"))
    assert first.status_code == 201, first.text
    assert first.json()["registration_number"] is None
    replay = await client.post(path, json=body, headers=headers(key="unregistered-mh"))
    assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]


def test_readiness_head_is_the_latest_revision() -> None:
    """Readiness compares `alembic_version` with MIGRATION_HEAD; a stale constant makes a
    fully migrated database report not-ready."""
    from pathlib import Path

    from accounting.metadata import MIGRATION_HEAD

    versions = Path(__file__).resolve().parents[3] / "dbs" / "accounting" / "versions"
    revisions = sorted(path.name[:4] for path in versions.glob("[0-9][0-9][0-9][0-9]_*.py"))
    assert MIGRATION_HEAD == revisions[-1]
