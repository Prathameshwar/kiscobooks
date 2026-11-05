import base64
import uuid

import httpx
import pytest
from billing_platform.bulk_files import csv_document, read_xlsx, xlsx_document
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.bulk_factories import post, run, setup, unit_row
from tests.test_api import headers
from tests.test_unit_api import policy, seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("kind", ["CSV", "XLSX"])
async def test_transport_templates_and_signed_private_reports(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    template = await client.get(
        root + "/templates", headers=auth, params={"resource": "unit_of_measure", "format": kind}
    )
    assert (
        template.status_code == 200 and template.headers["Cache-Control"] == "no-store"
    ), template.text
    columns = [
        "_key",
        "_set",
        "_resource",
        "code",
        "name",
        "symbol",
        "dimension",
        "decimal_places",
        "quantity_increment",
    ]
    values = [["r1", "r1", "unit_of_measure", "0001", "Each", "ea", "COUNT", "0", "1"]]
    raw = (
        csv_document(columns, values, template=True)
        if kind == "CSV"
        else xlsx_document(columns, values)
    )
    job = await post(
        client, root, auth, "", {"format": kind, "content_base64": base64.b64encode(raw).decode()}
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    ticket = await client.get(
        root + "/" + job["id"] + "/report-ticket", headers=auth, params={"format": kind}
    )
    assert ticket.status_code == 200 and ticket.json()["expires_in_seconds"] == 300, ticket.text
    report = await client.get(ticket.json()["download_path"], headers=auth)
    assert report.status_code == 200 and report.headers["Cache-Control"] == "no-store", report.text
    assert (
        "VALID" in report.text
        if kind == "CSV"
        else read_xlsx(report.content)[0].cells["state"].value == "VALID"
    )
    bad = await client.get(ticket.json()["download_path"] + "x", headers=auth)
    assert bad.status_code == 422, bad.text
    no_actor = await client.get(ticket.json()["download_path"])
    assert no_actor.status_code == 401
    rows = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()["items"]
    preview = await client.get(root + "/" + job["id"] + "/records/" + rows[0]["id"], headers=auth)
    assert preview.json()["after"]["code"] == "0001"


async def test_invalid_columns_and_revoked_preview_fields_stay_private(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    bad = unit_row("bad")
    bad["data"]["decimal_places"] = "secret-bad-value"
    bad["source_sheet"] = "=untrusted"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [bad, unit_row("good")]})
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"
    records = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()["items"]
    invalid = next(row for row in records if row["logical_key"] == "bad")
    result = await client.get(root + "/" + job["id"] + "/records/" + invalid["id"], headers=auth)
    assert result.status_code == 200 and result.json()["error_fields"] == [
        "decimal_places"
    ], result.text
    ticket = (await client.get(root + "/" + job["id"] + "/report-ticket", headers=auth)).json()
    report = await client.get(ticket["download_path"], headers=auth)
    assert report.status_code == 200 and "'=untrusted" in report.text
    assert "secret-bad-value" not in report.text
    await seed_context(factory, tenant_a, company, user, (policy(user, "name", "read"),), version=3)
    valid = next(row for row in records if row["logical_key"] == "good")
    denied = await client.get(root + "/" + job["id"] + "/records/" + valid["id"], headers=auth)
    assert denied.status_code == 403, denied.text
    assert (await client.get(ticket["download_path"], headers=auth)).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"format": "CSV", "content_base64": "invalid!"},
        {
            "format": "JSON",
            "records": [{"key": "r", "change_set": "r", "resource": "customer", "data": {}}],
        },
        {
            "format": "JSON",
            "records": [{"key": "r", "change_set": "r", "resource": "stock_balance", "data": {}}],
        },
    ],
)
async def test_unsupported_or_malformed_inputs_fail_without_internal_details(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    payload: dict[str, object],
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    result = await client.post(
        f"/v1/companies/{company}/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json=payload,
    )
    assert result.status_code == 422, result.text
    assert set(result.json()) == {"error"}


async def test_job_object_scope_permissions_and_query_validation(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    other, _, other_auth = await setup(factory, tenant_a)
    root, foreign_root = f"/v1/companies/{company}/bulk-jobs", f"/v1/companies/{other}/bulk-jobs"
    job = await post(
        client, foreign_root, other_auth, "", {"format": "JSON", "records": [unit_row("ea")]}
    )
    assert (await client.get(root + "/" + job["id"], headers=auth)).status_code == 403
    assert (await client.get(root)).status_code == 401
    assert (
        await client.get(
            root, headers=headers(company, tenant=tenant_a, user=user, permission="item.read")
        )
    ).status_code == 403
    assert (await client.get(root, headers=auth, params={"unknown": "value"})).status_code == 422
    assert (await client.get(root + "?limit=1&limit=2", headers=auth)).status_code == 422
