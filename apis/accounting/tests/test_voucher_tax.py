"""GST and TDS/TCS on journals and party documents (tax-accounting plan Phase 8)."""

import uuid
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from billing_platform.tax_calc import (
    SupplyContext,
    SupplyDetermination,
    SupplyReason,
    TaxComponent,
    TaxLine,
    TaxRequest,
    compute,
)
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import func, select

from accounting.domain import voucher_tax as rules
from accounting.domain.voucher_tax import Posting, TaxedLine, TaxException
from accounting.models.ledger import Journal, JournalLine
from accounting.models.voucher_tax import JournalTax
from accounting.schemas.subledger import SourceCreate, TaxPreviewRequest
from accounting.schemas.voucher_tax import SourceTax, VoucherTax, validate_source_tax
from accounting.tasks import voucher_tax as tasks
from tests.conftest import COMPANY, TENANT, headers
from tests.test_account_tax_defaults import account, purchase, sale
from tests.test_catalog_tax_replica import component, deliver, publish_rule, rate_event
from tests.test_fiscal_api import BASE, change
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_masters import activate
from tests.test_openings_sources import party_accounts
from tests.test_tax_mappings import gst, register, withheld

START = "2026-04-01"
DATE = "2026-04-02"
FEATURES = {"multi_currency", "credit_limits", "tds", "tcs"}
OTHER_COMPANY = uuid7()
OTHER_TENANT = uuid7()
ZERO = Decimal(0)


def registration(state: str, regime: str = "regular") -> dict[str, Any]:
    return {
        "id": str(uuid7()),
        "tax_system": "gst_in",
        "regime": regime,
        "jurisdiction_code": state,
        "valid_from": START,
        "valid_to": None,
    }


MH = registration("IN-MH")
CH = registration("IN-CH")
KA_COMPOSITION = registration("IN-KA", "composition")
EVIDENCE = {
    "source_reference": "Company-maintained citation",
    "source_url": "https://incometaxindia.gov.in/pages/acts/income-tax-act.aspx",
    "source_sha256": "ab" * 32,
}


def th(registrations: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, str]:
    values: dict[str, Any] = {"features": FEATURES} | kwargs
    return ledger_headers(registrations=[MH] if registrations is None else registrations, **values)


async def send(
    client: httpx.AsyncClient,
    path: str,
    body: dict[str, Any],
    *,
    status: int = 201,
    h: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = await client.post(BASE + path, json=body, headers=h or th())
    assert response.status_code == status, (path, response.text)
    return cast(dict[str, Any], response.json())


#: Mapping purpose -> (account tax profile purpose, account group, withholding duty).
HEADS = {
    "OUTPUT": ("OUTPUT_PAYABLE", "TAX_PAYABLE"),
    "INPUT": ("INPUT_RECOVERABLE", "ADVANCES"),
    "PENDING": ("INPUT_PENDING", "ADVANCES"),
    "RCM": ("RCM_PAYABLE", "TAX_PAYABLE"),
}


async def tax_head(
    client: httpx.AsyncClient,
    groups: dict[str, str],
    purpose: str,
    reg: dict[str, Any] | None,
) -> dict[str, Any]:
    """A TAX account with its profile and the effective posting mapping for ``purpose``."""
    h = th([reg] if reg else None)
    prefix, code = purpose.split("_", 1)
    if prefix in HEADS:
        profile_purpose, group = HEADS[prefix]
        profile = gst(code, profile_purpose, cast(dict[str, Any], reg))
    else:
        profile, group = withheld(prefix, "OUTPUT_PAYABLE"), "TAX_PAYABLE"
    name = purpose + ("_" + reg["jurisdiction_code"][-2:] if reg else "")
    row = await send(
        client,
        "/accounts",
        {"code": name, "name": name, "group_id": groups[group], "kind": "TAX"},
        h=h,
    )
    await send(client, "/account-tax-profiles", {"account_id": row["id"]} | profile, h=h)
    row = await activate(client, "/accounts", row, h=h)
    body: dict[str, Any] = {
        "purpose": purpose,
        "account_id": row["id"],
        "currency": "INR",
        "valid_from": START,
    }
    if reg is not None:
        body["company_registration_id"] = reg["id"]
    await send(client, "/posting-mappings", body, h=h)
    return row


RATES = {
    "INTRA_STATE": [("CGST", "9"), ("SGST", "9")],
    "INTER_STATE": [("IGST", "18")],
    "INTRA_UT": [("CGST", "9"), ("UTGST", "9")],
}


async def replicate_rates(app: FastAPI, rule: uuid.UUID) -> None:
    for applicability, parts in RATES.items():
        components = [component(key, key, rate, index) for index, (key, rate) in enumerate(parts)]
        message = rate_event(uuid7(), rule, 1, components=components, applicability=applicability)
        assert await deliver(app, message)


SERVICE_PURCHASE = {
    "supply_kind": "SERVICE",
    "code_system": "SAC",
    "code": "998314",
    "rcm_applicable": True,
    "assessable_inclusion": "NONE",
    "apportion_by": None,
    "valid_from": START,
}


async def world(client: httpx.AsyncClient, app: FastAPI) -> dict[str, Any]:
    """An open April 2026 period, GST rates, account defaults and mapped tax heads."""
    _, period, authority = await journal_setup(client, app)
    groups = {
        row["code"]: row["id"]
        for row in (await client.get(BASE + "/account-groups?limit=200", headers=th())).json()[
            "items"
        ]
    }
    accounts = (await client.get(BASE + "/accounts?limit=200", headers=th())).json()["items"]
    cash = next(row for row in accounts if row["kind"] == "CASH")
    service = await publish_rule(app)
    goods = await publish_rule(app, item_kind="GOODS", name="GST 18% goods")
    for rule in (service, goods):
        await replicate_rates(app, rule)
    income = await account(client, groups["SALES"], "GST_SALES")
    stock = await account(client, groups["PURCHASES"], "GST_GOODS")
    rcm = await account(client, groups["PURCHASES"], "RCM_SERVICES")
    blocked = await account(client, groups["PURCHASES"], "BLOCKED_SERVICES")
    defaults = "/account-tax-defaults"
    await send(client, defaults, sale(income["id"], service, valid_from=START))
    await send(client, defaults, purchase(stock["id"], goods, valid_from=START))
    await send(client, defaults, purchase(rcm["id"], service, **SERVICE_PURCHASE))
    await send(
        client,
        defaults,
        purchase(blocked["id"], service, **SERVICE_PURCHASE, itc_eligibility="INELIGIBLE"),
    )
    heads = {}
    for purpose in (
        "OUTPUT_CGST",
        "OUTPUT_SGST",
        "OUTPUT_IGST",
        "INPUT_IGST",
        "RCM_IGST",
    ):
        heads[purpose] = await tax_head(client, groups, purpose, MH)
    for purpose in ("TDS_PAYABLE", "TCS_PAYABLE"):
        heads[purpose] = await tax_head(client, groups, purpose, None)
    return {
        "period": period,
        "authority": authority,
        "groups": groups,
        "cash": cash,
        "income": income,
        "stock": stock,
        "goods_rule": goods,
        "rcm": rcm,
        "blocked": blocked,
        "heads": heads,
    }


def line(account_row: dict[str, Any], side: str, amount: str) -> dict[str, Any]:
    return {
        "account_id": account_row["id"],
        "side": side,
        "currency": "INR",
        "amount": amount,
        "exchange_rate": "1",
    }


def sale_journal(
    w: dict[str, Any], *, taxable: str = "1000", gross: str = "1180", **tax: Any
) -> dict[str, Any]:
    return {
        "document_date": DATE,
        "posting_date": DATE,
        "description": "Taxed sale",
        "lines": [line(w["cash"], "DEBIT", gross), line(w["income"], "CREDIT", taxable)],
        "tax": {"direction": "SALE"} | tax,
    }


def purchase_journal(
    w: dict[str, Any], expense: str, *, taxable: str = "1000", paid: str = "1000", **tax: Any
) -> dict[str, Any]:
    return {
        "document_date": DATE,
        "posting_date": DATE,
        "description": "Taxed purchase",
        "lines": [line(w[expense], "DEBIT", taxable), line(w["cash"], "CREDIT", paid)],
        "tax": {"direction": "PURCHASE"} | tax,
    }


async def preview(
    client: httpx.AsyncClient, body: dict[str, Any], *, h: dict[str, str] | None = None
) -> dict[str, Any]:
    return await send(client, "/voucher-tax-previews", body, status=200, h=h)


def generated(result: dict[str, Any]) -> dict[str, tuple[str, Decimal]]:
    return {
        row["purpose"]: (row["side"], Decimal(row["amount"]))
        for row in result["lines"]
        if row["generated"]
    }


async def post(client: httpx.AsyncClient, row: dict[str, Any], **kwargs: Any) -> httpx.Response:
    return await client.post(
        BASE + f"/journals/{row['id']}/post",
        json={"expected_version": row["row_version"]},
        headers=th(**kwargs),
    )


async def journal_lines(app: FastAPI, journal_id: str) -> list[JournalLine]:
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            return list(
                await db.scalars(
                    select(JournalLine)
                    .where(JournalLine.journal_id == uuid.UUID(journal_id))
                    .order_by(JournalLine.sequence)
                )
            )


async def evidence(app: FastAPI, tenant: uuid.UUID = TENANT) -> list[JournalTax]:
    with tenant_scope(tenant):
        async with app.state.session_factory() as db:
            return list(await db.scalars(select(JournalTax).order_by(JournalTax.id)))


# --- pure rules: no database ---------------------------------------------------------------


def test_states_compare_without_country_prefix() -> None:
    assert rules.bare_state("IN-MH") == rules.bare_state("mh") == "MH"
    assert rules.bare_state(None) is None and rules.bare_state("  ") is None
    assert rules.side_of("SALE") == "CREDIT" and rules.opposite("CREDIT") == "DEBIT"


@pytest.mark.parametrize(
    ("direction", "party_type", "party_state", "place", "expected"),
    [
        ("SALE", "UNREGISTERED", "MH", None, (SupplyContext.INTRA_STATE, False)),
        ("SALE", "REGULAR", "MH", "IN-KA", (SupplyContext.INTER_STATE, False)),
        ("SALE", "UNREGISTERED", "KA", None, (SupplyContext.INTER_STATE, False)),
        ("SALE", "OVERSEAS", None, None, (SupplyContext.INTER_STATE, True)),
        ("SALE", "SEZ_UNIT", "MH", None, (SupplyContext.INTER_STATE, True)),
        ("PURCHASE", "REGULAR", "MH", None, (SupplyContext.INTRA_STATE, False)),
        ("PURCHASE", "REGULAR", "GJ", None, (SupplyContext.INTER_STATE, False)),
        # Imports and SEZ supplies to the company are taxable inter-state, never zero-rated.
        ("PURCHASE", "OVERSEAS", None, None, (SupplyContext.INTER_STATE, False)),
        ("PURCHASE", "SEZ_UNIT", "MH", None, (SupplyContext.INTER_STATE, False)),
    ],
)
def test_determination_by_direction_and_party(
    direction: Any,
    party_type: str,
    party_state: str | None,
    place: str | None,
    expected: tuple[SupplyContext, bool],
) -> None:
    result = rules.determine(
        direction, "MH", party_type, party_state, place, utgst_states=frozenset()
    )
    assert isinstance(result, SupplyDetermination)
    assert (result.context, result.zero_rated) == expected


def test_union_territory_and_missing_place() -> None:
    ut = rules.determine(
        "SALE", "CH", "UNREGISTERED", "CH", None, utgst_states=frozenset({"IN-CH"})
    )
    assert isinstance(ut, SupplyDetermination) and ut.context is SupplyContext.INTRA_UT
    missing = rules.determine("SALE", "MH", "UNREGISTERED", None, None, utgst_states=frozenset())
    assert isinstance(missing, TaxException) and missing.code == "PLACE_OF_SUPPLY_MISSING"
    unknown = rules.determine("PURCHASE", "MH", "REGULAR", None, None, utgst_states=frozenset())
    assert isinstance(unknown, TaxException) and unknown.code == "PLACE_OF_SUPPLY_MISSING"
    with pytest.raises(ValueError):
        TaxException("NOT_A_CODE", "unknown")


def test_only_charging_suppliers_bill_gst() -> None:
    assert rules.supplier_charges("SALE", "UNREGISTERED")
    assert rules.supplier_charges("PURCHASE", "REGULAR")
    for kind in ("UNREGISTERED", "COMPOSITION", "OVERSEAS", "UIN"):
        assert not rules.supplier_charges("PURCHASE", kind)


def computation(context: SupplyContext, value: str = "1000") -> Any:
    parts = {
        SupplyContext.INTRA_STATE: [("CGST", "9"), ("SGST", "9")],
        SupplyContext.INTER_STATE: [("IGST", "18")],
        SupplyContext.INTRA_UT: [("CGST", "9"), ("UTGST", "9")],
    }[context]
    components = tuple(
        TaxComponent(cast(Any, code), cast(Any, "PERCENT"), cast(Any, "HALF_UP"), i, Decimal(p))
        for i, (code, p) in enumerate(parts)
    )
    reason = (
        SupplyReason.SAME_STATE
        if context is SupplyContext.INTRA_STATE
        else (
            SupplyReason.SAME_UT
            if context is SupplyContext.INTRA_UT
            else SupplyReason.DIFFERENT_STATE
        )
    )
    return compute(
        TaxRequest(
            lines=(
                TaxLine(
                    "L1", cast(Any, "SERVICE"), Decimal(value), cast(Any, "TAXABLE"), components
                ),
            ),
            determination=SupplyDetermination(context, False, reason),
            currency="INR",
            amount_precision=2,
            may_charge_tax=True,
        )
    )


def test_postings_follow_direction_recovery_and_reverse_charge() -> None:
    account = uuid7()
    intra = computation(SupplyContext.INTRA_STATE)
    sold = rules.gst_postings("SALE", intra, [TaxedLine("L1", account, False, False)])
    assert [(p.side, p.purpose, p.amount) for p in sold] == [
        ("CREDIT", "OUTPUT_CGST", Decimal("90.00")),
        ("CREDIT", "OUTPUT_SGST", Decimal("90.00")),
    ]
    inter = computation(SupplyContext.INTER_STATE)
    eligible = rules.gst_postings("PURCHASE", inter, [TaxedLine("L1", account, True, True)])
    assert eligible == [
        Posting("DEBIT", Decimal("180.00"), purpose="INPUT_IGST"),
        Posting("CREDIT", Decimal("180.00"), purpose="RCM_IGST"),
    ]
    blocked = rules.gst_postings("PURCHASE", inter, [TaxedLine("L1", account, True, False)])
    assert blocked[0] == Posting("DEBIT", Decimal("180.00"), account_id=account)
    assert blocked[1].purpose == "RCM_IGST"
    # Reverse-charge tax is never billed by the supplier.
    assert rules.supplier_tax(inter, [TaxedLine("L1", account, True, True)]) == 0
    assert rules.supplier_tax(inter, [TaxedLine("L1", account, False, True)]) == Decimal("180.00")
    assert rules.supplier_tax(None, []) == 0
    ut = computation(SupplyContext.INTRA_UT)
    assert [
        p.purpose for p in rules.gst_postings("SALE", ut, [TaxedLine("L1", account, False, False)])
    ] == [
        "OUTPUT_CGST",
        "OUTPUT_UTGST",
    ]


def test_withholding_base_party_amount_and_merging() -> None:
    taxable, gross, paid = Decimal("1000"), Decimal("1180"), Decimal("500")
    assert rules.withholding_base("BILL", taxable, gross, paid) == taxable
    assert rules.withholding_base("PAYMENT", taxable, gross, paid) == paid
    assert rules.withholding_base("INVOICE", taxable, gross, paid) == gross
    assert rules.party_amount(
        "INVOICE", taxable, Decimal(180), Decimal(180), Decimal(12)
    ) == Decimal("1192")
    assert rules.party_amount("BILL", taxable, Decimal(180), Decimal(180), Decimal(20)) == Decimal(
        "1160"
    )
    assert rules.party_amount("PAYMENT", taxable, ZERO, ZERO, ZERO) == taxable
    a, b = uuid7(), uuid7()
    merged = rules.aggregate(
        [
            (a, "DEBIT", Decimal(1)),
            (b, "CREDIT", Decimal(2)),
            (a, "DEBIT", Decimal(3)),
            (b, "DEBIT", ZERO),
        ]
    )
    assert merged == [(a, "DEBIT", Decimal(4)), (b, "CREDIT", Decimal(2))]
    assert all(type(amount) is Decimal for *_, amount in merged)
    assert rules.balance([("DEBIT", Decimal(5)), ("CREDIT", Decimal(5))]) == 0
    assert rules.snapshot_hash({"a": 1, "b": 2}) == rules.snapshot_hash({"b": 2, "a": 1})


def test_tax_block_shapes() -> None:
    validate_source_tax("INVOICE", None)
    with pytest.raises(ValueError):
        validate_source_tax("RECEIPT", SourceTax(taxable_value=Decimal(1)))
    with pytest.raises(ValueError):
        validate_source_tax("PAYMENT", SourceTax(gst=True, withholding_section_id=uuid7()))
    with pytest.raises(ValueError):
        validate_source_tax("BILL", SourceTax())
    with pytest.raises(ValueError):
        validate_source_tax("BILL", SourceTax(taxable_value=Decimal(1), gst=False))
    validate_source_tax("PAYMENT", SourceTax(gst=False, withholding_section_id=uuid7()))
    with pytest.raises(ValidationError):
        VoucherTax(direction="SALE", party_registration_id=uuid7())
    with pytest.raises(ValidationError):
        SourceTax(taxable_value=cast(Any, 1.5))
    with pytest.raises(ValidationError):
        SourceTax(place_of_supply="maharashtra")
    with pytest.raises(ValidationError):
        TaxPreviewRequest()
    with pytest.raises(ValidationError):
        TaxPreviewRequest.model_validate(
            {
                "source_document": {
                    "kind": "INVOICE",
                    "account_id": str(uuid7()),
                    "counterpart_account_id": str(uuid7()),
                    "currency": "INR",
                    "amount": "1",
                    "exchange_rate": "1",
                    "document_date": DATE,
                    "posting_date": DATE,
                    "reference": "X",
                    "source_system": "billing",
                    "source_type": "invoice",
                    "source_id": "1",
                    "description": "Untaxed",
                }
            }
        )
    assert SourceCreate.model_fields["tax"].default is None


# --- GST over HTTP -------------------------------------------------------------------------


async def test_intra_state_sale_splits_cgst_sgst_posts_once_and_stores_decimals(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    body = sale_journal(w, party_state="IN-MH")
    result = await preview(client, {"journal": body})
    assert result["status"] == "READY" and result["exceptions"] == [], result
    assert generated(result) == {
        "OUTPUT_CGST": ("CREDIT", Decimal("90")),
        "OUTPUT_SGST": ("CREDIT", Decimal("90")),
    }
    assert Decimal(result["tax_total"]) == Decimal("180")
    assert result["analysis"]["place_of_supply"] == "MH"
    key = str(uuid.uuid4())
    created = await client.post(BASE + "/journals", json=body, headers=th(key=key))
    assert created.status_code == 201, created.text
    replay = await client.post(BASE + "/journals", json=body, headers=th(key=key))
    assert replay.status_code == 201 and replay.json()["id"] == created.json()["id"]
    [row] = await evidence(app)
    assert row.supply_context == "INTRA_STATE" and row.line_count == 2
    for value in (row.taxable_value, row.tax_total):
        assert type(value) is Decimal
    assert row.tax_total == Decimal("180")
    stored = await journal_lines(app, created.json()["id"])
    assert len(stored) == 4 and all(type(item.amount) is Decimal for item in stored)
    posted_key = str(uuid.uuid4())
    posted = await post(client, created.json(), key=posted_key)
    assert posted.status_code == 200 and posted.json()["status"] == "POSTED", posted.text
    again = await post(client, created.json(), key=posted_key)
    assert again.status_code == 200 and again.headers["Idempotency-Replayed"] == "true"
    assert w["authority"].calls == 1 and len(await evidence(app)) == 1
    detail = await client.get(BASE + f"/journal-taxes/{row.id}", headers=th())
    assert detail.status_code == 200 and detail.json()["snapshot_hash"] == row.snapshot_hash
    listing = await client.get(BASE + "/journal-taxes", headers=th())
    assert listing.status_code == 200, listing.text
    [item] = listing.json()["items"]
    assert "snapshot" not in item and "request" not in item
    # A posted voucher is never recomputed: its evidence is not editable.
    edit = await client.put(
        BASE + f"/journals/{created.json()['id']}",
        json=body | {"expected_version": posted.json()["row_version"]},
        headers=th(),
    )
    assert edit.status_code == 409


async def test_inter_state_sale_is_igst_and_union_territory_is_utgst(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = await world(client, app)
    inter = await preview(
        client, {"journal": sale_journal(w, party_state="IN-MH", place_of_supply="IN-KA")}
    )
    assert inter["status"] == "READY", inter
    assert generated(inter) == {"OUTPUT_IGST": ("CREDIT", Decimal("180"))}
    assert inter["analysis"]["place_of_supply"] == "KA"
    missing = await preview(client, {"journal": sale_journal(w)})
    assert missing["status"] == "EXCEPTION" and missing["analysis"] is None
    assert [item["code"] for item in missing["exceptions"]] == ["PLACE_OF_SUPPLY_MISSING"]
    refused = await client.post(BASE + "/journals", json=sale_journal(w), headers=th())
    assert refused.status_code == 422 and "PLACE_OF_SUPPLY_MISSING" in refused.text

    monkeypatch.setattr(tasks, "_UTGST", frozenset({"CH"}))
    for purpose in ("OUTPUT_CGST", "OUTPUT_UTGST"):
        await tax_head(client, w["groups"], purpose, CH)
    ut_headers = th([CH])
    ut = await preview(client, {"journal": sale_journal(w, party_state="IN-CH")}, h=ut_headers)
    assert ut["status"] == "READY", ut
    assert generated(ut) == {
        "OUTPUT_CGST": ("CREDIT", Decimal("90")),
        "OUTPUT_UTGST": ("CREDIT", Decimal("90")),
    }
    created = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-CH"), headers=ut_headers
    )
    assert created.status_code == 201, created.text
    posted = await post(client, created.json(), registrations=[CH])
    assert posted.status_code == 200, posted.text
    [row] = await evidence(app)
    assert row.supply_context == "INTRA_UT" and row.company_registration_id == uuid.UUID(CH["id"])


async def test_reverse_charge_credits_rcm_and_recovers_only_eligible_input(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    eligible = purchase_journal(w, "rcm", party_state="IN-KA")
    result = await preview(client, {"journal": eligible})
    assert result["status"] == "READY", result
    assert generated(result) == {
        "INPUT_IGST": ("DEBIT", Decimal("180")),
        "RCM_IGST": ("CREDIT", Decimal("180")),
    }
    assert result["analysis"]["reverse_charge"] is True
    blocked = purchase_journal(w, "blocked", party_state="IN-KA")
    result = await preview(client, {"journal": blocked})
    assert result["status"] == "READY", result
    extra = [row for row in result["lines"] if row["generated"]]
    # Ineligible credit becomes cost on the expense account itself.
    assert [(row["account_id"], row["side"], Decimal(row["amount"])) for row in extra] == [
        (w["blocked"]["id"], "DEBIT", Decimal("180")),
        (w["heads"]["RCM_IGST"]["id"], "CREDIT", Decimal("180")),
    ]
    for body in (eligible, blocked):
        created = await client.post(BASE + "/journals", json=body, headers=th())
        assert created.status_code == 201, created.text
        posted = await post(client, created.json())
        assert posted.status_code == 200, posted.text
    rows = await evidence(app)
    assert len(rows) == 2 and all(row.reverse_charge for row in rows)
    # One voucher cannot mix forward and reverse charge.
    mixed = purchase_journal(w, "rcm", party_state="IN-KA")
    mixed["lines"] = [
        line(w["rcm"], "DEBIT", "1000"),
        line(w["stock"], "DEBIT", "1000"),
        line(w["cash"], "CREDIT", "2000"),
    ]
    result = await preview(client, {"journal": mixed})
    assert [item["code"] for item in result["exceptions"]] == ["MIXED_REVERSE_CHARGE"]


async def test_composition_company_may_not_charge_gst(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    h = th([KA_COMPOSITION])
    result = await preview(client, {"journal": sale_journal(w, party_state="IN-KA")}, h=h)
    assert result["status"] == "EXCEPTION"
    assert [item["code"] for item in result["exceptions"]] == ["REGIME_REFUSED"]
    refused = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-KA"), headers=h
    )
    assert refused.status_code == 422 and "REGIME_REFUSED" in refused.text
    assert await evidence(app) == []
    # Without any supplier registration on the date there is nothing to charge under.
    none = await preview(client, {"journal": sale_journal(w, party_state="IN-MH")}, h=th([]))
    assert [item["code"] for item in none["exceptions"]] == ["COMPANY_REGISTRATION_MISSING"]


async def test_closed_period_is_refused_before_tax_is_resolved(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    created = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-MH"), headers=th()
    )
    assert created.status_code == 201, created.text
    voided = await client.post(
        BASE + f"/journals/{created.json()['id']}/void",
        json={"expected_version": created.json()["row_version"], "reason": "Not needed"},
        headers=th(),
    )
    assert voided.status_code == 200, voided.text
    soft = await change(client, w["period"], "SOFT_CLOSED")
    assert soft.status_code == 200, soft.text
    closed = await change(client, soft.json(), "CLOSED")
    assert closed.status_code == 200, closed.text
    refused = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-MH"), headers=th()
    )
    assert refused.status_code == 409, refused.text
    assert "period" in refused.text.lower()
    assert len(await evidence(app)) == 1


async def test_rolled_back_create_leaves_no_journal_tax_or_audit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            before = await db.scalar(select(func.count(Outbox.id)))
            journals = await db.scalar(select(func.count(Journal.id)))
    policy = {
        "entity_type": "accounting.journal_tax",
        "field_key": "snapshot",
        "access": "write",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    denied = await client.post(
        BASE + "/journals",
        json=sale_journal(w, party_state="IN-MH"),
        headers=th(policies=[policy]),
    )
    assert denied.status_code == 403, denied.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == before
            assert await db.scalar(select(func.count(Journal.id))) == journals
            assert await db.scalar(select(func.count(JournalTax.id))) == 0


# --- TDS / TCS on party documents ----------------------------------------------------------


async def withholding(
    client: httpx.AsyncClient,
    party_id: str,
    *,
    kind: str = "TDS",
    certificate: bool = False,
    pan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """An active section with a rate and the party's profile; ``pan`` reuses an identifier."""
    if pan is None:
        pan = await send(
            client,
            "/party-identifiers",
            {
                "party_id": party_id,
                "scheme": "PAN",
                "value": "ABCDE1234F",
                "country_code": "IN",
                "valid_from": START,
            },
        )
    code, name = ("194C", "Contractors") if kind == "TDS" else ("206C1H", "Sale of goods")
    section = await send(
        client, "/withholding-sections", {"code": code, "kind": kind, "name": name}
    )
    section = await activate(client, "/withholding-sections", section, h=th())
    await send(
        client,
        "/withholding-rates",
        {
            "section_id": section["id"],
            "deductee_type": "COMPANY",
            "rate_percent": "2",
            "no_pan_rate_percent": "20",
            "single_transaction_threshold": "30000",
            "aggregate_annual_threshold": "100000",
            "threshold_currency": "INR",
            "threshold_basis": "AGGREGATE",
            "valid_from": START,
            **EVIDENCE,
        },
    )
    await send(
        client,
        "/party-withholding-profiles",
        {
            "party_id": party_id,
            "kind": kind,
            "deductee_type": "COMPANY",
            "pan_status": "VERIFIED",
            "pan_identifier_id": pan["id"],
            "default_section_id": section["id"],
            "valid_from": START,
        },
    )
    if certificate:
        await send(
            client,
            "/withholding-certificates",
            {
                "party_id": party_id,
                "section_id": section["id"],
                "certificate_reference": "LDC/2026/0001",
                "rate_percent": "0.5",
                "amount_limit": "50000",
                "currency": "INR",
                "valid_from": START,
                **EVIDENCE,
            },
        )
    return section | {"pan": pan}


def document(
    party_account: dict[str, Any],
    offset: dict[str, Any],
    amount: str,
    tax: dict[str, Any],
    *,
    kind: str = "BILL",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "account_id": party_account["id"],
        "counterpart_account_id": offset["id"],
        "currency": "INR",
        "amount": amount,
        "exchange_rate": "1",
        "document_date": DATE,
        "posting_date": DATE,
        "reference": "DOC-" + str(uuid.uuid4())[:8],
        "source_system": "billing",
        "source_type": kind.lower(),
        "source_id": str(uuid.uuid4()),
        "description": "Taxed source document",
        "tax": tax,
    }


async def post_document(
    client: httpx.AsyncClient, body: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    created = await client.post(BASE + "/source-documents", json=body, headers=th(**kwargs))
    assert created.status_code == 201, created.text
    journal = (
        await client.get(BASE + f"/journals/{created.json()['journal_id']}", headers=th())
    ).json()
    posted = await post(client, journal, **kwargs)
    assert posted.status_code == 200, posted.text
    return cast(dict[str, Any], posted.json())


async def test_tds_below_and_above_threshold_tracks_the_year(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    p, _, supplier = await party_accounts(client)
    section = await withholding(client, p["id"])
    tds = {"gst": False, "withholding_section_id": section["id"]}
    below = document(supplier, w["stock"], "10000", tds | {"taxable_value": "10000"})
    result = await preview(client, {"source_document": below})
    assert result["status"] == "READY" and Decimal(result["withholding_tax"]) == 0, result
    assert (
        not generated(result) and result["analysis"]["withholding"]["reason"] == "BELOW_THRESHOLD"
    )
    await post_document(client, below)

    above = document(supplier, w["stock"], "40000", tds | {"taxable_value": "40000"})
    result = await preview(client, {"source_document": above})
    assert [item["code"] for item in result["exceptions"]] == ["PARTY_AMOUNT_MISMATCH"]
    assert Decimal(result["party_amount"]) == Decimal("39200")
    refused = await client.post(BASE + "/source-documents", json=above, headers=th())
    assert refused.status_code == 422 and "PARTY_AMOUNT_MISMATCH" in refused.text
    above["amount"] = "39200"
    result = await preview(client, {"source_document": above})
    assert result["status"] == "READY", result
    assert generated(result) == {"TDS_PAYABLE": ("CREDIT", Decimal("800"))}
    await post_document(client, above)

    # The year holds 50000, 40000 of it withheld; 60000 more crosses the aggregate, so the
    # earlier unwithheld 10000 is caught up with the new value: 2% of 70000.
    later = document(supplier, w["stock"], "58600", tds | {"taxable_value": "60000"})
    result = await preview(client, {"source_document": later})
    assert result["status"] == "READY", result
    assert Decimal(result["withholding_tax"]) == Decimal("1400")
    rows = await evidence(app)
    assert [row.withholding_tax for row in rows] == [Decimal(0), Decimal("800")]
    assert all(type(row.withholding_amount) is Decimal for row in rows)

    # The feature gates withholding at preview and drafting alike.
    gated = await client.post(
        BASE + "/voucher-tax-previews",
        json={"source_document": later},
        headers=th(features={"multi_currency", "credit_limits"}),
    )
    assert gated.status_code == 409 and "tds" in gated.text.lower(), gated.text


@pytest.mark.parametrize("open_start", [False, True])
async def test_tds_certificate_rate_and_forward_charge_bill(
    client: httpx.AsyncClient, app: FastAPI, open_start: bool
) -> None:
    w = await world(client, app)
    p, _, supplier = await party_accounts(client)
    section = await withholding(client, p["id"], certificate=True)
    gstin = await register(
        client,
        p["id"],
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F1Z6",
            "state_code": "IN-GJ",
            "valid_from": None if open_start else START,
        },
    )
    assert gstin.status_code == 201, gstin.text
    tax = {
        "taxable_value": "40000",
        "party_registration_id": gstin.json()["id"],
        "withholding_section_id": section["id"],
    }
    # GJ supplier to an MH company: IGST input; TDS at the certificate's 0.5% on the value.
    body = document(supplier, w["stock"], "47000", tax)
    result = await preview(client, {"source_document": body})
    assert result["status"] == "READY", result
    assert generated(result) == {
        "INPUT_IGST": ("DEBIT", Decimal("7200")),
        "TDS_PAYABLE": ("CREDIT", Decimal("200")),
    }
    await post_document(client, body)
    [row] = await evidence(app)
    assert row.certificate_id is not None and row.certificate_base == Decimal("40000")
    assert row.party_registration_id == uuid.UUID(gstin.json()["id"])
    assert row.tax_total == Decimal("7200") and row.withholding_tax == Decimal("200")


async def test_tds_on_payment_and_tcs_on_sale(client: httpx.AsyncClient, app: FastAPI) -> None:
    w = await world(client, app)
    p, customer, supplier = await party_accounts(client)
    section = await withholding(client, p["id"])
    payment = document(
        supplier,
        w["cash"],
        "40000",
        {"gst": False, "withholding_section_id": section["id"]},
        kind="PAYMENT",
    )
    result = await preview(client, {"source_document": payment})
    assert result["status"] == "READY", result
    assert generated(result) == {"TDS_PAYABLE": ("CREDIT", Decimal("800"))}
    cash = next(row for row in result["lines"] if row["account_id"] == w["cash"]["id"])
    assert Decimal(cash["amount"]) == Decimal("39200")
    await post_document(client, payment)

    tcs = await withholding(client, p["id"], kind="TCS", pan=section["pan"])
    invoice = document(
        customer,
        w["income"],
        "40800",
        {"gst": False, "taxable_value": "40000", "withholding_section_id": tcs["id"]},
        kind="INVOICE",
    )
    result = await preview(client, {"source_document": invoice})
    assert result["status"] == "READY", result
    assert result["withholding_kind"] == "TCS"
    assert generated(result) == {"TCS_PAYABLE": ("CREDIT", Decimal("800"))}
    await post_document(client, invoice)
    kinds = sorted((row.withholding_kind or "") for row in await evidence(app))
    assert kinds == ["TCS", "TDS"]


# --- endpoint contract ---------------------------------------------------------------------


async def test_preview_and_reads_authentication_permission_scope_and_validation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    body = {"journal": sale_journal(w, party_state="IN-MH")}
    created = await client.post(BASE + "/journals", json=body["journal"], headers=th())
    assert created.status_code == 201, created.text
    [row] = await evidence(app)
    paths = ["/journal-taxes", f"/journal-taxes/{row.id}"]
    assert (await client.post(BASE + "/voucher-tax-previews", json=body)).status_code == 401
    for path in paths:
        assert (await client.get(BASE + path)).status_code == 401
    unpermitted = th(permissions=LEDGER_PERMISSIONS - {"ledger.read"})
    # Authorization precedes body validation.
    assert (
        await client.post(BASE + "/voucher-tax-previews", json={}, headers=unpermitted)
    ).status_code == 403
    for path in paths:
        assert (await client.get(BASE + path, headers=unpermitted)).status_code == 403
    assert (
        await client.post(BASE + "/voucher-tax-previews", json={}, headers=th())
    ).status_code == 422
    untaxed = {"journal": body["journal"] | {"tax": None}}
    assert (
        await client.post(BASE + "/voucher-tax-previews", json=untaxed, headers=th())
    ).status_code == 422
    plain = await client.post(BASE + "/journals/preview", json=body["journal"], headers=th())
    assert plain.status_code == 422
    other = th(company=OTHER_COMPANY)
    other_base = f"/v1/companies/{OTHER_COMPANY}"
    foreign = await client.get(other_base + f"/journal-taxes/{row.id}", headers=other)
    assert foreign.status_code == 403, foreign.text
    crossed = await client.post(other_base + "/voucher-tax-previews", json=body, headers=other)
    assert crossed.status_code == 403, crossed.text
    # A field the analysis reads cannot be denied to the reader and still be used.
    policy = {
        "entity_type": "accounting.account_tax_default",
        "field_key": "rule_id",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    hidden = await client.post(
        BASE + "/voucher-tax-previews", json=body, headers=th(policies=[policy])
    )
    assert hidden.status_code == 403, hidden.text


async def test_journal_tax_rows_are_tenant_isolated(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    created = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-MH"), headers=th()
    )
    assert created.status_code == 201, created.text
    assert len(await evidence(app)) == 1
    assert await evidence(app, OTHER_TENANT) == []
    stranger = headers(tenant=OTHER_TENANT, permissions=LEDGER_PERMISSIONS)
    listing = await client.get(BASE + "/journal-taxes", headers=stranger)
    assert listing.status_code == 200 and listing.json()["items"] == [], listing.text


async def test_draft_edits_recompute_and_posting_refuses_a_changed_analysis(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    w = await world(client, app)
    created = await client.post(
        BASE + "/journals", json=sale_journal(w, party_state="IN-MH"), headers=th()
    )
    assert created.status_code == 201, created.text
    path = BASE + f"/journals/{created.json()['id']}"
    edited = sale_journal(w, taxable="2000", gross="2360", party_state="IN-MH")
    updated = await client.put(
        path, json=edited | {"expected_version": created.json()["row_version"]}, headers=th()
    )
    assert updated.status_code == 200, updated.text
    [row] = await evidence(app)
    assert row.tax_total == Decimal("360") and row.row_version == 2
    untaxed = edited | {"tax": None, "expected_version": updated.json()["row_version"]}
    untaxed["lines"] = [line(w["cash"], "DEBIT", "2000"), line(w["income"], "CREDIT", "2000")]
    removed = await client.put(path, json=untaxed, headers=th())
    assert removed.status_code == 409, removed.text

    # TDS drafts; posting the first moves the year past the aggregate threshold, so the
    # others' stored analyses no longer hold. A bill's party amount is then wrong (422); a
    # payment still balances but its lines differ, so it must be recalculated (409).
    p, _, supplier = await party_accounts(client)
    section = await withholding(client, p["id"])
    tds = {"gst": False, "withholding_section_id": section["id"]}
    first = document(supplier, w["stock"], "20000", tds | {"taxable_value": "20000"})
    bill = document(supplier, w["stock"], "88200", tds | {"taxable_value": "90000"})
    payment = document(supplier, w["cash"], "90000", tds, kind="PAYMENT")
    drafts = []
    for body in (first, bill, payment):
        response = await client.post(BASE + "/source-documents", json=body, headers=th())
        assert response.status_code == 201, response.text
        drafts.append(
            (
                await client.get(BASE + f"/journals/{response.json()['journal_id']}", headers=th())
            ).json()
        )
    assert (await post(client, drafts[0])).status_code == 200
    wrong = await post(client, drafts[1])
    assert wrong.status_code == 422 and "PARTY_AMOUNT_MISMATCH" in wrong.text, wrong.text
    stale = await post(client, drafts[2])
    assert stale.status_code == 409 and "recalculate" in stale.text, stale.text
    for draft in drafts[1:]:
        current = await client.get(BASE + f"/journals/{draft['id']}", headers=th())
        assert current.json()["status"] != "POSTED"
