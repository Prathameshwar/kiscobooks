from reports.domain.book_summaries import summarize


def test_day_book_counts_all_rows_but_totals_only_current_movements():
    rows = [
        {"period": "CURRENT", "currency": "INR", "debit": "10.0001", "credit": "0.0000"},
        {"period": "CURRENT", "currency": "INR", "debit": "0.0000", "credit": "10.0001"},
        {"period": "COMPARATIVE", "currency": "USD", "debit": "99.0000", "credit": "0.0000"},
    ]
    assert summarize("DAY_BOOK", rows) == {
        "code": "DAY_BOOK",
        "record_count": 3,
        "entry_count": 2,
        "amounts": {"INR": {"debit": "10.0001", "credit": "10.0001"}},
    }


def test_ledger_summary_excludes_opening_and_comparative_turnover_but_keeps_closing():
    rows = [
        {
            "period": "CURRENT",
            "row_kind": "OPENING",
            "account_id": "cash",
            "currency": "INR",
            "balance": "100.0000",
        },
        {
            "period": "CURRENT",
            "row_kind": "ENTRY",
            "account_id": "cash",
            "currency": "INR",
            "debit": "50.0000",
            "credit": "0.0000",
            "balance": "150.0000",
        },
        {
            "period": "CURRENT",
            "row_kind": "OPENING",
            "account_id": "petty",
            "currency": "INR",
            "balance": "20.0000",
        },
        {
            "period": "COMPARATIVE",
            "row_kind": "ENTRY",
            "account_id": "cash",
            "currency": "INR",
            "debit": "999.0000",
            "credit": "0.0000",
            "balance": "999.0000",
        },
    ]
    assert summarize("CASH_BOOK", rows) == {
        "code": "CASH_BOOK",
        "record_count": 4,
        "entry_count": 1,
        "amounts": {"INR": {"debit": "50.0000", "credit": "0.0000", "closing": "170.0000"}},
    }


def test_invoice_summary_nets_returns_without_combining_currencies():
    rows = [
        {
            "row_kind": "INVOICE",
            "currency": "INR",
            "direction": "ORIGINAL",
            "commercial_total": "100.0000",
            "tax_total": "18.0000",
            "payable": "118.0000",
        },
        {
            "row_kind": "INVOICE",
            "currency": "INR",
            "direction": "REDUCTION",
            "commercial_total": "20.0000",
            "tax_total": "3.6000",
            "payable": "23.6000",
        },
        {
            "row_kind": "INVOICE",
            "currency": "USD",
            "direction": "ORIGINAL",
            "commercial_total": "10.0000",
            "tax_total": "0.0000",
            "payable": "10.0000",
        },
        {
            "row_kind": "COMPONENT",
            "currency": "INR",
            "commercial_total": "999.0000",
            "tax_total": "999.0000",
            "payable": "999.0000",
        },
    ]
    result = summarize("SALES_REGISTER", rows)
    assert (
        result is not None
        and result["record_count"] == 4
        and result["entry_count"] == 3
        and result["reduction_count"] == 1
    )
    assert result["amounts"] == {
        "INR": {"commercial_total": "80.0000", "payable": "94.4000", "tax_total": "14.4000"},
        "USD": {"commercial_total": "10.0000", "payable": "10.0000", "tax_total": "0.0000"},
    }


def test_tender_summary_counts_vouchers_tenders_instruments_and_exact_amounts():
    rows = [
        {"journal_id": "one", "instrument_id": "cheque", "currency": "INR", "amount": "70.0000", "signed_amount": "-70.0000"},
        {"journal_id": "one", "instrument_id": None, "currency": "INR", "amount": "30.0000", "signed_amount": "-30.0000"},
        {"journal_id": "two", "instrument_id": None, "currency": "INR", "amount": "25.0000", "signed_amount": "-25.0000"},
    ]
    assert summarize("PAYMENT_REGISTER", rows) == {
        "code": "PAYMENT_REGISTER",
        "record_count": 3,
        "entry_count": 3,
        "voucher_count": 2,
        "instrument_count": 1,
        "amounts": {"INR": {"amount": "125.0000"}},
    }


def test_stock_summary_excludes_openings_from_movement_and_sums_position_closings():
    rows = [
        {"row_kind": "OPENING", "position_id": "a", "unit": "PCS", "balance": "10.0000"},
        {
            "row_kind": "MOVEMENT",
            "position_id": "a",
            "unit": "PCS",
            "inward": "5.0000",
            "outward": "0.0000",
            "balance": "15.0000",
        },
        {"row_kind": "OPENING", "position_id": "b", "unit": "PCS", "balance": "2.0000"},
    ]
    assert summarize("ITEM_LEDGER", rows) == {
        "code": "ITEM_LEDGER",
        "record_count": 3,
        "entry_count": 1,
        "amounts": {},
        "quantities": {"inward": "5.0000", "outward": "0.0000", "closing": "17.0000"},
        "unit": "PCS",
    }
