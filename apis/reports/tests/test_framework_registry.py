import datetime as dt
import uuid
from dataclasses import asdict, replace
from decimal import Decimal

import pytest
from bank_evidence_fixture import evidence_dataset
from financial_fixture import financial_dataset, financial_manifest
from invoice_fixture import invoice_dataset
from pydantic import ValidationError

from reports.domain.reporting.contracts import (
    Column,
    DisplayConfiguration,
    ExportDefinition,
    Join,
    QueryPlan,
    ReportDocument,
    ResultManifest,
    Section,
    exact_storage,
    fingerprint,
    ratio,
)
from reports.domain.reporting.registry import Registration, Registry
from reports.domain.statements import CODES, calculate
from reports.schemas import report_parameters as p
from reports.tasks.report_catalog import DATASETS, METRICS, catalog, columns


def test_catalog_covers_legacy_and_versions_actual_rules_and_parameters():
    from reports.domain.reporting.inventory import CODES as INVENTORY_CODES
    from reports.tasks.analytics_catalog import CODES as ANALYTICS_CODES

    registry = catalog()
    assert {key[0] for key in registry.reports} == {
        *CODES,
        *INVENTORY_CODES,
        *ANALYTICS_CODES,
        "SOURCE_RECONCILIATION",
        "DAY_BOOK_ACTIVITY",
        "GSTR3B",
        "GSTR1",
    }
    for entry in registry.reports.values():
        assert entry.definition.parameter_schema_hash == fingerprint(entry.handler.parameters())
        assert len(entry.definition.implementation_hash) == 64
        assert entry.handler.parameters()["additionalProperties"] is False
    with pytest.raises(KeyError):
        registry.resolve("UNKNOWN")
    with pytest.raises(TypeError):
        registry.reports[("INJECTED", 2)] = object()


@pytest.mark.parametrize("code", ["SOURCE_RECONCILIATION", *CODES])
def test_reference_adapters_preserve_exact_legacy_rows_and_evidence(code):
    if code == "BANK_RECONCILIATION_EVIDENCE":
        facts, original, _ids = evidence_dataset()
        values = original.model_dump(mode="json", exclude_none=True)
    else:
        facts, ids = (
            invoice_dataset()
            if "INVOICE" in code or code in {"SALES_REGISTER", "PURCHASE_REGISTER", "TAX_GL_BRIDGE"}
            else financial_dataset()
        )
        values = {"date_from": "2026-04-01", "date_to": "2026-04-30"}
        if code == "BALANCE_CONTINUITY":
            values = {"date_from": "2027-04-01", "date_to": "2028-03-31"}
        if code in {"BANK_RECONCILIATION", "BANK_RECONCILIATION_WORKLIST"}:
            facts, original, _ids = evidence_dataset()
            values.update(account_id=str(original.account_id), currency="INR", basis="TRANSACTION")
            if code == "BANK_RECONCILIATION":
                values["statement_balance"] = "100.0000"
    # Version 5 remains the legacy contract; version 6 has an independently tested hierarchy.
    adapter = catalog().resolve(code, 5 if code == "TRIAL_BALANCE" else None).handler
    values = {
        key: value for key, value in values.items() if key in adapter.parameter_model.model_fields
    }
    proof = financial_manifest(facts).control
    generation = uuid.uuid4()
    rows, evidence = adapter.execute(facts, generation, values, proof)
    if code == "SOURCE_RECONCILIATION":
        assert any(row["kind"] == "GL_CONTROL" for row in rows)
        assert evidence["counts"] == proof.counts
    else:
        query = adapter.request(generation, values, proof.coverage_start)
        expected = calculate(facts, query, proof.coverage_start)
        assert (rows, evidence) == expected


@pytest.mark.parametrize(
    "model,values",
    [
        (p.SourceParameters, {"date_to": "2026-04-30"}),
        (
            p.StatementParameters,
            {"date_from": "2026-04-01", "date_to": "2026-04-30", "account_id": str(uuid.uuid4())},
        ),
        (p.DateRange, {"date_from": "2026-05-01", "date_to": "2026-04-30"}),
        (p.Comparison, {"comparative_from": "2026-04-01"}),
        (p.Comparison, {"comparative_from": "2026-04-01", "comparative_to": "2020-01-01"}),
        (p.CurrencyBasis, {"basis": "BASE", "currency": "USD"}),
        (p.CurrencyBasis, {"basis": "TRANSACTION"}),
        (
            p.BankWorklistParameters,
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "account_id": str(uuid.uuid4()),
                "currency": "INR",
                "basis": "BASE",
            },
        ),
        (
            p.InvoiceParameters,
            {"date_from": "2026-04-01", "date_to": "2026-04-30", "date_basis": "TAX_POINT"},
        ),
    ],
)
def test_report_specific_inputs_cannot_silently_ignore_filters(model, values):
    with pytest.raises(ValidationError):
        model.model_validate(values)


def test_native_invoice_currency_and_missing_source_coverage():
    adapter = catalog().resolve("SALES_REGISTER").handler
    values = {"date_from": "2026-04-01", "date_to": "2026-04-30", "currency": "USD"}
    request = adapter.request(uuid.uuid4(), values, dt.date(2026, 4, 1))
    assert request.currency == "USD" and request.basis == "TRANSACTION"
    facts, _ids = financial_dataset()
    control = financial_manifest(facts).control.model_copy(update={"coverage_start": None})
    with pytest.raises(ValueError, match="coverage"):
        adapter.execute(facts, uuid.uuid4(), values, control)


def test_new_report_registration_needs_no_dispatch_change():
    example = catalog().resolve("ACCOUNT_LEDGER")
    definition = replace(
        example.definition, code="SAMPLE", title="Sample", version=1, drilldowns=()
    )

    def handler():
        return Decimal("12.5000")

    registry = Registry([Registration(definition, handler)], DATASETS, METRICS)
    assert registry.resolve("SAMPLE").handler() == Decimal("12.5000")
    assert registry.resolve("SAMPLE").definition.identity != example.definition.identity


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_report",
        "duplicate_dataset",
        "duplicate_metric",
        "missing_handler",
        "no_permission",
        "no_views",
        "unknown_dataset",
        "unknown_metric",
        "duplicate_view",
        "duplicate_column",
        "missing_currency",
        "column_metric",
        "no_order",
        "no_grain",
        "overlapping_fields",
        "unknown_join",
        "join_local",
        "join_remote",
        "fan_out",
        "metric_cycle",
        "metric_missing",
        "ratio_operands",
        "metric_version",
    ],
)
def test_registry_rejects_invalid_startup_contracts(mutation):
    original = catalog().resolve("ACCOUNT_LEDGER")
    definition, handler = original.definition, original.handler
    datasets, metrics = list(DATASETS), list(METRICS)
    entries = None
    if mutation == "duplicate_report":
        entries = [original, original]
    elif mutation == "duplicate_dataset":
        datasets.append(datasets[0])
    elif mutation == "duplicate_metric":
        metrics.append(metrics[0])
    elif mutation == "missing_handler":
        handler = None
    elif mutation in {"no_permission", "no_views", "unknown_dataset", "unknown_metric"}:
        definition = replace(
            definition,
            **{
                "no_permission": {"permissions": ()},
                "no_views": {"views": ()},
                "unknown_dataset": {"datasets": ("unknown",)},
                "unknown_metric": {"metrics": ("unknown",)},
            }[mutation],
        )
    elif mutation in {
        "duplicate_view",
        "duplicate_column",
        "missing_currency",
        "column_metric",
        "no_order",
    }:
        view = definition.views[0]
        if mutation == "duplicate_view":
            definition = replace(definition, views=(view, view))
        else:
            view = replace(
                view,
                **{
                    "duplicate_column": {"columns": (view.columns[0], view.columns[0])},
                    "missing_currency": {"columns": (Column("amount", "Amount", "MONEY"),)},
                    "column_metric": {"columns": (Column("amount", "Amount", metric="unknown"),)},
                    "no_order": {"order": ()},
                }[mutation],
            )
            definition = replace(definition, views=(view,))
    elif mutation == "no_grain":
        datasets[0] = replace(datasets[0], identity=())
    elif mutation == "overlapping_fields":
        datasets[0] = replace(datasets[0], measures=("entity",))
    elif mutation in {"unknown_join", "join_local", "join_remote", "fan_out"}:
        join = Join("journal_line", "source_id", "source_id", "MANY_TO_ONE")
        join = replace(
            join,
            **{
                "unknown_join": {"target": "unknown"},
                "join_local": {"local_key": "unknown"},
                "join_remote": {"remote_key": "unknown"},
                "fan_out": {"cardinality": "ONE_TO_MANY"},
            }[mutation],
        )
        datasets[0] = replace(datasets[0], joins=(join,))
    else:
        metrics[0] = replace(
            metrics[0],
            **{
                "metric_cycle": {"dependencies": ("balance",)},
                "metric_missing": {"dependencies": ("missing",)},
                "ratio_operands": {"behavior": "RATIO"},
                "metric_version": {"version": 0},
            }[mutation],
        )
    with pytest.raises(ValueError):
        Registry(entries or [Registration(definition, handler)], datasets, metrics)


def test_valid_join_and_non_additive_metric_contracts():
    data = replace(
        DATASETS[0], joins=(Join("journal_line", "source_id", "source_id", "ONE_TO_MANY", True),)
    )
    entry = catalog().resolve("ACCOUNT_LEDGER")
    Registry(
        [replace(entry, definition=replace(entry.definition, drilldowns=()))],
        [data, *DATASETS[1:]],
        METRICS,
    )
    assert ratio(Decimal("-6"), Decimal("3")) == Decimal("-2")
    assert ratio(Decimal(1), Decimal(0)) is None
    with pytest.raises(ValueError):
        ratio(Decimal("NaN"), Decimal(1))
    assert exact_storage(Decimal("999999999999999.9999")) == Decimal("999999999999999.9999")
    for value in ("1000000000000000", "NaN", "0.00001"):
        with pytest.raises(ValueError):
            exact_storage(Decimal(value))


def test_result_document_and_export_identities_separate_rows_from_bytes():
    entry = catalog().resolve("TRIAL_BALANCE")
    plan = QueryPlan(
        "reference",
        1,
        "generation",
        "MATERIALIZED",
        ("journal_line",),
        "p",
        "a",
        ("ordinal",),
        1000,
    )
    result = ResultManifest("run", entry.definition.identity, "generation", plan, "schema")
    published = replace(result, row_count=12, content_hash="a" * 64)
    assert result.logical_fingerprint == published.logical_fingerprint
    assert replace(result, generation_id="later").logical_fingerprint != result.logical_fingerprint
    display = DisplayConfiguration(2, 4, "half_up", "DD/MM/YYYY")
    document = ReportDocument(
        "Trial Balance",
        "Example",
        "April",
        result,
        display,
        (Section("main", "Balances", entry.definition.views[0], "run"),),
    )
    assert "rows" not in asdict(document)
    renderer = ExportDefinition(
        "CSV", "text/csv", "1", "1", "none", 1000, 10000, 100000, 30, "EXACT_TEXT"
    )
    assert renderer.identity != replace(renderer, template_version="2").identity
    for updates in ({"version": 0}, {"max_rows": 0}, {"batch_rows": 201}, {"order": ()}):
        with pytest.raises(ValueError):
            replace(plan, **updates)
    for updates in ({"amount_precision": 5}, {"date_format": "auto"}):
        with pytest.raises(ValueError):
            replace(display, **updates)
    assert columns("invoice_id", "posting_date", "count", "description")[0].kind == "IDENTIFIER"
