import uuid
from decimal import Decimal

import pytest
from financial_fixture import financial_dataset, financial_manifest
from pydantic import ValidationError

from reports.domain.day_book import Parameters, calculate_activity
from reports.tasks.report_catalog import catalog


def activity(**values):
    facts, ids = financial_dataset()
    rows, evidence = calculate_activity(
        facts,
        uuid.uuid4(),
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            **values,
        },
        financial_manifest(facts).control,
    )
    return rows, evidence["day_book"], ids


def test_distinct_document_journal_and_line_counts_and_full_result_totals():
    rows, summary, _ = activity()
    assert len(rows) == summary["voucher_count"] == summary["journal_count"] == 4
    assert summary["line_count"] == 8
    assert summary["debit"] == summary["credit"] == "460.0000"
    assert sum((Decimal(row["debit"]) for row in rows), Decimal(0)) == Decimal("460")
    assert all(len(row["journals"]) == 1 for row in rows)


def test_account_filter_selects_whole_journals_and_keeps_balanced_totals():
    facts, ids = financial_dataset()
    rows, evidence = calculate_activity(
        facts,
        uuid.uuid4(),
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "account_id": ids["party"],
        },
        financial_manifest(facts).control,
    )
    summary = evidence["day_book"]
    assert len(rows) == summary["voucher_count"] == 2
    assert summary["debit"] == summary["credit"] == "320.0000"
    assert summary["line_count"] == 4


def test_accounting_and_voucher_views_have_identical_summaries():
    rows, summary, _ = activity(mode="ACCOUNTING")
    _, voucher_summary, _ = activity()
    assert summary == voucher_summary
    assert len(rows) == 8
    assert all(row["account_name"] for row in rows)


@pytest.mark.parametrize(
    "values,count",
    [
        ({"kinds": ["RECEIPT"]}, 1),
        ({"amount_min": "100", "amount_max": "120"}, 2),
        ({"q": "no match"}, 0),
        ({"sort": "number", "group_by": "none"}, 4),
        ({"sort": "-amount", "group_by": "kind"}, 4),
        ({"basis": "TRANSACTION", "currency": "INR", "group_by": "particulars"}, 4),
        ({"amount_min": "461"}, 0),
        ({"amount_max": "39"}, 0),
        ({"type_revision_ids": [str(uuid.uuid4())]}, 0),
        ({"conditions": [{"field": "kind", "operator": "not_contains", "value": "MANUAL"}]}, 3),
        ({"conditions": [{"field": "kind", "operator": "equals", "value": "RECEIPT"}]}, 1),
        (
            {
                "match": "ANY",
                "conditions": [
                    {"field": "kind", "operator": "equals", "value": "RECEIPT"},
                    {"field": "kind", "operator": "equals", "value": "OPENING"},
                ],
            },
            2,
        ),
    ],
)
def test_filters_apply_before_summary_and_grouping(values, count):
    rows, summary, _ = activity(**values)
    assert len(rows) == summary["voucher_count"] == count
    assert sum(item["count"] for item in summary["groups"].values()) == count


@pytest.mark.parametrize(
    "values",
    [
        {"amount_min": "2", "amount_max": "1"},
        {"amount_min": 1.2},
        {"basis": "TRANSACTION"},
        {"date_from": "2026-05-01"},
        {"conditions": [{"field": "secret", "value": "anything"}]},
        {"unexpected": True},
        {"kinds": [""]},
        {"date_to": "2040-04-01"},
    ],
)
def test_typed_filters_reject_invalid_or_unsupported_inputs(values):
    with pytest.raises(ValidationError):
        Parameters.model_validate({"date_from": "2026-04-01", "date_to": "2026-04-30", **values})


def test_new_definition_does_not_replace_retained_day_book():
    registry = catalog()
    assert registry.resolve("DAY_BOOK").definition.version == 5
    entry = registry.resolve("DAY_BOOK_ACTIVITY")
    assert entry.definition.version == 1
    assert {view.key for view in entry.definition.views} == {"default", "accounting"}
    assert entry.definition.parameter_schema_hash


def test_party_filter_keeps_complete_journals_and_unknown_account_has_no_matches():
    facts, _ = financial_dataset()
    party = str(next(row.source_id for row in facts if row.entity == "party"))
    rows, evidence = calculate_activity(
        facts,
        uuid.uuid4(),
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "party_id": party,
        },
        financial_manifest(facts).control,
    )
    assert len(rows) == 2
    assert evidence["day_book"]["debit"] == evidence["day_book"]["credit"] == "320.0000"
    assert activity(account_id=str(uuid.uuid4()))[0] == []


def test_newest_first_is_preserved_when_grouped_by_date():
    rows, _, _ = activity(sort="-date", group_by="date")
    assert [row["date"] for row in rows] == sorted((row["date"] for row in rows), reverse=True)


def test_search_matches_a_ledger_even_when_particulars_is_a_party_name():
    rows, _, _ = activity(q="income")
    assert len(rows) == 1
    assert rows[0]["number"] == "invoice"


def test_a_voucher_with_events_on_different_days_keeps_daily_totals_and_one_distinct_count():
    from fixtures import source

    facts, _ = financial_dataset()
    journals = [str(row.source_id) for row in facts if row.entity == "journal"]
    facts.append(
        source(
            "voucher_execution",
            uuid.uuid4(),
            {
                "voucher_id": str(uuid.uuid4()),
                "revision_id": str(uuid.uuid4()),
                "execution_id": str(uuid.uuid4()),
                "request_hash": "a" * 64,
                "kind": "JOURNAL",
                "profile": "STANDARD",
                "result": {
                    "outcome": "COMMITTED",
                    "effects": [
                        {"effect_kind": "JOURNAL", "effect_id": journal} for journal in journals
                    ],
                },
            },
        )
    )
    rows, evidence = calculate_activity(
        facts,
        uuid.uuid4(),
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        },
        financial_manifest(facts).control,
    )
    summary = evidence["day_book"]
    assert len(rows) == 4
    assert summary["voucher_count"] == 1
    assert summary["activity_count"] == 4
    assert summary["groups"]["2026-04-02"]["debit"] == "200.0000"
    assert summary["by_kind"]["JOURNAL"]["count"] == 1
    assert len({row["id"] for row in rows}) == 4


def test_same_day_events_share_one_activity_row_and_keep_individual_journals():
    from fixtures import source

    facts, _ = financial_dataset()
    selected = [
        row
        for row in facts
        if row.entity == "journal" and row.data["number"] in {"opening", "invoice"}
    ]
    identities = {str(row.source_id) for row in selected}
    facts = [
        source(row.entity, row.source_id, row.data | {"posting_date": "2026-04-02"})
        if row.entity == "journal" and str(row.source_id) in identities
        else row
        for row in facts
    ]
    facts.append(
        source(
            "voucher_execution",
            uuid.uuid4(),
            {
                "voucher_id": str(uuid.uuid4()),
                "revision_id": str(uuid.uuid4()),
                "execution_id": str(uuid.uuid4()),
                "request_hash": "a" * 64,
                "kind": "JOURNAL",
                "profile": "STANDARD",
                "result": {
                    "outcome": "COMMITTED",
                    "effects": [
                        {"effect_kind": "JOURNAL", "effect_id": identity} for identity in identities
                    ],
                },
            },
        )
    )
    rows, evidence = calculate_activity(
        facts,
        uuid.uuid4(),
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
        },
        financial_manifest(facts).control,
    )
    combined = next(row for row in rows if row["journal_count"] == 2)
    assert combined["debit"] == combined["credit"] == "300.0000"
    assert len(combined["journals"]) == 2
    assert combined["line_count"] == 4
    assert evidence["day_book"]["activity_count"] == 3
    assert evidence["day_book"]["voucher_count"] == 3
    assert evidence["day_book"]["debit"] == "460.0000"


def test_export_context_retains_human_filters_and_all_result_totals():
    import json
    from pathlib import Path

    from billing_platform.display import DisplayConfiguration

    from reports.domain.day_book import export_metadata

    _, summary, _ = activity()
    parameters = Parameters.model_validate(
        {
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "kinds": ["PURCHASE", "RECEIPT"],
            "q": "equipment",
            "amount_min": "1",
            "amount_max": "200",
            "party_id": str(uuid.uuid4()),
            "account_id": str(uuid.uuid4()),
            "type_revision_ids": [str(uuid.uuid4())],
            "match": "ANY",
            "conditions": [
                {"field": "number", "operator": "contains", "value": "PUR"},
                {"field": "narration", "operator": "equals", "value": "Equipment"},
            ],
        }
    ).model_dump(mode="json")
    fixture = json.loads(
        (Path(__file__).parents[3] / "libs/platform/tests/fixtures/report-display.json").read_text(
            "utf-8"
        )
    )
    values = dict(export_metadata(parameters, summary, DisplayConfiguration(**fixture["config"])))
    assert values["Vouchers"] == "4"
    assert values["Total debit (INR)"] == "460.00"
    assert values["Voucher kinds"] == "PURCHASE, RECEIPT"
    assert values["Conditions"] == "Number contains PUR OR Narration equals Equipment"
    assert values["Party"] == "Selected party"
    assert values["Voucher type"] == "All selected type revisions"
    assert str(parameters["party_id"]) not in str(values)
