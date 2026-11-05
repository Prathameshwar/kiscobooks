"""Regression coverage for the voucher import review findings."""

import datetime as dt
import uuid

import pytest
import test_imports_api as import_fixtures
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_foundation import create_type
from test_imports_api import (
    auth,
    bill,
    purchase_type,
    upload,
    validated,
    voucher_count,
)
from test_sources_custom_artifacts import definition, source

from vouchers.models import core as m
from vouchers.models import imports as im
from vouchers.tasks import imports as tasks

masters = import_fixtures.masters


async def test_read_denied_custom_field_is_hidden(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    response = await source(client, app, definitions=[definition("cf_secret", "text")])
    assert response.status_code == 200, response.text
    job = (
        await upload(client, prefix, kind["id"], [bill("A", **{"cf.cf_secret": "private-value"})])
    ).json()
    deny = [
        {
            "entity_type": "vouchers.voucher",
            "field_key": "custom_field:cf_secret",
            "access": "read",
            "effect": "deny",
            "scope_type": "company",
            "scope_id": str(COMPANY),
        }
    ]
    response = await client.get(
        prefix + f"/voucher-imports/{job['id']}/vouchers/A", headers=auth(policies=deny)
    )
    assert response.status_code == 200, response.text
    assert "private-value" not in response.text


@pytest.mark.parametrize("purge", [False, True])
async def test_expired_committing_job_cannot_create_next_draft(
    client, prefix, app, masters, monkeypatch, purge
):
    monkeypatch.setattr(tasks, "STEP", 1)
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A"), bill("B")])).json()
    ready = await validated(client, prefix, job)
    path = prefix + f"/voucher-imports/{job['id']}"
    first = await client.post(
        path + "/commit",
        headers=auth(),
        json={
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert first.json()["state"] == "COMMITTING", first.text
    assert await voucher_count(app) == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            stored = await db.get(im.VoucherImportJob, uuid.UUID(job["id"]))
            stored.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
            artifact = await db.scalar(
                select(im.VoucherImportArtifact).where(im.VoucherImportArtifact.job_id == stored.id)
            )
            artifact.expires_at = stored.expires_at
    if purge:
        fresh = await upload(client, prefix, kind["id"], [bill("C")])
        assert fresh.status_code == 202, fresh.text
        response = await client.post(path + "/run", headers=auth())
        assert response.status_code == 409, response.text
        assert await voucher_count(app) == 1
        return
    resumed = await client.post(path + "/run", headers=auth())
    assert resumed.status_code == 409, resumed.text
    assert await voucher_count(app) == 1


async def test_failed_job_can_be_revalidated_after_master_recovers(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    ready = await validated(client, prefix, job)
    await masters.evidence(app, version=2, only=masters.parties["SUP-1"])
    path = prefix + f"/voucher-imports/{job['id']}"
    committed = await client.post(
        path + "/commit",
        headers=auth(),
        json={
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert committed.json()["state"] == "FAILED", committed.text
    masters.versions[masters.parties["SUP-1"]] = 2
    retry = await client.post(
        path + "/validate",
        headers=auth(),
        json={"expected_version": committed.json()["row_version"]},
    )
    assert retry.status_code == 200 and retry.json()["state"] == "READY", retry.text


async def test_dated_financial_config_allows_payment_template(client, prefix):
    created = await client.post(
        prefix + "/voucher-configurations",
        headers=auth(),
        json={
            "code": "REVIEW_FIN",
            "name": "Financial policy",
            "policy": {"schema_version": 2, "financial": {"allocations_allowed": True}},
        },
    )
    assert created.status_code == 201, created.text
    config = created.json()
    published = await client.post(
        prefix + f"/voucher-configurations/{config['id']}/publish",
        headers=auth(),
        json={"expected_version": 1},
    )
    assert published.status_code == 200, published.text
    bound = await client.post(
        prefix + "/voucher-configuration-bindings",
        headers=auth(),
        json={
            "expected_version": 2,
            "configuration_revision_id": config["revision_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert bound.status_code == 201, bound.text
    kind = await create_type(
        client, prefix, code="REVIEW_PAY", kind="PAYMENT", policy={"schema_version": 2}
    )
    response = await client.get(
        prefix + "/voucher-import-templates",
        headers=auth(),
        params={"voucher_type_id": kind["id"], "format": "JSON"},
    )
    assert response.status_code == 200, response.text


async def test_new_custom_default_requires_revalidation(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    ready = await validated(client, prefix, job)
    changed = await source(
        client,
        app,
        definitions=[definition("cf_later", "text", default_value="added-after-review")],
    )
    assert changed.status_code == 200, changed.text
    done = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit",
        headers=auth(),
        json={
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert done.status_code == 200 and done.json()["state"] == "FAILED", done.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revision = await db.scalar(select(m.VoucherRevision))
            assert revision is None


def test_xlsx_numeric_identifier_is_accepted_as_text():
    import base64
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    from billing_platform.bulk_files import NS, xlsx_workbook

    from vouchers.domain import imports as rules

    shape = rules.template(frozenset())
    headers, lines = rules.examples(shape)
    original = xlsx_workbook(
        [("vouchers", shape.names("header"), headers), ("lines", shape.names("line"), lines)],
        marker=rules.MARKER,
    )
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source_zip,
        zipfile.ZipFile(output, "w") as target,
    ):
        for name in source_zip.namelist():
            raw = source_zip.read(name)
            if name == "xl/worksheets/sheet2.xml":
                tree = ET.fromstring(raw)  # noqa: S314 -- locally generated workbook fixture.
                cells = tree.findall(f"{{{NS}}}sheetData/{{{NS}}}row")[2].findall(f"{{{NS}}}c")
                cell = cells[shape.names("line").index("account_code")]
                coordinate = cell.attrib["r"]
                cell.clear()
                cell.attrib.update({"r": coordinate, "t": "n"})
                ET.SubElement(cell, f"{{{NS}}}v").text = "123"
                raw = ET.tostring(tree)
            target.writestr(name, raw)
    from billing_platform.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError, match="text"):
        tasks.decode("XLSX", base64.b64encode(output.getvalue()).decode(), None, shape)
