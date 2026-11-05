import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ConflictError
from fixtures import dataset, manifest, source
from reporting_contract.contract import Fact

from reports.domain.reconcile import immutable_claim, reconcile
from reports.tasks.runs import spreadsheet


def changed(items, entity, **updates):
    old = next(row for row in items if row.entity == entity)
    return [
        source(row.entity, row.source_id, row.data | updates)
        if row.source_id == old.source_id
        else row
        for row in items
    ]


def test_exact_projection_grains_and_hashes():
    items = dataset()
    lines, summaries, evidence = reconcile(items, manifest(items).control)
    assert len(lines) == 2 and len(summaries) == 2
    assert all(type(row["base_amount"]) is Decimal for row in lines)
    assert {row["grain"] for row in summaries} == {"DAY", "MONTH"}
    assert all(row["debit"] == row["credit"] == Decimal("100.0000") for row in summaries)
    journals = {str(row.source_id): row.data for row in items if row.entity == "journal"}
    assert sum(immutable_claim(row, journals) is not None for row in items) == 3
    assert immutable_claim(source("account", uuid.uuid4(), None), journals) is None
    bad = items[0].model_dump(mode="json")
    bad["content_hash"] = "0" * 64
    with pytest.raises(ValueError):
        Fact.model_validate(bad)
    with pytest.raises(ValueError):
        manifest(items).model_validate(manifest(items).model_dump() | {"schema_hash": "0" * 64})


@pytest.mark.parametrize(
    "entity,updates",
    [
        ("account", {"group_id": str(uuid.uuid4())}),
        ("account_group", {"head_id": str(uuid.uuid4())}),
        ("journal", {"fiscal_period_id": str(uuid.uuid4())}),
        ("journal", {"posting_date": "2026-03-31"}),
        ("journal", {"posting_date": "2026-05-01"}),
        ("journal", {"base_currency": "USD"}),
        ("journal", {"total_debit": "101.0000"}),
        ("journal", {"total_credit": "101.0000"}),
        ("journal_line", {"account_id": str(uuid.uuid4())}),
        ("journal_line", {"journal_id": str(uuid.uuid4())}),
        ("journal_line", {"base_amount": "99.0000"}),
        ("fiscal_period", {"fiscal_year_id": str(uuid.uuid4())}),
    ],
)
def test_missing_or_conflicting_financial_inputs_block_readiness(entity, updates):
    items = changed(dataset(), entity, **updates)
    with pytest.raises(ConflictError):
        reconcile(items, manifest(items).control)


def test_counts_coverage_cycles_duplicates_and_control_totals_fail_closed():
    items = dataset()
    control = manifest(items).control
    with pytest.raises(ConflictError):
        reconcile(items + items[:1], control)
    with pytest.raises(ConflictError):
        reconcile(items[:-1], control)
    with pytest.raises(ConflictError):
        reconcile(items, control.model_copy(update={"coverage_start": None}))
    with pytest.raises(ConflictError):
        reconcile(items, control.model_copy(update={"base_totals": {}}))
    group = next(row for row in items if row.entity == "account_group")
    loop = changed(items, "account_group", parent_id=str(group.source_id))
    with pytest.raises(ConflictError):
        reconcile(loop, manifest(loop).control)
    draft = changed(items, "journal", status="DRAFT")
    journals = {str(row.source_id): row.data for row in draft if row.entity == "journal"}
    assert all(immutable_claim(row, journals) is None for row in draft)
    _, summary, _ = reconcile(draft, manifest(draft).control.model_copy(update={"base_totals": {}}))
    assert summary == []


@pytest.mark.parametrize("value", ["=1+1", " +SUM(1)", "-1", "@lookup", "\tformula", "\nformula"])
def test_csv_formula_prefix_is_escaped(value):
    assert spreadsheet(value).startswith("'")


def test_csv_normal_text_and_exact_string_are_preserved():
    assert spreadsheet("Assets") == "Assets" and spreadsheet("100.0000") == "100.0000"


def test_opening_settlement_and_classification_history_remain_separate_from_gl():
    from fixtures import settlement_dataset

    rows = settlement_dataset()
    group = next(row for row in rows if row.entity == "account_group")
    child = source(
        "account_group",
        uuid.uuid4(),
        group.data | {"parent_id": str(group.source_id), "code": "CHILD"},
    )
    rows.append(child)
    rows = changed(rows, "account", group_id=str(child.source_id))
    lines, _, proof = reconcile(rows, manifest(rows).control)
    assert len(lines) == 2 and proof["counts"]["allocation"] == 1
    journals = {str(row.source_id): row.data for row in rows if row.entity == "journal"}
    allocation = next(row for row in rows if row.entity == "allocation")
    reversed_item = source(
        "allocation", allocation.source_id, allocation.data | {"reversal_date": "2026-04-03"}
    )
    assert immutable_claim(allocation, journals) == immutable_claim(reversed_item, journals)
    for entity, changes in (
        ("open_item", {"party_id": str(uuid.uuid4())}),
        ("allocation", {"currency": "USD"}),
        ("opening_batch", {"journal_id": str(uuid.uuid4())}),
        ("source_document", {"journal_id": str(uuid.uuid4())}),
    ):
        broken = changed(rows, entity, **changes)
        with pytest.raises(ConflictError):
            reconcile(broken, manifest(broken).control)


def test_fx_component_can_have_zero_transaction_amount():
    from reporting_contract.contract import Line

    item = next(row for row in dataset() if row.entity == "journal_line")
    result = Line.model_validate(
        item.data
        | {"component": "FX", "amount": "0.0000", "party_id": str(uuid.uuid4()), "role": "CUSTOMER"}
    )
    assert result.amount == "0.0000" and result.base_amount == "100.0000"
