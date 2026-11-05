"""Money import rules with no database: parsing, kind/ledger rules, content and probes."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from vouchers.domain import import_checks as checks
from vouchers.domain import import_kinds as kinds
from vouchers.domain import import_money as money
from vouchers.domain.imports import AccountFacts, Master, OpenBill, Resolution, Staged

FACTS = {
    "BANK": AccountFacts("BANK", None, None, "MANUAL_ALLOWED", "INR"),
    "CASH": AccountFacts("CASH", None, None, "MANUAL_ALLOWED", None),
    "EXP": AccountFacts("GENERAL", None, None, "MANUAL_ALLOWED", None),
    "USD": AccountFacts("GENERAL", None, None, "MANUAL_ALLOWED", "USD"),
    "SUP": AccountFacts("PARTY", uuid.uuid4(), "SUPPLIER", None, None),
    "CUS": AccountFacts("PARTY", uuid.uuid4(), "CUSTOMER", None, None),
    "ODD": AccountFacts("PARTY", uuid.uuid4(), "OTHER", None, None),
}
IDS = {code: uuid.uuid4() for code in [*FACTS, "OLD"]}


def found(bills=None) -> Resolution:
    return Resolution(
        parties={}, gstin_parties={}, party_ids={}, party_ledgers={},
        accounts={code: Master(IDS[code], 1, "RETIRED" if code == "OLD" else "ACTIVE")
                  for code in IDS},
        account_facts={IDS[code]: facts for code, facts in FACTS.items()}
        | {IDS["OLD"]: FACTS["EXP"]},
        bills=bills or {},
    )


def doc(kind, *lines, header=None):
    shape = money.template(kind, frozenset())
    item = Staged("K", 1, {"document_date": "2026-10-10", "currency": "INR"} | (header or {}),
                  [dict(row, _row=str(n + 3), _sheet="lines") for n, row in enumerate(lines)],
                  [("vouchers", 3)])
    return money.parse(item, shape, kind)


def ln(no, account, side, amount="10", **extra):
    return {"line_no": str(no), "account_code": account, "side": side, "amount": amount} | extra


def codes(issues):
    return {issue.code for issue in issues}


def test_templates_follow_each_kind():
    def names(kind):
        shape = kinds.template(kind, frozenset(), ())
        return set(shape.names("header")) | set(shape.names("line"))

    assert {"purpose", "against_bill", "tender_mode"} <= names("PAYMENT")
    assert "tender_mode" not in names("JOURNAL") and "against_bill" not in names("JOURNAL")
    assert "tracking" not in names("CONTRA") and "purpose" not in names("CONTRA")
    with pytest.raises(PermissionError, match="financial"):
        kinds.template("PAYMENT", frozenset({"financial"}), ())
    with pytest.raises(ValueError):
        kinds.family("MEMORANDUM")
    assert kinds.required("RECEIPT") == money.REQUIRED_NATIVE
    assert kinds.label("CREDIT_NOTE") == "Credit Note"


def test_a_bank_reference_and_a_new_bill_due_date_are_optional():
    parsed, issues = doc("PAYMENT", ln(1, "SUP", "DEBIT", "10", tracking="NEW_REF",
                                       bill_reference="R1"),
                         ln(2, "BANK", "CREDIT", "10", tender_mode="UPI"))
    assert not issues, issues
    assert parsed.total == Decimal("10")
    masters, issues = money.resolve(parsed, found())
    assert not issues, issues
    body = money.content(parsed, masters, job_id=uuid.uuid4(), type_revision_id=uuid.uuid4(),
                         class_id=None, include=frozenset())
    account = body["financial"]["accounts"][0]
    assert account["bill_reference"] == "R1" and "due_date" not in account
    assert "reference" not in body["financial"]["tenders"][0]


def test_parse_checks_tender_evidence_tracking_and_balance():
    parsed, issues = doc("PAYMENT", ln(1, "EXP", "DEBIT", "10.5"),
                         ln(2, "BANK", "CREDIT", "10.5", tender_mode="NEFT",
                            tender_reference="UTR"))
    assert not issues and parsed.total == Decimal("10.5") and parsed.purpose == "GENERAL"
    _, issues = doc(
        "PAYMENT",
        ln(1, "EXP", "DEBIT", "0"),
        ln(1, "CASH", "CREDIT", tender_mode="CASH", tender_reference="X"),
        ln(3, "BANK", "CREDIT", tender_mode="UPI"),
        ln(4, "BANK", "CREDIT", tender_mode="CHEQUE", tender_reference="1"),
        ln(5, "BANK", "CREDIT", tender_reference="1"),
        ln(6, "SUP", "DEBIT", tracking="NEW_REF"),
        ln(7, "SUP", "DEBIT", tracking="ON_ACCOUNT", bill_reference="B"),
        ln(8, "SUP", "DEBIT", tracking="ADVANCE", against_bill="B"),
    )
    assert codes(issues) >= {
        "invalid_decimal", "invalid_line_no", "cash_has_no_instrument", "required",
        "invalid_choice", "tracking_conflict",
    }
    _, issues = doc("JOURNAL", ln(1, "EXP", "DEBIT"))
    assert codes(issues) == {"too_few_lines"}
    _, issues = doc("JOURNAL", ln(1, "EXP", "DEBIT", "2"), ln(2, "BANK", "CREDIT", "1"))
    assert codes(issues) == {"unbalanced"}
    settled, _ = doc("RECEIPT", ln(1, "BANK", "DEBIT", tender_mode="UPI", tender_reference="U"),
                     ln(2, "CUS", "CREDIT", against_bill="INV"))
    assert settled.purpose == "SETTLEMENT"
    contra, _ = doc("CONTRA", ln(1, "CASH", "DEBIT", tender_mode="CASH"),
                    ln(2, "BANK", "CREDIT", tender_mode="NEFT", tender_reference="N"))
    assert contra.purpose == "TRANSFER"


def test_ledger_and_party_rules():
    def check(kind, *lines, header=None, **options):
        parsed, issues = doc(kind, *lines, header=header)
        assert parsed is not None, issues
        return codes(money.resolve(parsed, found(), **options)[1])

    bank = {"tender_mode": "NEFT", "tender_reference": "N"}
    assert check("PAYMENT", ln(1, "NOPE", "DEBIT"), ln(2, "OLD", "CREDIT")) == {
        "unknown_master", "inactive_master"
    }
    assert check("PAYMENT", ln(1, "USD", "DEBIT"), ln(2, "BANK", "CREDIT", **bank)) == {
        "currency_mismatch"
    }
    assert check("PAYMENT", ln(1, "EXP", "DEBIT"), ln(2, "SUP", "CREDIT")) == {
        "cash_bank_required"
    }
    assert "tender_on_ledger" in check(
        "PAYMENT", ln(1, "EXP", "DEBIT", tender_mode="CASH"), ln(2, "CASH", "CREDIT",
                                                                tender_mode="CASH"))
    assert check("PAYMENT", ln(1, "ODD", "DEBIT"), ln(2, "BANK", "CREDIT", **bank)) == {
        "party_role"
    }
    assert check("PAYMENT", ln(1, "EXP", "DEBIT", tracking="ON_ACCOUNT"),
                 ln(2, "BANK", "CREDIT", **bank)) == {"tracking_not_allowed"}
    assert check("PAYMENT", ln(1, "EXP", "DEBIT", against_bill="B"),
                 ln(2, "BANK", "CREDIT", **bank)) == {"not_a_party"}
    advance = {"purpose": "ADVANCE"}
    assert check("PAYMENT", ln(1, "SUP", "DEBIT"), ln(2, "BANK", "CREDIT", **bank),
                 header=advance) == {"advance_tracking"}
    assert check("PAYMENT", ln(1, "CUS", "DEBIT", tracking="ADVANCE"),
                 ln(2, "BANK", "CREDIT", **bank), header=advance) == {"advance_role"}
    assert check("PAYMENT", ln(1, "SUP", "DEBIT"), ln(2, "BANK", "CREDIT", **bank),
                 header={"purpose": "REFUND"}) == {"refund_role"}
    assert check("PAYMENT", ln(1, "EXP", "DEBIT"), ln(2, "BANK", "CREDIT", **bank),
                 profile="ADVANCE") == {"advance_purpose_required"}
    # Journals carry no tenders, so cash/bank movements belong to Payment/Receipt/Contra.
    assert check("JOURNAL", ln(1, "EXP", "DEBIT"), ln(2, "BANK", "CREDIT")) == {
        "journal_cash_bank"
    }
    assert check("PAYMENT", ln(1, "EXP", "DEBIT"), ln(2, "BANK", "CREDIT", **bank),
                 header=advance) == {"party_required"}


def test_bills_content_and_probes():
    item = uuid.uuid4()
    # A supplier bill is a DEBT item; the supplier's own credit (e.g. a debit note) is not.
    bills = {(IDS["SUP"], "b-1"): (OpenBill(item, "DEBT", "INR", Decimal("4")),),
             (IDS["SUP"], "two"): (OpenBill(item, "DEBT", "INR", Decimal(1)),) * 2,
             (IDS["SUP"], "usd"): (OpenBill(item, "DEBT", "USD", Decimal(1)),),
             (IDS["SUP"], "credit"): (OpenBill(item, "CREDIT", "INR", Decimal(1)),)}
    cheque = {"tender_mode": "CHEQUE", "tender_reference": "000777",
              "instrument_date": "2026-10-09"}
    for reference, code in (("NONE", "unknown_bill"), ("TWO", "ambiguous_bill"),
                            ("USD", "currency_mismatch"), ("CREDIT", "wrong_bill_direction")):
        parsed, _ = doc("PAYMENT", ln(1, "SUP", "DEBIT", against_bill=reference),
                        ln(2, "BANK", "CREDIT", **cheque))
        assert codes(money.resolve(parsed, found(bills))[1]) == {code}
    parsed, _ = doc("PAYMENT", ln(1, "SUP", "DEBIT", against_bill="B-1"),
                    ln(2, "BANK", "CREDIT", **cheque), header={"narration": "Rent"})
    assert money.bill_requests(parsed, found(bills)) == {(IDS["SUP"], "B-1")}
    masters, issues = money.resolve(parsed, found(bills))
    assert not issues
    job = uuid.uuid4()
    body = money.content(parsed, masters, job_id=job, type_revision_id=uuid.uuid4(),
                         class_id=uuid.uuid4(), include=frozenset({"posting_date", "narration"}))
    allocation = body["financial"]["allocations"][0]
    assert allocation["debt"] == {"item_id": str(item)} and allocation["amount"] == "4.0000"
    assert body["financial"]["tenders"][0]["instrument_date"] == "2026-10-09"
    assert body["narration"] == "Rent" and "class_id" in body
    probes = money.probes(parsed, masters)
    leaf = next(p for p in probes if p["probe"] == "instrument")
    # Our own cheque leaf: the number alone identifies it on the bank ledger.
    assert leaf["group"] == "CHEQUE" and leaf["date"] is None
    assert any(p["probe"] == "allocation" for p in probes)
    received, _ = doc("RECEIPT", ln(1, "BANK", "DEBIT", "7", **cheque),
                      ln(2, "EXP", "CREDIT", "7"))
    masters, _ = money.resolve(received, found())
    drawer = money.probes(received, masters)[0]
    assert drawer["date"] == "2026-10-09" and drawer["value"] == "7.0000"
    textual = money.file_identities(received)
    assert textual[0][0][-2:] == ("2026-10-09", "7.0000")
    new_ref, _ = doc("PAYMENT", ln(1, "SUP", "DEBIT", tracking="NEW_REF", bill_reference="R",
                                   due_date="2026-11-01"),
                     ln(2, "CASH", "CREDIT", tender_mode="CASH"))
    masters, _ = money.resolve(new_ref, found())
    body = money.content(new_ref, masters, job_id=job, type_revision_id=uuid.uuid4(),
                         class_id=None, include=frozenset())
    assert body["financial"]["accounts"][0]["due_date"] == "2026-11-01"
    assert [p["probe"] for p in money.probes(new_ref, masters)] == ["signature"]


def test_job_collisions_identity_and_consumption():
    # Each row is checked at a different instant but still consumes the same bill balance.
    first = checks.probe("allocation", "error", item_id="b", amount="6", remaining="10",
                         checked_at="2026-10-15T10:00:00+00:00")
    second = checks.probe("allocation", "error", item_id="b", amount="5", remaining="10",
                          checked_at="2026-10-15T10:00:01+00:00")
    utr = checks.probe("instrument", "error", account_id="a", group="ELECTRONIC",
                       reference="x", side=None, date=None, value=None)
    found_ = checks.within([("A", [first, utr]), ("B", [second, dict(utr)])])
    assert [item["probe"] for item, _ in found_["B"]] == ["allocation", "instrument"]
    assert found_["B"][1][1] == "A"
    assert checks.column(utr) == "tender_reference"
    assert checks.message(first)[0] == "exceeds_outstanding"
    with pytest.raises(ValueError):
        checks.probe("nonsense", "error")
    assert checks.signature([("a", "DEBIT", Decimal("1.5"))]) == [["a", "DEBIT", "1.5000"]]
    assert dt.date(2026, 1, 1).isoformat() == "2026-01-01"
