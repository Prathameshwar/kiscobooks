"""Every registered report must expose executable, bounded result navigation."""

import uuid
from decimal import localcontext

import pytest
from billing_platform.errors import ValidationFailedError
from conftest import COMPANY, PERMISSIONS, TENANT, headers
from test_framework_execution import proof
from test_native_ledger import prepared

from reports.tasks.report_catalog import catalog


@pytest.mark.parametrize("code", [key[0] for key in catalog().reports])
def test_each_report_declares_search_filters_sorts_and_detail_link(code):
    from reports.domain.reporting.navigation import capabilities

    entry = catalog().resolve(code)
    info = capabilities(entry.definition)
    assert info["search_fields"]
    assert "row_kind" in info["filters"]
    assert "ordinal" in info["sort_fields"]
    assert any(link.key == "row_detail" for link in entry.definition.drilldowns)


def test_exact_sort_and_filters_preserve_original_running_balances():
    from reports.domain.reporting.navigation import select_rows
    from reports.schemas.framework import ResultQuery

    definition = catalog().resolve("ACCOUNT_LEDGER").definition
    values = [
        (1, {"number": "RCPT-01", "date": "2026-04-01", "debit": "9.9999", "balance": "100.0000"}),
        (2, {"number": "RCPT-02", "date": "2026-04-02", "debit": "10.0000", "balance": "110.0000"}),
        (3, {"number": "PAY-01", "date": "2026-04-03", "debit": "0.0000", "balance": "90.0000"}),
    ]
    with localcontext() as context:
        context.prec = 6
        selected = select_rows(definition, ResultQuery(q="  RCPT  ", sort="-debit"), values)
    assert [ordinal for ordinal, _row in selected] == [2, 1]
    assert [row["balance"] for _ordinal, row in selected] == ["110.0000", "100.0000"]
    with pytest.raises(ValidationFailedError):
        select_rows(definition, ResultQuery(sort="configuration_hash"), values)


@pytest.mark.parametrize("capacity", [False, True])
async def test_async_result_query_is_pinned_exportable_and_idempotent(
    app, client, tmp_path, capacity
):
    from reports.tasks.framework_worker import process

    generation, _facts, ids = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    base = f"/v2/companies/{COMPANY}/report-runs"
    response = await client.post(
        base,
        headers=headers(),
        json={
            "code": "ACCOUNT_LEDGER",
            "generation_id": str(generation[2]),
            "parameters": {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "account_id": str(ids["cash"]),
            },
        },
    )
    assert response.status_code == 202, response.text

    async def authority(job):
        return proof(job)

    parent = response.json()["id"]
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(parent), authority
    )
    original = (await client.get(base + "/" + parent + "/rows", headers=headers())).json()["items"]
    key = headers()
    for _ in range(2):
        selected = await client.post(
            base + "/" + parent + "/queries",
            headers=key,
            json={"sort": "-date", "filters": {"row_kind": "ENTRY"}},
        )
        assert selected.status_code == 202, selected.text
        child = selected.json()
    assert child["origin"]["parent_id"] == parent
    assert child["origin"].get("ordinal") is None
    if capacity:
        app.state.settings.bulk_result_limit = 1
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(child["id"]),
        authority,
    )
    path = base + "/" + child["id"]
    detail = (await client.get(path, headers=headers())).json()
    if capacity:
        assert detail["status"] == "BLOCKED"
        assert detail["failure_code"] == "REPORT_CAPACITY_EXCEEDED"
        assert (await client.get(path + "/rows", headers=headers())).status_code == 409
        return
    assert detail["status"] == "COMPLETE", detail
    result = (await client.get(path + "/rows", headers=headers(), params={"limit": 1})).json()
    assert result["items"][0]["source_ordinal"] in {row["ordinal"] for row in original}
    assert result["items"][0]["data"]["row_kind"] == "ENTRY"
    assert result["items"][0]["drilldowns"]
    assert detail["result"]["evidence"]["classification"] == "SELECTED_RESULT"
    assert detail["result"]["selection"]["balance_semantics"] == "ORIGINAL_RESULT"
    for denied in (headers(user=uuid.uuid4()), headers(permissions=PERMISSIONS - {"ledger.read"})):
        assert (
            await client.post(base + "/" + parent + "/queries", headers=denied, json={})
        ).status_code == 403
        assert (await client.get(path + "/rows", headers=denied)).status_code == 403
    from test_framework_exports import new_export

    app.state.settings.exports_enabled = True
    app.state.settings.artifact_root = tmp_path / "private"
    exported, target = await new_export(client, path, "HTML")
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(exported["id"]),
        authority,
    )
    grant = await client.get(target + "/download-token", headers=headers())
    assert grant.status_code == 200, grant.text
    downloaded = await client.get(
        target + "/download", headers=headers(), params={"token": grant.json()["token"]}
    )
    assert downloaded.status_code == 200, downloaded.text
    assert "Selected rows" in downloaded.text
    bad = await client.post(
        base + "/" + parent + "/queries", headers=headers(), json={"filters": {"unknown": "x"}}
    )
    assert bad.status_code == 422
    assert (await client.post(base + "/" + parent + "/queries", json={})).status_code == 401


def sample(code):
    from bank_evidence_fixture import evidence_dataset
    from financial_fixture import financial_dataset, financial_manifest
    from fixtures import source
    from invoice_fixture import invoice_dataset
    from test_invoice_reports import component_dataset, purchase_dataset, tax_dataset
    from test_money_reports import bank_dataset

    from reports.domain.reporting.inventory import CODES as INVENTORY_CODES

    if code in INVENTORY_CODES:
        from inventory_fixture import inventory_dataset, parameters

        facts, stock_ids = inventory_dataset()
        return facts, parameters(code, stock_ids), financial_manifest(facts).control

    if code == "BANK_BOOK":
        facts, _ids = bank_dataset()
        parameters = {"date_from": "2026-04-01", "date_to": "2026-04-30"}
    elif code.startswith("BANK_RECONCILIATION"):
        facts, request, _ids = evidence_dataset()
        parameters = {
            "date_from": str(request.date_from),
            "date_to": str(request.date_to),
            "account_id": str(request.account_id),
            "basis": "TRANSACTION",
            "currency": "INR",
        }
        if code == "BANK_RECONCILIATION_EVIDENCE":
            parameters["session_id"] = str(request.session_id)
        elif code == "BANK_RECONCILIATION":
            parameters["statement_balance"] = "100.0000"
    else:
        if code == "INVOICE_COMPONENT_REGISTER":
            facts, _ids, _commercial = component_dataset()
        elif code in {"PURCHASE_REGISTER", "INVOICE_CREDIT_REGISTER"}:
            facts, *_identities = purchase_dataset()
        elif code in {"INVOICE_TAX_REGISTER", "TAX_GL_BRIDGE"}:
            facts, _ids, _registration = tax_dataset()
        else:
            facts, _ids = (
                invoice_dataset()
                if "INVOICE" in code or code == "SALES_REGISTER"
                else financial_dataset()
            )
        if code == "PAYMENT_REGISTER":
            facts = [
                source(row.entity, row.source_id, row.data | {"kind": "PAYMENT"})
                if row.entity == "journal" and row.data["number"] == "expense"
                else row
                for row in facts
            ]
        parameters = {"date_from": "2026-04-01", "date_to": "2026-04-30"}
    adapter = catalog().resolve(code).handler
    parameters = {
        key: value
        for key, value in parameters.items()
        if key in adapter.parameter_model.model_fields
    }
    return facts, parameters, financial_manifest(facts).control


@pytest.mark.parametrize("code", [key[0] for key in catalog().reports])
def test_each_report_rows_have_valid_filters_sort_and_executable_mappings(code):
    from reports.domain.reporting.drilldowns import parameters_for
    from reports.domain.reporting.navigation import capabilities, normalize, select_rows
    from reports.schemas.framework import ResultQuery

    facts, parameters, control = sample(code)
    entry = catalog().resolve(code)
    rows, _evidence = entry.handler.execute(facts, uuid.uuid4(), parameters, control)
    assert rows, code
    values = list(enumerate(rows, 1))
    for key in capabilities(entry.definition)["sort_fields"]:
        for direction in ("", "-"):
            selected = select_rows(entry.definition, ResultQuery(sort=direction + key), values)
            assert {ordinal for ordinal, _row in selected} == {ordinal for ordinal, _row in values}
    for row in rows:
        for key in capabilities(entry.definition)["search_fields"]:
            if row.get(key) and len(str(row[key])) >= 2:
                query = ResultQuery(q=str(row[key])[:2])
                assert row in [
                    value for _ordinal, value in select_rows(entry.definition, query, values)
                ]
                break
        for key, kind in capabilities(entry.definition)["filters"].items():
            if key not in row or row[key] is None:
                continue
            value = str(row[key]).lower() if kind == "BOOLEAN" else str(row[key])
            query = normalize(entry.definition, ResultQuery(filters={key: value}))
            assert row in [
                value for _ordinal, value in select_rows(entry.definition, query, values)
            ]
        for mapping in entry.definition.drilldowns:
            selected = parameters_for(mapping.key, parameters, row, str(control.coverage_start))
            if selected is not None and mapping.key != "row_detail":
                catalog().resolve(mapping.target).handler.normalize(selected)


async def test_signed_journal_link_executes_next_level_on_same_frozen_source(app, client):
    from reports.tasks.framework_worker import process

    generation, _facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    base = f"/v2/companies/{COMPANY}/report-runs"
    response = await client.post(
        base,
        headers=headers(),
        json={
            "code": "DAY_BOOK",
            "generation_id": str(generation[2]),
            "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30"},
        },
    )

    async def authority(job):
        return proof(job)

    parent = response.json()["id"]
    await process(
        app.state.session_factory, app.state.settings, TENANT, COMPANY, uuid.UUID(parent), authority
    )
    page = (await client.get(base + "/" + parent + "/rows", headers=headers())).json()["items"]
    row = next(row for row in page if row["data"].get("journal_id"))
    detail_link = next(link for link in row["drilldowns"] if link["key"] == "row_detail")
    assert (await client.get(detail_link["href"], headers=headers())).json()["data"] == row["data"]
    assert (await client.get(detail_link["href"] + "x", headers=headers())).status_code == 422
    assert (
        await client.get(detail_link["href"], headers=headers(user=uuid.uuid4()))
    ).status_code == 403
    link = next(link for link in row["drilldowns"] if link["key"] == "journal_entries")
    child = await client.post(link["href"], headers=headers(), json={"token": link["token"]})
    assert child.status_code == 202, child.text
    child_id = child.json()["id"]
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(child_id),
        authority,
    )
    entries = (await client.get(base + "/" + child_id + "/rows", headers=headers())).json()["items"]
    assert entries and all(
        item["data"]["journal_id"] == row["data"]["journal_id"] for item in entries
    )
    assert child.json()["generation_id"] == str(generation[2])


@pytest.mark.parametrize("code", [key[0] for key in catalog().reports])
async def test_each_report_api_query_and_next_level_links(app, client, code):
    from reports.domain.reporting.navigation import capabilities
    from reports.tasks.framework_worker import process

    facts, parameters, _control = sample(code)
    generation, _facts, _ids = await prepared(app, dataset=(facts, {}))
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    base = f"/v2/companies/{COMPANY}/report-runs"

    async def authority(job):
        return proof(job)

    async def complete(response):
        assert response.status_code == 202, response.text
        identity = response.json()["id"]
        await process(
            app.state.session_factory,
            app.state.settings,
            TENANT,
            COMPANY,
            uuid.UUID(identity),
            authority,
        )
        detail = (await client.get(base + "/" + identity, headers=headers())).json()
        assert detail["status"] == "COMPLETE", detail
        return detail

    parent = await complete(
        await client.post(
            base,
            headers=headers(),
            json={"code": code, "generation_id": str(generation[2]), "parameters": parameters},
        )
    )
    parent_path = base + "/" + parent["id"]

    async def all_rows(path):
        values = []
        params = {"limit": 200}
        while True:
            response = await client.get(path + "/rows", headers=headers(), params=params)
            assert response.status_code == 200, response.text
            page = response.json()
            values.extend(page["items"])
            if not page["page"]["has_more"]:
                return values
            params["cursor"] = page["page"]["next_cursor"]

    original = await all_rows(parent_path)
    selection = await client.post(
        parent_path + "/queries", headers=headers(), json={"sort": "-ordinal"}
    )
    if code == "TRIAL_BALANCE":
        # V6 totals and ancestry require the complete company result. Hierarchy
        # presentation is selected through its dedicated endpoint, never a query run.
        assert selection.status_code == 422, selection.text
        assert "complete-company standard inputs" in selection.json()["error"]["message"]
        hierarchy = await client.get(parent_path + "/hierarchy", headers=headers())
        assert hierarchy.status_code == 200, hierarchy.text
        assert hierarchy.json()["items"]
    else:
        selected = await complete(selection)
        items = await all_rows(base + "/" + selected["id"])
        assert [item["data"] for item in items] == [item["data"] for item in reversed(original)]
    discovery = await client.get(
        f"/v2/companies/{COMPANY}/report-definitions/{code}", headers=headers()
    )
    assert (
        discovery.json()["navigation"]["search_fields"]
        == capabilities(catalog().resolve(code).definition)["search_fields"]
    )
    for item in original:
        for link in item["drilldowns"]:
            if link["method"] == "GET":
                value = await client.get(link["href"], headers=headers())
                assert value.status_code == 200, value.text
                assert value.json()["data"] == item["data"]
        break
    executed = set()
    for item in original:
        for link in item["drilldowns"]:
            if link["method"] == "POST" and link["key"] not in executed:
                child = await complete(
                    await client.post(
                        link["href"], headers=headers(), json={"token": link["token"]}
                    )
                )
                assert child["generation_id"] == parent["generation_id"]
                assert child["origin"]["mapping"] == link["key"]
                if link["key"] == "journal_entries":
                    journal_rows = await all_rows(base + "/" + child["id"])
                    assert journal_rows, (code, item["data"])
                    assert all(
                        value["data"]["journal_id"] == item["data"]["journal_id"]
                        for value in journal_rows
                    )
                executed.add(link["key"])


@pytest.mark.parametrize(
    "query",
    [
        {"sort": "unknown"},
        {"sort": "date,date"},
        {"sort": "date,number,credit,debit"},
        {"q": "x"},
        {"filters": {"debit_min": "NaN"}},
        {"filters": {"date_from": "bad"}},
    ],
)
def test_query_rejects_invalid_boundaries(query):
    from reports.domain.reporting.navigation import normalize
    from reports.schemas.framework import ResultQuery

    with pytest.raises(ValidationFailedError):
        normalize(catalog().resolve("ACCOUNT_LEDGER").definition, ResultQuery.model_validate(query))


def test_income_expenditure_exposes_surplus_without_trading_gross_profit():
    import uuid

    from reports.tasks.report_catalog import catalog

    facts, parameters, control = sample("INCOME_EXPENSE")
    rows, _ = (
        catalog()
        .resolve("INCOME_EXPENSE")
        .handler.execute(facts, uuid.uuid4(), parameters, control)
    )
    assert rows[-1]["row_kind"] == "NET_SURPLUS_DEFICIT"
    assert rows[-1]["amount"] == "160.0000"
    assert not any(row["row_kind"] in {"GROSS_PROFIT", "NET_PROFIT"} for row in rows)
    assert {row["nature"] for row in rows if row.get("account_id")} == {"INCOME", "EXPENSE"}


def test_result_sort_ties_nulls_and_ranges_are_exact():
    from reports.domain.reporting.navigation import select_rows
    from reports.schemas.framework import ResultQuery

    definition = catalog().resolve("ACCOUNT_LEDGER").definition
    values = [
        (1, {"debit": "10.0000"}),
        (2, {"debit": None}),
        (3, {"debit": "10.0000"}),
        (4, {"debit": "9.9999"}),
    ]
    assert [
        ordinal for ordinal, _ in select_rows(definition, ResultQuery(sort="-debit"), values)
    ] == [1, 3, 4, 2]
    assert [
        ordinal
        for ordinal, _ in select_rows(
            definition, ResultQuery(filters={"debit_min": "10", "debit_max": "10.0000"}), values
        )
    ] == [1, 3]
    with pytest.raises(ValidationFailedError, match="range"):
        select_rows(definition, ResultQuery(filters={"debit_min": "11", "debit_max": "10"}), values)
    with pytest.raises(ValidationFailedError, match="range"):
        select_rows(
            definition,
            ResultQuery(filters={"date_from": "2026-05-01", "date_to": "2026-04-01"}),
            values,
        )


def test_document_date_drilldown_uses_actual_journal_posting_day():
    from reports.domain.reporting.drilldowns import parameters_for

    identity = str(uuid.uuid4())
    selected = parameters_for(
        "journal_entries",
        {"date_from": "2026-03-01", "date_to": "2026-03-31"},
        {"journal_id": identity, "posting_date": "2026-04-02"},
        "2026-03-01",
    )
    assert selected == {"date_from": "2026-04-02", "date_to": "2026-04-02", "journal_id": identity}


async def test_native_detail_uses_saved_position_without_scanning_prior_rows(
    app, client, monkeypatch
):
    from reports.queries import results
    from reports.tasks.framework_worker import process

    generation, _facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    base = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        base,
        headers=headers(),
        json={
            "code": "ACCOUNT_LEDGER",
            "generation_id": str(generation[2]),
            "parameters": {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "comparative_from": "2027-04-01",
                "comparative_to": "2027-04-30",
            },
        },
    )
    assert created.status_code == 202, created.text

    async def authority(job):
        return proof(job)

    identity = created.json()["id"]
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(identity),
        authority,
    )
    params = {"limit": 2}
    last = None
    while True:
        page = (
            await client.get(base + "/" + identity + "/rows", headers=headers(), params=params)
        ).json()
        last = page["items"][-1]
        if not page["page"]["has_more"]:
            break
        params["cursor"] = page["page"]["next_cursor"]

    def forbidden_scan(*args, **kwargs):
        raise AssertionError("row detail must seek to its signed saved position")

    monkeypatch.setattr(results, "batches", forbidden_scan)
    link = next(link for link in last["drilldowns"] if link["key"] == "row_detail")
    detail = await client.get(link["href"], headers=headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"] == last["data"]
    assert last["data"]["period"] == "COMPARATIVE"


async def test_new_navigation_rejects_wrong_company_and_cross_tenant_objects(app, client):
    from reports.tasks.framework_worker import process

    generation, _facts, _ids = await prepared(app)
    app.state.settings.framework_enabled = app.state.settings.native_queries_enabled = True
    base = f"/v2/companies/{COMPANY}/report-runs"
    created = await client.post(
        base,
        headers=headers(),
        json={
            "code": "DAY_BOOK",
            "generation_id": str(generation[2]),
            "parameters": {"date_from": "2026-04-01", "date_to": "2026-04-30"},
        },
    )
    assert created.status_code == 202, created.text

    async def authority(job):
        return proof(job)

    identity = created.json()["id"]
    await process(
        app.state.session_factory,
        app.state.settings,
        TENANT,
        COMPANY,
        uuid.UUID(identity),
        authority,
    )
    other = uuid.uuid4()
    wrong = base.replace(str(COMPANY), str(other)) + "/" + identity
    assert (
        await client.post(wrong + "/queries", headers=headers(company=other), json={})
    ).status_code == 403
    assert (await client.get(wrong + "/rows/1", headers=headers(company=other))).status_code == 403
    assert (
        await client.post(
            base + "/" + identity + "/queries", headers=headers(tenant=other), json={}
        )
    ).status_code == 404
    assert (
        await client.get(base + "/" + identity + "/rows/1", headers=headers(tenant=other))
    ).status_code == 404
    denied = headers(
        policies=[
            {"access": "read", "effect": "deny", "field": "amount", "resource": "journal_line"}
        ]
    )
    assert (
        await client.post(base + "/" + identity + "/queries", headers=denied, json={})
    ).status_code == 403
    assert (await client.get(base + "/" + identity + "/rows/1", headers=denied)).status_code == 403


async def test_journal_drilldown_uses_its_scoped_native_index(app):
    from billing_platform.db import tenant_scope
    from test_native_ledger import request

    from reports.queries.native_context import NativeContext
    from reports.queries.native_ledger import LedgerQuery

    identities, _facts, _ids = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            if db.bind.dialect.name != "mysql":
                pytest.skip("native MySQL journal index access regression")
            context = await NativeContext.load(db, COMPANY, identities[2])
            candidates = LedgerQuery(context, request(identities[2], "DAY_BOOK"))
            selected = (await db.execute(candidates.entry_selection(None, 1))).one()
            journal = LedgerQuery(
                context, request(identities[2], "DAY_BOOK", journal_id=selected.journal_id)
            )
            connection = await db.connection()

            async def reads():
                value = await connection.exec_driver_sql(
                    "SHOW SESSION STATUS LIKE 'Handler_read_next'"
                )
                return int(value.one()[1])

            started = await reads()
            statement = journal.entry_selection(None, 200).with_hint(
                journal.line, "FORCE INDEX (ix_report_posted_line_journal)", dialect_name="mysql"
            )
            rows = (await db.execute(statement)).all()
            scanned = await reads() - started
            assert rows and all(row.journal_id == selected.journal_id for row in rows)
            assert scanned <= len(rows) + 1


def test_identity_result_filter_normalizes_uuid_spelling():
    from reports.domain.reporting.navigation import select_rows
    from reports.schemas.framework import ResultQuery

    identity = uuid.uuid4()
    values = [(1, {"account_id": str(identity)})]
    selected = select_rows(
        catalog().resolve("ACCOUNT_LEDGER").definition,
        ResultQuery(filters={"account_id": identity.hex.upper()}),
        values,
    )
    assert selected == values


def test_bank_instrument_rows_retain_selected_account_for_result_filtering():
    facts, parameters, control = sample("BANK_RECONCILIATION")
    rows, _evidence = catalog().resolve("BANK_RECONCILIATION").handler.execute(
        facts, uuid.uuid4(), parameters, control
    )
    assert rows and all(row["account_id"] == parameters["account_id"] for row in rows)


@pytest.mark.parametrize(
    "value,kind",
    [
        ("NaN", "MONEY"),
        ("1e34", "MONEY"),
        ("1" * 129, "MONEY"),
        (True, "INTEGER"),
        ("x", "INTEGER"),
        ("yes", "BOOLEAN"),
        ("2026-02-30", "DATE"),
    ],
)
def test_typed_result_filters_reject_nonfinite_invalid_and_oversized_values(value, kind):
    from reports.domain.reporting.navigation import scalar

    with pytest.raises(ValidationFailedError):
        scalar(value, kind)


def test_result_ranges_identity_and_multikey_sort_fail_closed():
    from reports.domain.reporting.navigation import normalize, select_rows
    from reports.schemas.framework import ResultQuery

    definition = catalog().resolve("ACCOUNT_LEDGER").definition
    for query in [
        ResultQuery(filters={"account_id": "invalid"}),
        ResultQuery(filters={"number": "x" * 201}),
        ResultQuery(q="  a  "),
        ResultQuery(filters={"date_from": "2026-05-01", "date_to": "2026-04-01"}),
    ]:
        with pytest.raises(ValidationFailedError):
            normalize(definition, query)
    values = [
        (1, {"date": "2026-04-01", "debit": "10", "number": "A"}),
        (2, {"date": "2026-04-01", "debit": "10", "number": "A"}),
        (3, {"date": "2026-04-02", "debit": "9", "number": "B"}),
        (4, {"date": None, "debit": None, "number": "C"}),
    ]
    assert [
        ordinal
        for ordinal, _ in select_rows(definition, ResultQuery(sort="date,-debit,number"), values)
    ] == [1, 2, 3, 4]
    assert [
        ordinal
        for ordinal, _ in select_rows(definition, ResultQuery(filters={"debit_max": "9"}), values)
    ] == [3]
    assert [
        ordinal
        for ordinal, _ in select_rows(
            definition, ResultQuery(filters={"date_from": "2026-04-02"}), values
        )
    ] == [3]
    assert [ordinal for ordinal, _ in select_rows(definition, ResultQuery(q="zz"), values)] == []
    assert [
        ordinal
        for ordinal, _ in select_rows(definition, ResultQuery(filters={"number": "a"}), values)
    ] == [1, 2]
    assert [
        ordinal
        for ordinal, _ in select_rows(definition, ResultQuery(filters={"debit_min": "11"}), values)
    ] == []


def test_drilldown_boundaries_do_not_drop_currency_party_or_comparative_context():
    from reports.domain.reporting.drilldowns import parameters_for

    account, group, party, journal, invoice = [str(uuid.uuid4()) for _ in range(5)]
    params = {
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
        "comparative_from": "2025-04-01",
        "comparative_to": "2025-04-30",
        "basis": "TRANSACTION",
        "currency": "USD",
        "party_id": party,
        "role": "CUSTOMER",
    }
    assert parameters_for(
        "account_entries",
        params,
        {"account_id": account, "period": "COMPARATIVE", "grain": "DAY", "date": "2025-04-02"},
        None,
    ) == {
        "account_id": account,
        "date_from": "2025-04-02",
        "date_to": "2025-04-02",
        "basis": "TRANSACTION",
        "currency": "USD",
        "party_id": party,
        "role": "CUSTOMER",
    }
    assert (
        parameters_for(
            "account_entries",
            params,
            {"account_id": account, "grain": "DAY", "date": "2026-05-01"},
            None,
        )
        is None
    )
    assert parameters_for("account_entries", {}, {"account_id": account}, None) is None
    assert parameters_for("group_entries", params, {"group_id": group}, None)["group_id"] == group
    assert parameters_for("group_entries", params, {}, None) is None
    assert parameters_for("journal_entries", params, {}, None) is None
    assert (
        parameters_for("party_bills", params, {"account_id": account, "row_kind": "OPENING"}, None)
        is None
    )
    assert parameters_for("party_bills", params, {}, None) is None
    assert (
        parameters_for("party_bills", params, {"party_account_id": account}, None)["account_id"]
        == account
    )
    assert parameters_for(
        "invoice_gl", params, {"invoice_id": invoice, "posting_date": "2026-05-02"}, "2025-01-01"
    ) == {
        "date_from": "2025-01-01",
        "date_to": "2026-05-02",
        "invoice_id": invoice,
        "currency": "USD",
    }
    assert (
        parameters_for("invoice_gl", params, {"invoice_id": invoice}, None)["date_from"]
        == "2026-04-01"
    )
    assert parameters_for("invoice_gl", params, {}, None) is None
    assert parameters_for("journal_entries", {}, {"journal_id": journal}, None) is None
    assert parameters_for("unknown", params, {}, None) is None
