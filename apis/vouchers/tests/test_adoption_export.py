import uuid

from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft
from test_sources_custom_artifacts import definition, source

from vouchers.models import core as m


async def test_adoption_backfill_preserves_history_and_scopes(client, prefix, app):
    kind = await create_type(client, prefix)
    first = definition("cf_code", "text", validation={"max_length": 200})
    assert (await source(client, app, definitions=[first])).status_code == 200
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], custom_fields={"cf_code": "Alpha"}
    )
    update = first | {
        "source_version": 2,
        "definition": first["definition"] | {"is_searchable": True},
    }
    assert (await source(client, app, definitions=[update])).status_code == 200
    listed = await client.get(prefix + "/voucher-field-adoptions", headers=headers())
    item = listed.json()["items"][0]
    denied = await client.post(
        prefix + "/voucher-field-adoptions/" + item["id"] + "/apply",
        headers=headers(permissions=frozenset({"vouchers.read"})),
        json={"expected_version": 1},
    )
    assert denied.status_code == 403
    review = await client.get(prefix + "/voucher-field-adoptions/" + item["id"], headers=headers())
    assert review.status_code == 200 and review.json()["proposed_definition"]["is_searchable"]
    preview = await client.post(
        prefix + "/voucher-field-adoptions/" + item["id"] + "/preview",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert preview.status_code == 200 and preview.json()["can_apply"], preview.text
    pending = await client.get(prefix + "/voucher-field-adoptions/" + item["id"], headers=headers())
    assert pending.json()["status"] == "PENDING" and pending.json()["row_version"] == 1
    applied = await client.post(
        prefix + "/voucher-field-adoptions/" + item["id"] + "/apply",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "APPLIED"
    pinned = await client.get(
        prefix + f'/vouchers/{voucher["id"]}/field-set', headers=headers()
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["header"][0]["definition"]["is_searchable"] is False
    found = await client.get(
        prefix + "/vouchers",
        headers=headers(),
        params={"custom_key": "cf_code", "custom_value": "Alpha"},
    )
    assert [row["id"] for row in found.json()["items"]] == [voucher["id"]]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revision = await db.scalar(
                select(m.VoucherRevision).where(
                    m.VoucherRevision.id == uuid.UUID(voucher["revision_id"])
                )
            )
            assert revision.definition_snapshot["header"][0]["is_searchable"] is False
    bad = update | {
        "source_version": 3,
        "definition": update["definition"] | {"validation": {"max_length": 2}},
    }
    assert (await source(client, app, definitions=[bad])).status_code == 200
    item = (await client.get(prefix + "/voucher-field-adoptions", headers=headers())).json()[
        "items"
    ][-1]
    rejected = await client.post(
        prefix + "/voucher-field-adoptions/" + item["id"] + "/apply",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert rejected.status_code in {409, 422}, rejected.text


async def test_source_identity_conflict_and_permission_safe_exports(client, prefix, app):
    key = uuid.uuid4()
    first = definition("cf_secret", "text")
    assert (await source(client, app, message_id=key, definitions=[first])).status_code == 200
    altered = first | {"source_version": 2}
    assert (await source(client, app, message_id=key, definitions=[altered])).status_code == 409
    kind = await create_type(client, prefix)
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], custom_fields={"cf_secret": "private"}
    )
    rules = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "custom_field:cf_secret",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    exported = await client.get(prefix + "/voucher-export", headers=headers(policies=rules))
    assert exported.status_code == 200, exported.text
    assert "private" not in exported.text
    assert (
        await client.get(
            prefix + "/voucher-export", headers=headers(permissions=frozenset({"vouchers.read"}))
        )
    ).status_code == 403
    fields = await client.get(
        prefix + "/voucher-types/" + kind["id"] + "/field-set",
        params={"date": "2026-10-10"},
        headers=headers(policies=rules),
    )
    assert fields.status_code == 200, fields.text
    assert not fields.json()["custom"]
    retired = await client.post(
        prefix + "/voucher-types/" + kind["id"] + "/retire",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert retired.status_code == 200, retired.text
    assert (
        await client.get(prefix + "/vouchers/" + voucher["id"], headers=headers())
    ).status_code == 200


async def test_voucher_revision_field_set_uses_pinned_metadata_and_live_denies(client, prefix, app):
    kind = await create_type(client, prefix)
    field = definition("cf_reference", "text")
    assert (await source(client, app, definitions=[field])).status_code == 200
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], custom_fields={"cf_reference": "PO-42"}
    )
    path = prefix + f'/vouchers/{voucher["id"]}/field-set'
    result = await client.get(path, headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()["revision_id"] == voucher["revision_id"]
    assert [row["definition"]["key"] for row in result.json()["header"]] == ["cf_reference"]
    assert result.json()["items"] == {}
    denied_rules = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "custom_field:cf_reference",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    hidden = await client.get(path, headers=headers(policies=denied_rules))
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["header"] == []
    assert (
        await client.get(path, headers=headers(permissions=frozenset()))
    ).status_code == 403
    other, _ = await draft(client, prefix, kind["revision_id"])
    assert (
        await client.get(
            path, params={"revision_id": other["revision_id"]}, headers=headers()
        )
    ).status_code == 404


async def test_typed_custom_filter_rejects_invalid_values(client, prefix, app):
    assert (
        await source(
            client, app, definitions=[definition("cf_flag", "boolean", is_searchable=True)]
        )
    ).status_code == 200
    result = await client.get(
        prefix + "/vouchers",
        params={"custom_key": "cf_flag", "custom_value": "123"},
        headers=headers(),
    )
    assert result.status_code == 422, result.text


async def test_custom_search_case_rules_are_database_independent(client, prefix, app):
    kind = await create_type(client, prefix)
    defs = [
        definition("cf_exact", "text", is_searchable=True, validation={"max_length": 200}),
        definition(
            "cf_fold",
            "text",
            is_searchable=True,
            validation={"max_length": 200, "case_sensitive": False},
        ),
    ]
    assert (await source(client, app, definitions=defs)).status_code == 200
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], custom_fields={"cf_exact": "Alpha", "cf_fold": "Alpha"}
    )
    exact = await client.get(
        prefix + "/vouchers",
        headers=headers(),
        params={"custom_key": "cf_exact", "custom_value": "alpha"},
    )
    folded = await client.get(
        prefix + "/vouchers",
        headers=headers(),
        params={"custom_key": "cf_fold", "custom_value": "alpha"},
    )
    assert exact.json()["items"] == []
    assert [row["id"] for row in folded.json()["items"]] == [voucher["id"]]
