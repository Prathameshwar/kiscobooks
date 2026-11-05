import uuid

from billing_platform.db import tenant_scope
from sqlalchemy import select

from accounting.models.gst_return import GstReturnRecord
from accounting.models.reporting import ReportChangeFact
from tests.invoice_helpers import posted_purchase
from tests.test_fiscal_api import BASE
from tests.test_voucher_tax import MH, th


def record(**extra):
    return {
        "registration_id": MH["id"],
        "return_date": "2026-10-01",
        "event_date": "2026-10-01",
        "category": "4A4",
        "source_entity": "EXTERNAL",
        "reference": "ISD-1",
        "evidence_hash": "a" * 64,
        "explanation": "Reviewed ISD distribution certificate",
        "igst": "100",
        **extra,
    }


async def test_outward_return_capture_rejects_explicit_non_indian_registration(app, client):
    await posted_purchase(client, app)
    response = await client.post(
        BASE + "/gst-return-records",
        headers=th(registrations=[MH | {"country_code": "US"}]),
        json={"records": [record()]},
    )
    assert response.status_code == 422, response.text


async def test_capture_is_replayable_exact_and_published_in_same_transaction(app, client):
    await posted_purchase(client, app)
    auth = th()
    body = {"records": [record()]}
    response = await client.post(BASE + "/gst-return-records", headers=auth, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["igst"] == "100.0000"
    again = await client.post(BASE + "/gst-return-records", headers=auth, json=body)
    assert again.json()["id"] == response.json()["id"]
    from tests.conftest import TENANT

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            fact = await db.scalar(
                select(ReportChangeFact).where(
                    ReportChangeFact.fact["entity"].as_string() == "gst_return_record"
                )
            )
            assert fact is not None
            assert fact.fact["data"]["igst"] == "100.0000"


async def test_external_evidence_and_gstin_scope_are_required(app, client):
    await posted_purchase(client, app)
    for item in (record(registration_id=str(uuid.uuid4())), record(explanation="")):
        response = await client.post(
            BASE + "/gst-return-records", headers=th(), json={"records": [item]}
        )
        assert response.status_code == 422, response.text


async def test_committed_allocations_cannot_be_changed(app, client):
    import pytest
    from billing_platform.errors import ConflictError

    from tests.conftest import TENANT

    await posted_purchase(client, app)
    response = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [record()]}
    )
    assert response.status_code == 201, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(GstReturnRecord, uuid.UUID(response.json()["id"]))
            row.explanation = "rewrite"
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()


async def test_native_purchase_allocation_checks_exact_source_and_cannot_repeat(app, client):
    from accounting.models.invoice import InvoiceSupplyFact, InvoiceTaxComponent
    from tests.conftest import TENANT

    await posted_purchase(client, app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            supply = await db.scalar(select(InvoiceSupplyFact))
            component = await db.scalar(
                select(InvoiceTaxComponent).where(InvoiceTaxComponent.supply_id == supply.id)
            )
            item = record(
                category="INWARD_TAXABLE",
                source_entity="invoice_supply_fact",
                source_id=str(supply.id),
                taxable=format(supply.taxable, "f"),
                igst=format(component.amount, "f"),
            )
    rejected = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [item | {"igst": "1"}]}
    )
    assert rejected.status_code == 422, rejected.text
    wrong_class = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [item | {"category": "3.1d"}]}
    )
    assert wrong_class.status_code == 422, wrong_class.text
    wrong_rate = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item | {"conversion_rate": "85.00000000"}]},
    )
    assert wrong_rate.status_code == 422, wrong_rate.text
    accepted = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [item]}
    )
    assert accepted.status_code == 201, accepted.text
    repeated = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [item]}
    )
    assert repeated.status_code == 409, repeated.text


async def test_native_domestic_credit_cannot_be_relabelled_as_import_or_isd(app, client):
    from tests.test_invoice_credit_api import action, balance, post_action

    data = await posted_purchase(client, app)
    component = data["component"]
    verified = await client.post(
        BASE + "/invoice-credit-actions",
        headers=th(),
        json=action(component),
    )
    assert verified.status_code == 201, verified.text
    position = await balance(client, component)
    created = await client.post(
        BASE + "/invoice-credit-actions",
        headers=th(),
        json=action(component, kind="CLAIM", expected_event_id=position["latest_event_id"]),
    )
    assert created.status_code == 201, created.text
    item = record(
        category="4A5",
        source_entity="invoice_credit_action",
        source_id=created.json()["id"],
        igst="180",
    )
    draft = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item]},
    )
    assert draft.status_code == 409, draft.text
    posted = await post_action(client, created.json())
    assert posted.status_code == 200, posted.text
    for category in ("4A1", "4A2", "4A3", "4A4"):
        rejected = await client.post(
            BASE + "/gst-return-records",
            headers=th(),
            json={"records": [item | {"category": category}]},
        )
        assert rejected.status_code == 422, rejected.text
    accepted = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item]},
    )
    assert accepted.status_code == 201, accepted.text
    repeated = await client.post(
        BASE + "/gst-return-records", headers=th(), json={"records": [item]}
    )
    assert repeated.status_code == 409, repeated.text


async def test_generic_blocked_credit_does_not_prove_section_16_4_or_pos_restriction(app, client):
    from tests.test_invoice_credit_api import action, post_action

    data = await posted_purchase(client, app)
    created = await client.post(
        BASE + "/invoice-credit-actions",
        headers=th(),
        json=action(
            data["component"],
            kind="BLOCK",
            amount="30",
            offset_account_id=data["expense"]["id"],
        ),
    )
    assert created.status_code == 201, created.text
    posted = await post_action(client, created.json())
    assert posted.status_code == 200, posted.text
    item = record(
        category="4D2",
        source_entity="invoice_credit_action",
        source_id=created.json()["id"],
        igst="30",
    )
    rejected = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item]},
    )
    assert rejected.status_code == 422, rejected.text
    accepted = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item | {"category": "INWARD_INELIGIBLE"}]},
    )
    assert accepted.status_code == 201, accepted.text


async def test_native_journal_cannot_be_relabelled_as_exempt_or_eco(app, client):
    from tests.test_voucher_tax import post, sale_journal, world

    data = await world(client, app)
    created = await client.post(
        BASE + "/journals",
        headers=th(),
        json=sale_journal(data, party_state="IN-KA"),
    )
    assert created.status_code == 201, created.text
    posted = await post(client, created.json())
    assert posted.status_code == 200, posted.text
    item = record(
        source_entity="journal",
        source_id=created.json()["id"],
        category="3.1a",
        taxable="1000",
        igst="180",
    )
    for category in ("3.1c", "3.1b", "3.1.1i", "3.1.1ii"):
        response = await client.post(
            BASE + "/gst-return-records",
            headers=th(),
            json={"records": [item | {"category": category}]},
        )
        assert response.status_code == 422, response.text
    accepted = await client.post(
        BASE + "/gst-return-records",
        headers=th(),
        json={"records": [item]},
    )
    assert accepted.status_code == 201, accepted.text
