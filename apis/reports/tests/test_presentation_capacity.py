import io
import json
import uuid
import zipfile
from dataclasses import replace

import pytest
from billing_platform.db import tenant_scope
from conftest import COMPANY, TENANT, headers
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.tasks.framework_worker import process


async def authority(job):
    return proof(job)


async def run_report(app, client, **choices):
    generation, _facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    path = f"/v2/companies/{COMPANY}/report-runs"
    response = await client.post(
        path,
        headers=headers(),
        json={
            "code": "OUTSTANDING_BILLS",
            "generation_id": str(generation[2]),
            "parameters": {"date_to": "2026-04-30"},
            **choices,
        },
    )
    assert response.status_code == 202, response.text
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(response.json()["id"]),
        authority,
    )
    return path + "/" + response.json()["id"]


async def test_registered_views_validate_and_group_exact_party_balances(app, client):
    path = await run_report(app, client, view="party_balances")
    detail = (await client.get(path, headers=headers())).json()
    assert detail["status"] == "COMPLETE", detail
    assert detail["view"] == "party_balances"
    rows = (await client.get(path + "/rows", headers=headers())).json()["items"]
    assert len(rows) == 1
    assert rows[0]["data"]["account_name"]
    assert rows[0]["data"]["account_code"]
    assert rows[0]["data"]["debt"] == "150.0000"
    assert rows[0]["data"]["unapplied_credit"] == "70.0000"
    assert rows[0]["data"]["net_debt"] == "80.0000"
    rejected = await client.post(
        path.rsplit("/", 1)[0],
        headers=headers(),
        json={
            "code": "OUTSTANDING_BILLS",
            "generation_id": detail["generation_id"],
            "parameters": {"date_to": "2026-04-30"},
            "view": "unknown",
        },
    )
    assert rejected.status_code == 422


@pytest.mark.parametrize("format_name", ["HTML", "PDF"])
async def test_business_run_and_package_preserve_every_row_and_manifest(
    app, client, tmp_path, monkeypatch, format_name
):
    from reports.tasks import export_artifacts

    path = await run_report(app, client, view="default")
    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    original = export_artifacts.definition
    monkeypatch.setattr(
        export_artifacts,
        "definition",
        lambda name, settings: replace(original(name, settings), max_rows=1),
    )
    output = await client.post(
        path + "/exports",
        headers=headers(),
        json={"format": format_name, "view": "default", "delivery": "PACKAGE"},
    )
    assert output.status_code == 202, output.text
    identity = uuid.UUID(output.json()["id"])
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, identity, authority
    )
    target = f"/v2/companies/{COMPANY}/report-exports/{identity}"
    status = (await client.get(target, headers=headers())).json()
    assert status["status"] == "COMPLETE", status
    token = (await client.get(target + "/download-token", headers=headers())).json()["token"]
    download = await client.get(target + "/download", headers=headers(), params={"token": token})
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["row_count"] == 2
        assert [(p["first_ordinal"], p["row_count"]) for p in manifest["parts"]] == [(1, 1), (2, 1)]
        import hashlib

        for part in manifest["parts"]:
            content = archive.read(part["filename"])
            assert hashlib.sha256(content).hexdigest() == part["content_hash"]
            if format_name == "HTML":
                assert "Direction" in content.decode()
            else:
                from pypdf import PdfReader

                assert "Direction" in "".join(
                    page.extract_text() for page in PdfReader(io.BytesIO(content)).pages
                )
    incompatible = await client.post(
        path + "/exports", headers=headers(), json={"format": "CSV", "view": "party_balances"}
    )
    assert incompatible.status_code == 422


async def test_bulk_summary_exceeds_standard_limit_in_bounded_units(app, client):
    app.state.settings.native_result_limit = 2
    path = await run_report(
        app,
        client,
        code="ACCOUNT_SUMMARY",
        execution="BULK",
        parameters={"date_from": "2026-06-01", "date_to": "2026-06-03"},
    )
    detail = (await client.get(path, headers=headers())).json()
    assert detail["status"] == "COMPLETE", detail
    assert detail["execution"] == "BULK"
    assert detail["completed_rows"] > 2
    assert detail["result"]["plan"]["key"] == "bulk_account_summary"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            from sqlalchemy import select

            from reports.models.framework import ReportJob

            job = await db.scalar(select(ReportJob).where(ReportJob.id == uuid.UUID(detail["id"])))
            assert job.checkpoint["next_unit"] == 3


async def test_bulk_setup_renews_lease_before_the_first_period(app, client, monkeypatch):
    import asyncio
    import datetime as dt

    from billing_platform.db.types import utcnow

    from reports.models import framework as models
    from reports.tasks import framework_jobs as jobs
    from reports.tasks import framework_worker as worker
    from reports.tasks.bulk_summary import NativeContext

    now = [utcnow()]
    renewed = asyncio.Event()
    heartbeats = []
    original_load, original_heartbeat = NativeContext.load, jobs.heartbeat
    monkeypatch.setattr(jobs, "utcnow", lambda: max(now[0], utcnow()))
    monkeypatch.setattr(models, "utcnow", lambda: max(now[0], utcnow()))
    monkeypatch.setattr(worker, "PULSE_SECONDS", 0.01)

    async def heartbeat(*args):
        await original_heartbeat(*args)
        # The worker commits outside heartbeat(). Advance the simulated clock
        # only after that renewal is durable, rather than racing its commit.
        from sqlalchemy import event

        @event.listens_for(args[0].sync_session, "after_commit", once=True)
        def committed(_session):
            heartbeats.append(now[0])
            renewed.set()

    async def load(*args):
        context = await original_load(*args)
        for _ in range(2):
            renewed.clear()
            now[0] += dt.timedelta(seconds=35)
            await asyncio.wait_for(renewed.wait(), timeout=2)
        return context

    monkeypatch.setattr(jobs, "heartbeat", heartbeat)
    monkeypatch.setattr(NativeContext, "load", load)
    path = await run_report(
        app,
        client,
        code="ACCOUNT_SUMMARY",
        execution="BULK",
        parameters={"date_from": "2026-06-01", "date_to": "2026-06-02"},
    )
    detail = (await client.get(path, headers=headers())).json()
    assert detail["status"] == "COMPLETE", detail
    assert detail["attempt"] == 1
    assert len(heartbeats) >= 2


def test_package_rejects_total_budget_without_publishing(tmp_path):
    from reports.domain.reporting.contracts import Column
    from reports.rendering.packaged import PackageWriter
    from reports.rendering.tabular import Budget, CsvWriter

    columns = (Column("id", "ID"),)

    def writer(path, budget, first):
        return CsvWriter(path, columns, budget)

    package = PackageWriter(
        tmp_path / "report",
        columns,
        Budget(2, 2, 4096, 10),
        Budget(1, 1, 4096, 10),
        "CSV",
        writer,
        {"run_id": "example"},
        2,
    )
    package.append([{"id": "one"}, {"id": "two"}])
    with pytest.raises(ValueError, match="budget"):
        package.append([{"id": "three"}])
    package.abort()
    with zipfile.ZipFile(tmp_path / "report") as archive:
        assert "manifest.json" not in archive.namelist()


async def test_bulk_checkpoint_replays_only_completed_periods(app, client, monkeypatch):
    import datetime as dt

    from billing_platform.db.types import utcnow

    from reports.models.framework import ReportJob
    from reports.tasks import bulk_summary

    original = bulk_summary.execute
    calls = []

    async def interrupted(db, context, query, maximum, **kwargs):
        calls.append(query.date_from)
        if len(calls) == 2:
            raise OSError("temporary database interruption")
        return await original(db, context, query, maximum, **kwargs)

    monkeypatch.setattr(bulk_summary, "execute", interrupted)
    path = await run_report(
        app,
        client,
        code="ACCOUNT_SUMMARY",
        execution="BULK",
        parameters={"date_from": "2026-06-01", "date_to": "2026-06-03"},
    )
    initial = (await client.get(path, headers=headers())).json()
    assert initial["status"] == "QUEUED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            job = await db.get(ReportJob, uuid.UUID(initial["id"]))
            assert job.checkpoint["next_unit"] == 1
            job.available_at = utcnow() - dt.timedelta(seconds=1)
    calls.clear()

    async def resumed(db, context, query, maximum, **kwargs):
        calls.append(query.date_from)
        return await original(db, context, query, maximum, **kwargs)

    monkeypatch.setattr(bulk_summary, "execute", resumed)
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(initial["id"]),
        authority,
    )
    final = (await client.get(path, headers=headers())).json()
    assert final["status"] == "COMPLETE", final
    assert final["attempt"] == 2
    assert calls == [dt.date(2026, 6, 2), dt.date(2026, 6, 3)]
    rows = (await client.get(path + "/rows", headers=headers())).json()["items"]
    assert len(rows) == final["completed_rows"]
    assert len(
        {
            (
                r["data"]["row_kind"],
                r["data"].get("account_id", r["data"].get("group_id")),
                r["data"]["date"],
            )
            for r in rows
        }
    ) == len(rows)


async def test_bulk_bounds_and_presentation_package_admission(app, client, tmp_path):
    app.state.settings.bulk_result_limit = 1
    path = await run_report(
        app,
        client,
        code="ACCOUNT_SUMMARY",
        execution="BULK",
        parameters={"date_from": "2026-06-01", "date_to": "2026-06-03"},
    )
    detail = (await client.get(path, headers=headers())).json()
    assert detail["status"] == "BLOCKED"
    assert detail["failure_code"] == "REPORT_CAPACITY_EXCEEDED"
    assert detail["completed_rows"] == 0


async def test_bulk_monthly_comparatives_match_standard_financial_rules(app, client):
    import datetime as dt

    from reports.domain.statements import calculate
    from reports.schemas.requests import RunRequest

    generation, facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = True
    app.state.settings.native_queries_enabled = True
    parameters = {
        "date_from": "2026-04-01",
        "date_to": "2027-04-30",
        "grain": "MONTH",
        "comparative_from": "2026-04-01",
        "comparative_to": "2026-05-31",
    }
    path = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        path,
        headers=headers(),
        json={
            "code": "ACCOUNT_SUMMARY",
            "generation_id": str(generation[2]),
            "execution": "BULK",
            "parameters": parameters,
        },
    )
    assert created.status_code == 202, created.text
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(created.json()["id"]),
        authority,
    )
    target = path + "/" + created.json()["id"]
    detail = (await client.get(target, headers=headers())).json()
    assert detail["status"] == "COMPLETE", detail
    values, cursor = [], None
    while True:
        page = (
            await client.get(
                target + "/rows",
                headers=headers(),
                params={"limit": 200, **({"cursor": cursor} if cursor else {})},
            )
        ).json()
        values.extend(row["data"] for row in page["items"])
        cursor = page["page"]["next_cursor"]
        if cursor is None:
            break
    query = RunRequest.model_validate(
        parameters | {"code": "ACCOUNT_SUMMARY", "generation_id": generation[2]}
    )
    expected, _ = calculate(facts, query, dt.date(2026, 4, 1))

    def key(row):
        return (
            row["period"],
            row["date"],
            row["row_kind"],
            row.get("account_id", row.get("group_id")),
        )

    assert sorted(values, key=key) == sorted(expected, key=key)


def test_bulk_units_preserve_partial_months_and_comparatives():
    from reports.schemas.requests import RunRequest
    from reports.tasks.bulk_summary import units

    query = RunRequest.model_validate(
        {
            "code": "ACCOUNT_SUMMARY",
            "generation_id": uuid.uuid4(),
            "date_from": "2026-12-15",
            "date_to": "2027-01-02",
            "grain": "MONTH",
            "comparative_from": "2025-12-15",
            "comparative_to": "2026-01-02",
        }
    )
    values = list(units(query))
    assert [(str(q.date_from), str(q.date_to), phase) for q, phase in values] == [
        ("2026-12-15", "2026-12-31", "CURRENT"),
        ("2027-01-01", "2027-01-02", "CURRENT"),
        ("2025-12-15", "2025-12-31", "COMPARATIVE"),
        ("2026-01-01", "2026-01-02", "COMPARATIVE"),
    ]


def test_bulk_period_splits_preserve_later_opening_turnover():
    import datetime as dt
    from decimal import Decimal

    from financial_fixture import financial_dataset

    from reports.domain.statements import Facts, calculate_data
    from reports.queries.native_statements import AggregatedFacts
    from reports.schemas.requests import RunRequest
    from reports.tasks.bulk_summary import units

    facts, ids = financial_dataset()
    dimensions = Facts(facts)
    lines = [
        {
            "account_id": ids["cash"],
            "side": "DEBIT",
            "opening_effect": True,
            "posting_date": dt.date(2027, 4, 1),
            "value": Decimal("25"),
            "signed": Decimal("25"),
        }
    ]
    data = AggregatedFacts(dimensions, lines)
    query = RunRequest.model_validate(
        {
            "code": "ACCOUNT_SUMMARY",
            "generation_id": uuid.uuid4(),
            "date_from": "2027-03-01",
            "date_to": "2027-04-30",
            "grain": "MONTH",
        }
    )
    expected, _ = calculate_data(data, query, dt.date(2026, 4, 1))
    actual = []
    for unit, _phase in units(query):
        values, _ = calculate_data(
            data, unit, dt.date(2026, 4, 1), opening_boundary=query.date_from
        )
        actual.extend(values)

    def key(row):
        return row["row_kind"], row.get("account_id", row.get("group_id")), row["date"]

    assert sorted(actual, key=key) == sorted(expected, key=key)


def test_reference_party_balances_preserve_currency_role_period_and_exact_credit():
    from decimal import localcontext

    from reports.domain.reporting.views import party_balances

    base = {
        "party_id": "party",
        "account_id": "account",
        "role": "CUSTOMER",
        "report_currency": "INR",
        "direction": "DEBT",
        "report_amount": "123456789012.1234",
    }
    rows = [
        base,
        base | {"direction": "CREDIT", "report_amount": "123456789012.0000"},
        base | {"period": "COMPARATIVE", "report_amount": "2.0000"},
        base | {"report_currency": "USD", "report_amount": "3.0000"},
        base | {"role": "SUPPLIER", "direction": "CREDIT", "report_amount": "4.0000"},
    ]
    with localcontext() as caller:
        caller.prec = 6
        result = party_balances(rows)
    by_identity = {(row["period"], row["currency"], row["role"]): row for row in result}
    current = by_identity["CURRENT", "INR", "CUSTOMER"]
    assert current["debt"] == "123456789012.1234"
    assert current["unapplied_credit"] == "123456789012.0000"
    assert current["net_debt"] == "0.1234"
    assert by_identity["COMPARATIVE", "INR", "CUSTOMER"]["net_debt"] == "2.0000"
    assert by_identity["CURRENT", "USD", "CUSTOMER"]["net_debt"] == "3.0000"
    assert by_identity["CURRENT", "INR", "SUPPLIER"]["net_debt"] == "-4.0000"
    assert len(result) == 4
