"""Immutable evidence and correction/retry of a partially successful import."""

import base64
import datetime as dt
import uuid

import pytest
import test_imports_api as import_fixtures
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_imports_api import auth, bill, purchase_type, upload, validated, voucher_count

from vouchers.models import imports as m

masters = import_fixtures.masters


@pytest.mark.parametrize("fmt", ["CSV", "TSV", "XLSX", "JSON"])
async def test_history_corrections_preserve_success_and_downloads(
    client, prefix, app, masters, fmt
):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    original = [bill("A"), bill("B", total="99999")]
    staged = await upload(client, prefix, kind["id"], original)
    job = staged.json()
    ready = await validated(client, prefix, job)
    path = prefix + f"/voucher-imports/{job['id']}"
    done = await client.post(
        path + "/commit",
        headers=auth(),
        json={
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert done.status_code == 200 and done.json()["created_count"] == 1, done.text
    attempts = (await client.get(path + "/history/attempts", headers=auth())).json()["items"]
    assert len(attempts) == 2 and attempts[1]["phase"] == "VALIDATE"
    old = await client.get(path + f"/attempts/{attempts[1]['id']}/results", headers=auth())
    assert old.status_code == 200, old.text
    before = old.json()
    assert {row["state"] for row in before["items"]} == {"VALID", "INVALID"}
    correction = {
        "voucher_type_id": kind["id"],
        "format": "JSON",
        "document": {"schema_version": 1, "vouchers": [bill("A"), bill("B")]},
        "expected_version": done.json()["row_version"],
    }
    refused = await client.post(
        path + "/revisions",
        headers=auth(),
        json=correction
        | {
            "document": {
                "schema_version": 1,
                "vouchers": [bill("A", narration="changed"), bill("B")],
            }
        },
    )
    assert refused.status_code == 409, refused.text
    revised = await client.post(path + "/revisions", headers=auth(), json=correction)
    assert revised.status_code == 200 and revised.json()["revision"] == 2, revised.text
    retry = await client.post(
        path + "/retry", headers=auth(), json={"expected_version": revised.json()["row_version"]}
    )
    assert retry.status_code == 200 and retry.json()["state"] == "READY", retry.text
    finished = await client.post(
        path + "/commit",
        headers=auth(),
        json={
            "expected_version": retry.json()["row_version"],
            "selection_digest": retry.json()["selection_digest"],
        },
    )
    assert finished.status_code == 200 and finished.json()["created_count"] == 2, finished.text
    assert await voucher_count(app) == 2
    assert (
        await client.get(path + f"/attempts/{attempts[1]['id']}/results", headers=auth())
    ).json() == before
    revisions = (await client.get(path + "/history/revisions", headers=auth())).json()["items"]
    assert [row["revision"] for row in revisions] == [2, 1]
    for download_kind in ("SOURCE", "NORMALIZED", "CORRECTION", "RESULT"):
        options = {"kind": download_kind, "format": fmt}
        ticket = (await client.post(path + "/download-ticket", headers=auth(), json=options)).json()
        downloaded = await client.post(
            path + "/download", headers=auth(), json=options | {"token": ticket["token"]}
        )
        assert downloaded.status_code == 200 and downloaded.content, downloaded.text
        assert downloaded.headers["cache-control"] == "no-store"
        if download_kind in {"NORMALIZED", "CORRECTION"}:
            from vouchers.domain import imports as rules
            from vouchers.tasks import imports as run

            if fmt == "JSON":
                _, values = run.decode(fmt, None, downloaded.json(), rules.template(frozenset()))
            else:
                _, values = run.decode(
                    fmt,
                    base64.b64encode(downloaded.content).decode(),
                    None,
                    rules.template(frozenset()),
                )
            assert {row.import_key for row in values} == {"A", "B"}
        denied = [
            {
                "entity_type": "vouchers.voucher",
                "field_key": "invoice",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
        assert (
            await client.post(
                path + "/download",
                headers=auth(policies=denied),
                json=options | {"token": ticket["token"]},
            )
        ).status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            effects = list(await db.scalars(select(m.VoucherImportEffect)))
            assert len(effects) == 2


async def test_template_snapshot_and_tsv_transport(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    today = dt.date.today().isoformat()
    body = {"voucher_type_id": kind["id"], "document_date": today, "posting_date": today}
    headers = auth()
    created = await client.post(
        prefix + "/voucher-import-template-snapshots", headers=headers, json=body
    )
    assert created.status_code == 201, created.text
    assert created.json()["snapshot"]["options"]["classes"]["items"] == []
    replay = await client.post(
        prefix + "/voucher-import-template-snapshots", headers=headers, json=body
    )
    assert replay.json()["id"] == created.json()["id"]
    denied = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "invoice",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    fetched = await client.get(
        prefix + "/voucher-import-template-snapshots/" + created.json()["id"],
        headers=auth(policies=denied),
    )
    assert fetched.status_code == 403, fetched.text
    template = await client.get(
        prefix + "/voucher-import-templates",
        headers=auth(),
        params={"voucher_type_id": kind["id"], "format": "TSV"},
    )
    assert template.status_code == 200 and "\t" in template.text
    staged = await client.post(
        prefix + "/voucher-imports",
        headers=auth(),
        json={
            "voucher_type_id": kind["id"],
            "template_id": created.json()["id"],
            "format": "TSV",
            "content_base64": base64.b64encode(template.content).decode(),
        },
    )
    assert staged.status_code == 202, staged.text
    other = uuid.uuid4()
    foreign = await client.get(
        prefix.replace(str(COMPANY), str(other)) + "/voucher-imports/" + staged.json()["id"],
        headers=auth(company=other),
    )
    assert foreign.status_code == 403
