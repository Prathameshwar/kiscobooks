"""Voucher lists use current revisions and bounded, authority-aware access paths."""

import datetime as dt

from billing_platform.ids import uuid7
from conftest import COMPANY, headers

from tests.test_foundation import create_type, draft
from tests.test_invoice_capture import invoice_body
from tests.test_purchase_lifecycle_integrity import accept, owner, request_for, seed


async def test_voucher_list_current_date_filters_sort_and_cursor(client, prefix):
    first_type = await create_type(client, prefix, code="LIST-A")
    second_type = await create_type(client, prefix, code="LIST-B")
    today = dt.date.today()
    first, first_body = await draft(
        client, prefix, first_type["revision_id"], document_date=str(today)
    )
    second, _ = await draft(client, prefix, first_type["revision_id"], document_date=str(today))
    later, _ = await draft(
        client, prefix, second_type["revision_id"], document_date=str(today + dt.timedelta(days=1))
    )

    page = await client.get(
        prefix + "/vouchers",
        params={"sort": "-document_date", "limit": 2},
        headers=headers(),
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["items"][0]["id"] == later["id"]
    assert body["items"][0]["document_date"] == str(today + dt.timedelta(days=1))
    assert body["items"][0]["type_id"] == second_type["id"]
    next_page = await client.get(
        prefix + "/vouchers",
        params={"sort": "-document_date", "limit": 2, "cursor": body["page"]["next_cursor"]},
        headers=headers(),
    )
    assert next_page.status_code == 200, next_page.text
    assert {row["id"] for row in body["items"] + next_page.json()["items"]} == {
        first["id"],
        second["id"],
        later["id"],
    }
    ascending = await client.get(
        prefix + "/vouchers", params={"sort": "document_date", "limit": 2}, headers=headers()
    )
    assert ascending.status_code == 200
    ascending_next = await client.get(
        prefix + "/vouchers",
        params={
            "sort": "document_date",
            "limit": 2,
            "cursor": ascending.json()["page"]["next_cursor"],
        },
        headers=headers(),
    )
    assert [row["id"] for row in ascending_next.json()["items"]] == [later["id"]]
    assert (
        await client.get(
            prefix + "/vouchers",
            params={"sort": "document_date", "cursor": body["page"]["next_cursor"]},
            headers=headers(),
        )
    ).status_code == 422

    filtered = await client.get(
        prefix + "/vouchers",
        params={
            "type_id": first_type["id"],
            "document_from": str(today),
            "document_to": str(today),
        },
        headers=headers(),
    )
    assert filtered.status_code == 200, filtered.text
    assert {row["id"] for row in filtered.json()["items"]} == {first["id"], second["id"]}
    by_revision = await client.get(
        prefix + "/vouchers",
        params={"type_revision_id": first_type["revision_id"]},
        headers=headers(),
    )
    assert by_revision.status_code == 200
    assert {row["id"] for row in by_revision.json()["items"]} == {
        first["id"], second["id"]
    }
    by_id = await client.get(prefix + "/vouchers", params={"q": first["id"]}, headers=headers())
    assert by_id.status_code == 200
    assert [row["id"] for row in by_id.json()["items"]] == [first["id"]]
    by_kind = await client.get(
        prefix + "/voucher-types", params={"kind": "MEMORANDUM"}, headers=headers()
    )
    assert by_kind.status_code == 200 and len(by_kind.json()["items"]) == 2
    assert (
        await client.get(prefix + "/vouchers", params={"type_id": str(uuid7())}, headers=headers())
    ).json()["items"] == []

    denied = headers(
        policies=[
            {
                "entity_type": "vouchers.voucher",
                "field_key": "document_date",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert (
        await client.get(prefix + "/vouchers", params={"sort": "document_date"}, headers=denied)
    ).status_code == 403
    assert (
        await client.get(prefix + "/vouchers", params={"document_from": str(today)}, headers=denied)
    ).status_code == 403
    masked = await client.get(prefix + "/vouchers", headers=denied)
    assert masked.status_code == 200
    assert all("document_date" not in row for row in masked.json()["items"])
    assert (
        await client.get(
            prefix + "/voucher-types", params={"document_from": str(today)}, headers=headers()
        )
    ).status_code == 422
    assert (
        await client.get(
            prefix + "/vouchers",
            params={"document_from": str(today + dt.timedelta(days=1)), "document_to": str(today)},
            headers=headers(),
        )
    ).status_code == 422
    other_tenant = await client.get(prefix + "/vouchers", headers=headers(tenant=uuid7()))
    assert other_tenant.status_code == 200 and other_tenant.json()["items"] == []

    changed = await client.put(
        prefix + "/vouchers/" + first["id"],
        json={
            "expected_version": 1,
            "content": first_body | {"document_date": str(today + dt.timedelta(days=2))},
        },
        headers=headers(),
    )
    assert changed.status_code == 200, changed.text
    current_only = await client.get(
        prefix + "/vouchers",
        params={"document_from": str(today), "document_to": str(today)},
        headers=headers(),
    )
    assert {row["id"] for row in current_only.json()["items"]} == {second["id"]}


async def test_voucher_list_issued_number_search(client, prefix):
    kind = await create_type(client, prefix, code="NUMBERED")
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    path = prefix + "/vouchers/" + voucher["id"]
    for action, version, actor in (
        ("submit", 1, headers()),
        ("approve", 2, headers(user=uuid7())),
    ):
        result = await client.post(
            path + "/" + action, json={"expected_version": version}, headers=actor
        )
        assert result.status_code == 200, result.text
    series = await client.post(
        prefix + "/voucher-series", json={"code": "LIST", "prefix": "LIST-"}, headers=headers()
    )
    assert series.status_code == 201, series.text
    issued = await client.post(
        path + "/issue",
        json={"expected_version": 3, "series_id": series.json()["id"]},
        headers=headers(),
    )
    assert issued.status_code == 200, issued.text
    number = issued.json()["issue_number"]
    found = await client.get(prefix + "/vouchers", params={"q": number[:5]}, headers=headers())
    assert found.status_code == 200, found.text
    assert [row["id"] for row in found.json()["items"]] == [voucher["id"]]
    assert found.json()["items"][0]["issue_number"] == number
    exact = await client.get(
        prefix + "/vouchers", params={"issue_number": number}, headers=headers()
    )
    assert exact.status_code == 200 and len(exact.json()["items"]) == 1
    escaped = await client.get(prefix + "/vouchers", params={"q": "LIST-%"}, headers=headers())
    assert escaped.status_code == 200 and escaped.json()["items"] == []
    denied = headers(
        policies=[
            {
                "entity_type": "vouchers.voucher",
                "field_key": "issue_number",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert (
        await client.get(prefix + "/vouchers", params={"q": "LIST-"}, headers=denied)
    ).status_code == 403


async def test_voucher_list_exposes_counterparty_account_reference_and_amount(
    client, prefix, app, monkeypatch
):
    kind = await create_type(client, prefix, kind="PURCHASE", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    body["tax"]["supplier_invoice_number"] = "SUP-INV-99"
    supplier = uuid7()
    await seed(app, body, supplier=supplier, ledger_party=supplier)
    request = request_for(kind, body, supplier)
    created = await client.post(prefix + "/vouchers", json=request, headers=headers())
    assert created.status_code == 201, created.text
    document = created.json()
    owner(app, monkeypatch)
    accepted = await accept(client, prefix, document)
    assert accepted.status_code == 200, accepted.text

    listed = await client.get(prefix + "/vouchers", params={"q": document["id"]}, headers=headers())
    assert listed.status_code == 200, listed.text
    row = listed.json()["items"][0]
    assert row["party_account_id"] == body["party_account_id"]
    assert row["ref_number"] == "SUP-INV-99"
    assert row["amount"] == "1000.0000"
    assert row["currency"] == request["currency"]

    invoice_denied = headers(
        policies=[
            {
                "entity_type": "vouchers.voucher",
                "field_key": "invoice",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    masked_invoice = await client.get(
        prefix + "/vouchers", params={"q": document["id"]}, headers=invoice_denied
    )
    assert masked_invoice.status_code == 200, masked_invoice.text
    masked_row = masked_invoice.json()["items"][0]
    assert "ref_number" not in masked_row
    assert "amount" not in masked_row
    assert "party_account_id" not in masked_row
    assert "currency" not in masked_row
