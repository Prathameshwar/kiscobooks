"""Purchase import rules with no database: template, grouping, lexical parsing, resolution."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from vouchers.domain import imports as rules
from vouchers.schemas.documents import VoucherInput

SHAPE = rules.template(frozenset(), [rules.CustomColumn("cf_project", "text")])
OPTIONAL = frozenset({"narration", "posting_date", "references", "class_id"})
LEAN = rules.template(OPTIONAL)


def header(**changes):
    return {
        "import_key": "A",
        "document_date": "2026-10-10",
        "supplier_code": "SUP-1",
        "supplier_invoice_number": "INV-1",
        "supplier_invoice_date": "2026-10-09",
        "currency": "INR",
        "tax_profile": "UNTAXED_ACCOUNT",
        "supplier_declared_total": "100",
    } | changes


def line(**changes):
    return {
        "import_key": "A", "line_no": "1", "supply_kind": "SERVICE", "account_code": "EXP",
        "description": "Rent", "amount": "100", "_row": "3", "_sheet": "lines",
    } | changes


def staged(head=None, lines=None):
    return rules.Staged("A", 1, head or header(), lines or [line()], [("vouchers", 3)])


def codes(issues):
    return {(issue.column, issue.code) for issue in issues}


def test_template_respects_denied_fields_and_lists_instructions():
    assert "narration" in SHAPE.names("header") and "cf.cf_project" in SHAPE.names("header")
    assert "narration" not in LEAN.names("header") and "posting_date" not in LEAN.flat()
    assert LEAN.flat().count("import_key") == 1
    with pytest.raises(PermissionError, match="invoice"):
        rules.template(frozenset({"invoice"}))
    guide = rules.instructions(SHAPE)
    assert ["vouchers.cf.cf_project", "no", "Custom field (text)"] in guide
    assert ["vouchers.import_key", "yes", "Unique voucher key within this file"] in guide
    head, lines = rules.examples(SHAPE)
    assert head[0][0] == "PB-0001" and lines[0][1] == "1"
    assert len(rules.flat_examples(SHAPE)[0]) == len(SHAPE.flat())


def test_sheet_grouping_rejects_structure_and_orphans():
    names = {"vouchers": SHAPE.names("header"), "lines": SHAPE.names("line")}
    _, issues = rules.group_sheets({}, {"vouchers": ["import_key"], "extra": ["x"]}, SHAPE)
    assert codes(issues) >= {(None, "unknown_sheet"), (None, "missing_sheet")}
    _, issues = rules.group_sheets({}, {**names, "vouchers": ["bogus"]}, SHAPE)
    assert ("bogus", "unknown_column") in codes(issues)
    tables = {
        "vouchers": [(3, header()), (4, header()), (5, header(import_key="B"))],
        "lines": [(3, line()), (4, line(import_key="ZZ"))],
    }
    result, issues = rules.group_sheets(tables, names, SHAPE)
    assert ("import_key", "orphan_line") in codes(issues)
    first, second = result
    assert ("import_key", "duplicate_import_key") in codes(first.issues)
    assert (None, "no_lines") in codes(second.issues)
    assert first.rows == [("vouchers", 3), ("lines", 3)]


def test_flat_grouping_requires_agreeing_header_columns():
    names = SHAPE.flat()
    rows = [(3, header() | line()), (4, header(currency="USD") | line(line_no="2"))]
    result, issues = rules.group_flat(rows, names, SHAPE)
    assert not issues
    assert ("currency", "header_mismatch") in codes(result[0].issues)
    assert len(result[0].lines) == 2
    _, issues = rules.group_flat([], ["import_key", "x"], SHAPE)
    assert ("x", "unknown_column") in codes(issues)
    _, issues = rules.group_flat([], [], SHAPE)
    assert (None, "empty_file") in codes(issues)


def test_json_grouping_requires_text_and_template_fields():
    _, issues = rules.group_json([], SHAPE)
    assert (None, "invalid_document") in codes(issues)
    document = {"schema_version": 1, "vouchers": [
        header() | {"lines": [{"line_no": "1", "supply_kind": "SERVICE", "account_code": "E",
                               "description": "d", "amount": "1"}]},
        header() | {"lines": []},
        "bad",
        header(import_key="C", supplier_declared_total=1) | {"lines": []},
        header(import_key="D") | {"lines": [{"unknown": "x"}]},
    ]}
    result, issues = rules.group_json(document, SHAPE)
    assert [item.import_key for item in result] == ["A"]
    assert ("import_key", "duplicate_import_key") in codes(result[0].issues)
    assert len([issue for issue in issues if issue.code == "invalid_voucher"]) == 3


def test_bounds_on_keys_lines_and_vouchers():
    many = [rules.Staged(str(n), n, header(), [line()], [("CSV", n)]) for n in range(501)]
    _, issues = rules._bounded(many, [])
    assert (None, "too_many_vouchers") in codes(issues)
    item = rules.Staged("bad key!", 1, header(), [line()] * 201, [("CSV", 3)])
    rules._bounded([item], [])
    assert codes(item.issues) >= {("import_key", "invalid_import_key"), (None, "too_many_lines")}


def test_parse_is_exact_and_never_coerces():
    parsed, issues = rules.parse(
        staged(header(**{"cf.cf_project": "Alpha", "narration": "Rent bill"}),
               [line(line_no="2", amount="10.5"), line(discount_pct="5")]),
        SHAPE,
    )
    assert not issues and parsed is not None
    assert [row.line_no for row in parsed.lines] == [1, 2]
    assert parsed.lines[1].amount == Decimal("10.5") and parsed.custom == {"cf_project": "Alpha"}
    assert parsed.posting_date == parsed.document_date == dt.date(2026, 10, 10)
    bad = header(
        document_date="10/10/2026", supplier_gstin="27ABCDE1234F1Z5", currency="inr",
        exchange_rate="0", supplier_declared_total="1e3", narration="x\x01",
        tax_profile="VAT", place_of_supply="MH",
    )
    _, issues = rules.parse(
        staged(bad, [
            line(supply_kind="GOODS", amount="0.12345"),
            line(supply_kind="ITEM", discount_pct="101", discount_amount="1"),
            line(line_no="0", account_code="", description="x" * 1001),
        ]),
        SHAPE,
    )
    assert codes(issues) >= {
        ("document_date", "invalid_date"),
        ("supplier_code", "supplier_required"),
        ("currency", "invalid_format"),
        ("exchange_rate", "invalid_decimal"),
        ("supplier_declared_total", "invalid_decimal"),
        ("narration", "invalid_text"),
        ("tax_profile", "invalid_choice"),
        ("place_of_supply", "invalid_format"),
        ("supply_kind", "unsupported_supply_kind"),
        ("supply_kind", "invalid_choice"),
        ("amount", "invalid_decimal"),
        ("discount_pct", "invalid_decimal"),
        ("discount_amount", "discount_conflict"),
        ("line_no", "invalid_format"),
        ("description", "invalid_text"),
    }
    _, issues = rules.parse(
        staged(header(supplier_code=None) | {"supplier_code": ""}, [line(), line()]), LEAN
    )
    assert ("line_no", "invalid_line_no") in codes(issues)
    missing = {key: value for key, value in header().items() if key != "supplier_code"}
    _, issues = rules.parse(staged(missing | {"supplier_invoice_number": ""}), LEAN)
    assert codes(issues) >= {("supplier_code", "supplier_required")}


def test_custom_cells_are_typed_for_the_native_validator():
    assert rules.custom_value("integer", "-12") == -12
    assert rules.custom_value("boolean", "Yes") is True
    assert rules.custom_value("boolean", "0") is False
    assert rules.custom_value("multi_select", "a| b |") == ["a", "b"]
    assert rules.custom_value("currency_amount", "10.00 INR") == {
        "amount": "10.00", "currency": "INR"
    }
    assert rules.custom_value("date", "2026-01-01") == "2026-01-01"
    for kind, value in (("integer", "1.5"), ("boolean", "maybe"), ("auto_number", "1")):
        with pytest.raises(ValueError):
            rules.custom_value(kind, value)
    shape = rules.template(frozenset(), [rules.CustomColumn("cf_count", "integer")])
    _, issues = rules.parse(staged(header(**{"cf.cf_count": "x"})), shape)
    assert ("cf.cf_count", "invalid_custom_field") in codes(issues)


def found(**changes):
    party, ledger, account = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    active = rules.Master
    base = {
        "parties": {"SUP-1": active(party, 2, "ACTIVE")},
        "gstin_parties": {"27ABCDE1234F1Z5": (party,)},
        "party_ids": {party: active(party, 2, "ACTIVE")},
        "party_ledgers": {party: (("SUP-1-L", active(ledger, 3, "ACTIVE")),)},
        "accounts": {"EXP": active(account, 4, "ACTIVE")},
    }
    return rules.Resolution(**(base | changes)), party, ledger, account


def parsed(**head):
    result, issues = rules.parse(staged(header(**head)), SHAPE)
    assert result is not None, issues
    return result


def variant(resolution, **changes):
    fields = {name: getattr(resolution, name) for name in (
        "parties", "gstin_parties", "party_ids", "party_ledgers", "accounts"
    )}
    return rules.Resolution(**(fields | changes))


def gstin_bill():
    head = {k: v for k, v in header(supplier_gstin="27ABCDE1234F1Z5").items()
            if k != "supplier_code"}
    result = rules.parse(staged(head), SHAPE)[0]
    assert result is not None
    return result


def test_resolution_is_exact_active_and_unambiguous():
    resolution, party, ledger, _ = found()
    masters, issues = rules.resolve(parsed(), resolution, "vouchers", 3)
    assert not issues and masters["party"][0] == party and masters["ledger"].source_id == ledger
    assert rules.resolve(gstin_bill(), resolution, "v", 3)[0]["party"][0] == party
    other = uuid.uuid4()
    two = {party: (("L1", rules.Master(ledger, 1, "ACTIVE")),
                   ("L2", rules.Master(other, 1, "ACTIVE")))}
    for changes, column, code in (
        ({"parties": {}}, "supplier_code", "unknown_master"),
        ({"parties": {"SUP-1": rules.Master(party, 2, "RETIRED")}}, "supplier_code",
         "inactive_master"),
        ({"party_ledgers": {}}, "supplier_ledger_code", "unknown_master"),
        ({"party_ledgers": two}, "supplier_ledger_code", "ambiguous_master"),
        ({"accounts": {}}, "account_code", "unknown_master"),
        ({"accounts": {"EXP": rules.Master(other, 1, "RETIRED")}}, "account_code",
         "inactive_master"),
    ):
        _, issues = rules.resolve(parsed(), variant(resolution, **changes), "v", 3)
        assert (column, code) in codes(issues), (changes, issues)
    masters, issues = rules.resolve(
        parsed(supplier_ledger_code="L2"), variant(resolution, party_ledgers=two), "v", 3
    )
    assert not issues and masters["ledger"].source_id == other
    for gstins, code in (({"27ABCDE1234F1Z5": (party, other)}, "ambiguous_master"),
                         ({}, "unknown_master")):
        broken = variant(resolution, gstin_parties=gstins)
        assert ("supplier_gstin", code) in codes(rules.resolve(gstin_bill(), broken, "v", 3)[1])


def test_content_is_native_deterministic_and_respects_field_policy():
    resolution, party, ledger, account = found()
    job = uuid.uuid4()
    item = rules.parse(
        staged(header(narration="Note", due_date="2026-11-01", place_of_supply="IN-MH",
                      exchange_rate="1.25", supplier_difference_reason="Rounding"),
               [line(discount_pct="5"), line(line_no="2", discount_amount="2")]),
        SHAPE,
    )[0]
    masters = rules.resolve(item, resolution, "v", 3)[0]
    revision, klass = uuid.uuid4(), uuid.uuid4()
    body = rules.content(item, masters, job_id=job, type_revision_id=revision, class_id=klass,
                         payment_days=30, include=OPTIONAL)
    native = VoucherInput.model_validate(body)
    assert native.invoice is not None and native.invoice.party_account_id == ledger
    assert native.parties[0].party_id == party and native.parties[0].source_version == 2
    assert native.invoice.supplies[0].account_id == account
    assert [c.input_kind for c in native.invoice.components] == ["PERCENT", "FIXED"]
    assert native.invoice.due_date == dt.date(2026, 11, 1)
    assert native.references[0].reference == "INV-1" and native.narration == "Note"
    assert native.class_id == klass and native.posting_date == dt.date(2026, 10, 10)
    again = rules.content(item, masters, job_id=job, type_revision_id=revision, class_id=klass,
                          payment_days=30, include=OPTIONAL)
    assert again == body
    plain = rules.parse(staged(), SHAPE)[0]
    lean = rules.content(plain, rules.resolve(plain, resolution, "v", 3)[0], job_id=job,
                         type_revision_id=revision, class_id=None, payment_days=30,
                         include=frozenset())
    assert {"posting_date", "references", "narration", "class_id"}.isdisjoint(lean)
    assert lean["invoice"]["due_date"] == "2026-11-08"


def test_control_total_classification():
    state, difference, issue = rules.control(Decimal("100"), Decimal("100"), Decimal(1), None)
    assert (state, difference, issue) == ("VALID", Decimal(0), None)
    state, difference, issue = rules.control(Decimal("100.5"), Decimal("100"), Decimal(1), "r")
    assert state == "WARNING" and difference == Decimal("0.5") and issue is None
    state, _, issue = rules.control(Decimal("100.5"), Decimal("100"), Decimal(1), None)
    assert state == "INVALID" and issue.code == "difference_reason_required"
    state, _, issue = rules.control(Decimal("90"), Decimal("100"), Decimal(1), "r", row=7)
    assert state == "INVALID" and issue.code == "supplier_total_mismatch" and issue.row == 7


def test_duplicate_rules_match_number_and_date_optionally_with_supplier():
    bill = parsed(supplier_invoice_number=" Inv-1 ")
    assert rules.duplicate_identity(bill, "DATE_NUMBER") == ("inv-1", "2026-10-09")
    assert rules.duplicate_identity(bill, "DATE_NUMBER_PARTY") == (
        "inv-1", "2026-10-09", "party:code:SUP-1"
    )
    ledger = parsed(supplier_ledger_code="L-2")
    assert rules.duplicate_identity(ledger, "DATE_NUMBER_ACCOUNT")[-1] == "account:code:SUP-1/l-2"
    other_day = parsed(supplier_invoice_date="2026-10-08")
    assert rules.duplicate_identity(other_day, "DATE_NUMBER") != rules.duplicate_identity(
        parsed(), "DATE_NUMBER"
    )
    assert rules.bill_key("DATE_NUMBER_ACCOUNT", "A", dt.date(2026, 1, 1), party="p",
                          account="x") == ("a", "2026-01-01", "account:x")
    with pytest.raises(ValueError, match="duplicate rule"):
        rules.bill_key("FISCAL_YEAR", "A", dt.date(2026, 1, 1), party=None, account=None)


def test_import_keys_collide_case_insensitively_and_reject_double_dots():
    names = {"vouchers": SHAPE.names("header"), "lines": SHAPE.names("line")}
    tables = {"vouchers": [(3, header()), (4, header(import_key="a"))], "lines": [(3, line())]}
    result, _ = rules.group_sheets(tables, names, SHAPE)
    assert ("import_key", "duplicate_import_key") in codes(result[0].issues)
    item = rules.Staged("a..b", 1, header(), [line()], [("CSV", 3)])
    rules._bounded([item], [])
    assert ("import_key", "invalid_import_key") in codes(item.issues)


def test_live_shape_refuses_columns_denied_after_upload():
    item = staged(header(narration="Late"))
    assert ("narration", "unknown_column") in codes(rules.unexpected(item, LEAN))
    assert not rules.unexpected(staged(), LEAN)
