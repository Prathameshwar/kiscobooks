"""Configuration, disclosure and worker boundaries used by financial entry."""

import asyncio
import importlib
import runpy
import secrets
import sys
import uuid

import pytest
from conftest import COMPANY, TENANT, USER, headers
from test_foundation import create_type, draft


def denied(field, *, entity="vouchers.configuration", access="read", **changes):
    return {
        "entity_type": entity,
        "field_key": field,
        "access": access,
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        **changes,
    }


async def test_class_revision_binding_close_and_retirement_preserve_captured_policy(client, prefix):
    kind = await create_type(client, prefix)
    class_result = await client.post(
        prefix + f'/voucher-types/{kind["id"]}/classes',
        headers=headers(),
        json={
            "expected_version": 1,
            "code": "REVIEW",
            "name": "Review class",
            "policy": {"narration_required": True},
        },
    )
    assert class_result.status_code == 201, class_result.text
    cls = class_result.json()
    captured, _ = await draft(client, prefix, kind["revision_id"], class_id=cls["id"])
    assert captured["class_id"] == cls["id"]
    config = (
        await client.post(
            prefix + "/voucher-configurations",
            headers=headers(),
            json={"code": "REVIEW", "name": "Reviewed policy", "policy": {"max_lines": 2}},
        )
    ).json()
    path = prefix + "/voucher-configurations/" + config["id"]
    revised = await client.post(
        path + "/revisions",
        headers=headers(),
        json={"expected_version": 1, "policy": {"max_lines": 3}},
    )
    assert revised.status_code == 200, revised.text
    published = await client.post(
        path + "/publish", headers=headers(), json={"expected_version": 2}
    )
    assert published.status_code == 200, published.text
    binding = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=headers(),
        json={
            "expected_version": 3,
            "configuration_revision_id": published.json()["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert binding.status_code == 201, binding.text
    close = prefix + "/voucher-configuration-bindings/" + binding.json()["id"] + "/close"
    assert (
        await client.post(
            close, headers=headers(), json={"expected_version": 1, "valid_to": "2020-01-01"}
        )
    ).status_code == 409
    key = headers()
    data = {"expected_version": 1, "valid_to": "2021-01-01"}
    closed = await client.post(close, headers=key, json=data)
    assert closed.status_code == 200 and closed.json()["valid_to"] == "2021-01-01"
    assert (await client.post(close, headers=key, json=data)).json() == closed.json()
    assert (
        await client.post(close, headers=headers(), json=data | {"expected_version": 2})
    ).status_code == 409
    retired = await client.post(path + "/retire", headers=headers(), json={"expected_version": 4})
    assert retired.status_code == 200, retired.text
    assert (
        await client.post(path + "/retire", headers=headers(), json={"expected_version": 5})
    ).status_code == 409
    assert (
        await client.post(
            path + "/revisions", headers=headers(), json={"expected_version": 5, "policy": {}}
        )
    ).status_code == 409
    old = await client.get(prefix + "/vouchers/" + captured["id"], headers=headers())
    assert (
        old.status_code == 200
        and old.json()["configuration_hash"] == captured["configuration_hash"]
    )


@pytest.mark.parametrize(
    "resource,params,policy,status",
    [
        ("voucher-types", {}, denied("id"), 403),
        ("voucher-types", {"q": "G"}, denied("code"), 403),
        ("vouchers", {"q": "  "}, None, 422),
        ("vouchers", {"q": "G"}, denied("issue_number", entity="vouchers.voucher"), 403),
        ("voucher-types", {"status": "ACTIVE"}, denied("status"), 403),
        ("voucher-types", {"code": "GENERAL"}, denied("code"), 403),
        ("vouchers", {"code": "GENERAL"}, None, 422),
        ("voucher-types", {"parent_id": str(uuid.uuid4())}, None, 422),
        ("voucher-types", {"type_revision_id": str(uuid.uuid4())}, None, 422),
        (
            "voucher-classes",
            {"type_revision_id": str(uuid.uuid4())},
            denied("type_revision_id"),
            403,
        ),
        ("voucher-types", {"custom_key": "cf_x", "custom_value": "x"}, None, 422),
        ("vouchers", {"custom_key": "cf_missing", "custom_value": "x"}, None, 422),
        (
            "vouchers",
            {"custom_key": "cf_secret", "custom_value": "x"},
            denied("cf_secret", entity="vouchers.voucher"),
            403,
        ),
        ("voucher-types", {"cursor": "invalid"}, None, 422),
        ("voucher-types", {}, denied("code", access="invalid"), 403),
        ("voucher-field-adoptions", {"cursor": "invalid"}, None, 422),
        ("voucher-field-adoptions", {}, denied("policy"), 403),
    ],
)
async def test_lists_cannot_infer_denied_or_unsupported_fields(
    client, prefix, resource, params, policy, status
):
    response = await client.get(
        prefix + "/" + resource, params=params, headers=headers(policies=[policy] if policy else [])
    )
    assert response.status_code == status, response.text


async def test_http_write_throttle_and_body_bound(client, app, prefix):
    # Filling a real-clock window can straddle its boundary on slow/coverage runs.
    clock = [1000.0]
    app.state.write_limiter.clock = lambda: clock[0]
    large = await client.post(prefix + "/voucher-types", content=b" " * 262145)
    assert large.status_code == 413 and large.headers["cache-control"] == "no-store"
    for _ in range(240):
        app.state.write_limiter.allow(f"{TENANT}:{COMPANY}:{USER}", limit=240)
    response = await client.post(
        prefix + "/voucher-types",
        headers=headers(),
        json={"code": "LIMITED", "name": "Limited", "kind": "MEMORANDUM"},
    )
    assert response.status_code == 429
    clock[0] += 60
    response = await client.post(
        prefix + "/voucher-types",
        headers=headers(),
        json={"code": "LIMITED", "name": "Limited", "kind": "MEMORANDUM"},
    )
    assert response.status_code == 201


async def test_pending_artifact_is_rendered_by_the_polling_worker(client, app, prefix, monkeypatch):
    from vouchers.tasks import artifact_worker as worker

    kind = await create_type(client, prefix)
    document, _ = await draft(client, prefix, kind["revision_id"])
    template = (
        await client.post(
            prefix + "/voucher-templates",
            headers=headers(),
            json={"code": "WORKER", "title": "Worker document"},
        )
    ).json()
    pending = await client.post(
        prefix + f'/vouchers/{document["id"]}/artifacts',
        headers=headers(),
        json={"expected_version": 1, "template_revision_id": template["revision_id"]},
    )
    assert pending.status_code == 202

    async def stop_after_iteration(seconds):
        raise asyncio.CancelledError

    # Keep the fixture's engine alive to inspect the committed result after worker shutdown.
    class Engine:
        async def dispose(self):
            pass

    monkeypatch.setattr(worker, "create_engine", lambda url: Engine())
    monkeypatch.setattr(
        worker, "create_session_factory", lambda *args, **kwargs: app.state.session_factory
    )
    monkeypatch.setattr(worker.asyncio, "sleep", stop_after_iteration)
    with pytest.raises(asyncio.CancelledError):
        await worker.run(app.state.settings)
    ready = await client.get(
        prefix + "/voucher-artifacts/" + pending.json()["id"], headers=headers()
    )
    assert ready.status_code == 200 and ready.json()["status"] == "READY"


@pytest.mark.parametrize(
    "module", ["artifact_worker", "source_worker", "execution_worker", "audit_publisher"]
)
def test_worker_cli_help_does_not_require_credentials(module, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["worker", "--help"])
    # Import with its package identity before exercising the script entry point.
    path = importlib.import_module("vouchers.tasks." + module).__file__
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(path, run_name="__main__")
    assert stopped.value.code == 0
    assert "--env-file" in capsys.readouterr().out


async def test_source_worker_polls_configured_owner_and_disposes_on_cancel(app, monkeypatch):
    from billing_platform.service_auth import CompanyServiceScope
    from pydantic import SecretStr

    from vouchers.tasks import source_worker as worker

    disposed, visited = [], []

    class Engine:
        async def dispose(self):
            disposed.append(True)

    async def synchronize(factory, client, selected):
        visited.append(selected)
        return 0

    async def stop(seconds):
        raise asyncio.CancelledError

    owner = worker.Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="worker.test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    monkeypatch.setattr(worker, "create_engine", lambda url: Engine())
    monkeypatch.setattr(
        worker, "create_session_factory", lambda *args, **kwargs: app.state.session_factory
    )
    monkeypatch.setattr(worker, "synchronize", synchronize)
    monkeypatch.setattr(worker.asyncio, "sleep", stop)
    settings = app.state.settings.model_copy(update={"snapshot_owners": [owner]})
    with pytest.raises(asyncio.CancelledError):
        await worker.run(settings)
    assert visited == [owner] and disposed == [True]


def test_publisher_cli_failure_never_discloses_connection_credentials(monkeypatch):
    from vouchers.tasks import audit_publisher as publisher

    secret = secrets.token_hex(32)
    settings = publisher.AuditPublisherSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        audit_broker_url="amqp://local:" + secret + "@127.0.0.1:5672/test",
        audit_broker_user="local",
        audit_event_secret=secret,
    )
    monkeypatch.setattr(publisher, "AuditPublisherSettings", lambda **kwargs: settings)

    async def failing(config):
        raise ConnectionError(config.broker_url)

    monkeypatch.setattr(publisher, "run_publisher", failing)
    monkeypatch.setattr(sys, "argv", ["publisher"])
    with pytest.raises(SystemExit) as stopped:
        publisher.main()
    assert str(stopped.value) == "Vouchers audit worker failed: ConnectionError"
    assert secret not in str(stopped.value)


async def test_typed_custom_filters_and_incompatible_adoption_preview(client, prefix, app):
    from test_sources_custom_artifacts import definition, source

    definitions = [
        definition("cf_boolean", "boolean", is_searchable=True),
        definition(
            "cf_multi",
            "multi_select",
            is_searchable=True,
            choices=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
        ),
        definition("cf_text", "text", is_searchable=True, validation={"max_length": 20}),
    ]
    result = await source(client, app, definitions=definitions)
    assert result.status_code == 200, result.text
    kind = await create_type(client, prefix)
    voucher, _ = await draft(
        client,
        prefix,
        kind["revision_id"],
        custom_fields={"cf_boolean": True, "cf_multi": ["a", "b"], "cf_text": "original"},
    )
    for key, value, status in [
        ("cf_boolean", "true", 200),
        ("cf_boolean", "not-json", 422),
        ("cf_multi", '["a"]', 200),
        ("cf_multi", '["a","b"]', 422),
    ]:
        selected = await client.get(
            prefix + "/vouchers",
            headers=headers(),
            params={"custom_key": key, "custom_value": value},
        )
        assert selected.status_code == status, selected.text
        if status == 200:
            assert selected.json()["items"][0]["id"] == voucher["id"]
    changes = [
        item
        | {
            "source_version": 2,
            "definition": item["definition"]
            | (
                {"validation": {"max_length": 2}}
                if item["definition"]["key"] == "cf_text"
                else {"is_searchable": False}
            ),
        }
        for item in (definitions[0], definitions[2])
    ]
    assert (await source(client, app, definitions=changes)).status_code == 200
    first = (
        await client.get(prefix + "/voucher-field-adoptions?limit=1", headers=headers())
    ).json()
    second = (
        await client.get(
            prefix + "/voucher-field-adoptions",
            headers=headers(),
            params={"limit": 1, "cursor": first["page"]["next_cursor"]},
        )
    ).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    for adoption in first["items"] + second["items"]:
        path = prefix + "/voucher-field-adoptions/" + adoption["id"]
        detail = (await client.get(path, headers=headers())).json()
        if detail["proposed_definition"]["key"] != "cf_text":
            continue
        preview = await client.post(
            path + "/preview", headers=headers(), json={"expected_version": 1}
        )
        assert preview.status_code == 200 and not preview.json()["can_apply"]
        reread = (await client.get(path, headers=headers())).json()
        assert reread["status"] == "PENDING" and reread["row_version"] == 1
        assert (
            await client.get(
                path, headers=headers(policies=[denied("cf_text", entity="vouchers.voucher")])
            )
        ).status_code == 403


async def test_conditional_disclosure_and_history_remain_authority_bound(client, prefix):
    kind = await create_type(client, prefix)
    voucher, body = await draft(client, prefix, kind["revision_id"], narration="restricted")
    path = prefix + "/vouchers/" + voucher["id"]
    condition = {"field": "narration", "cmp": "eq", "value": "restricted"}
    policy = denied("narration", entity="vouchers.voucher", condition=condition)
    hidden = await client.get(path, headers=headers(policies=[policy]))
    assert hidden.status_code == 200 and hidden.json().get("narration") is None
    visible = await client.get(
        path, headers=headers(policies=[policy | {"condition": condition | {"value": "different"}}])
    )
    assert visible.status_code == 200 and visible.json()["narration"] == "restricted"
    # Conditions without row values must not grant a list disclosure exception.
    no_allow = denied(
        "status",
        entity="vouchers.voucher",
        effect="allow",
        condition={"field": "status", "cmp": "eq", "value": "DRAFT"},
    )
    listed = await client.get(
        prefix + "/vouchers",
        headers=headers(policies=[denied("status", entity="vouchers.voucher"), no_allow]),
    )
    assert listed.status_code == 200 and listed.json()["items"][0].get("status") is None
    denied_identity = await client.get(
        path, headers=headers(policies=[denied("id", entity="vouchers.voucher")])
    )
    assert denied_identity.status_code == 403
    for query in ("limit=0", "cursor=invalid"):
        assert (await client.get(path + "/history?" + query, headers=headers())).status_code == 422
    forbidden = await client.put(
        path,
        headers=headers(policies=[policy | {"access": "write"}]),
        json={"expected_version": 1, "content": body | {"narration": "different"}},
    )
    assert forbidden.status_code == 403
