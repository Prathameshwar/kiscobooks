"""Starter definitions must accept their ordinary native entry paths."""

import datetime as dt

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select
from test_foundation import create_type
from test_invoice_capture import invoice_body

from vouchers.domain.company_defaults import PREVIOUS_VERSION, SECOND_VERSION, catalogue
from vouchers.domain.configuration import policy_wire
from vouchers.domain.documents import validate_content
from vouchers.domain.invoice import validate_invoice
from vouchers.models import core as m
from vouchers.schemas.documents import VoucherInput
from vouchers.tasks.administration import write_type_revision


def content(**changes):
    return VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": dt.date.today(),
            "posting_date": dt.date.today(),
            "currency": "INR",
            "mode": "ACCOUNTS",
            "narration": "Reviewed adjustment",
            **changes,
        }
    )


def validate(body, definition, stage="SUBMITTED"):
    validate_content(
        body,
        definition.policy,
        kind=definition.kind,
        profile=definition.profile,
        stage=stage,
        today=dt.date.today(),
    )


def test_default_journal_accepts_allocation_only_bill_adjustment():
    journal = next(row for row in catalogue(frozenset()) if row.code == "JRN")
    validate(
        content(
            financial={
                "purpose": "BILL_ADJUSTMENT",
                "allocations": [
                    {
                        "allocation_key": str(uuid7()),
                        "debt": {"item_id": str(uuid7())},
                        "credit": {"item_id": str(uuid7())},
                        "amount": "100",
                        "currency": "INR",
                    }
                ],
            }
        ),
        journal,
    )


def test_configured_money_cannot_submit_a_shell_after_removing_static_account_requirement():
    journal = next(row for row in catalogue(frozenset()) if row.code == "JRN")
    # A pure allocation journal cannot require ACCOUNTS; native money itself must be present.
    journal = journal.model_copy(
        update={"policy": journal.policy.model_copy(update={"required_sections": frozenset()})}
    )
    validate(content(), journal, stage="DRAFT")
    with pytest.raises(ValidationFailedError, match="financial"):
        validate(content(), journal)


@pytest.mark.parametrize("code,role", [("CRN", "CUSTOMER"), ("DBN", "SUPPLIER")])
def test_notes_use_the_native_source_invoice_without_redundant_external_reference(code, role):
    note = next(row for row in catalogue(frozenset()) if row.code == code)
    invoice = invoice_body()
    invoice.update(
        components=[], source_invoice_id=str(uuid7()), accepted_calculation_hash="a" * 64
    )
    invoice["supplies"][0]["supply_kind"] = "ACCOUNT"
    validate(
        content(
            invoice=invoice, parties=[{"role": role, "party_id": str(uuid7()), "source_version": 1}]
        ),
        note,
    )


async def test_existing_company_can_prepare_defaults_without_browser_feature_authority(
    client, prefix
):
    response = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["features"] == [] and response.json()["created_count"] == 20


@pytest.mark.parametrize(
    "features,status",
    [
        # Approval follows the company's approval_workflow feature: without it, submit approves.
        (frozenset(), "APPROVED"),
        (frozenset({"approval_workflow"}), "SUBMITTED"),
    ],
    ids=["no-approval-workflow", "approval-workflow"],
)
async def test_provisioned_journal_bill_adjustment_saves_and_submits(
    client, prefix, features, status
):
    response = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers(features=features)
    )
    assert response.status_code == 200
    rows = (await client.get(prefix + "/voucher-types?kind=JOURNAL", headers=headers())).json()[
        "items"
    ]
    journal = (
        await client.get(prefix + "/voucher-types/" + rows[0]["id"], headers=headers())
    ).json()
    body = content(
        financial={
            "purpose": "BILL_ADJUSTMENT",
            "allocations": [
                {
                    "allocation_key": str(uuid7()),
                    "debt": {"item_id": str(uuid7())},
                    "credit": {"item_id": str(uuid7())},
                    "amount": "100",
                    "currency": "INR",
                }
            ],
        }
    ).model_dump(mode="json")
    body["type_revision_id"] = journal["revision_id"]
    saved = await client.post(prefix + "/vouchers", headers=headers(), json=body)
    assert saved.status_code == 201, saved.text
    submitted = await client.post(
        prefix + "/vouchers/" + saved.json()["id"] + "/submit",
        json={"expected_version": saved.json()["row_version"]},
        headers=headers(),
    )
    assert submitted.status_code == 200 and submitted.json()["status"] == status, submitted.text


async def test_all_defaults_expose_their_real_entry_fields(client, prefix, app):
    features = frozenset({"inventory", "bom_definitions", "approval_workflow", "multi_currency"})
    auth = headers(features=features)
    response = await client.post(prefix + "/voucher-type-defaults/bootstrap", json={}, headers=auth)
    assert response.status_code == 200 and response.json()["created_count"] == 39
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(m.VoucherType)))
    for row in rows:
        fields = await client.get(
            prefix + "/voucher-types/" + str(row.id) + "/field-set",
            params={
                "date": dt.date.today().isoformat(),
                "posting_date": dt.date.today().isoformat(),
            },
            headers=auth,
        )
        assert fields.status_code == 200, (row.code, fields.text)
        data = fields.json()
        assert data["configuration"]["kind"] == row.kind
        assert data["configuration"]["profile"] == row.profile
        policy, native = data["configuration"]["policy"], data["native"]["properties"]
        if row.kind in {"CONTRA", "JOURNAL", "PAYMENT", "RECEIPT"}:
            assert "financial" in native
        if policy.get("invoice") is not None:
            assert "invoice" in native
        if policy.get("stock") is not None:
            assert "stock" in native
        if policy.get("order") is not None:
            assert "fulfillment_terms" in native


async def test_v1_default_rules_upgrade_without_changing_authored_or_historical_rules(
    client, prefix, app
):
    old = {row.code: row for row in catalogue(frozenset(), version=PREVIOUS_VERSION)}
    authored = await create_type(
        client,
        prefix,
        code="PUR_ACC",
        name=old["PUR_ACC"].name,
        kind="PURCHASE",
        policy=policy_wire(old["PUR_ACC"].policy),
    )
    legacy_ids = []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            for code in ("JRN", "CRN", "DBN"):
                definition = old[code]
                row = m.VoucherType(
                    id=uuid7(),
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    code=code,
                    name=definition.name,
                    kind=definition.kind,
                    profile=definition.profile,
                    status="ACTIVE",
                    current_revision=1,
                    created_by=None,
                    updated_by=None,
                )
                db.add(row)
                await db.flush()
                legacy = await write_type_revision(db, row, definition.policy, actor_user_id=None)
                legacy_ids.append(legacy.id)
    response = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 3 and response.json()["preserved_count"] == 1
    saved = (
        await client.get(prefix + "/voucher-types/" + authored["id"], headers=headers())
    ).json()
    assert saved["revision_id"] == authored["revision_id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            legacy = list(
                await db.scalars(
                    select(m.VoucherTypeRevision).where(m.VoucherTypeRevision.id.in_(legacy_ids))
                )
            )
            assert len(legacy) == 3 and all(revision.revision_number == 1 for revision in legacy)
            assert all(revision.policy["required_sections"] for revision in legacy)
            updated = list(
                await db.scalars(
                    select(m.VoucherType).where(
                        m.VoucherType.id.in_([revision.type_id for revision in legacy])
                    )
                )
            )
            assert all(row.current_revision == 2 for row in updated)


async def _system_type(app, definition):
    """A type as company provisioning wrote it: no author, one revision, the starter name."""
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = m.VoucherType(
                id=uuid7(),
                tenant_id=TENANT,
                company_id=COMPANY,
                code=definition.code,
                name=definition.name,
                kind=definition.kind,
                profile=definition.profile,
                status="ACTIVE",
                current_revision=1,
                created_by=None,
                updated_by=None,
            )
            db.add(row)
            await db.flush()
            first = await write_type_revision(db, row, definition.policy, actor_user_id=None)
            return row.id, first.id


@pytest.mark.parametrize("version", [PREVIOUS_VERSION, SECOND_VERSION])
async def test_untouched_account_bill_from_an_earlier_catalogue_follows_the_service_line_rule(
    client, prefix, app, version
):
    old = {row.code: row for row in catalogue(frozenset(), version=version)}["PUR_ACC"]
    assert old.policy.invoice.allowed_supply_kinds == {"ACCOUNT"}
    type_id, first_revision = await _system_type(app, old)
    response = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(m.VoucherType, type_id)
            revisions = {
                revision.revision_number: revision
                for revision in await db.scalars(
                    select(m.VoucherTypeRevision).where(m.VoucherTypeRevision.type_id == type_id)
                )
            }
    assert row.current_revision == 2 and set(revisions) == {1, 2}
    # The first revision is history and stays exactly as it was issued.
    assert revisions[1].id == first_revision
    assert revisions[1].policy["invoice"]["allowed_supply_kinds"] == ["ACCOUNT"]
    assert sorted(revisions[2].policy["invoice"]["allowed_supply_kinds"]) == ["ACCOUNT", "SERVICE"]
    again = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers()
    )
    assert again.json()["updated_count"] == 0


async def test_an_authored_account_bill_keeps_its_rules_when_defaults_are_prepared(
    client, prefix, app
):
    authored = await create_type(
        client,
        prefix,
        code="PUR_ACC",
        name="Purchase - Account Bill",
        kind="PURCHASE",
        policy={"invoice": {"allowed_supply_kinds": ["ACCOUNT"]}},
    )
    response = await client.post(
        prefix + "/voucher-type-defaults/bootstrap", json={}, headers=headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 0
    saved = (
        await client.get(prefix + "/voucher-types/" + authored["id"], headers=headers())
    ).json()
    assert saved["revision_id"] == authored["revision_id"]
    assert saved["policy"]["invoice"]["allowed_supply_kinds"] == ["ACCOUNT"]


def test_default_purchase_account_bill_takes_a_service_supply_and_the_first_two_did_not():
    invoice = invoice_body()
    invoice.update(components=[])
    assert invoice["supplies"][0]["supply_kind"] == "SERVICE"
    supplier = {"role": "SUPPLIER", "party_id": str(uuid7()), "source_version": 1}
    body = content(invoice=invoice, parties=[supplier])
    current = {row.code: row for row in catalogue(frozenset())}["PUR_ACC"]
    validate_invoice(body, current.policy.invoice, kind="PURCHASE", profile="STANDARD")
    for version in (PREVIOUS_VERSION, SECOND_VERSION):
        earlier = {row.code: row for row in catalogue(frozenset(), version=version)}["PUR_ACC"]
        with pytest.raises(ValidationFailedError, match="supply kind"):
            validate_invoice(body, earlier.policy.invoice, kind="PURCHASE", profile="STANDARD")
