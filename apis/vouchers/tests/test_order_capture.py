"""Non-posting order terms remain native, scoped and revision-bound."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft
from unit_source_factories import unit_masters

from vouchers.models import core as m
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.artifacts import render_pending
from vouchers.tasks.sources import apply_bundle


async def test_quotation_planned_units_are_separate_from_stock_and_billing(
    client, prefix, app, monkeypatch
):
    kind = await create_type(
        client, prefix, code="QUOTE", name="Quotation", kind="SALES_ORDER", profile="QUOTATION"
    )
    field_set = await client.get(
        prefix + "/voucher-types/" + kind["id"] + "/field-set",
        params={"date": dt.date.today().isoformat()},
        headers=headers(),
    )
    assert field_set.status_code == 200, field_set.text
    native = field_set.json()["native"]["properties"]
    assert "fulfillment_terms" in native
    assert "planned_quantity" in native["lines"]["items"]["properties"]["item"]["properties"]
    item_id, unit_id, party_id = uuid7(), uuid7(), uuid7()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(),
            tenant_id=TENANT,
            company_id=COMPANY,
            masters=(
                *unit_masters(item_id, unit_id),
                {
                    "entity_type": "item_transaction_policy",
                    "source_id": item_id,
                    "source_version": 4294967297,
                    "status": "ACTIVE",
                    "facts": {
                        "kind": "GOODS",
                        "item_version": 1,
                        "inventory_mode": "NON_STOCK",
                        "sellable": True,
                        "purchasable": False,
                    },
                },
            ),
        ),
        "catalog",
    )
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(),
            tenant_id=TENANT,
            company_id=COMPANY,
            masters=(
                {
                    "entity_type": "party",
                    "source_id": party_id,
                    "source_version": 1,
                    "status": "ACTIVE",
                },
            ),
        ),
        "accounting",
    )
    today = dt.date.today()
    created, body = await draft(
        client,
        prefix,
        kind["revision_id"],
        mode="ITEMS",
        parties=[{"role": "CUSTOMER", "party_id": str(party_id), "source_version": 1}],
        lines=[
            {
                "line_key": str(uuid7()),
                "description": "Quoted goods",
                "item": {
                    "item_id": str(item_id),
                    "item_version": 1,
                    "unit_id": str(unit_id),
                    "actual_quantity": "0",
                    "billed_quantity": "0",
                    "planned_quantity": "10",
                },
            }
        ],
        fulfillment_terms={
            "purpose": "QUOTE",
            "valid_until": (today + dt.timedelta(days=30)).isoformat(),
            "required_by": (today + dt.timedelta(days=45)).isoformat(),
            "delivery_terms": "Deliver to buyer",
        },
    )
    assert created["lines"][0]["item"]["planned_quantity"] == "10.0000"
    assert created["fulfillment_terms"]["purpose"] == "QUOTE"
    located = await client.get(
        prefix + "/vouchers",
        params={"party_id": str(party_id), "item_id": str(item_id), "kind": "SALES_ORDER"},
        headers=headers(),
    )
    assert located.status_code == 200, located.text
    assert [row["id"] for row in located.json()["items"]] == [created["id"]]
    absent = await client.get(
        prefix + "/vouchers", params={"party_id": str(uuid7())}, headers=headers()
    )
    assert absent.status_code == 200 and absent.json()["items"] == []
    denied_party = await client.get(
        prefix + "/vouchers",
        params={"party_id": str(party_id)},
        headers=headers(
            policies=[
                {
                    "entity_type": "vouchers.voucher",
                    "field_key": "parties",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
    )
    assert denied_party.status_code == 403
    denied_item = await client.get(
        prefix + "/vouchers",
        params={"item_id": str(item_id)},
        headers=headers(
            policies=[
                {
                    "entity_type": "vouchers.voucher_item",
                    "field_key": "item_id",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
    )
    assert denied_item.status_code == 403
    other_company = uuid7()
    assert (
        await client.get(
            f"/v1/companies/{other_company}/vouchers/" + created["id"],
            headers=headers(company=other_company),
        )
    ).status_code == 403
    protected = await client.get(
        prefix + "/vouchers/" + created["id"],
        headers=headers(
            policies=[
                {
                    "entity_type": "vouchers.voucher",
                    "field_key": "fulfillment_terms",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                }
            ]
        ),
    )
    assert protected.status_code == 200
    assert "fulfillment_terms" not in protected.json()
    submitted = await client.post(
        prefix + "/vouchers/" + created["id"] + "/submit",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    template = await client.post(
        prefix + "/voucher-templates",
        json={
            "code": "QUOTE_TERMS",
            "title": "Quotation terms",
            "fields": ["fulfillment_terms"],
        },
        headers=headers(),
    )
    assert template.status_code == 201, template.text
    artifact = await client.post(
        prefix + "/vouchers/" + created["id"] + "/artifacts",
        json={"expected_version": 2, "template_revision_id": template.json()["revision_id"]},
        headers=headers(),
    )
    assert artifact.status_code == 202, artifact.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await render_pending(db, uuid.UUID(artifact.json()["id"]))
    artifact_status = await client.get(
        prefix + "/voucher-artifacts/" + artifact.json()["id"], headers=headers()
    )
    assert artifact_status.status_code == 200, artifact_status.text
    rendered = await client.get(
        prefix + "/voucher-artifacts/" + artifact.json()["id"] + "/download",
        params={"token": artifact_status.json()["download_token"]},
        headers=headers(),
    )
    assert rendered.status_code == 200, rendered.text
    assert "Deliver to buyer" in rendered.text
    assert (
        await client.get(
            prefix + "/voucher-artifacts/" + artifact.json()["id"] + "/download",
            params={"token": artifact_status.json()["download_token"]},
            headers=headers(
                policies=[
                    {
                        "entity_type": "vouchers.voucher",
                        "field_key": "fulfillment_terms",
                        "access": "read",
                        "effect": "deny",
                        "scope_type": "company",
                        "scope_id": str(COMPANY),
                    }
                ]
            ),
        )
    ).status_code == 403
    assert (
        await client.post(
            prefix + "/vouchers/" + created["id"] + "/post",
            json={"expected_version": 2},
            headers=headers(),
        )
    ).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            terms = await db.scalar(select(m.VoucherFulfillmentTerms))
            assert terms is not None and terms.purpose == "QUOTE"
            assert terms.revision_id == uuid.UUID(created["revision_id"])
            assert await db.scalar(select(m.VoucherPostingReference.id)) is None
            assert set((await db.scalars(select(m.VoucherOperation.purpose))).all()) == {"ARTIFACT"}
    approved = await client.post(
        prefix + "/vouchers/" + created["id"] + "/approve",
        json={"expected_version": 2},
        headers=headers(user=uuid7()),
    )
    assert approved.status_code == 200, approved.text
    series = await client.post(
        prefix + "/voucher-series", json={"code": "QUOTE"}, headers=headers()
    )
    assert series.status_code == 201, series.text
    issued = await client.post(
        prefix + "/vouchers/" + created["id"] + "/issue",
        json={"expected_version": 3, "series_id": series.json()["id"]},
        headers=headers(),
    )
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED", issued.text
    assert (
        await client.post(
            prefix + "/vouchers/" + created["id"] + "/expire",
            json={"expected_version": 4},
            headers=headers(),
        )
    ).status_code == 409
    assert (
        await client.post(
            prefix + "/vouchers/" + created["id"] + "/accept",
            json={"expected_version": 4},
            headers=headers(permissions=frozenset({"vouchers.read"})),
        )
    ).status_code == 403
    accepted = await client.post(
        prefix + "/vouchers/" + created["id"] + "/accept",
        json={"expected_version": 4},
        headers=headers(),
    )
    assert accepted.status_code == 200 and accepted.json()["status"] == "ACCEPTED"
    assert (
        await client.post(
            prefix + "/vouchers/" + created["id"] + "/accept",
            json={"expected_version": 4},
            headers=headers(),
        )
    ).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(m.VoucherPostingReference.id)) is None
            assert set((await db.scalars(select(m.VoucherOperation.purpose))).all()) == {"ARTIFACT"}
    expiring_content = body | {
        "fulfillment_terms": body["fulfillment_terms"]
        | {"valid_until": (today + dt.timedelta(days=1)).isoformat()}
    }
    expiring = await client.post(prefix + "/vouchers", json=expiring_content, headers=headers())
    assert expiring.status_code == 201, expiring.text
    expiring_path = prefix + "/vouchers/" + expiring.json()["id"]
    for action_name, version, actor in (
        ("submit", 1, None),
        ("approve", 2, uuid7()),
    ):
        step = await client.post(
            expiring_path + "/" + action_name,
            json={"expected_version": version},
            headers=headers(user=actor) if actor else headers(),
        )
        assert step.status_code == 200, step.text
    issued_expiring = await client.post(
        expiring_path + "/issue",
        json={"expected_version": 3, "series_id": series.json()["id"]},
        headers=headers(),
    )
    assert issued_expiring.status_code == 200, issued_expiring.text
    monkeypatch.setattr(
        "vouchers.tasks.documents.utcnow",
        lambda: dt.datetime.now(dt.UTC) + dt.timedelta(days=2),
    )
    expired = await client.post(
        expiring_path + "/expire", json={"expected_version": 4}, headers=headers()
    )
    assert expired.status_code == 200 and expired.json()["status"] == "EXPIRED", expired.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(m.VoucherPostingReference.id)) is None
            assert set((await db.scalars(select(m.VoucherOperation.purpose))).all()) == {"ARTIFACT"}
    assert body["lines"][0]["item"]["actual_quantity"] == "0"


@pytest.mark.parametrize(
    ("kind", "purpose", "role", "sellable", "purchasable"),
    [
        ("SALES_ORDER", "SALE", "CUSTOMER", False, True),
        ("PURCHASE_ORDER", "PURCHASE", "SUPPLIER", True, False),
    ],
)
async def test_order_submission_rejects_disabled_item_direction(
    client, prefix, app, kind, purpose, role, sellable, purchasable
):
    voucher_type = await create_type(client, prefix, code="DIRECTION", name="Direction", kind=kind)
    item_id, unit_id, party_id = uuid7(), uuid7(), uuid7()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(),
            tenant_id=TENANT,
            company_id=COMPANY,
            masters=(
                *unit_masters(item_id, unit_id),
                {
                    "entity_type": "item_transaction_policy",
                    "source_id": item_id,
                    "source_version": 4294967297,
                    "status": "ACTIVE",
                    "facts": {
                        "kind": "GOODS",
                        "item_version": 1,
                        "inventory_mode": "NON_STOCK",
                        "sellable": sellable,
                        "purchasable": purchasable,
                    },
                },
            ),
        ),
        "catalog",
    )
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(),
            tenant_id=TENANT,
            company_id=COMPANY,
            masters=(
                {
                    "entity_type": "party",
                    "source_id": party_id,
                    "source_version": 1,
                    "status": "ACTIVE",
                },
            ),
        ),
        "accounting",
    )
    created, _ = await draft(
        client,
        prefix,
        voucher_type["revision_id"],
        mode="ITEMS",
        parties=[{"role": role, "party_id": str(party_id), "source_version": 1}],
        lines=[
            {
                "line_key": str(uuid7()),
                "item": {
                    "item_id": str(item_id),
                    "item_version": 1,
                    "unit_id": str(unit_id),
                    "actual_quantity": "0",
                    "billed_quantity": "0",
                    "planned_quantity": "1",
                },
            }
        ],
        fulfillment_terms={"purpose": purpose},
    )
    submitted = await client.post(
        prefix + "/vouchers/" + created["id"] + "/submit",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert submitted.status_code == 409, submitted.text
    assert "not enabled" in submitted.json()["error"]["message"]


async def test_existing_revision_cannot_gain_fulfillment_terms(app):
    tenant, company = uuid7(), uuid7()
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            voucher_type = m.VoucherType(
                tenant_id=tenant,
                company_id=company,
                code="T",
                name="Test",
                kind="SALES_ORDER",
                profile="STANDARD",
            )
            db.add(voucher_type)
            await db.flush()
            revision = m.VoucherTypeRevision(
                tenant_id=tenant,
                company_id=company,
                type_id=voucher_type.id,
                revision_number=1,
                policy={},
                content_hash="a" * 64,
            )
            voucher = m.Voucher(
                tenant_id=tenant,
                company_id=company,
                type_id=voucher_type.id,
            )
            db.add_all((revision, voucher))
            await db.flush()
            document = m.VoucherRevision(
                tenant_id=tenant,
                company_id=company,
                voucher_id=voucher.id,
                revision_number=1,
                type_revision_id=revision.id,
                document_date=dt.date.today(),
                fiscal_start_date=dt.date.today(),
                mode="ITEMS",
                currency="INR",
                narration="",
                custom_fields={},
                definition_snapshot={},
                configuration_evidence={},
                configuration_hash="a" * 64,
                content_hash="b" * 64,
            )
            db.add(document)
            await db.flush()
            document_id = document.id
        with pytest.raises(ConflictError, match="new voucher revision"):
            async with app.state.session_factory() as db, db.begin():
                db.add(
                    m.VoucherFulfillmentTerms(
                        tenant_id=tenant,
                        company_id=company,
                        revision_id=document_id,
                        purpose="SALE",
                        delivery_terms="",
                        payment_terms="",
                    )
                )
                await db.flush()
