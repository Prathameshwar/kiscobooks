"""Configured commercial roles are typed, revision-bound and source-validated."""

import datetime as dt

from billing_platform.ids import uuid7
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from test_foundation import create_type

from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.sources import apply_bundle


async def test_sales_attribution_is_off_by_default_and_source_validated(client, prefix, app):
    seller, broker = uuid7(), uuid7()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(message_id=uuid7(), tenant_id=TENANT, company_id=COMPANY,
                     masters=({"entity_type": "salesperson", "source_id": seller,
                               "source_version": 2, "status": "ACTIVE",
                               "facts": {"code": "S01", "name": "Original seller"}},)),
        "identity",
    )
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(message_id=uuid7(), tenant_id=TENANT, company_id=COMPANY,
                     masters=({"entity_type": "broker_party", "source_id": broker,
                               "source_version": 3, "status": "ACTIVE"},)),
        "accounting",
    )
    disabled = await create_type(client, prefix, code="SALES_OFF", name="Sales off", kind="SALES")
    assignments = [
        {"role": "SELLER", "principal_id": str(seller), "source_version": 2, "share": "100"},
        {"role": "BROKER", "principal_id": str(broker), "source_version": 3, "share": "100"},
    ]
    body = {"type_revision_id": disabled["revision_id"],
            "document_date": dt.date.today().isoformat(), "currency": "INR",
            "assignments": assignments}
    rejected = await client.post(prefix + "/vouchers", headers=headers(), json=body)
    assert rejected.status_code == 422, rejected.text
    enabled = await create_type(
        client, prefix, code="SALES_ATTR", name="Sales attributed", kind="SALES",
        policy={"schema_version": 2,
                "commercial_attribution": {"seller": "OPTIONAL", "broker": "OPTIONAL"}},
    )
    body["type_revision_id"] = enabled["revision_id"]
    stale = await client.post(
        prefix + "/vouchers", headers=headers(),
        json=body | {"assignments": assignments[:1] + [assignments[1] | {"source_version": 2}]},
    )
    assert stale.status_code == 409, stale.text
    created = await client.post(prefix + "/vouchers", headers=headers(), json=body)
    assert created.status_code == 201, created.text
    assert {row["role"] for row in created.json()["assignments"]} == {"SELLER", "BROKER"}
    assert created.json()["assignments"][0]["share"] == "100.0000"
    seller_assignment = next(
        row for row in created.json()["assignments"] if row["role"] == "SELLER"
    )
    assert seller_assignment["source_code"] == "S01"
    assert seller_assignment["source_name"] == "Original seller"
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(message_id=uuid7(), tenant_id=TENANT, company_id=COMPANY,
                     masters=({"entity_type": "salesperson", "source_id": seller,
                               "source_version": 3, "status": "ACTIVE",
                               "facts": {"code": "S01", "name": "Renamed seller"}},)),
        "identity",
    )
    historical = await client.get(
        prefix + f"/vouchers/{created.json()['id']}", headers=headers(),
    )
    assert next(row for row in historical.json()["assignments"] if row["role"] == "SELLER")[
        "source_name"
    ] == "Original seller"
    seller_list = await client.get(
        prefix + "/vouchers", headers=headers(),
        params={"assignment_role": "SELLER", "assignment_principal_id": str(seller)},
    )
    assert seller_list.status_code == 200, seller_list.text
    assert [row["id"] for row in seller_list.json()["items"]] == [created.json()["id"]]
    hidden = await client.get(
        prefix + "/vouchers",
        headers=headers(policies=[{
            "entity_type": "vouchers.voucher", "field_key": "assignments",
            "access": "read", "effect": "deny", "scope_type": "company",
            "scope_id": str(COMPANY),
        }]),
        params={"assignment_role": "SELLER", "assignment_principal_id": str(seller)},
    )
    assert hidden.status_code == 403, hidden.text
    missing = await client.get(
        prefix + "/vouchers", headers=headers(),
        params={"assignment_role": "SELLER", "assignment_principal_id": str(broker)},
    )
    assert missing.status_code == 200 and not missing.json()["items"]
    bad_share = await client.post(
        prefix + "/vouchers", headers=headers(),
        json=body | {"assignments": assignments[:1] + [assignments[1] | {"share": "50"}]},
    )
    assert bad_share.status_code == 422, bad_share.text


async def test_reassigning_a_draft_needs_approval_and_a_reason(client, prefix, app):
    first, second = uuid7(), uuid7()
    await apply_bundle(
        app.state.session_factory,
        SourceBundle(
            message_id=uuid7(), tenant_id=TENANT, company_id=COMPANY,
            masters=tuple(
                {"entity_type": "salesperson", "source_id": seller,
                 "source_version": 1, "status": "ACTIVE"}
                for seller in (first, second)
            ),
        ),
        "identity",
    )
    configured = await create_type(
        client, prefix, code="SALES_REASSIGN", name="Sales reassignment", kind="SALES",
        policy={"schema_version": 2, "commercial_attribution": {"seller": "OPTIONAL"}},
    )
    body = {
        "type_revision_id": configured["revision_id"],
        "document_date": dt.date.today().isoformat(), "currency": "INR",
        "assignments": [{"role": "SELLER", "principal_id": str(first),
                         "source_version": 1}],
    }
    created = await client.post(prefix + "/vouchers", headers=headers(), json=body)
    assert created.status_code == 201, created.text
    voucher = created.json()
    path = prefix + f"/vouchers/{voucher['id']}"
    same = await client.put(
        path, headers=headers(permissions=PERMISSIONS - {"vouchers.approve"}),
        json={"expected_version": voucher["row_version"],
              "content": body | {"assignments": [
                  {"role": "SELLER", "principal_id": str(first),
                   "source_version": 1, "share": "100.0000"}
              ]}},
    )
    assert same.status_code == 200, same.text
    voucher = same.json()
    replacement = body | {
        "assignments": [{"role": "SELLER", "principal_id": str(second),
                         "source_version": 1, "override_reason": "Customer reassigned"}]
    }
    without_approval = await client.put(
        path, headers=headers(permissions=PERMISSIONS - {"vouchers.approve"}),
        json={"expected_version": voucher["row_version"], "reason": "Customer reassigned",
              "content": replacement},
    )
    assert without_approval.status_code == 403, without_approval.text
    without_reason = await client.put(
        path, headers=headers(),
        json={"expected_version": voucher["row_version"],
              "content": replacement | {"assignments": [
                  {"role": "SELLER", "principal_id": str(second), "source_version": 1}
              ]}},
    )
    assert without_reason.status_code == 422, without_reason.text
    changed = await client.put(
        path, headers=headers(),
        json={"expected_version": voucher["row_version"], "reason": "Customer reassigned",
              "content": replacement},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["assignments"][0]["principal_id"] == str(second)
