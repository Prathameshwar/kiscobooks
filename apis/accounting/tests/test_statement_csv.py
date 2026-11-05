"""B43 mapped CSV evidence stays outside Accounting financial posting."""

from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from accounting.domain.statement_csv import CsvMapping, parse_statement


def mapping() -> CsvMapping:
    return CsvMapping(uuid7(), "INR", "Date", "Debit", "Credit", "Ref", "Narration", "ID")


def test_mapped_csv_normalizes_exact_rows_and_preserves_bank_identity():
    raw = (
        b"Date,Debit,Credit,Ref,Narration,ID\n"
        b"2025-04-01,12.34,,R1,Charge,T1\n"
        b"2025-04-02,,20,R2,Receipt,T2\n"
    )
    result = parse_statement(raw, mapping())
    assert len(result.rows) == 2
    assert [(row.side, row.amount) for row in result.rows] == [
        ("DEBIT", Decimal("12.3400")),
        ("CREDIT", Decimal("20.0000")),
    ]
    assert all(not row.needs_duplicate_review for row in result.rows)
    assert result.rows[0].row_sha256 != result.rows[1].row_sha256


def test_no_transaction_id_requires_duplicate_review_not_silent_deduplication():
    item = replace(mapping(), transaction_id_column=None)
    raw = b"Date,Debit,Credit,Ref,Narration\n2025-04-01,,20,R2,Receipt\n"
    assert parse_statement(raw, item).rows[0].needs_duplicate_review


@pytest.mark.parametrize(
    "row",
    [
        b"2025-04-01,1,2,R,Text,T1",
        b"2025-04-01,,,R,Text,T1",
        b"2025-04-01,-1,,R,Text,T1",
        b"2025-04-01,1.00001,,R,Text,T1",
        b"2025-04-01,1,,R,=CMD(),T1",
        b"2025-04-01,1,,R,Text,T1,EXTRA",
    ],
)
def test_ambiguous_or_unsafe_rows_are_refused(row: bytes):
    with pytest.raises(ValidationFailedError):
        parse_statement(b"Date,Debit,Credit,Ref,Narration,ID\n" + row + b"\n", mapping())


def test_duplicate_headers_and_missing_columns_are_refused():
    with pytest.raises(ValidationFailedError, match="unique"):
        parse_statement(b"Date,Debit,Debit,Ref,Narration,ID\n", mapping())
    with pytest.raises(ValidationFailedError, match="missing column"):
        parse_statement(b"Date,Debit,Credit,Ref,Narration\n2025-04-01,1,,R,Text\n", mapping())
    with pytest.raises(ValidationFailedError, match="duplicate bank transaction ID"):
        parse_statement(
            b"Date,Debit,Credit,Ref,Narration,ID\n"
            b"2025-04-01,1,,R1,One,T1\n2025-04-02,,2,R2,Two,T1\n",
            mapping(),
        )


def test_formula_in_unmapped_column_is_refused_before_storage_or_export():
    raw = (
        b"Date,Debit,Credit,Ref,Narration,ID,Extra\n"
        b'2025-04-01,1,,R,Text,T1,=HYPERLINK(""https://example.com"")\n'
    )
    with pytest.raises(ValidationFailedError, match="formula-like"):
        parse_statement(raw, mapping())


def test_non_ascii_currency_is_refused():
    with pytest.raises(ValidationFailedError, match="currency"):
        parse_statement(
            b"Date,Debit,Credit,Ref,Narration,ID\n2025-04-01,1,,R,Text,T1\n",
            replace(mapping(), currency="\u0130NR"),
        )


def test_blank_line_does_not_shift_source_line_number():
    raw = (
        b"Date,Debit,Credit,Ref,Narration,ID\n"
        b"2025-04-01,1,,R,Text,T1\n"
        b"\n"
        b"2025-04-02,,2,R2,Text,T2\n"
    )
    result = parse_statement(raw, mapping())
    assert [row.line_number for row in result.rows] == [2, 4]


def test_mapped_currency_account_and_running_balance_are_preserved():
    item = replace(
        mapping(),
        currency_column="Currency",
        account_column="Account",
        account_value="XX1234",
        balance_column="Balance",
    )
    raw = (
        b"Date,Debit,Credit,Ref,Narration,ID,Currency,Account,Balance\n"
        b"2025-04-01,12,,R,Charge,T1,INR,XX1234,-12\n"
    )
    result = parse_statement(raw, item)
    assert result.rows[0].running_balance == Decimal("-12.0000")
    with pytest.raises(ValidationFailedError, match="currencies"):
        parse_statement(raw.replace(b",INR,", b",USD,"), item)
    with pytest.raises(ValidationFailedError, match="accounts"):
        parse_statement(raw.replace(b",XX1234,", b",XX9999,"), item)
