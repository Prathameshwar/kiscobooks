import uuid

from billing_platform.db import tenant_scope
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from financial_fixture import financial_dataset, financial_manifest
from sqlalchemy import select
from test_framework_execution import proof
from test_source_versions import staged

from reports.models.source_versions import ReportSourceCut
from reports.tasks.framework_worker import process
from reports.tasks.source_publication import publish

REGISTRATION = str(uuid.uuid4())
GST = (
    {
        "id": REGISTRATION,
        "number": "27ABCDE1234F1Z5",
        "legal_name": "GST Example",
        "tax_system": "gst_in",
        "regime": "regular",
        "country_code": "IN",
        "valid_from": "2020-04-01",
        "valid_to": None,
        "jurisdiction_code": "IN-MH",
        "filing_preferences": [
            {"frequency": "MONTHLY", "valid_from": "2020-04-01", "valid_to": None}
        ],
    },
)


async def prepared(app, client, *, activity=False, native=False, draft_credit=False):
    facts, _ = financial_dataset()
    if native:
        from fixtures import source
        from reporting_contract.gst import GstReturnRecord
        from test_invoice_reports import purchase_dataset, tax_dataset

        facts, ids, *_ = purchase_dataset() if draft_credit else tax_dataset()
        facts = [
            source(row.entity, row.source_id, row.data | {"company_registration_id": REGISTRATION})
            if row.entity == "invoice_supply_fact"
            else row
            for row in facts
        ]
        data = GstReturnRecord(
            registration_id=REGISTRATION,
            return_date="2026-04-01",
            event_date="2026-04-01",
            category="INWARD_TAXABLE" if draft_credit else "3.1a",
            source_entity="invoice_supply_fact",
            source_id=ids["supply"],
            reference="INV-1",
            evidence_hash="a" * 64,
            taxable="200",
            igst="20",
        ).model_dump(mode="json")
        facts.append(source("gst_return_record", uuid.uuid4(), data))
        if draft_credit:
            from reporting_contract.invoice import InvoiceCreditAction

            component = next(row for row in facts if row.entity == "invoice_tax_component")
            journal = next(
                row for row in facts if row.entity == "journal" and row.data["number"] == "invoice"
            )
            draft_journal_id = uuid.uuid4()
            action_data = InvoiceCreditAction(
                invoice_id=ids["invoice"],
                component_id=str(component.source_id),
                expected_event_id=str(uuid.uuid4()),
                kind="CLAIM",
                amount="20",
                event_date="2026-04-01",
                posting_date="2026-04-01",
                currency="INR",
                journal_id=str(draft_journal_id),
                offset_account_id=None,
                cash_deposit_line_id=None,
                annual_return_filed_on=None,
                document_verified=True,
                supply_received=True,
                business_use=True,
                restrictions_checked=True,
                supplier_report_matched=True,
                tax_payment_verified=True,
                return_filed=True,
                supplier_paid=False,
                reference="Draft claim",
                evidence_sha256="a" * 64,
                reason="Unposted credit instruction",
            ).model_dump(mode="json")
            facts.append(source("journal", draft_journal_id, journal.data | {"status": "DRAFT"}))
            facts.append(source("invoice_credit_action", uuid.uuid4(), action_data))
    if activity:
        from reporting_contract.contract import Fact, digest
        from reporting_contract.gst import COVERAGE_AREAS, GstReturnRecord

        for category, values in [
            ("3.1a", {"taxable": "1000", "igst": "180"}),
            ("CASH_DEPOSIT", {"igst": "180"}),
            ("OFFSET_NORMAL_CASH", {"igst": "180"}),
            ("GSTR1", {"taxable": "1000", "igst": "180"}),
            ("GSTR2B", {}),
            ("IMS", {}),
            *[
                (
                    "COVERAGE",
                    {"coverage_area": area, "coverage_status": "COMPLETE", "covered_sequence": 1},
                )
                for area in COVERAGE_AREAS
            ],
        ]:
            data = GstReturnRecord(
                registration_id=REGISTRATION,
                return_date="2026-10-01",
                event_date="2026-10-01",
                source_entity="EXTERNAL",
                category=category,
                reference="retained-source",
                evidence_hash="a" * 64,
                explanation="Verified preparation evidence",
                **values,
            ).model_dump(mode="json")
            value = {"entity": "gst_return_record", "source_id": str(uuid.uuid4()), "data": data}
            facts.append(Fact(**value, content_hash=digest(value)))
    facts.sort(key=lambda row: (row.entity, str(row.source_id)))
    identities, _ = await staged(app, source=facts, control=financial_manifest(facts).control)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    response = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=headers(registrations=GST),
        json={
            "code": "GSTR3B",
            "generation_id": str(identities[2]),
            "parameters": {
                "registration_id": REGISTRATION,
                "period": "2026-04" if native else "2026-10",
            },
        },
    )
    assert response.status_code == 202, response.text

    async def authority(job):
        return proof(job)

    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    result = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{response.json()['id']}",
        headers=headers(registrations=GST),
    )
    assert result.json()["status"] == "COMPLETE", result.text
    return response.json()["id"], result.json()


async def test_draft_credit_instruction_does_not_create_unallocated_gst_activity(app, client):
    _, result = await prepared(app, client, native=True, draft_credit=True)
    assert not any(
        issue["code"] == "UNALLOCATED_SOURCE"
        for issue in result["result"]["evidence"]["gstr3b"]["issues"]
    )


async def test_legacy_3b_preparation_stays_readable_but_requires_current_calculations_for_review(
    app, client, monkeypatch
):
    monkeypatch.setattr("reports.domain.gstr3b.CALCULATION_VERSION", 0)
    identity, value = await prepared(app, client, activity=True)
    assert value["result"]["evidence"]["gstr3b"]["calculation_version"] == 0
    result = await client.post(
        f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-review",
        headers=headers(registrations=GST, permissions=PERMISSIONS | {"accounting.finance.manage"}),
        json={"state": "REVIEWED", "reference": "Retained proof", "evidence_hash": "a" * 64},
    )
    assert result.status_code == 409, result.text


async def test_native_supply_reaches_voucher_and_keeps_exact_statutory_amounts(app, client):
    identity, result = await prepared(app, client, native=True)
    assert result["result"]["evidence"]["gstr3b"]["form"]["3.1a"]["igst"] == "20.00"
    response = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-records",
        headers=headers(registrations=GST),
    )
    row = response.json()["items"][0]["data"]
    assert row["voucher_id"] and row["invoice_id"] and row["journal_id"]
    assert row["taxable"] == "200.0000"
    filtered = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-records?category=4A",
        headers=headers(registrations=GST),
    )
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []
    invalid = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-records?category=unapproved",
        headers=headers(registrations=GST),
    )
    assert invalid.status_code == 422


async def test_positive_native_form_and_review_lifecycle_are_frozen(app, client):
    identity, result = await prepared(app, client, activity=True)
    evidence = result["result"]["evidence"]["gstr3b"]
    assert evidence["form"]["3.1a"]["igst"] == "180.00"
    assert evidence["payment"]["IGST"]["normal_unpaid"] == "0.00"
    assert evidence["issues"] == [], evidence["issues"]
    target = f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-review"
    auth = headers(registrations=GST, permissions=PERMISSIONS | {"accounting.finance.manage"})
    reviewed = await client.post(
        target,
        headers=auth,
        json={"state": "REVIEWED", "reference": "reviewer-proof", "evidence_hash": "a" * 64},
    )
    assert reviewed.status_code == 201, reviewed.text
    filed = await client.post(
        target,
        headers=auth,
        json={
            "state": "EXTERNALLY_FILED",
            "reference": "portal-ARN",
            "evidence_hash": "b" * 64,
            "filed_date": "2026-11-01",
        },
    )
    assert filed.status_code == 201, filed.text
    history = await client.get(target, headers=auth)
    assert [row["state"] for row in history.json()["items"]] == ["REVIEWED", "EXTERNALLY_FILED"]
    same = await client.get(f"/v2/companies/{COMPANY}/report-runs/{identity}", headers=auth)
    assert same.json()["result"] == result["result"]
    reopened = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=auth,
        json={
            "code": "GSTR3B",
            "generation_id": result["generation_id"],
            "parameters": {"registration_id": REGISTRATION, "period": "2026-10"},
        },
    )
    assert reopened.status_code == 409, reopened.text
    reader = headers(registrations=GST, permissions=PERMISSIONS - {"report.definition.manage"})
    denied = await client.post(
        f"/v2/companies/{COMPANY}/report-runs",
        headers=reader,
        json={
            "code": "GSTR3B",
            "generation_id": result["generation_id"],
            "parameters": {"registration_id": REGISTRATION, "period": "2026-10"},
        },
    )
    assert denied.status_code == 403, denied.text


async def test_gst_card_is_hidden_for_inapplicable_company(client):
    result = await client.get(f"/v2/companies/{COMPANY}/report-definitions", headers=headers())
    assert result.status_code == 200
    assert "GSTR3B" not in {row["definition"]["code"] for row in result.json()["items"]}
    denied = await client.get(
        f"/v2/companies/{COMPANY}/report-definitions/GSTR3B", headers=headers()
    )
    assert denied.status_code == 403


async def test_native_empty_books_show_missing_evidence_not_nil(app, client):
    identity, result = await prepared(app, client)
    evidence = result["result"]["evidence"]["gstr3b"]
    assert evidence["status"] == "NEEDS_ATTENTION"
    assert evidence["nil"] is False
    assert len(evidence["issues"]) == 8
    assert result["parameters"]["_gst_context"]["registration"]["number"] == GST[0]["number"]
    denied = await client.get(
        f"/v2/companies/{COMPANY}/report-runs/{identity}",
        headers=headers(registrations=GST, user=uuid.uuid4()),
    )
    assert denied.status_code == 403


async def test_review_requires_finance_authority_and_readiness(app, client):
    identity, _ = await prepared(app, client)
    target = f"/v2/companies/{COMPANY}/report-runs/{identity}/gst-review"
    body = {"state": "REVIEWED", "reference": "review-proof", "evidence_hash": "a" * 64}
    denied = await client.post(target, headers=headers(registrations=GST), json=body)
    assert denied.status_code == 403
    attention = await client.post(
        target,
        headers=headers(registrations=GST, permissions=PERMISSIONS | {"accounting.finance.manage"}),
        json=body,
    )
    assert attention.status_code == 409


async def test_foreign_gstin_and_client_supplied_configuration_are_rejected(app, client):
    app.state.settings.framework_enabled = True
    target = f"/v2/companies/{COMPANY}/report-runs"
    for parameters in (
        {"registration_id": str(uuid.uuid4()), "period": "2026-10"},
        {"registration_id": REGISTRATION, "period": "2026-10", "_gst_context": {"number": "fake"}},
    ):
        response = await client.post(
            target,
            headers=headers(registrations=GST),
            json={"code": "GSTR3B", "generation_id": str(uuid.uuid4()), "parameters": parameters},
        )
        assert response.status_code == 422, response.text
