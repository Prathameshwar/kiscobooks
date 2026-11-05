import uuid

import pytest
from conftest import COMPANY, PERMISSIONS, headers
from test_framework_execution import accepted
from test_framework_exports import authority, new_export
from test_source_versions import staged


@pytest.mark.parametrize("damage", ["hash", "count", "gap", "missing"])
async def test_result_page_rejects_damaged_retained_batches(app, client, prefix, tmp_path, damage):
    from conftest import TENANT
    from sqlalchemy import delete, update
    from test_framework_exports import complete_run

    from reports.models.framework import ReportResultBatch

    target = await complete_run(app, client, prefix, tmp_path)
    table = ReportResultBatch.__table__
    where = (
        table.c.tenant_id == TENANT,
        table.c.company_id == COMPANY,
        table.c.job_id == uuid.UUID(target.rsplit("/", 1)[-1]),
    )
    # Simulate external corruption in this disposable schema; normal ORM forbids edits.
    async with app.state.engine.begin() as connection:
        if damage == "missing":
            await connection.execute(delete(table).where(*where))
        else:
            values = {
                "hash": {"content_hash": "0" * 64},
                "count": {"row_count": 1},
                "gap": {"first_ordinal": 2},
            }[damage]
            await connection.execute(update(table).where(*where).values(**values))
    result = await client.get(target + "/rows?limit=2", headers=headers())
    assert result.status_code == 409, result.text


async def test_capabilities_field_set_and_export_permission(app, client, tmp_path):
    path = f"/v2/companies/{COMPANY}/report-definitions/ACCOUNT_LEDGER/field-set"
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    result = await client.get(path, headers=headers())
    assert result.status_code == 200, result.text
    fields = result.json()
    assert fields["formats"] == ["CSV", "XLSX", "HTML", "PDF"]
    assert fields["views"][0]["key"] == "default"
    assert fields["native"]["properties"]["date_from"]["format"] == "date"
    limits = {value["format"]: value for value in fields["export_limits"]}
    assert limits["PDF"]["max_rows"] == 5000
    assert limits["HTML"]["max_cells"] == 200000
    denied = await client.get(path, headers=headers(permissions=PERMISSIONS - {"report.export"}))
    assert denied.status_code == 200 and denied.json()["formats"] == []
    assert (await client.get(path)).status_code == 401
    assert (
        await client.get(
            path,
            headers=headers(
                policies=[
                    {"access": "read", "effect": "deny", "entity_type": "account", "field": "name"}
                ]
            ),
        )
    ).status_code == 403
    app.state.settings.artifact_root = tmp_path / "file"
    app.state.settings.artifact_root.write_text("not a directory")
    assert (await client.get(path, headers=headers())).json()["formats"] == []


async def test_job_history_is_actor_bound_keyset_paged_and_lean(app, client, prefix):
    path, first = await accepted(app, client, prefix)
    assert first["parameters"] == {}
    created = await client.post(
        path,
        headers=headers(),
        json={"code": "SOURCE_RECONCILIATION", "generation_id": first["generation_id"]},
    )
    assert created.status_code == 202
    page = await client.get(path + "?limit=1", headers=headers())
    assert page.status_code == 200, page.text
    value = page.json()
    assert len(value["items"]) == 1 and value["page"]["has_more"]
    assert set(value["items"][0]) == {"id", "code", "kind", "status", "created_at"}
    next_page = await client.get(
        path, headers=headers(), params={"limit": 1, "cursor": value["page"]["next_cursor"]}
    )
    assert next_page.status_code == 200 and not next_page.json()["page"]["has_more"]
    assert {value["items"][0]["id"], next_page.json()["items"][0]["id"]} == {
        first["id"],
        created.json()["id"],
    }
    assert (await client.get(path, headers=headers(user=uuid.uuid4()))).json()["items"] == []
    assert (await client.get(path + "?offset=1", headers=headers())).status_code == 422
    assert (await client.get(path + "?limit=1&limit=2", headers=headers())).status_code == 422
    assert (
        await client.get(
            path, headers=headers(), params={"limit": 2, "cursor": value["page"]["next_cursor"]}
        )
    ).status_code == 422
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=headers(permissions=frozenset()))).status_code == 403


async def test_versioned_generation_history_excludes_legacy_and_preserves_scope(
    app, client, prefix
):
    await accepted(app, client, prefix)
    identities, _ = await staged(app)
    path = f"/v2/companies/{COMPANY}/report-generations"
    response = await client.get(path, headers=headers())
    assert response.status_code == 200, response.text
    assert [value["id"] for value in response.json()["items"]] == [str(identities[2])]


async def test_run_and_export_commands_cannot_target_the_other_resource(
    app, client, prefix, tmp_path
):
    path, queued = await accepted(app, client, prefix)
    wrong = f"/v2/companies/{COMPANY}/report-exports/{queued['id']}/cancel"
    assert (await client.post(wrong, headers=headers())).status_code == 409
    assert (await client.get(path + "/" + queued["id"], headers=headers())).json()[
        "status"
    ] == "QUEUED"
    from conftest import TENANT

    from reports.tasks.framework_worker import process

    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(queued["id"]),
        authority,
    )
    run = path + "/" + queued["id"]
    exported, _ = await new_export(client, run)
    assert (
        await client.post(path + "/" + exported["id"] + "/cancel", headers=headers())
    ).status_code == 409
    assert (await client.get(path + "/" + exported["id"], headers=headers())).status_code == 409
