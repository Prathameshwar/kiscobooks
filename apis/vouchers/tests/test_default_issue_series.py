"""A type that names no series still issues: it numbers from its own automatic series."""

from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from conftest import TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft

from vouchers.models import core as m
from vouchers.tasks.documents import default_series_code

NO_APPROVAL = {"schema_version": 2, "approval_required": False}


async def issue(client, prefix, type_revision_id, **body):
    item, _ = await draft(client, prefix, type_revision_id)
    path = prefix + "/vouchers/" + item["id"]
    submitted = await client.post(path + "/submit", json={"expected_version": 1}, headers=headers())
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "APPROVED"
    return await client.post(
        path + "/issue", json={"expected_version": 2} | body, headers=headers()
    )


async def test_a_type_without_a_series_issues_from_one_automatic_series(client, prefix, app):
    kind = await create_type(client, prefix, policy=NO_APPROVAL)
    first = await issue(client, prefix, kind["revision_id"])
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ISSUED"
    second = await issue(client, prefix, kind["revision_id"])
    assert second.status_code == 200, second.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            series = list(await db.scalars(select(m.VoucherNumberSeries)))
            assert [
                (row.code, row.prefix, row.numbering_mode, row.reset_policy) for row in series
            ] == [("D-GENERAL", "GENERAL/", "AUTOMATIC", "FINANCIAL_YEAR")]
            numbers = sorted(
                (row.sequence, row.display_number)
                for row in await db.scalars(select(m.VoucherNumberAssignment))
            )
            assert [sequence for sequence, _ in numbers] == [1, 2]
            assert all(number.startswith("GENERAL/") for _, number in numbers), numbers
            created = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "vouchers.series.create")
                )
            )
            assert len(created) == 1
            assert created[0].payload["reason"] == "default series for GENERAL"


async def test_a_configured_series_list_is_still_required(client, prefix):
    series = await client.post(
        prefix + "/voucher-series", json={"code": "DOC", "prefix": "DOC-"}, headers=headers()
    )
    assert series.status_code == 201, series.text
    kind = await create_type(
        client, prefix, policy=NO_APPROVAL | {"allowed_series_ids": [series.json()["id"]]}
    )
    refused = await issue(client, prefix, kind["revision_id"])
    assert refused.status_code == 422, refused.text
    assert "not allowed" in refused.text


def test_default_series_codes_fit_the_series_code_pattern():
    assert default_series_code("SO") == "D-SO"
    long = default_series_code("A" * 40)
    assert len(long) == 20 and long.startswith("D-AAAAAAAAAAAA-")
    assert default_series_code("A" * 40) != default_series_code("A" * 39 + "B")


async def test_a_retired_automatic_series_is_named_instead_of_reused(client, prefix, app):
    kind = await create_type(client, prefix, policy=NO_APPROVAL)
    assert (await issue(client, prefix, kind["revision_id"])).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            series = await db.scalar(select(m.VoucherNumberSeries))
            series.status = "RETIRED"
    refused = await issue(client, prefix, kind["revision_id"])
    assert refused.status_code == 409, refused.text
    assert "automatic series D-GENERAL is retired" in refused.text
