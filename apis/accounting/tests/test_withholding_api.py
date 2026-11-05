"""TDS/TCS withholding masters and the read-only preview over HTTP."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models import masters as m
from tests.conftest import COMPANY, PERMISSIONS, TENANT, headers
from tests.test_fiscal_api import facts

FEATURES = {"tds", "tcs"}
START = dt.date.today() + dt.timedelta(days=1)
EVIDENCE = {
    "source_reference": "Company-maintained citation",
    "source_url": "https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
    "source_sha256": "ab" * 32,
}
OTHER_COMPANY = uuid7()
OTHER_TENANT = uuid7()


@pytest.fixture(autouse=True)
def future_policy_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Collection and execution can span midnight in the full coverage suite.
    monkeypatch.setattr(f"{__name__}.START", dt.date.today() + dt.timedelta(days=1))


def url(path: str, company: uuid.UUID = COMPANY) -> str:
    return f"/v1/companies/{company}{path}"


def h(**kwargs: Any) -> dict[str, str]:
    values: dict[str, Any] = {"features": FEATURES, "finance": facts()} | kwargs
    return headers(**values)


async def send(
    client: httpx.AsyncClient,
    path: str,
    body: dict[str, Any],
    *,
    status: int = 201,
    company: uuid.UUID = COMPANY,
    method: str = "POST",
    **kwargs: Any,
) -> dict[str, Any]:
    response = await client.request(
        method,
        url(path, company),
        json=body,
        headers=h(company=company, **kwargs),
    )
    assert response.status_code == status, response.text
    return cast(dict[str, Any], response.json())


async def activate(
    client: httpx.AsyncClient, path: str, row: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    return await send(
        client,
        f"{path}/{row['id']}/activate",
        {"expected_version": row["row_version"]},
        status=200,
        **kwargs,
    )


async def world(client: httpx.AsyncClient, **kwargs: Any) -> dict[str, Any]:
    """Initialized company with an active party, its PAN, and an active TDS section.

    The party is created active with its supplier role and that role's account, the only way a
    party exists (docs/party-ledger-mandatory-plan.md).
    """
    await send(client, "/accounting-setup/initialize", {}, status=200, **kwargs)
    party = await send(
        client,
        "/parties/create-with-details",
        {
            "code": "VEND",
            "name": "Vendor",
            "legal_name": "Vendor Ltd",
            "country_code": "IN",
            "role": "SUPPLIER",
        },
        **kwargs,
    )
    pan = await send(
        client,
        "/party-identifiers",
        {
            "party_id": party["id"],
            "scheme": "PAN",
            "value": "ABCDE1234F",
            "country_code": "IN",
            "valid_from": START.isoformat(),
        },
        **kwargs,
    )
    section = await send(
        client,
        "/withholding-sections",
        {"code": "194C", "kind": "TDS", "name": "Contractors"},
        **kwargs,
    )
    section = await activate(client, "/withholding-sections", section, **kwargs)
    return {"party": party, "pan": pan, "section": section}


def rate_body(section: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "section_id": section["id"],
        "deductee_type": "COMPANY",
        "rate_percent": "2",
        "no_pan_rate_percent": "20",
        "single_transaction_threshold": "30000",
        "aggregate_annual_threshold": "100000",
        "threshold_currency": "INR",
        "threshold_basis": "AGGREGATE",
        "valid_from": START.isoformat(),
        **EVIDENCE,
    } | changes


def profile_body(w: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "party_id": w["party"]["id"],
        "kind": "TDS",
        "deductee_type": "COMPANY",
        "pan_status": "VERIFIED",
        "pan_identifier_id": w["pan"]["id"],
        "default_section_id": w["section"]["id"],
        "valid_from": START.isoformat(),
    } | changes


def certificate_body(w: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "party_id": w["party"]["id"],
        "section_id": w["section"]["id"],
        "certificate_reference": "LDC/2026/0001",
        "rate_percent": "0.5",
        "amount_limit": "50000",
        "currency": "INR",
        "valid_from": START.isoformat(),
        **EVIDENCE,
    } | changes


async def full(client: httpx.AsyncClient) -> dict[str, Any]:
    w = await world(client)
    w["rate"] = await send(client, "/withholding-rates", rate_body(w["section"]))
    w["profile"] = await send(client, "/party-withholding-profiles", profile_body(w))
    w["certificate"] = await send(client, "/withholding-certificates", certificate_body(w))
    return w


def preview_body(w: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "party_id": w["party"]["id"],
        "section_id": w["section"]["id"],
        "posting_date": START.isoformat(),
        "amount": "40000",
        "currency": "INR",
    } | changes


PATHS = {
    "withholding_section": "/withholding-sections",
    "withholding_rate": "/withholding-rates",
    "party_withholding_profile": "/party-withholding-profiles",
    "withholding_certificate": "/withholding-certificates",
}


async def test_happy_path_creates_reads_lists_and_stores_decimals(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await full(client)
    assert w["section"]["status"] == "ACTIVE"
    assert w["rate"]["rate_percent"] == "2.0000"
    assert w["profile"]["pan_status"] == "VERIFIED"
    assert w["certificate"]["amount_limit"] == "50000.0000"
    for name, path in PATHS.items():
        key = name.removeprefix("party_").split("_")[-1]
        row = w[key]
        detail = await client.get(url(f"{path}/{row['id']}"), headers=h())
        assert detail.status_code == 200, detail.text
        listing = await client.get(url(path), headers=h())
        assert listing.status_code == 200, listing.text
        assert [item["id"] for item in listing.json()["items"]] == [row["id"]]
        fields = await client.get(url(f"{path}/field-set"), headers=h())
        assert fields.status_code == 200
    filtered = await client.get(
        url(f"/withholding-rates?section_id={w['section']['id']}&deductee_type=COMPANY"),
        headers=h(),
    )
    assert len(filtered.json()["items"]) == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rate = await db.get(m.WithholdingRate, uuid.UUID(w["rate"]["id"]))
            certificate = await db.get(m.WithholdingCertificate, uuid.UUID(w["certificate"]["id"]))
    assert rate is not None and certificate is not None
    for value in (
        rate.rate_percent,
        rate.no_pan_rate_percent,
        rate.single_transaction_threshold,
        rate.aggregate_annual_threshold,
        certificate.rate_percent,
        certificate.amount_limit,
    ):
        assert type(value) is Decimal


async def test_unauthenticated_requests_are_rejected(client: httpx.AsyncClient) -> None:
    for path in [*PATHS.values(), "/withholding-previews"]:
        assert (await client.get(url(path))).status_code in {401, 405}
        assert (await client.post(url(path), json={})).status_code == 401


async def test_missing_permission_is_403_even_with_invalid_bodies(
    client: httpx.AsyncClient,
) -> None:
    w = await world(client)
    denied = h(permissions=PERMISSIONS - {"accounting.withholding.manage"})
    response = await client.post(
        url("/withholding-rates"), json=rate_body(w["section"]), headers=denied
    )
    assert response.status_code == 403
    unreadable = h(permissions=PERMISSIONS - {"accounting.withholding.read"})
    listing = await client.get(url("/withholding-sections"), headers=unreadable)
    assert listing.status_code == 403
    # The preview authorizes before body validation, so an invalid body still answers 403.
    preview = await client.post(url("/withholding-previews"), json={}, headers=unreadable)
    assert preview.status_code == 403
    invalid = await client.post(url("/withholding-previews"), json={}, headers=h())
    assert invalid.status_code == 422


async def test_wrong_company_objects_and_references_are_forbidden(
    client: httpx.AsyncClient,
) -> None:
    w = await full(client)
    other = await world(client, company=OTHER_COMPANY)
    for name, path in PATHS.items():
        key = name.removeprefix("party_").split("_")[-1]
        foreign = await client.get(
            url(f"{path}/{w[key]['id']}", OTHER_COMPANY), headers=h(company=OTHER_COMPANY)
        )
        assert foreign.status_code == 403, (name, foreign.text)
    # Creating in company B while naming company A's section is refused.
    response = await client.post(
        url("/withholding-rates", OTHER_COMPANY),
        json=rate_body(w["section"]),
        headers=h(company=OTHER_COMPANY),
    )
    assert response.status_code == 403
    response = await client.post(
        url("/withholding-previews", OTHER_COMPANY),
        json=preview_body(other, section_id=w["section"]["id"]),
        headers=h(company=OTHER_COMPANY),
    )
    assert response.status_code == 403
    # A context for company B never reaches company A's path.
    response = await client.get(
        url(f"/withholding-sections/{w['section']['id']}"), headers=h(company=OTHER_COMPANY)
    )
    assert response.status_code == 401


async def test_cross_tenant_rows_are_invisible_for_every_table(
    client: httpx.AsyncClient,
) -> None:
    w = await full(client)
    other = h(tenant=OTHER_TENANT)
    response = await client.post(url("/accounting-setup/initialize"), json={}, headers=other)
    assert response.status_code == 200, response.text
    for name, path in PATHS.items():
        key = name.removeprefix("party_").split("_")[-1]
        listing = await client.get(url(path), headers=h(tenant=OTHER_TENANT))
        assert listing.status_code == 200
        assert listing.json()["items"] == [], name
        detail = await client.get(url(f"{path}/{w[key]['id']}"), headers=h(tenant=OTHER_TENANT))
        assert detail.status_code == 404, name


async def test_invalid_inputs_answer_422(client: httpx.AsyncClient) -> None:
    w = await world(client)
    section = w["section"]
    changes: dict[str, Any]
    for changes in (
        {"rate_percent": 2.0},
        {"rate_percent": "101"},
        {"rate_percent": "25"},
        {"source_url": "http://incometaxindia.gov.in/x"},
        {"source_url": "https://example.com/x"},
        {"source_url": "https://user:pw@incometaxindia.gov.in/x"},
        {"source_sha256": "XYZ"},
        {"threshold_basis": "EXCESS"},
        {"threshold_currency": "USD"},
        {"deductee_type": "ALIEN"},
        {"unexpected": True},
    ):
        response = await client.post(
            url("/withholding-rates"), json=rate_body(section, **changes), headers=h()
        )
        assert response.status_code == 422, (changes, response.text)
    for changes in (
        {"pan_identifier_id": None},
        {"pan_status": "NOT_AVAILABLE"},
        {"kind": "TCS"},
    ):
        response = await client.post(
            url("/party-withholding-profiles"), json=profile_body(w, **changes), headers=h()
        )
        assert response.status_code == 422, (changes, response.text)
    for changes in ({"currency": None}, {"currency": "USD"}, {"amount_limit": "0"}):
        response = await client.post(
            url("/withholding-certificates"), json=certificate_body(w, **changes), headers=h()
        )
        assert response.status_code == 422, (changes, response.text)
    response = await client.post(
        url("/withholding-sections"),
        json={"code": "bad code", "kind": "TDS", "name": "x"},
        headers=h(),
    )
    assert response.status_code == 422


async def test_profile_rejects_an_identifier_that_is_not_a_pan(
    client: httpx.AsyncClient,
) -> None:
    w = await world(client)
    gst = await send(
        client,
        "/party-tax-registrations",
        {
            "party_id": w["party"]["id"],
            "scheme": "GST_IN",
            "registration_number": "27ABCDE1234F1Z0",
            "country_code": "IN",
            "state_code": "IN-MH",
            "valid_from": START.isoformat(),
        },
    )
    tan = await send(
        client,
        "/party-identifiers",
        {
            "party_id": w["party"]["id"],
            "scheme": "TAN",
            "value": "MUMA12345B",
            "country_code": "IN",
            "valid_from": START.isoformat(),
        },
        status=201,
    )
    assert gst["id"] != tan["id"]
    response = await client.post(
        url("/party-withholding-profiles"),
        json=profile_body(w, pan_identifier_id=tan["id"]),
        headers=h(),
    )
    assert response.status_code == 422, response.text


async def test_overlapping_intervals_conflict(client: httpx.AsyncClient) -> None:
    w = await full(client)
    later = (START + dt.timedelta(days=10)).isoformat()
    for path, body in (
        ("/withholding-rates", rate_body(w["section"], valid_from=later)),
        ("/party-withholding-profiles", profile_body(w, valid_from=later)),
        (
            "/withholding-certificates",
            certificate_body(w, valid_from=later, certificate_reference="LDC/2026/0002"),
        ),
    ):
        response = await client.post(url(path), json=body, headers=h())
        assert response.status_code == 409, (path, response.text)
    # A different deductee type is a separate rate term.
    await send(client, "/withholding-rates", rate_body(w["section"], deductee_type="INDIVIDUAL"))


async def test_rate_supersession_requires_a_closed_adjacent_predecessor(
    client: httpx.AsyncClient,
) -> None:
    w = await world(client)
    end = START + dt.timedelta(days=30)
    open_rate = await send(client, "/withholding-rates", rate_body(w["section"]))
    successor = rate_body(
        w["section"],
        supersedes_id=open_rate["id"],
        valid_from=(end + dt.timedelta(days=1)).isoformat(),
        rate_percent="1",
    )
    # The predecessor is still open-ended.
    response = await client.post(url("/withholding-rates"), json=successor, headers=h())
    assert response.status_code == 409, response.text
    closed = await send(
        client,
        f"/withholding-rates/{open_rate['id']}",
        {"expected_version": open_rate["row_version"], "valid_to": end.isoformat()},
        method="PATCH",
        status=200,
    )
    gap = successor | {"valid_from": (end + dt.timedelta(days=2)).isoformat()}
    response = await client.post(url("/withholding-rates"), json=gap, headers=h())
    assert response.status_code == 409, response.text
    other_type = successor | {"deductee_type": "INDIVIDUAL"}
    response = await client.post(url("/withholding-rates"), json=other_type, headers=h())
    assert response.status_code == 409, response.text
    created = await send(client, "/withholding-rates", successor)
    assert created["supersedes_id"] == closed["id"]
    second = successor | {"deductee_type": "COMPANY", "valid_from": created["valid_from"]}
    response = await client.post(url("/withholding-rates"), json=second, headers=h())
    assert response.status_code == 409


async def test_effective_rows_only_shorten_their_end_date(client: httpx.AsyncClient) -> None:
    w = await full(client)
    # A future row may still be corrected, but never re-keyed.
    future = await send(
        client,
        f"/withholding-rates/{w['rate']['id']}",
        {"expected_version": w["rate"]["row_version"], "rate_percent": "3"},
        method="PATCH",
        status=200,
    )
    assert future["rate_percent"] == "3.0000"
    response = await client.patch(
        url(f"/withholding-rates/{w['rate']['id']}"),
        json={"expected_version": future["row_version"], "deductee_type": "INDIVIDUAL"},
        headers=h(),
    )
    assert response.status_code in {409, 422}, response.text
    today = dt.date.today().isoformat()
    current = await send(
        client,
        "/withholding-rates",
        rate_body(w["section"], deductee_type="INDIVIDUAL", valid_from=today),
    )
    response = await client.patch(
        url(f"/withholding-rates/{current['id']}"),
        json={"expected_version": current["row_version"], "rate_percent": "3"},
        headers=h(),
    )
    assert response.status_code == 409, response.text
    ended = await send(
        client,
        f"/withholding-rates/{current['id']}",
        {"expected_version": current["row_version"], "valid_to": today},
        method="PATCH",
        status=200,
    )
    assert ended["valid_to"] == today
    response = await client.patch(
        url(f"/withholding-sections/{w['section']['id']}"),
        json={"expected_version": w["section"]["row_version"], "code": "194J"},
        headers=h(),
    )
    assert response.status_code in {409, 422}, response.text
    renamed = await send(
        client,
        f"/withholding-sections/{w['section']['id']}",
        {"expected_version": w["section"]["row_version"], "name": "Contract work"},
        method="PATCH",
        status=200,
    )
    assert renamed["name"] == "Contract work"


async def test_idempotent_replay_has_one_effect(client: httpx.AsyncClient, app: FastAPI) -> None:
    w = await world(client)
    replay = h(key="withholding-rate-replay")
    first = await client.post(
        url("/withholding-rates"), json=rate_body(w["section"]), headers=replay
    )
    second = await client.post(
        url("/withholding-rates"), json=rate_body(w["section"]), headers=replay
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            count = await db.scalar(select(func.count(m.WithholdingRate.id)))
    assert count == 1
    changed = await client.post(
        url("/withholding-rates"),
        json=rate_body(w["section"], deductee_type="INDIVIDUAL"),
        headers=replay,
    )
    assert changed.status_code in {409, 422}


async def test_writes_need_the_matching_feature(client: httpx.AsyncClient) -> None:
    w = await world(client)
    response = await client.post(
        url("/withholding-sections"),
        json={"code": "206C", "kind": "TCS", "name": "Collection"},
        headers=h(features={"tds"}),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "feature_not_enabled", response.text
    for path, body in (
        ("/withholding-rates", rate_body(w["section"])),
        ("/party-withholding-profiles", profile_body(w)),
        ("/withholding-certificates", certificate_body(w)),
        ("/withholding-previews", preview_body(w)),
    ):
        response = await client.post(url(path), json=body, headers=h(features=set()))
        assert response.status_code == 409, (path, response.text)
    # Reads remain available after a feature is switched off.
    listing = await client.get(url("/withholding-sections"), headers=h(features=set()))
    assert listing.status_code == 200


async def test_preview_applies_certificate_then_fallback_and_reports_decimals(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await full(client)
    below = await send(client, "/withholding-previews", preview_body(w, amount="20000"), status=200)
    assert (below["applies"], below["reason"]) == (False, "BELOW_THRESHOLD")
    result = await send(
        client,
        "/withholding-previews",
        preview_body(w, amount="40000", certificate_consumed="20000"),
        status=200,
    )
    assert result["applies"] and result["certificate_id"] == w["certificate"]["id"]
    assert [(p["base_amount"], p["rate_source"]) for p in result["portions"]] == [
        ("30000.0000", "CERTIFICATE"),
        ("10000.0000", "NORMAL"),
    ]
    assert Decimal(result["withholding_amount"]) == Decimal("350.00")
    assert result["withholding_amount"] == "350.00"
    caught_up = await send(
        client,
        "/withholding-previews",
        preview_body(w, amount="20000", ytd_amount="90000", certificate_consumed="50000"),
        status=200,
    )
    assert caught_up["base_amount"] == "110000.0000"
    assert caught_up["certificate_id"] is None
    assert caught_up["withholding_amount"] == "2200.00"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            count = await db.scalar(select(func.count(m.WithholdingCertificate.id)))
    assert count == 1


async def test_preview_rejects_foreign_currency_float_and_missing_profile(
    client: httpx.AsyncClient,
) -> None:
    w = await world(client)
    await send(client, "/withholding-rates", rate_body(w["section"]))
    response = await client.post(
        url("/withholding-previews"), json=preview_body(w, currency="USD"), headers=h()
    )
    assert response.status_code == 422
    response = await client.post(
        url("/withholding-previews"), json=preview_body(w, amount=40000.5), headers=h()
    )
    assert response.status_code == 422
    response = await client.post(url("/withholding-previews"), json=preview_body(w), headers=h())
    assert response.status_code == 409
    response = await client.post(
        url("/withholding-previews"),
        json=preview_body(w),
        headers=h(finance=None),
    )
    assert response.status_code == 409


async def test_preview_refuses_a_retired_section(client: httpx.AsyncClient) -> None:
    w = await world(client)
    section = await send(
        client, "/withholding-sections", {"code": "194J", "kind": "TDS", "name": "Fees"}
    )
    section = await activate(client, "/withholding-sections", section)
    retired = await send(
        client,
        f"/withholding-sections/{section['id']}/deactivate",
        {"expected_version": section["row_version"]},
        status=200,
    )
    assert retired["status"] == "INACTIVE"
    response = await client.post(
        url("/withholding-previews"),
        json=preview_body(w, section_id=section["id"]),
        headers=h(),
    )
    assert response.status_code == 409, response.text
