import datetime as dt
import secrets
import time
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    sign_service_body,
)
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr
from sqlalchemy import func, select
from test_foundation import create_type, draft
from unit_source_factories import unit_masters

from vouchers.config import SourceCredential
from vouchers.models import core as m
from vouchers.tasks.artifacts import render_pending


async def source(
    client,
    app,
    *,
    issuer="identity",
    definitions=(),
    masters=(),
    message_id=None,
    tenant=TENANT,
    company=COMPANY,
):
    secret = secrets.token_hex(32)
    key_id = issuer + ".test"
    app.state.settings.source_credentials[key_id] = SourceCredential(
        issuer=issuer,
        secret=SecretStr(secret),
        scopes=[CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)],
    )
    payload = {
        "message_id": str(message_id or uuid7()),
        "tenant_id": str(tenant),
        "company_id": str(company),
        "definitions": list(definitions),
        "masters": list(masters),
    }
    body = canonical_json(payload)
    key = ServiceKey(issuer, "vouchers", frozenset({"vouchers.sources.apply"}), secret.encode())
    stamp = int(time.time())
    signature = sign_service_body(
        key,
        key_id=key_id,
        operation="vouchers.sources.apply",
        timestamp=stamp,
        body=service_request_bytes(method="POST", path="/internal/v1/sources", query="", body=body),
    )
    return await client.post(
        "/internal/v1/sources",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Service-Key-Id": key_id,
            "X-Service-Issuer": issuer,
            "X-Service-Timestamp": str(stamp),
            "X-Service-Signature": signature,
        },
    )


def definition(key, kind, **extra):
    return {
        "entity_type": "vouchers.voucher",
        "source_version": 1,
        "definition": {"key": key, "data_type": kind} | extra,
    }


async def test_signed_source_ingress_obeys_rate_limit(client, app):
    class DenyLimiter:
        def allow(self, key, *, limit):
            assert key.startswith("service:identity.test:")
            assert limit == 1200
            return False

    app.state.write_limiter = DenyLimiter()
    assert (await source(client, app)).status_code == 429


@pytest.mark.parametrize("on_item", [False, True])
async def test_custom_field_condition_can_read_its_custom_parent(client, prefix, app, on_item):
    entity = "vouchers.voucher_item" if on_item else "vouchers.voucher"
    defs = [
        definition("cf_parent", "text"),
        definition(
            "cf_child",
            "text",
            validation={"required": True},
            visibility={"field": "cf_parent", "cmp": "eq", "value": "yes"},
        ),
    ]
    assert (
        await source(client, app, definitions=[row | {"entity_type": entity} for row in defs])
    ).status_code == 200
    bound_key = "item_field_keys" if on_item else "header_field_keys"
    kind = await create_type(client, prefix, policy={bound_key: ["cf_parent", "cf_child"]})
    field_set = await client.get(
        prefix + f'/voucher-types/{kind["id"]}/field-set',
        params={"date": dt.date.today().isoformat()},
        headers=headers(),
    )
    assert field_set.status_code == 200, field_set.text
    assert {row["definition"]["key"] for row in field_set.json()["custom"]} == {
        "cf_parent",
        "cf_child",
    }
    values = {"cf_parent": "yes", "cf_child": "accepted"}
    if on_item:
        item_id, unit_id = uuid7(), uuid7()
        assert (
            await source(
                client,
                app,
                issuer="catalog",
                masters=unit_masters(item_id, unit_id),
            )
        ).status_code == 200
        content = {
            "mode": "ITEMS",
            "lines": [
                {
                    "line_key": str(uuid7()),
                    "item": {
                        "item_id": str(item_id),
                        "item_version": 1,
                        "unit_id": str(unit_id),
                        "actual_quantity": "1",
                        "billed_quantity": "1",
                        "custom_fields": values,
                    },
                }
            ],
        }
    else:
        content = {"custom_fields": values}
    saved, request_body = await draft(client, prefix, kind["revision_id"], **content)
    stored = saved["lines"][0]["item"]["custom_fields"] if on_item else saved["custom_fields"]
    assert stored == values
    pinned = await client.get(prefix + f'/vouchers/{saved["id"]}/field-set', headers=headers())
    assert pinned.status_code == 200, pinned.text
    rows = (
        pinned.json()["items"][content["lines"][0]["line_key"]]
        if on_item
        else pinned.json()["header"]
    )
    assert {row["definition"]["key"] for row in rows} == {"cf_parent", "cf_child"}
    policies = [
        {
            "entity_type": entity,
            "field_key": "custom_field:cf_parent",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    hidden_type = await client.get(
        prefix + f'/voucher-types/{kind["id"]}/field-set',
        params={"date": dt.date.today().isoformat()},
        headers=headers(
            policies=policies,
            layouts=[
                {"entity_type": entity, "field_key": key, "label_override": "private"}
                for key in ("cf_parent", "cf_child")
            ],
        ),
    )
    assert hidden_type.status_code == 200, hidden_type.text
    assert hidden_type.json()["custom"] == []
    assert hidden_type.json()["layouts"] == []
    assert hidden_type.json()["configuration"]["policy"][bound_key] == []
    hidden_pinned = await client.get(
        prefix + f'/vouchers/{saved["id"]}/field-set', headers=headers(policies=policies)
    )
    assert hidden_pinned.status_code == 200, hidden_pinned.text
    assert (
        hidden_pinned.json()["items"][content["lines"][0]["line_key"]]
        if on_item
        else hidden_pinned.json()["header"]
    ) == []
    if on_item:
        line_denied = [
            {
                "entity_type": "vouchers.voucher",
                "field_key": "lines",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
        hidden_lines = await client.get(
            prefix + f'/voucher-types/{kind["id"]}/field-set',
            params={"date": dt.date.today().isoformat()},
            headers=headers(policies=line_denied),
        )
        assert hidden_lines.status_code == 200, hidden_lines.text
        assert hidden_lines.json()["custom"] == []
        assert hidden_lines.json()["configuration"]["policy"][bound_key] == []
    blocked = await client.post(
        prefix + "/vouchers",
        json=request_body,
        headers=headers(policies=policies),
    )
    assert blocked.status_code == 403, blocked.text


@pytest.mark.parametrize("on_item", [False, True])
async def test_all_twelve_custom_types_and_unique_claims(client, prefix, app, on_item):
    kind = await create_type(client, prefix)
    choices = [{"value": "A", "label": "Alpha"}, {"value": "B", "label": "Beta"}]
    definitions = [
        definition(
            "cf_text",
            "text",
            is_searchable=True,
            validation={"max_length": 200, "unique_within": "company"},
        ),
        definition("cf_long", "long_text"),
        definition("cf_integer", "integer"),
        definition("cf_decimal", "decimal"),
        definition("cf_bool", "boolean"),
        definition("cf_date", "date"),
        definition("cf_time", "datetime"),
        definition("cf_money", "currency_amount"),
        definition("cf_select", "select", choices=choices),
        definition("cf_multi", "multi_select", choices=choices),
        definition("cf_dynamic", "dynamic_select", option_source_key="voucher_types"),
        definition("cf_auto", "auto_number", sequence_config={"prefix": "A-", "padding": 3}),
    ]
    entity = "vouchers.voucher_item" if on_item else "vouchers.voucher"
    definitions = [value | {"entity_type": entity} for value in definitions]
    item_id, unit_id, line_key = uuid7(), uuid7(), uuid7()
    if on_item:
        facts = list(unit_masters(item_id, unit_id))
        assert (await source(client, app, issuer="catalog", masters=facts)).status_code == 200

    def payload(values):
        return (
            {
                "mode": "ITEMS",
                "lines": [
                    {
                        "line_key": str(line_key),
                        "item": {
                            "item_id": str(item_id),
                            "item_version": 1,
                            "unit_id": str(unit_id),
                            "actual_quantity": "11",
                            "billed_quantity": "10",
                            "custom_fields": values,
                        },
                    }
                ],
            }
            if on_item
            else {"custom_fields": values}
        )

    def stored(value):
        return value["lines"][0]["item"]["custom_fields"] if on_item else value["custom_fields"]

    result = await source(client, app, definitions=definitions)
    assert result.status_code == 200, result.text
    custom = {
        "cf_text": "unique",
        "cf_long": "notes",
        "cf_integer": 3,
        "cf_decimal": "12.5000",
        "cf_bool": True,
        "cf_date": "2026-10-10",
        "cf_time": "2026-10-10T00:00:00Z",
        "cf_money": {"amount": "9.2500", "currency": "INR"},
        "cf_select": "A",
        "cf_multi": ["A", "B"],
        "cf_dynamic": kind["id"],
    }
    row, body = await draft(client, prefix, kind["revision_id"], **payload(custom))
    assert stored(row)["cf_auto"] == "A-001"
    assert isinstance(stored(row)["cf_decimal"], str)
    duplicate = await client.post(prefix + "/vouchers", json=body, headers=headers())
    assert duplicate.status_code == 409, duplicate.text
    good = await client.post(
        prefix + "/vouchers",
        json=body | payload(custom | {"cf_text": "second"}),
        headers=headers(),
    )
    assert good.status_code == 201, good.text
    assert stored(good.json())["cf_auto"] == "A-002"
    found = await client.get(
        prefix + "/vouchers",
        params={"custom_key": "cf_text", "custom_value": "unique", "custom_entity": entity},
        headers=headers(),
    )
    assert found.status_code == 200 and [i["id"] for i in found.json()["items"]] == [row["id"]]
    revised = await client.put(
        prefix + "/vouchers/" + row["id"],
        json={"expected_version": 1, "content": body | payload(custom | {"cf_text": "updated"})},
        headers=headers(),
    )
    assert revised.status_code == 200, revised.text
    stale = await client.get(
        prefix + "/vouchers",
        params={"custom_key": "cf_text", "custom_value": "unique", "custom_entity": entity},
        headers=headers(),
    )
    assert stale.status_code == 200 and stale.json()["items"] == []
    current = await client.get(
        prefix + "/vouchers",
        params={"custom_key": "cf_text", "custom_value": "updated", "custom_entity": entity},
        headers=headers(),
    )
    assert current.status_code == 200
    assert [item["id"] for item in current.json()["items"]] == [row["id"]]
    bad = await client.post(
        prefix + "/vouchers",
        json=body | payload(custom | {"cf_text": "third", "cf_decimal": 1.25}),
        headers=headers(),
    )
    assert bad.status_code == 422, bad.text
    source_def = definitions[0] | {
        "source_version": 2,
        "definition": definitions[0]["definition"]
        | {"validation": {"max_length": 150, "unique_within": "company"}},
    }
    changed = await source(client, app, definitions=[source_def])
    assert changed.status_code == 200, changed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherFieldAdoption.id))) == 1


async def test_owner_signature_scope_version_and_item_identity(client, prefix, app):
    kind = await create_type(client, prefix, policy={"default_mode": "ITEMS"})
    item_id, unit_id = uuid7(), uuid7()
    facts = list(unit_masters(item_id, unit_id))
    unavailable = await client.post(
        prefix + "/vouchers",
        json={
            "type_revision_id": kind["revision_id"],
            "document_date": dt.date.today().isoformat(),
            "currency": "INR",
            "mode": "ITEMS",
            "lines": [
                {
                    "line_key": str(uuid7()),
                    "item": {
                        "item_id": str(item_id),
                        "item_version": 1,
                        "unit_id": str(unit_id),
                        "actual_quantity": "11",
                        "billed_quantity": "10",
                    },
                }
            ],
        },
        headers=headers(),
    )
    assert unavailable.status_code == 409, unavailable.text
    msg = uuid7()
    result = await source(client, app, issuer="catalog", masters=facts, message_id=msg)
    assert result.status_code == 200, result.text
    repeated = await source(client, app, issuer="catalog", masters=facts, message_id=msg)
    assert repeated.json()["replayed"]
    wrong = await source(client, app, issuer="catalog", masters=facts, company=uuid7())
    assert wrong.status_code == 401
    foreign = await source(client, app, issuer="identity", masters=facts)
    assert foreign.status_code == 422
    conflict = await source(
        client, app, issuer="catalog", masters=[facts[0] | {"status": "RETIRED"}]
    )
    assert conflict.status_code == 409
    lines = [
        {
            "line_key": str(uuid7()),
            "description": "Paid and free physical quantity",
            "item": {
                "item_id": str(item_id),
                "item_version": 1,
                "unit_id": str(unit_id),
                "actual_quantity": "11",
                "billed_quantity": "10",
            },
        }
    ]
    saved, body = await draft(client, prefix, kind["revision_id"], mode="ITEMS", lines=lines)
    assert saved["lines"][0]["item"]["actual_quantity"] == "11.0000"
    assert (
        await source(
            client,
            app,
            issuer="catalog",
            masters=[facts[0] | {"source_version": 2, "status": "RETIRED"}],
        )
    ).status_code == 200
    stale = await client.post(
        prefix + f'/vouchers/{saved["id"]}/submit', json={"expected_version": 1}, headers=headers()
    )
    assert stale.status_code == 409, stale.text


async def test_artifact_is_pinned_escaped_idempotent_and_live_protected(client, prefix, app):
    kind = await create_type(client, prefix)
    row, _ = await draft(client, prefix, kind["revision_id"], narration="<script>secret()</script>")
    template = await client.post(
        prefix + "/voucher-templates",
        json={"code": "PRINT", "title": "Prepared document"},
        headers=headers(),
    )
    assert template.status_code == 201, template.text
    body = {"expected_version": 1, "template_revision_id": template.json()["revision_id"]}
    key = headers()
    result = await client.post(prefix + f'/vouchers/{row["id"]}/artifacts', json=body, headers=key)
    assert result.status_code == 202, result.text
    artifact = result.json()["id"]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await render_pending(db, uuid.UUID(artifact))
            again = await render_pending(db, uuid.UUID(artifact))
            assert again.status == "READY"
    status = await client.get(prefix + f"/voucher-artifacts/{artifact}", headers=headers())
    assert status.status_code == 200, status.text
    token = status.json()["download_token"]
    assert (
        await client.get(
            prefix + f"/voucher-artifacts/{artifact}/download",
            params={"token": token},
            headers=headers(permissions=frozenset({"vouchers.artifact.read"})),
        )
    ).status_code == 403
    download = await client.get(
        prefix + f"/voucher-artifacts/{artifact}/download",
        params={"token": token},
        headers=headers(),
    )
    assert download.status_code == 200, download.text
    assert "<script>" not in download.text and "&lt;script&gt;" in download.text
    assert (
        await client.get(
            prefix + f"/voucher-artifacts/{artifact}/download",
            params={"token": token + "x"},
            headers=headers(),
        )
    ).status_code == 422
    policy = {
        "entity_type": "vouchers.voucher",
        "field_key": "narration",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
    }
    assert (
        await client.get(
            prefix + f"/voucher-artifacts/{artifact}/download",
            params={"token": token},
            headers=headers(policies=[policy]),
        )
    ).status_code == 403
    assert (
        await client.post(prefix + f'/vouchers/{row["id"]}/artifacts', json=body, headers=key)
    ).json()["id"] == artifact
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherArtifact.id))) == 1
            assert await db.scalar(select(func.count(m.VoucherNumberAssignment.id))) == 0


async def test_issue_print_does_not_reuse_an_earlier_draft_artifact(client, prefix, app):
    kind = await create_type(
        client, prefix, policy={"approval_required": False, "self_approval_allowed": True}
    )
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    template = (
        await client.post(
            prefix + "/voucher-templates",
            json={"code": "LIFECYCLE", "title": "Document"},
            headers=headers(),
        )
    ).json()
    path = prefix + "/vouchers/" + voucher["id"]
    first = await client.post(
        path + "/artifacts",
        json={"expected_version": 1, "template_revision_id": template["revision_id"]},
        headers=headers(),
    )
    series = (
        await client.post(
            prefix + "/voucher-series", json={"code": "SERIES", "prefix": "DOC-"}, headers=headers()
        )
    ).json()
    issued = await client.post(
        path + "/issue", json={"expected_version": 1, "series_id": series["id"]}, headers=headers()
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["issue_number"].startswith("DOC-")
    second = await client.post(
        path + "/artifacts",
        json={"expected_version": 2, "template_revision_id": template["revision_id"]},
        headers=headers(),
    )
    assert second.status_code == 202, second.text
    assert second.json()["id"] != first.json()["id"]


async def test_large_authorized_document_renders_without_text_truncation(client, prefix, app):
    kind = await create_type(client, prefix)
    definitions = [definition("cf_long_" + str(number), "long_text") for number in range(20)]
    assert (await source(client, app, definitions=definitions)).status_code == 200
    values = {row["definition"]["key"]: "<&" * 2000 for row in definitions}
    voucher, _ = await draft(client, prefix, kind["revision_id"], custom_fields=values)
    template = (
        await client.post(
            prefix + "/voucher-templates",
            json={"code": "LARGE", "title": "Document", "fields": ["custom_fields"]},
            headers=headers(),
        )
    ).json()
    artifact = (
        await client.post(
            prefix + "/vouchers/" + voucher["id"] + "/artifacts",
            json={"expected_version": 1, "template_revision_id": template["revision_id"]},
            headers=headers(),
        )
    ).json()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            rendered = await render_pending(db, uuid.UUID(artifact["id"]))
            assert len(rendered.body) > 65535
            assert "&lt;&amp;" in rendered.body
