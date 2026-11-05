"""Duplicate supplier-bill guard (decision D2): a lookup and a confirmable refusal at submit.

One supplier's bill number is recorded once per fiscal year unless the person at the keyboard
says it is meant. Matching ignores case and runs of whitespace, looks only at bills that still
stand, and never at the voucher being submitted.
"""

import copy
import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import func, select
from test_foundation import create_type
from test_invoice_capture import invoice_body
from test_purchase_lifecycle_integrity import CALCULATION, TODAY, owner, path, request_for, seed

from vouchers.domain.documents import fiscal_start
from vouchers.domain.duplicate_bill import annotate, normalize_bill_reference
from vouchers.models import core as m

LOOKUP = "/vouchers/duplicate-bills"
POLICY = {"invoice": {}}
CODE = "duplicate_supplier_bill"
ACK = "duplicate supplier bill acknowledged"
FISCAL_START = fiscal_start(dt.date.today(), 4, 1)


class Books:
    """One company's Purchase type and one supplier whose payable ledger is projected."""

    def __init__(self, kind, base, supplier):
        self.kind, self.base, self.supplier = kind, base, supplier


async def books(client, prefix, app, policy=None, kind="PURCHASE") -> Books:
    made = await create_type(client, prefix, kind=kind, policy=POLICY | (policy or {}))
    base = invoice_body()
    base["components"] = []
    supplier = uuid7()
    await seed(app, base, supplier=supplier, ledger_party=supplier)
    return Books(made, base, supplier)


async def another_supplier(app, books_):
    base = invoice_body()
    base["components"] = []
    supplier = uuid7()
    await seed(app, base, supplier=supplier, ledger_party=supplier)
    return Books(books_.kind, base, supplier)


async def save(client, prefix, ledger, reference, *, user=None, **changes):
    body = copy.deepcopy(ledger.base) | {"bill_reference": reference}
    request = request_for(ledger.kind, body, ledger.supplier, **changes)
    created = await client.post(
        prefix + "/vouchers", json=request, headers=headers(user=user or uuid7())
    )
    assert created.status_code == 201, created.text
    return created.json()


async def accept(client, prefix, document, user):
    result = await client.post(
        path(prefix, document, "/invoice-acceptance"),
        json={"expected_version": document["row_version"], "calculation_hash": CALCULATION},
        headers=headers(user=user),
    )
    assert result.status_code == 200, result.text
    return result.json()


async def ready(client, prefix, ledger, reference, *, user, **changes):
    """A saved and accepted bill, ready to submit."""
    return await accept(
        client, prefix, await save(client, prefix, ledger, reference, user=user, **changes), user
    )


async def lookup(client, prefix, ledger, reference, *, day=TODAY, exclude=None, **kwargs):
    params = {"party_id": str(ledger.supplier), "bill_reference": reference, "document_date": day}
    if exclude is not None:
        params["exclude_voucher_id"] = str(exclude)
    return await client.get(
        prefix + LOOKUP, params=params, headers=kwargs.pop("headers", headers())
    )


async def found(client, prefix, ledger, reference, **kwargs):
    result = await lookup(client, prefix, ledger, reference, **kwargs)
    assert result.status_code == 200, result.text
    return result.json()["items"]


async def submit(client, prefix, document, user, *, acknowledge=None, reason=None, key=None):
    body = {"expected_version": document["row_version"]}
    if acknowledge is not None:
        body["acknowledge_duplicate_bill"] = acknowledge
    if reason is not None:
        body["reason"] = reason
    return await client.post(
        path(prefix, document, "/submit"), json=body, headers=headers(user=user, key=key)
    )


# 1. Domain rules, no database ---------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right",
    [
        ("INV-1", "inv-1"),
        ("  INV-1  ", "INV-1"),
        ("INV   1", "inv 1"),
        ("INV\t1\n", "INV 1"),
        ("INV" + chr(0xA0) + "1", "inv 1"),
        ("Straße 1", "STRASSE 1"),
    ],
)
def test_references_that_differ_only_in_case_or_whitespace_are_the_same_bill(left, right):
    assert normalize_bill_reference(left) == normalize_bill_reference(right)


@pytest.mark.parametrize("left,right", [("INV-1", "INV-10"), ("INV 1", "INV1"), ("A/1", "A / 1")])
def test_other_references_are_different_bills(left, right):
    assert normalize_bill_reference(left) != normalize_bill_reference(right)


def test_system_notes_never_overflow_the_reason_column():
    assert annotate("", "note") == "note"
    assert annotate("why", "note") == "why [note]"
    assert annotate("keep") == "keep"
    long = annotate("x" * 500, "a long system note")
    assert len(long) == 500 and long.endswith("[a long system note]")


# 2. The lookup --------------------------------------------------------------------------------


async def test_lookup_returns_lean_rows_for_a_live_bill(client, prefix, app):
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "INV-100")
    items = await found(client, prefix, ledger, "INV-100")
    assert items == [
        {
            "id": first["id"],
            "status": "DRAFT",
            "document_date": TODAY,
            "bill_reference": "INV-100",
            "revision_number": 1,
        }
    ]
    assert (await lookup(client, prefix, ledger, "INV-100")).headers["Cache-Control"] == "no-store"


async def test_lookup_ignores_case_and_runs_of_whitespace(client, prefix, app):
    ledger = await books(client, prefix, app)
    saved = await save(client, prefix, ledger, "Acme / INV   100")
    for typed in ("acme / inv 100", "  ACME /  INV 100  ", "Acme\t/ INV\n100"):
        assert [row["id"] for row in await found(client, prefix, ledger, typed)] == [saved["id"]]
    for other in ("Acme / INV 1000", "Acme/INV 100", "INV 100"):
        assert await found(client, prefix, ledger, other) == []


async def test_lookup_ignores_bills_that_no_longer_stand(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    cancelled = await save(client, prefix, ledger, "INV-7")
    gone = await client.post(
        path(prefix, cancelled, "/cancel"),
        json={"expected_version": cancelled["row_version"], "reason": "Entered twice"},
        headers=headers(),
    )
    assert gone.status_code == 200, gone.text
    author, other = uuid7(), uuid7()
    refused = await ready(client, prefix, ledger, "INV-8", user=author)
    submitted = (await submit(client, prefix, refused, author)).json()
    rejected = await client.post(
        path(prefix, submitted, "/reject"),
        json={"expected_version": submitted["row_version"], "reason": "Wrong supplier"},
        headers=headers(user=other),
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert await found(client, prefix, ledger, "INV-7") == []
    assert await found(client, prefix, ledger, "INV-8") == []


async def test_lookup_is_per_supplier(client, prefix, app):
    ledger = await books(client, prefix, app)
    other = await another_supplier(app, ledger)
    mine = await save(client, prefix, ledger, "INV-1")
    theirs = await save(client, prefix, other, "INV-1")
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-1")] == [mine["id"]]
    assert [r["id"] for r in await found(client, prefix, other, "INV-1")] == [theirs["id"]]


async def test_lookup_is_per_fiscal_year(client, prefix, app):
    ledger = await books(client, prefix, app)
    old_day = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    last_year = await save(
        client, prefix, ledger, "INV-9", document_date=old_day, posting_date=old_day
    )
    start = FISCAL_START.isoformat()
    this_year = await save(client, prefix, ledger, "INV-9", document_date=start, posting_date=start)
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-9")] == [this_year["id"]]
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-9", day=old_day)] == [
        last_year["id"]
    ]
    # A date anywhere in the same fiscal year finds the whole year.
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-9", day=start)] == [
        this_year["id"]
    ]


async def test_lookup_looks_only_at_purchases(client, prefix, app):
    ledger = await books(client, prefix, app)
    sales = Books(
        await create_type(client, prefix, code="SALE", kind="SALES", policy=POLICY),
        ledger.base,
        ledger.supplier,
    )
    await save(client, prefix, sales, "INV-1")
    assert await found(client, prefix, ledger, "INV-1") == []
    purchase = await save(client, prefix, ledger, "INV-1")
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-1")] == [purchase["id"]]


async def test_lookup_excludes_the_named_voucher_and_uses_the_current_revision(client, prefix, app):
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "INV-5")
    assert await found(client, prefix, ledger, "INV-5", exclude=first["id"]) == []
    body = copy.deepcopy(ledger.base) | {"bill_reference": "INV-6"}
    edited = await client.put(
        path(prefix, first),
        json={
            "expected_version": first["row_version"],
            "content": request_for(ledger.kind, body, ledger.supplier),
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    assert await found(client, prefix, ledger, "INV-5") == []
    [row] = await found(client, prefix, ledger, "INV-6")
    assert row["revision_number"] == 2 and row["id"] == first["id"]


async def test_lookup_returns_at_most_five_most_recent_first(client, prefix, app):
    ledger = await books(client, prefix, app)
    for offset in range(7):
        day = (FISCAL_START + dt.timedelta(days=offset)).isoformat()
        await save(client, prefix, ledger, "INV-3", document_date=day, posting_date=day)
    items = await found(client, prefix, ledger, "INV-3")
    assert len(items) == 5
    assert [row["document_date"] for row in items] == sorted(
        (row["document_date"] for row in items), reverse=True
    )


async def test_lookup_authentication_permission_company_and_input(client, prefix, app):
    ledger = await books(client, prefix, app)
    await save(client, prefix, ledger, "INV-1")
    params = {"party_id": str(ledger.supplier), "bill_reference": "INV-1", "document_date": TODAY}
    assert (await client.get(prefix + LOOKUP, params=params)).status_code == 401
    lacking = headers(permissions=frozenset({"vouchers.submit"}))
    assert (await client.get(prefix + LOOKUP, params=params, headers=lacking)).status_code == 403
    other = uuid.uuid4()
    # Credentials issued for another company are not this company's credentials at all (401); a
    # caller holding the permission in another company only is authenticated but not permitted.
    wrong_url = prefix.replace(str(COMPANY), str(other)) + LOOKUP
    assert (await client.get(wrong_url, params=params, headers=headers())).status_code == 401
    elsewhere = headers(company=other)
    mixed = headers() | {
        "X-Actor-Context": elsewhere["X-Actor-Context"],
        "X-Actor-Signature": elsewhere["X-Actor-Signature"],
    }
    foreign = await client.get(prefix + LOOKUP, params=params, headers=mixed)
    assert foreign.status_code == 403, foreign.text
    for bad in (
        {k: v for k, v in params.items() if k != "party_id"},
        {k: v for k, v in params.items() if k != "bill_reference"},
        params | {"bill_reference": "   "},
        params | {"bill_reference": "x" * 121},
        params | {"document_date": "31-12-2026"},
        params | {"party_id": "not-a-uuid"},
        params | {"limit": "50"},
    ):
        result = await client.get(prefix + LOOKUP, params=bad, headers=headers())
        assert result.status_code == 422, (bad, result.text)
    twice = await client.get(
        prefix + LOOKUP + "?bill_reference=a&bill_reference=b", headers=headers()
    )
    assert twice.status_code == 422


async def test_lookup_is_closed_to_a_caller_who_may_not_read_the_filtered_fields(
    client, prefix, app
):
    ledger = await books(client, prefix, app)
    await save(client, prefix, ledger, "INV-1")
    for field in ("invoice", "parties", "document_date", "status"):
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


async def test_lookup_never_shows_another_tenants_bills(client, prefix, app):
    ledger = await books(client, prefix, app)
    mine = await save(client, prefix, ledger, "INV-1")
    assert [r["id"] for r in await found(client, prefix, ledger, "INV-1")] == [mine["id"]]
    stranger = headers(tenant=uuid7(), user=uuid7())
    result = await lookup(client, prefix, ledger, "INV-1", headers=stranger)
    assert result.status_code == 200, result.text
    assert result.json() == {"items": [], "truncated": False}


# 3. Enforcement at submit ----------------------------------------------------------------------


async def test_submit_refuses_a_recorded_bill_number_with_a_stable_code(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-77")
    user = uuid7()
    second = await ready(client, prefix, ledger, " sup-77 ", user=user)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == CODE
    assert first["id"] in error["message"] and "DRAFT" in error["message"]
    assert error["fields"] == {
        "matches.0.id": first["id"],
        "matches.0.status": "DRAFT",
        "matches.0.document_date": TODAY,
        "matches.0.bill_reference": "SUP-77",
        "matches.0.revision_number": "1",
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            voucher = await db.get(m.Voucher, uuid.UUID(second["id"]))
            assert (voucher.status, voucher.row_version) == ("DRAFT", second["row_version"])
            assert await db.scalar(select(func.count(m.VoucherTransition.id))) == 0
            assert (
                await db.scalar(
                    select(func.count(Outbox.id)).where(
                        Outbox.event_type == "vouchers.voucher.submit"
                    )
                )
                == 0
            )


async def test_an_acknowledged_duplicate_is_submitted_and_the_acknowledgement_is_recorded(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-78")
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-78", user=user)
    submitted = await submit(
        client, prefix, second, user, acknowledge=True, reason="Supplier re-issued the bill"
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            [row] = list(await db.scalars(select(m.VoucherTransition)))
            assert row.reason.startswith("Supplier re-issued the bill") and ACK in row.reason
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "vouchers.voucher.submit")
            )
            assert ACK in event.payload["reason"]
            assert event.payload["changes"] == {
                "duplicate_bill_acknowledged": True,
                "duplicate_voucher_ids": [first["id"]],
            }


async def test_acknowledging_replayed_with_the_same_key_has_one_effect(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    await save(client, prefix, ledger, "SUP-79")
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-79", user=user)
    key = str(uuid.uuid4())
    one = await submit(client, prefix, second, user, acknowledge=True, key=key)
    two = await submit(client, prefix, second, user, acknowledge=True, key=key)
    assert one.status_code == two.status_code == 200
    assert two.headers["Idempotency-Replayed"] == "true"
    # The same key cannot be reused with a different answer to the question.
    changed = await submit(client, prefix, second, user, acknowledge=False, key=key)
    assert changed.status_code == 422
    assert changed.json()["error"]["code"] == "idempotency_key_reused"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherTransition.id))) == 1


async def test_a_bill_never_duplicates_itself_and_other_suppliers_do_not_count(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    other = await another_supplier(app, ledger)
    await save(client, prefix, other, "SUP-80")
    user = uuid7()
    only = await ready(client, prefix, ledger, "SUP-80", user=user)
    assert (await submit(client, prefix, only, user)).status_code == 200


async def test_an_acknowledgement_that_was_not_needed_is_not_recorded(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    user = uuid7()
    only = await ready(client, prefix, ledger, "SUP-81", user=user)
    assert (await submit(client, prefix, only, user, acknowledge=True)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            [row] = list(await db.scalars(select(m.VoucherTransition)))
            assert ACK not in row.reason


async def test_a_cancelled_bill_does_not_block_the_same_number(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-82")
    assert (
        await client.post(
            path(prefix, first, "/cancel"),
            json={"expected_version": first["row_version"], "reason": "Entered twice"},
            headers=headers(),
        )
    ).status_code == 200
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-82", user=user)
    assert (await submit(client, prefix, second, user)).status_code == 200


async def test_the_guard_applies_to_purchases_only(client, prefix, app, monkeypatch):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    sales = Books(
        await create_type(client, prefix, code="SALE", kind="SALES", policy=POLICY),
        ledger.base,
        ledger.supplier,
    )
    await save(client, prefix, sales, "SUP-83")
    user = uuid7()
    second = await ready(client, prefix, sales, "SUP-83", user=user)
    assert (await submit(client, prefix, second, user)).status_code == 200


async def test_a_whitespace_only_reference_cannot_be_submitted(client, prefix, app, monkeypatch):
    # Since the 2026-11-02 review a Purchase needs a real bill number at submit, rather than a
    # blank one slipping past the duplicate guard.
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await client.post(
        prefix + "/vouchers",
        json=request_for(
            ledger.kind, copy.deepcopy(ledger.base) | {"bill_reference": "   "}, ledger.supplier
        ),
        headers=headers(),
    )
    if first.status_code == 422:
        return  # the contract already refuses a blank reference
    assert first.status_code == 201, first.text
    user = uuid7()
    second = await ready(client, prefix, ledger, "   ", user=user)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 422, refused.text
    assert "bill number" in refused.json()["error"]["message"]


async def test_the_acknowledgement_belongs_to_submit_alone(client, prefix, app):
    ledger = await books(client, prefix, app)
    draft = await save(client, prefix, ledger, "SUP-84")
    refused = await client.post(
        path(prefix, draft, "/cancel"),
        json={
            "expected_version": draft["row_version"],
            "reason": "No",
            "acknowledge_duplicate_bill": True,
        },
        headers=headers(),
    )
    assert refused.status_code == 422, refused.text
    for bad in ("yes", 1, None):
        result = await client.post(
            path(prefix, draft, "/submit"),
            json={"expected_version": 1, "acknowledge_duplicate_bill": bad},
            headers=headers(),
        )
        assert result.status_code == 422, (bad, result.text)
    extra = await client.post(
        path(prefix, draft, "/submit"),
        json={"expected_version": 1, "acknowledge": True},
        headers=headers(),
    )
    assert extra.status_code == 422


async def test_a_caller_who_cannot_read_vouchers_is_refused_without_the_matching_rows(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app)
    first = await save(client, prefix, ledger, "SUP-85")
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-85", user=user)
    blind = headers(user=user, permissions=frozenset({"vouchers.submit"}))
    refused = await client.post(
        path(prefix, second, "/submit"),
        json={"expected_version": second["row_version"]},
        headers=blind,
    )
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == CODE and "fields" not in error
    assert first["id"] not in refused.text


async def test_the_guard_also_applies_where_approval_is_not_required(
    client, prefix, app, monkeypatch
):
    owner(app, monkeypatch)
    ledger = await books(client, prefix, app, {"approval_required": False})
    first = await save(client, prefix, ledger, "SUP-86")
    user = uuid7()
    second = await ready(client, prefix, ledger, "SUP-86", user=user)
    refused = await submit(client, prefix, second, user)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == CODE
    accepted = await submit(client, prefix, second, user, acknowledge=True)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "APPROVED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            [row] = list(await db.scalars(select(m.VoucherTransition)))
            assert ACK in row.reason and "approval not required" in row.reason
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "vouchers.voucher.submit")
            )
            assert event.payload["changes"]["duplicate_voucher_ids"] == [first["id"]]
            assert event.payload["changes"]["approval"] == "not_required"
