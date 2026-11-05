"""Duplicate supplier-bill guard, review findings: payable-ledger key, guarded fields,
normalisation and a bounded, fail-closed candidate walk.

``test_duplicate_supplier_bill.py`` covers the guard itself; this file covers what an independent
review found missing from it.
"""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select
from test_duplicate_supplier_bill import (
    CODE,
    FISCAL_START,
    LOOKUP,
    another_supplier,
    books,
    found,
    lookup,
    ready,
    save,
    submit,
)
from test_purchase_lifecycle_integrity import TODAY, owner

from vouchers.domain.duplicate_bill import normalize_bill_reference
from vouchers.models import core as m
from vouchers.tasks import duplicate_bills

INCOMPLETE = "duplicate supplier bill check incomplete"


async def ask(client, prefix, params, **kwargs):
    base = {"bill_reference": "INV-1", "document_date": TODAY}
    return await client.get(
        prefix + LOOKUP, params=base | params, headers=kwargs.pop("headers", headers())
    )


async def by_ledger(client, prefix, ledger, reference, **kwargs):
    result = await ask(
        client,
        prefix,
        {"party_account_id": ledger.base["party_account_id"], "bill_reference": reference},
        **kwargs,
    )
    assert result.status_code == 200, result.text
    return result.json()


def day(offset: int) -> dict[str, str]:
    value = (FISCAL_START + dt.timedelta(days=offset)).isoformat()
    return {"document_date": value, "posting_date": value}


# 1. Normalisation (pure) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right",
    [
        ("INV-1", "inv-1"),
        ("INV" + chr(0xA0) + "1", "INV 1"),
        ("INV" + chr(0x2003) + " 1", "INV 1"),
        ("INV-1.", "INV-1"),
        ("INV-1 ,;:", "INV-1"),
        (" .:INV-1;. ", "inv-1"),
        ("INV" + chr(0x2011) + "1", "INV-1"),
        ("INV" + chr(0x2013) + "1", "INV-1"),
        ("INV" + chr(0x2014) + "1", "INV-1"),
        ("INV" + chr(0x2212) + "1", "INV-1"),
        ("INV" + chr(0xFE58) + "1", "INV-1"),
        ("INV" + chr(0x200B) + "-1", "INV-1"),
        (chr(0xFEFF) + "INV-1", "INV-1"),
        ("INV" + chr(0xAD) + "-1", "INV-1"),
        ("IN" + chr(0x200D) + "V-1", "INV-1"),
        ("".join(chr(ord(c) + 0xFEE0) if c != "-" else chr(0xFF0D) for c in "INV-1"), "inv-1"),
        ("Straße-1", "STRASSE-1"),
    ],
)
def test_references_that_differ_only_in_formatting_are_the_same_bill(left, right):
    assert normalize_bill_reference(left) == normalize_bill_reference(right)


@pytest.mark.parametrize(
    "left,right",
    [
        ("INV-1", "INV-2"),
        ("INV/1", "INV-1"),
        ("0418", "418"),
        ("INV 1", "INV1"),
        ("INV.1", "INV1"),
        ("INV-1", "INV--1"),
        ("INV-10", "INV-1"),
    ],
)
def test_references_that_differ_in_content_stay_different_bills(left, right):
    assert normalize_bill_reference(left) != normalize_bill_reference(right)


@pytest.mark.parametrize("value", ["", "   ", "...", " , ; : ", chr(0x200B), chr(0xFEFF) + " ."])
def test_a_reference_with_nothing_but_formatting_has_no_key(value):
    assert normalize_bill_reference(value) == ""


# 2. The payable ledger is a key too ---------------------------------------------------------


async def test_submit_refuses_a_bill_without_header_parties_by_its_payable_ledger(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-77", parties=[])
    user = uuid7()
    second = await ready(client, prefix, ledger, " sup-77 ", user=user, parties=[])
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == CODE and error["fields"]["matches.0.id"] == first["id"]
    accepted = await submit(client, prefix, second, user, acknowledge=True)
    assert accepted.status_code == 200, accepted.text


async def test_the_ledger_key_matches_across_a_bill_with_and_without_a_header_supplier(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    with_party = await save(client, prefix, ledger, "SUP-1")
    without = await save(client, prefix, ledger, "SUP-2", parties=[])
    user = uuid7()
    plain = await ready(client, prefix, ledger, "sup-1", user=user, parties=[])
    refused = await submit(client, prefix, plain, user)
    assert refused.status_code == 409
    assert refused.json()["error"]["fields"]["matches.0.id"] == with_party["id"]
    other = uuid7()
    named = await ready(client, prefix, ledger, "SUP-2", user=other)
    again = await submit(client, prefix, named, other)
    assert again.status_code == 409, again.text
    assert again.json()["error"]["fields"]["matches.0.id"] == without["id"]


async def test_another_payable_ledger_is_not_the_same_supplier(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    other = await another_supplier(app, ledger)
    await save(client, prefix, other, "SUP-90", parties=[])
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-90", user=user, parties=[])
    assert (await submit(client, prefix, second, user)).status_code == 200


async def test_a_bill_matched_by_supplier_and_ledger_is_reported_once(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-91")
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-91", user=user)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409
    fields = refused.json()["error"]["fields"]
    assert fields["matches.0.id"] == first["id"] and "matches.1.id" not in fields
    result = await ask(
        client,
        prefix,
        {
            "party_id": str(ledger.supplier),
            "party_account_id": ledger.base["party_account_id"],
            "bill_reference": "SUP-91",
            "exclude_voucher_id": second["id"],
        },
    )
    assert [row["id"] for row in result.json()["items"]] == [first["id"]]


async def test_lookup_by_party_account_alone_and_by_supplier_alone(client, prefix, app):
    ledger = await books(client, prefix, app)
    with_party = await save(client, prefix, ledger, "INV-1")
    without = await save(client, prefix, ledger, "INV-1", parties=[], **day(1))
    both = {row["id"] for row in (await by_ledger(client, prefix, ledger, " inv-1 "))["items"]}
    assert both == {with_party["id"], without["id"]}
    # The supplier alone keeps working exactly as before: it cannot see a bill with no party row.
    assert [row["id"] for row in await found(client, prefix, ledger, "INV-1")] == [with_party["id"]]
    other = await another_supplier(app, ledger)
    assert (await by_ledger(client, prefix, other, "INV-1"))["items"] == []


async def test_lookup_needs_the_supplier_or_the_ledger(client, prefix, app):
    ledger = await books(client, prefix, app)
    for params in ({}, {"party_id": None}, {"exclude_voucher_id": str(uuid7())}):
        result = await ask(client, prefix, {k: v for k, v in params.items() if v is not None})
        assert result.status_code == 422, (params, result.text)
    for bad in ({"party_account_id": "not-a-uuid"}, {"party_account_id": ""}):
        result = await ask(client, prefix, bad | {"party_id": str(ledger.supplier)})
        assert result.status_code == 422, (bad, result.text)
    twice = await client.get(
        prefix + LOOKUP + f"?party_account_id={uuid7()}&party_account_id={uuid7()}"
        f"&bill_reference=a&document_date={TODAY}",
        headers=headers(),
    )
    assert twice.status_code == 422


async def test_ledger_lookup_never_crosses_tenant_or_company(client, prefix, app):
    ledger = await books(client, prefix, app)
    mine = await save(client, prefix, ledger, "INV-1", parties=[])
    rows = (await by_ledger(client, prefix, ledger, "INV-1"))["items"]
    assert [row["id"] for row in rows] == [mine["id"]]
    stranger = await by_ledger(
        client, prefix, ledger, "INV-1", headers=headers(tenant=uuid7(), user=uuid7())
    )
    assert stranger["items"] == []
    elsewhere = uuid7()
    own = prefix.replace(str(COMPANY), str(elsewhere))
    foreign = await by_ledger(client, own, ledger, "INV-1", headers=headers(company=elsewhere))
    assert foreign["items"] == []
    # This company's credentials do not open another company's URL, nor the reverse.
    params = {"party_account_id": ledger.base["party_account_id"]}
    assert (await ask(client, own, params, headers=headers())).status_code == 401
    other = headers(company=elsewhere)
    mixed = headers() | {
        "X-Actor-Context": other["X-Actor-Context"],
        "X-Actor-Signature": other["X-Actor-Signature"],
    }
    assert (await ask(client, prefix, params, headers=mixed)).status_code == 403
    assert (await ask(client, prefix, params, headers={})).status_code == 401
    lacking = headers(permissions=frozenset({"vouchers.submit"}))
    assert (await ask(client, prefix, params, headers=lacking)).status_code == 403


# 3. Every returned or filtered field is guarded ---------------------------------------------


async def test_lookup_is_closed_when_kind_or_id_is_not_readable(client, prefix, app):
    ledger = await books(client, prefix, app)
    await save(client, prefix, ledger, "INV-1")
    for field in ("kind", "id"):
        policy = {
            "entity_type": "vouchers.voucher",
            "field_key": field,
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
        result = await lookup(client, prefix, ledger, "INV-1", headers=headers(policies=[policy]))
        assert result.status_code == 403, (field, result.text)
    assert {"kind", "id"} <= duplicate_bills.GUARDED_FIELDS


# 4. A bounded, batched walk that fails closed -------------------------------------------------


def small_walk(monkeypatch, *, ceiling, batch):
    monkeypatch.setattr(duplicate_bills, "CANDIDATE_CEILING", ceiling)
    monkeypatch.setattr(duplicate_bills, "BATCH_SIZE", batch)


async def numbered(client, prefix, ledger, count, *, oldest="OLD-1", **changes):
    """``count`` bills, the oldest (document date) carrying ``oldest``; returns it first."""
    rows = [await save(client, prefix, ledger, oldest, **day(0), **changes)]
    for index in range(1, count):
        rows.append(await save(client, prefix, ledger, f"NEW-{index}", **day(index), **changes))
    return rows


async def test_an_older_duplicate_beyond_the_ceiling_is_reported_as_truncated(
    client, prefix, app, monkeypatch
):
    ledger = await books(client, prefix, app)
    small_walk(monkeypatch, ceiling=3, batch=2)
    await numbered(client, prefix, ledger, 5)
    result = await lookup(client, prefix, ledger, "OLD-1")
    assert result.status_code == 200, result.text
    assert result.json() == {"items": [], "truncated": True}
    ledger_view = await by_ledger(client, prefix, ledger, "OLD-1")
    assert ledger_view == {"items": [], "truncated": True}


async def test_a_walk_that_reaches_every_row_is_complete_even_at_the_exact_ceiling(
    client, prefix, app, monkeypatch
):
    ledger = await books(client, prefix, app)
    rows = await numbered(client, prefix, ledger, 5)
    small_walk(monkeypatch, ceiling=5, batch=2)
    result = await lookup(client, prefix, ledger, "OLD-1")
    assert result.json() == {
        "items": [
            {
                "id": rows[0]["id"],
                "status": "DRAFT",
                "document_date": FISCAL_START.isoformat(),
                "bill_reference": "OLD-1",
                "revision_number": 1,
            }
        ],
        "truncated": False,
    }
    small_walk(monkeypatch, ceiling=4, batch=2)
    assert (await lookup(client, prefix, ledger, "OLD-1")).json()["truncated"] is True


async def test_batches_cross_rows_that_share_a_date_without_skipping_or_repeating(
    client, prefix, app, monkeypatch
):
    ledger = await books(client, prefix, app)
    same = day(2)
    first = await save(client, prefix, ledger, "TARGET", **same)
    for index in range(6):
        await save(client, prefix, ledger, f"OTHER-{index}", **same)
    small_walk(monkeypatch, ceiling=100, batch=2)
    result = (await lookup(client, prefix, ledger, "TARGET")).json()
    assert [row["id"] for row in result["items"]] == [first["id"]]
    assert result["truncated"] is False
    for index in range(6):
        again = (await lookup(client, prefix, ledger, f"other-{index}")).json()
        assert len(again["items"]) == 1 and again["truncated"] is False


async def test_enough_matches_stop_the_walk_before_the_ceiling(client, prefix, app, monkeypatch):
    ledger = await books(client, prefix, app)
    for index in range(6):
        await save(client, prefix, ledger, "DUP", **day(index))
    small_walk(monkeypatch, ceiling=5, batch=2)
    result = (await lookup(client, prefix, ledger, "DUP")).json()
    assert len(result["items"]) == 5 and result["truncated"] is False


async def test_submit_fails_closed_when_the_check_was_incomplete(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    old = await save(client, prefix, ledger, "SUP-95", **day(0))
    for index in range(1, 4):
        await save(client, prefix, ledger, f"NEW-{index}", **day(index))
    user = uuid7()
    second = await ready(client, prefix, ledger, "sup-95", user=user)
    small_walk(monkeypatch, ceiling=3, batch=2)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == CODE and "incomplete" in error["message"]
    assert "fields" not in error
    assert old["id"] not in refused.text
    accepted = await submit(
        client, prefix, second, user, acknowledge=True, reason="Checked by hand"
    )
    assert accepted.status_code == 200, accepted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            [row] = list(await db.scalars(select(m.VoucherTransition)))
            assert row.reason.startswith("Checked by hand") and INCOMPLETE in row.reason
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "vouchers.voucher.submit")
            )
            assert event.payload["changes"] == {
                "duplicate_bill_acknowledged": True,
                "duplicate_voucher_ids": [],
                "duplicate_check_incomplete": True,
            }


async def test_a_complete_walk_without_a_match_submits_without_acknowledgement(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    for index in range(3):
        await save(client, prefix, ledger, f"NEW-{index}", **day(index))
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-96", user=user)
    small_walk(monkeypatch, ceiling=3, batch=2)
    assert (await submit(client, prefix, second, user)).status_code == 200


async def test_an_incomplete_ledger_walk_alone_also_fails_closed(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    for index in range(4):
        await save(client, prefix, ledger, f"NEW-{index}", parties=[], **day(index))
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-97", user=user, parties=[])
    small_walk(monkeypatch, ceiling=3, batch=2)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409 and "incomplete" in refused.json()["error"]["message"]


def test_the_production_ceiling_is_the_documented_one():
    assert duplicate_bills.CANDIDATE_CEILING == 20_000
    assert 0 < duplicate_bills.BATCH_SIZE <= 1000
