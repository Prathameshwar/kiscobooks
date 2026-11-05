"""Payment, Receipt, Contra and Journal imports: balanced ledger entries with bank evidence.

Each voucher is header + entry rows. Kind rules mirror what the Accounting owner enforces at
posting, so a file is told about them at validation instead of at posting:

- Payment pays out: its cash/bank lines are credits. Receipt takes in: they are debits.
- Contra moves money between the company's own cash/bank ledgers only.
- Journal uses no cash/bank ledger unless the type allows it, and carries no tenders.
- Every cash/bank line carries exactly one tender; CASH only on a cash ledger.
- Party ledgers are tracked (on account, new reference, advance, or against a bill);
  other ledgers are not, and must accept manual entries.
- An advance names the right party role; a refund the opposite one.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from vouchers.domain import import_checks as checks
from vouchers.domain.imports import (
    CODE,
    COMMON_HEAD,
    MAX_LINES,
    NARRATION,
    AccountFacts,
    Column,
    CustomColumn,
    Issue,
    Master,
    OpenBill,
    Resolution,
    Staged,
    Template,
    _custom,
    _Reader,
)

MONEY_KINDS = ("PAYMENT", "RECEIPT", "CONTRA", "JOURNAL")
MODES = frozenset({"CASH", "CHEQUE", "NEFT", "RTGS", "IMPS", "UPI", "CARD", "BANK_TRANSFER"})
TRACKING = frozenset({"NONE", "NEW_REF", "ON_ACCOUNT", "ADVANCE"})
PURPOSES = {
    "PAYMENT": frozenset({"GENERAL", "SETTLEMENT", "ADVANCE", "REFUND"}),
    "RECEIPT": frozenset({"GENERAL", "SETTLEMENT", "ADVANCE", "REFUND"}),
    "CONTRA": frozenset({"TRANSFER"}),
    "JOURNAL": frozenset({"GENERAL"}),
}
CASH_BANK = frozenset({"CASH", "BANK"})
# Which side a cash/bank ledger sits on, and the party role an advance belongs to.
MONEY_SIDE = {"PAYMENT": "CREDIT", "RECEIPT": "DEBIT"}
ADVANCE_ROLE = {"PAYMENT": "SUPPLIER", "RECEIPT": "CUSTOMER"}
REFUND_ROLE = {"PAYMENT": "CUSTOMER", "RECEIPT": "SUPPLIER"}
REQUIRED_NATIVE = frozenset({"financial", "document_date", "currency"})
LINE_NO = re.compile(r"[1-9][0-9]{0,2}")
FOUR = Decimal("0.0001")


def columns(kind: str) -> tuple[tuple[Column, ...], tuple[Column, ...]]:
    settles = kind in {"PAYMENT", "RECEIPT"}
    header = (
        *COMMON_HEAD,
        Column("currency", True, "currency", "ISO 4217 code", "INR"),
        *(
            (
                Column(
                    "purpose", False, "financial", ", ".join(sorted(PURPOSES[kind])), "SETTLEMENT"
                ),
            )
            if settles
            else ()
        ),
        NARRATION,
    )
    line = [
        Column("import_key", True, None, "Parent voucher key", "PV-0001"),
        Column("line_no", True, None, "1-200, unique within the voucher", "1"),
        Column("account_code", True, "financial", "Ledger code", "BANK-HDFC"),
        Column("side", True, "financial", "DEBIT or CREDIT", "CREDIT"),
        Column("amount", True, "financial", "Positive amount, up to 4 decimals", "1000.00"),
        Column("description", False, "financial", "Line description"),
    ]
    if kind != "CONTRA":
        line += [
            Column(
                "tracking",
                False,
                "financial",
                "Party lines: ON_ACCOUNT (default), NEW_REF, ADVANCE",
            ),
            Column("bill_reference", False, "financial", "NEW_REF bill reference"),
            Column("due_date", False, "financial", "NEW_REF due date, YYYY-MM-DD"),
        ]
    if settles:
        line.append(
            Column(
                "against_bill", False, "financial", "Open bill reference this party line settles"
            )
        )
    if kind != "JOURNAL":
        line += [
            Column(
                "tender_mode",
                False,
                "financial",
                "Cash/bank lines: " + ", ".join(sorted(MODES)),
                "NEFT",
            ),
            Column(
                "tender_reference",
                False,
                "financial",
                "Cheque number or transfer reference (UTR)",
                "UTR0001",
            ),
            Column("instrument_date", False, "financial", "Cheque date, YYYY-MM-DD"),
        ]
    return header, tuple(line)


def template(
    kind: str, denied: frozenset[str], header_custom: Iterable[CustomColumn] = ()
) -> Template:
    if blocked := sorted(REQUIRED_NATIVE & denied):
        raise PermissionError("money import requires writable " + ", ".join(blocked))
    header, line = columns(kind)
    return Template(
        tuple(c for c in header if c.native not in denied) + tuple(header_custom),
        tuple(c for c in line if c.native not in denied),
    )


@dataclass(frozen=True, slots=True)
class MoneyLine:
    line_no: int
    account_code: str
    side: str
    amount: Decimal
    description: str
    tracking: str | None
    bill_reference: str | None
    due_date: dt.date | None
    against_bill: str | None
    tender_mode: str | None
    tender_reference: str | None
    instrument_date: dt.date | None
    row: tuple[str, int]


@dataclass(frozen=True, slots=True)
class MoneyDoc:
    kind: str
    import_key: str
    class_code: str | None
    document_date: dt.date
    posting_date: dt.date
    currency: str
    purpose: str
    narration: str | None
    custom: dict[str, Any]
    lines: tuple[MoneyLine, ...]

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines if line.side == "DEBIT"), Decimal(0))


def parse(item: Staged, shape: Template, kind: str) -> tuple[MoneyDoc | None, list[Issue]]:
    """L2 lexical checks plus balance and tender evidence, with no master knowledge."""
    issues = list(item.issues)
    sheet, number = item.rows[0]
    head = _Reader(item.header, sheet, number, issues)
    names = set(shape.names("header"))
    document_date = head.date("document_date", required=True)
    posting_date = head.date("posting_date") if "posting_date" in names else None
    class_code = head.pattern("voucher_class_code", CODE, "codes are at most 40 characters")
    currency = head.pattern(
        "currency", re.compile(r"[A-Z]{3}"), "use an ISO 4217 code", required=True
    )
    purpose = head.choice("purpose", PURPOSES[kind]) if "purpose" in names else None
    narration = head.text("narration", limit=1000) if "narration" in names else None
    custom = _custom(head, (c for c in shape.header if isinstance(c, CustomColumn)))
    lines: list[MoneyLine] = []
    seen: set[int] = set()
    present = set(shape.names("line"))
    for cells in item.lines:
        place = (cells.get("_sheet", sheet), int(cells.get("_row", number)))
        reader = _Reader(cells, *place, issues)
        raw = reader.pattern("line_no", LINE_NO, "use 1-200", required=True)
        line_no = int(raw) if raw is not None else None
        if line_no is not None and (line_no > MAX_LINES or line_no in seen):
            reader.fail("line_no", "invalid_line_no", "line_no must be unique and at most 200")
        if line_no is not None:
            seen.add(line_no)
        account = reader.pattern(
            "account_code", CODE, "codes are at most 40 characters", required=True
        )
        side = reader.choice("side", frozenset({"DEBIT", "CREDIT"}), required=True)
        amount = reader.decimal("amount", required=True)
        if amount == 0:
            reader.fail("amount", "invalid_decimal", "amount must be positive")
            amount = None
        description = reader.text("description", limit=500) or ""
        tracking = reader.choice("tracking", TRACKING) if "tracking" in present else None
        bill_reference = reader.text("bill_reference") if "bill_reference" in present else None
        due_date = reader.date("due_date") if "due_date" in present else None
        against = reader.text("against_bill") if "against_bill" in present else None
        mode = reader.choice("tender_mode", MODES) if "tender_mode" in present else None
        reference = reader.text("tender_reference") if "tender_reference" in present else None
        instrument = reader.date("instrument_date") if "instrument_date" in present else None
        if mode == "CASH" and (reference or instrument):
            reader.fail(
                "tender_reference",
                "cash_has_no_instrument",
                "cash has no cheque or transfer reference",
            )
        if mode == "CHEQUE" and instrument is None:
            reader.fail("instrument_date", "required", "a cheque needs its date")
        if mode is None and (reference or instrument):
            reader.fail("tender_mode", "required", "a tender reference needs its mode")
        if tracking == "NEW_REF" and not bill_reference:
            reader.fail("bill_reference", "required", "a new reference needs bill_reference")
        if tracking not in {None, "NEW_REF"} and (bill_reference or due_date):
            reader.fail("tracking", "invalid_choice", "bill fields need tracking NEW_REF")
        if against and tracking not in {None, "ON_ACCOUNT"}:
            reader.fail(
                "against_bill", "tracking_conflict", "a line settling a bill is tracked ON_ACCOUNT"
            )
        if None not in (line_no, account, side, amount):
            lines.append(
                MoneyLine(
                    line_no or 0,
                    account or "",
                    side or "",
                    amount or Decimal(0),
                    description,
                    tracking,
                    bill_reference,
                    due_date,
                    against,
                    mode,
                    reference,
                    instrument,
                    place,
                )
            )
    debit = sum((ln.amount for ln in lines if ln.side == "DEBIT"), Decimal(0))
    credit = sum((ln.amount for ln in lines if ln.side == "CREDIT"), Decimal(0))
    if not issues and len(lines) < 2:
        head.fail("line_no", "too_few_lines", "a voucher needs at least two ledger lines")
    elif not issues and debit != credit:
        head.fail("amount", "unbalanced", "debits and credits must be equal")
    if issues or document_date is None or currency is None:
        return None, issues
    default = {"CONTRA": "TRANSFER", "JOURNAL": "GENERAL"}.get(kind) or (
        "SETTLEMENT" if any(line.against_bill for line in lines) else "GENERAL"
    )
    return MoneyDoc(
        kind,
        item.import_key,
        class_code,
        document_date,
        posting_date or document_date,
        currency,
        purpose or default,
        narration,
        custom,
        tuple(sorted(lines, key=lambda line: line.line_no)),
    ), []


def file_identities(doc: MoneyDoc) -> list[tuple[tuple[str, ...], str, str]]:
    """Bank instruments repeated inside one file (textual, before ledgers resolve)."""
    return [
        (
            ("instrument", line.account_code.casefold(), *(part or "" for part in facts)),
            "tender_reference",
            "duplicate_instrument",
        )
        for line in doc.lines
        if (facts := instrument(line)) is not None
    ]


def direction(role: str | None, side: str) -> str:
    """An open item's direction for its party, as Accounting records it: a customer debit or a
    supplier credit is DEBT (the party owes, or is owed, the document's amount)."""
    return "DEBT" if (role == "CUSTOMER") == (side == "DEBIT") else "CREDIT"


def instrument(line: MoneyLine) -> tuple[str, str, str | None, str | None] | None:
    """Bank instrument identity: (group, reference, date, value), or None for cash.

    A cheque we issue is one leaf of our book, so its number alone identifies it on the bank
    ledger. A received cheque carries the drawer's number, so its date and amount join in. An
    electronic transfer reference is unique on the bank ledger.
    """
    if line.tender_mode in {None, "CASH"} or not line.tender_reference:
        return None
    cheque = line.tender_mode == "CHEQUE"
    received = cheque and line.side == "DEBIT"
    return (
        "CHEQUE" if cheque else "ELECTRONIC",
        line.tender_reference.strip().casefold(),
        str(line.instrument_date) if received else None,
        format(line.amount.quantize(FOUR), "f") if received else None,
    )


def resolve(
    doc: MoneyDoc,
    found: Resolution,
    *,
    profile: str = "STANDARD",
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """L4/L5: exact active ledgers, then the kind's ledger, tender and party rules."""
    issues: list[Issue] = []
    accounts: dict[int, tuple[Master, AccountFacts]] = {}
    for line in doc.lines:
        master = found.account(line.account_code)
        facts = found.account_facts.get(master.source_id) if master else None
        sheet, row = line.row
        if master is None or facts is None:
            issues.append(
                Issue(
                    sheet,
                    row,
                    "account_code",
                    "unknown_master",
                    f"line {line.line_no}: ledger code does not exist",
                    "L4",
                )
            )
        elif master.status != "ACTIVE":
            issues.append(
                Issue(
                    sheet,
                    row,
                    "account_code",
                    "inactive_master",
                    f"line {line.line_no}: ledger is not active",
                    "L4",
                )
            )
        elif facts.currency not in {None, doc.currency}:
            issues.append(
                Issue(
                    sheet,
                    row,
                    "account_code",
                    "currency_mismatch",
                    f"line {line.line_no}: ledger uses another currency",
                    "L4",
                )
            )
        else:
            accounts[line.line_no] = (master, facts)
    if issues:
        return None, issues

    def fail(line: MoneyLine | None, column: str | None, code: str, message: str) -> None:
        sheet, row = line.row if line else doc.lines[0].row
        prefix = f"line {line.line_no}: " if line else ""
        issues.append(Issue(sheet, row, column, code, prefix + message, "L5"))

    kind = doc.kind
    if profile == "ADVANCE" and doc.purpose != "ADVANCE":
        fail(None, "purpose", "advance_purpose_required", "an advance type records advances")
    money_lines = [ln for ln in doc.lines if accounts[ln.line_no][1].kind in CASH_BANK]
    if kind in MONEY_SIDE and not money_lines:
        fail(None, "account_code", "cash_bank_required", "a cash or bank ledger is required")
    if doc.purpose in {"ADVANCE", "REFUND"} and not any(
        accounts[ln.line_no][1].kind == "PARTY" for ln in doc.lines
    ):
        fail(
            None, "account_code", "party_required", "an advance or refund names the party's ledger"
        )
    if kind == "CONTRA" and (
        len(money_lines) != len(doc.lines)
        or len({accounts[ln.line_no][0].source_id for ln in doc.lines}) < 2
    ):
        fail(
            None,
            "account_code",
            "contra_ledgers",
            "a contra moves money between two different cash or bank ledgers only",
        )
    for line in doc.lines:
        master, facts = accounts[line.line_no]
        money = facts.kind in CASH_BANK
        if kind == "JOURNAL" and money:
            # Journals carry no tenders; cash and bank move through Payment, Receipt, Contra.
            fail(
                line,
                "account_code",
                "journal_cash_bank",
                "use a payment, receipt or contra for cash or bank ledgers",
            )
        if money and kind in MONEY_SIDE and line.side != MONEY_SIDE[kind]:
            fail(
                line,
                "side",
                "wrong_side",
                f"cash/bank lines of a {kind.lower()} are {MONEY_SIDE[kind].lower()}s",
            )
        if kind != "JOURNAL" and money and line.tender_mode is None:
            fail(line, "tender_mode", "required", "a cash or bank line needs its tender")
        if not money and line.tender_mode is not None:
            fail(line, "tender_mode", "tender_on_ledger", "only cash or bank lines carry a tender")
        if (
            money
            and line.tender_mode is not None
            and ((line.tender_mode == "CASH") != (facts.kind == "CASH"))
        ):
            fail(line, "tender_mode", "wrong_tender", "CASH tenders belong on cash ledgers only")
        if facts.kind == "PARTY":
            if facts.party_role not in {"CUSTOMER", "SUPPLIER"}:
                fail(
                    line,
                    "account_code",
                    "party_role",
                    "the party ledger has no customer or supplier role",
                )
            if (line.tracking or "ON_ACCOUNT") == "NONE":
                fail(line, "tracking", "tracking_required", "party lines are tracked")
            if doc.purpose == "ADVANCE":
                if line.tracking != "ADVANCE":
                    fail(line, "tracking", "advance_tracking", "advance lines use ADVANCE")
                if kind in ADVANCE_ROLE and facts.party_role != ADVANCE_ROLE[kind]:
                    fail(
                        line,
                        "account_code",
                        "advance_role",
                        f"a {kind.lower()} advance is with a {ADVANCE_ROLE[kind].lower()}",
                    )
            if (
                doc.purpose == "REFUND"
                and kind in REFUND_ROLE
                and (facts.party_role != REFUND_ROLE[kind])
            ):
                fail(
                    line,
                    "account_code",
                    "refund_role",
                    f"a {kind.lower()} refund goes to a {REFUND_ROLE[kind].lower()}",
                )
        else:
            if (line.tracking or "NONE") != "NONE":
                fail(line, "tracking", "tracking_not_allowed", "only party lines are tracked")
            if line.against_bill:
                fail(line, "against_bill", "not_a_party", "only party lines settle bills")
            if facts.posting_policy != "MANUAL_ALLOWED":
                fail(
                    line,
                    "account_code",
                    "manual_posting_blocked",
                    "the ledger does not accept manual entries",
                )
    if issues:
        return None, issues
    bills: dict[int, OpenBill] = {}
    for line in doc.lines:
        if not line.against_bill:
            continue
        master, facts = accounts[line.line_no]
        matches = found.bill(master.source_id, line.against_bill)
        # The settling line becomes an open item of the same party; it must be the opposite one.
        wanted = "DEBT" if direction(facts.party_role, line.side) == "CREDIT" else "CREDIT"
        if not matches:
            fail(line, "against_bill", "unknown_bill", "no open bill with this reference")
        elif len(matches) > 1:
            fail(line, "against_bill", "ambiguous_bill", "several open bills share this reference")
        elif matches[0].currency != doc.currency:
            fail(line, "against_bill", "currency_mismatch", "the bill uses another currency")
        elif matches[0].direction != wanted:
            fail(
                line,
                "against_bill",
                "wrong_bill_direction",
                "this line cannot settle that bill (it is on the same side)",
            )
        elif matches[0].remaining <= 0:
            fail(line, "against_bill", "bill_settled", "the bill has nothing outstanding")
        else:
            bills[line.line_no] = matches[0]
    if issues:
        return None, issues
    return {"accounts": accounts, "bills": bills}, []


def content(
    doc: MoneyDoc,
    masters: dict[str, Any],
    *,
    job_id: uuid.UUID,
    type_revision_id: uuid.UUID,
    class_id: uuid.UUID | None,
    include: frozenset[str],
) -> dict[str, Any]:
    """Native ``VoucherInput`` with deterministic entry, tender and allocation identities."""

    def key(suffix: str) -> str:
        return str(uuid.uuid5(job_id, f"{doc.import_key}:{suffix}"))

    accounts, tenders, allocations = [], [], []
    for line in doc.lines:
        master, facts = masters["accounts"][line.line_no]
        line_key = key(f"line:{line.line_no}")
        tracking = line.tracking or ("ON_ACCOUNT" if facts.kind == "PARTY" else "NONE")
        entry: dict[str, Any] = {
            "line_key": line_key,
            "account_id": str(master.source_id),
            "source_version": master.source_version,
            "side": line.side,
            "currency": doc.currency,
            "amount": format(line.amount, "f"),
            "description": line.description,
            "tracking": tracking,
        }
        if tracking == "NEW_REF":
            # Without a due date Accounting dates the new bill on its document date.
            entry["bill_reference"] = line.bill_reference
            if line.due_date is not None:
                entry["due_date"] = line.due_date.isoformat()
        accounts.append(entry)
        if line.tender_mode is not None:
            tender: dict[str, Any] = {
                "tender_key": key(f"tender:{line.line_no}"),
                "line_key": line_key,
                "mode": line.tender_mode,
                "amount": format(line.amount, "f"),
                "currency": doc.currency,
            }
            if line.tender_reference:
                tender["reference"] = line.tender_reference
            if line.instrument_date:
                tender["instrument_date"] = line.instrument_date.isoformat()
            tenders.append(tender)
        bill: OpenBill | None = masters["bills"].get(line.line_no)
        if bill is not None:
            this, other = {"line_key": line_key}, {"item_id": str(bill.item_id)}
            allocations.append(
                {
                    "allocation_key": key(f"allocation:{line.line_no}"),
                    "debt": other if bill.direction == "DEBT" else this,
                    "credit": this if bill.direction == "DEBT" else other,
                    "amount": format(min(line.amount, bill.remaining).quantize(FOUR), "f"),
                    "currency": doc.currency,
                }
            )
    body: dict[str, Any] = {
        "type_revision_id": str(type_revision_id),
        "document_date": doc.document_date.isoformat(),
        "currency": doc.currency,
        "mode": "ACCOUNTS",
        "financial": {
            "purpose": doc.purpose,
            "accounts": accounts,
            "tenders": tenders,
            "allocations": allocations,
        },
        "custom_fields": doc.custom,
    }
    if class_id is not None:
        body["class_id"] = str(class_id)
    if "posting_date" in include:
        body["posting_date"] = doc.posting_date.isoformat()
    if doc.narration is not None and "narration" in include:
        body["narration"] = doc.narration
    return body


def probes(doc: MoneyDoc, masters: dict[str, Any]) -> list[dict[str, Any]]:
    """What identifies this money voucher against existing ones and the rest of the job."""
    result: list[dict[str, Any]] = []
    cash_only = True
    for line in doc.lines:
        master, _ = masters["accounts"][line.line_no]
        if (facts := instrument(line)) is not None:
            cash_only = False
            group, reference, date, value = facts
            result.append(
                checks.probe(
                    "instrument",
                    "error",
                    account_id=str(master.source_id),
                    group=group,
                    reference=reference,
                    side=line.side if group == "CHEQUE" else None,
                    date=date,
                    value=value,
                )
            )
        bill: OpenBill | None = masters["bills"].get(line.line_no)
        if bill is not None:
            result.append(
                checks.probe(
                    "allocation",
                    "error",
                    item_id=str(bill.item_id),
                    amount=format(min(line.amount, bill.remaining).quantize(FOUR), "f"),
                    owner_remaining=format(bill.remaining, "f"),
                )
            )
    if cash_only:
        result.append(
            checks.probe(
                "signature",
                "warning",
                kind=doc.kind,
                date=doc.document_date.isoformat(),
                entries=checks.signature(
                    (str(masters["accounts"][ln.line_no][0].source_id), ln.side, ln.amount)
                    for ln in doc.lines
                ),
            )
        )
    return result


def ledger_codes(doc: MoneyDoc) -> set[str]:
    return {line.account_code for line in doc.lines}


def bill_requests(doc: MoneyDoc, found: Resolution) -> set[tuple[uuid.UUID, str]]:
    """Second lookup: open bills named by party lines, once their ledgers resolved."""
    result = set()
    for line in doc.lines:
        master = found.account(line.account_code)
        if line.against_bill and master is not None:
            result.add((master.source_id, line.against_bill))
    return result
