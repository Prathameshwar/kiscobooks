import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from reporting_contract.gst_outward import AREAS
from sqlalchemy import select

from accounting.models.gst_outward import GstOutwardRecord
from accounting.models.reporting import ReportChange, ReportChangeFact
from tests.conftest import TENANT
from tests.invoice_helpers import posted_purchase
from tests.test_fiscal_api import BASE
from tests.test_voucher_tax import MH, th


def headers():
    return th(registrations=[MH | {"country_code": "IN", "number": "27ABCDE1234F1Z5"}])


def record(**extra):
    return {
        "registration_id": MH["id"],
        "return_date": "2026-10-01",
        "document_date": "2026-10-01",
        "kind": "INVOICE",
        "document_number": "SALE-1",
        "source_entity": "EXTERNAL",
        "reference": "Reviewed sales invoice SALE-1",
        "evidence_hash": "a" * 64,
        "explanation": "Original outward invoice retained",
        "invoice_value": "1180.0000",
        "details": {
            "recipient_type": "UNREGISTERED",
            "place_of_supply": "24",
            "items": [{"hsn": "9983", "uqc": "NA", "rate": "18", "taxable": "1000", "igst": "180"}],
        },
        **extra,
    }


async def test_iff_capture_rejects_the_third_month_of_a_qrmp_quarter(app, client):
    await posted_purchase(client, app)
    values = record(return_date="2026-09-01", document_date="2026-09-01")
    values["details"] |= {
        "recipient_type": "REGISTERED",
        "recipient_gstin": "24ABCDE1234F1Z5",
        "prior_filed_channel": "IFF",
        "prior_filing_date": "2026-10-01",
        "prior_filing_reference": "Retained IFF proof",
        "prior_filing_hash": "b" * 64,
    }
    response = await client.post(
        BASE + "/gst-outward-records",
        json={"records": [values]},
        headers=th(
            registrations=[
                MH
                | {
                    "country_code": "IN",
                    "number": "27ABCDE1234F1Z5",
                    "filing_preferences": [
                        {"frequency": "QRMP", "valid_from": "2026-07-01", "valid_to": "2026-10-01"}
                    ],
                }
            ]
        ),
    )
    assert response.status_code == 422, response.text


async def test_outward_capture_replay_and_frozen_change_contract(app, client):
    await posted_purchase(client, app)
    auth = headers()
    response = await client.post(
        BASE + "/gst-outward-records", headers=auth, json={"records": [record()]}
    )
    assert response.status_code == 201, response.text
    assert response.json()["taxable"] == "1000.0000"
    replay = await client.post(
        BASE + "/gst-outward-records", headers=auth, json={"records": [record()]}
    )
    assert replay.json()["id"] == response.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            fact = await db.scalar(
                select(ReportChangeFact).where(
                    ReportChangeFact.fact["entity"].as_string() == "gst_outward_record"
                )
            )
            assert fact is not None
            assert fact.fact["data"]["details"]["items"][0]["igst"] == "180.0000"
            saved = await db.get(GstOutwardRecord, uuid.UUID(response.json()["id"]))
            saved.explanation = "rewrite"
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()


async def test_outward_scope_and_atomic_validation(app, client):
    await posted_purchase(client, app)
    for item in (record(registration_id=str(uuid.uuid4())), record(invoice_value="1200")):
        response = await client.post(
            BASE + "/gst-outward-records", headers=headers(), json={"records": [item]}
        )
        assert response.status_code == 422, response.text
    response = await client.post(
        BASE + "/gst-outward-records",
        headers=headers(),
        json={
            "records": [
                record(),
                record(document_number="SALE-2", registration_id=str(uuid.uuid4())),
            ]
        },
    )
    assert response.status_code == 422, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(GstOutwardRecord)) is None


async def test_purchase_cannot_be_disguised_as_outward_invoice(app, client):
    data = await posted_purchase(client, app)
    item = record(source_entity="invoice_record", source_id=str(data["invoice"].id))
    response = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [item]}
    )
    assert response.status_code == 422, response.text


async def test_tax_note_can_link_the_original_outward_invoice(app, client):
    await posted_purchase(client, app)
    invoice = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [record()]}
    )
    assert invoice.status_code == 201, invoice.text
    note = record(
        kind="CREDIT_NOTE", document_number="CN-1", original_record_id=invoice.json()["id"]
    )
    response = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [note]}
    )
    assert response.status_code == 201, response.text


async def test_repeated_amendment_requires_latest_evidence_and_keeps_the_chain(app, client):
    await posted_purchase(client, app)
    root = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [record()]}
    )
    assert root.status_code == 201, root.text
    revised = record(
        kind="AMENDMENT", original_record_id=root.json()["id"], return_date="2026-11-01"
    )
    revised["details"] |= {
        "original_filing_reference": "Original filing proof",
        "original_filing_hash": "b" * 64,
        "annual_return_checked": True,
    }
    previous = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [revised]}
    )
    assert previous.status_code == 201, previous.text
    obsolete = revised | {"return_date": "2026-12-01"}
    rejected = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [obsolete]}
    )
    assert rejected.status_code == 409, rejected.text
    latest = obsolete | {"original_record_id": previous.json()["id"]}
    accepted = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [latest]}
    )
    assert accepted.status_code == 201, accepted.text


async def test_completeness_batch_retains_its_final_committed_feed_sequence(app, client):
    await posted_purchase(client, app)
    rows = [
        record(
            kind="COVERAGE",
            document_number="",
            invoice_value="0",
            details={"coverage_area": area, "coverage_status": "COMPLETE"},
        )
        for area in AREAS
    ]
    captured = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": rows}
    )
    assert captured.status_code == 201, captured.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            source_cut = await db.scalar(
                select(ReportChange).order_by(ReportChange.sequence.desc())
            )
            proofs = list(
                await db.scalars(
                    select(GstOutwardRecord).where(GstOutwardRecord.kind == "COVERAGE")
                )
            )
            assert len(proofs) == len(AREAS)
            assert {proof.details["covered_sequence"] for proof in proofs} == {source_cut.sequence}


async def test_iff_and_linked_note_cannot_use_a_different_statutory_profile(app, client):
    await posted_purchase(client, app)
    wrong = record(
        kind="ADVANCE",
        details={
            "place_of_supply": "24",
            "recipient_type": "REGISTERED",
            "recipient_gstin": "24ABCDE1234F1Z5",
            "prior_filed_channel": "IFF",
            "prior_filing_reference": "IFF proof",
            "prior_filing_hash": "b" * 64,
            "prior_filing_date": "2026-11-01",
            "items": [
                {"hsn": "998314", "uqc": "NA", "taxable": "1000", "igst": "180", "rate": "18"}
            ],
        },
    )
    rejected = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [wrong]}
    )
    assert rejected.status_code == 422, rejected.text
    original = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [record()]}
    )
    assert original.status_code == 201, original.text
    note = record(
        kind="DEBIT_NOTE", document_number="DN-1", original_record_id=original.json()["id"]
    )
    note["details"] |= {"recipient_type": "REGISTERED", "recipient_gstin": "24ABCDE1234F1Z5"}
    rejected = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [note]}
    )
    assert rejected.status_code == 422, rejected.text


async def test_native_sales_detail_matches_committed_invoice_and_rate(app, client):
    from accounting.models.invoice import InvoiceRecord, InvoiceSupplyFact
    from tests.test_invoice_tax_posting import test_gst_invoice_native_component_postings

    await test_gst_invoice_native_component_postings(client, app, "SALES", "income")
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            invoice = await db.scalar(select(InvoiceRecord))
            supply = await db.scalar(select(InvoiceSupplyFact))
            item = record(
                source_entity="invoice_record",
                source_id=str(invoice.id),
                document_number=invoice.bill_reference,
                document_date=invoice.document_date.isoformat(),
            )
            item["details"] |= {
                "recipient_type": "REGISTERED",
                "recipient_gstin": "24ABCDE1234F1Z6",
            }
            item["details"]["items"][0]["source_line_id"] = str(supply.id)
            item["details"]["items"][0]["hsn"] = supply.classification_code
    wrong = record(
        **{key: value for key, value in item.items() if key != "details"},
        details={**item["details"], "items": [item["details"]["items"][0] | {"rate": "5"}]},
    )
    rejected = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [wrong]}
    )
    assert rejected.status_code == 422, rejected.text
    wrong_currency = {
        **item,
        "details": {
            **item["details"],
            "source_currency": "USD",
            "source_invoice_value": "14.75",
            "conversion_rate": "80",
            "conversion_date": item["document_date"],
            "conversion_reference": "Unrelated conversion",
        },
    }
    rejected = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [wrong_currency]}
    )
    assert rejected.status_code == 422, rejected.text
    accepted = await client.post(
        BASE + "/gst-outward-records", headers=headers(), json={"records": [item]}
    )
    assert accepted.status_code == 201, accepted.text
