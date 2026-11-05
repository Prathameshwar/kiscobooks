"""Invoice-kind import templates (Purchase, Sales, Credit/Debit Note), file grouping, lexical
parsing and native draft construction; shared by the money kinds' module.

Pure rules with no database or framework: callers resolve masters and run native writes.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal

MARKER = "_voucher_schema_version"
SCHEMA_VERSION = 1
MAX_VOUCHERS = 500
MAX_LINES = 200
MAX_ERRORS = 50
KEY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_-]|\.(?!\.)){0,63}")
CODE = re.compile(r"[^\x00-\x1f]{1,40}")
GSTIN = re.compile(r"[0-9A-Z]{15}")
AMOUNT = re.compile(r"[0-9]{1,15}(?:\.[0-9]{1,4})?")
RATE = re.compile(r"[0-9]{1,11}(?:\.[0-9]{1,8})?")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TAX_PROFILES = frozenset(
    {"INDIA_DOMESTIC_SERVICE", "INDIA_DOMESTIC_SERVICE_RCM", "UNTAXED_ACCOUNT"}
)
SUPPLY_KINDS = frozenset({"ACCOUNT", "SERVICE"})
PRICE_BASES = frozenset({"NET_EXCL_TAX", "GROSS_INCL_TAX"})
TRUE, FALSE = frozenset({"true", "yes", "1"}), frozenset({"false", "no", "0"})

State = Literal["VALID", "WARNING", "INVALID"]


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    required: bool
    native: str | None
    description: str
    example: str = ""


INVOICE_KINDS = ("PURCHASE", "SALES", "CREDIT_NOTE", "DEBIT_NOTE")
NOTE_KINDS = frozenset({"CREDIT_NOTE", "DEBIT_NOTE"})
# The party a document is with, and the original invoice kind a note returns against.
PARTY_ROLE = {
    "PURCHASE": "SUPPLIER",
    "DEBIT_NOTE": "SUPPLIER",
    "SALES": "CUSTOMER",
    "CREDIT_NOTE": "CUSTOMER",
}
ORIGINAL_KIND = {"CREDIT_NOTE": "SALES", "DEBIT_NOTE": "PURCHASE"}


def party_columns(prefix: str, example: str) -> tuple[Column, ...]:
    noun = prefix.capitalize()
    return (
        Column(
            f"{prefix}_code",
            False,
            "parties",
            f"Accounting party code (or {prefix}_gstin)",
            example,
        ),
        Column(f"{prefix}_gstin", False, "parties", f"{noun} GSTIN instead of {prefix}_code"),
        Column(f"{prefix}_ledger_code", False, "invoice", f"{noun} ledger when it has several"),
    )


COMMON_HEAD = (
    Column("import_key", True, None, "Unique voucher key within this file", "PB-0001"),
    Column("voucher_class_code", False, "class_id", "Optional class of the chosen type"),
    Column("document_date", True, "document_date", "YYYY-MM-DD", "2026-10-10"),
    Column("posting_date", False, "posting_date", "YYYY-MM-DD; defaults to document_date"),
)
TRADE_TAIL = (
    Column("due_date", False, "invoice", "YYYY-MM-DD; defaults to company payment terms"),
    Column("currency", True, "currency", "ISO 4217 code", "INR"),
    Column("exchange_rate", False, "invoice", "Required when currency differs from base"),
    Column("place_of_supply", False, "invoice", "IN-xx state code", "IN-MH"),
    Column("tax_profile", True, "invoice", ", ".join(sorted(TAX_PROFILES)), "UNTAXED_ACCOUNT"),
)
NARRATION = Column("narration", False, "narration", "Free text")
HEADER = (
    *COMMON_HEAD,
    *party_columns("supplier", "SUP-1"),
    Column("supplier_invoice_number", True, "invoice", "Supplier bill number", "INV-1001"),
    Column("supplier_invoice_date", True, "invoice", "YYYY-MM-DD", "2026-10-09"),
    *TRADE_TAIL,
    Column("supplier_declared_total", True, "invoice", "Supplier bill total", "1000.00"),
    Column("supplier_difference_reason", False, "invoice", "Required for a tolerated difference"),
    NARRATION,
)


def trade_lines(ledger: str, example: str) -> tuple[Column, ...]:
    return (
        Column("import_key", True, None, "Parent voucher key", "PB-0001"),
        Column("line_no", True, None, "1-200, unique within the voucher", "1"),
        Column("supply_kind", True, "invoice", "ACCOUNT or SERVICE", "SERVICE"),
        Column("account_code", True, "invoice", f"{ledger} ledger code", example),
        Column("description", True, "invoice", "Line description", "Office rent"),
        Column("amount", True, "invoice", "Line amount, up to 4 decimals", "1000.00"),
        Column("price_basis", False, "invoice", "NET_EXCL_TAX (default) or GROSS_INCL_TAX"),
        Column("discount_pct", False, "invoice", "Line discount percent, if the policy allows it"),
        Column("discount_amount", False, "invoice", "Fixed line discount, if the policy allows it"),
    )


LINE = trade_lines("Purchase/expense", "EXP-RENT")
SALES_HEADER = (
    *COMMON_HEAD,
    *party_columns("customer", "CUS-1"),
    Column(
        "source_reference",
        False,
        "references",
        "Source system order/invoice ID; it identifies the sale",
        "WEB-10001",
    ),
    Column("source_reference_date", False, "references", "YYYY-MM-DD"),
    Column("customer_order_number", False, "references", "Customer purchase order"),
    Column("customer_order_date", False, "references", "YYYY-MM-DD"),
    *TRADE_TAIL,
    NARRATION,
)
NOTE_LINE = (
    Column("import_key", True, None, "Parent voucher key", "CN-0001"),
    Column("line_no", True, None, "1-200, unique within the voucher", "1"),
    Column("original_line_no", True, "invoice", "Line number on the original invoice", "1"),
    Column("description", True, "invoice", "Line description", "Returned service"),
    Column("amount", True, "invoice", "Amount returned on this line, up to 4 decimals", "250.00"),
)


def note_header(prefix: str, original: str, party: str) -> tuple[Column, ...]:
    return (
        *COMMON_HEAD,
        *party_columns(prefix, party),
        Column(original, True, "invoice", "Number of the original invoice", "INV-1001"),
        Column(
            "return_reference",
            False,
            "references",
            "The party's return or note reference; it identifies the note",
            "RET-77",
        ),
        Column("currency", True, "currency", "ISO 4217 code", "INR"),
        NARRATION,
    )


COLUMNS = {
    "PURCHASE": (HEADER, LINE),
    "SALES": (SALES_HEADER, trade_lines("Sales/income", "INC-SALES")),
    "CREDIT_NOTE": (note_header("customer", "original_invoice_number", "CUS-1"), NOTE_LINE),
    "DEBIT_NOTE": (note_header("supplier", "original_bill_number", "SUP-1"), NOTE_LINE),
}
REQUIRED_NATIVE = frozenset({"invoice", "parties", "document_date", "currency"})


@dataclass(frozen=True, slots=True)
class CustomColumn:
    key: str
    data_type: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class Template:
    header: tuple[Column | CustomColumn, ...]
    line: tuple[Column | CustomColumn, ...]

    def names(self, part: Literal["header", "line"]) -> list[str]:
        return [label(column) for column in (self.header if part == "header" else self.line)]

    def flat(self) -> list[str]:
        return self.names("header") + [name for name in self.names("line") if name != "import_key"]


def label(column: Column | CustomColumn) -> str:
    return column.name if isinstance(column, Column) else "cf." + column.key


@dataclass(frozen=True, slots=True)
class Issue:
    sheet: str
    row: int
    column: str | None
    code: str
    message: str
    layer: str = "L2"
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Staged:
    import_key: str
    ordinal: int
    header: dict[str, str]
    lines: list[dict[str, str]]
    rows: list[tuple[str, int]]
    issues: list[Issue] = field(default_factory=list)

    @classmethod
    def from_stored(
        cls, key: str, ordinal: int, source: Mapping[str, Any], rows: Iterable[Iterable[Any]]
    ) -> Staged:
        positions = [(str(sheet), int(row)) for sheet, row in rows]
        return cls(key, ordinal, dict(source["header"]), list(source["lines"]), positions)


@dataclass(frozen=True, slots=True)
class ParsedLine:
    line_no: int
    supply_kind: str | None
    account_code: str | None
    description: str
    amount: Decimal
    price_basis: str
    discount_pct: Decimal | None
    discount_amount: Decimal | None
    original_line_no: int | None = None


@dataclass(frozen=True, slots=True)
class Parsed:
    import_key: str
    class_code: str | None
    document_date: dt.date
    posting_date: dt.date
    party_code: str | None
    party_gstin: str | None
    party_ledger_code: str | None
    currency: str
    narration: str | None
    custom: dict[str, Any]
    lines: tuple[ParsedLine, ...]
    kind: str = "PURCHASE"
    supplier_invoice_number: str | None = None
    supplier_invoice_date: dt.date | None = None
    due_date: dt.date | None = None
    exchange_rate: Decimal | None = None
    place_of_supply: str | None = None
    tax_profile: str = "UNTAXED_ACCOUNT"
    declared_total: Decimal | None = None
    difference_reason: str | None = None
    source_reference: str | None = None
    source_reference_date: dt.date | None = None
    order_number: str | None = None
    order_date: dt.date | None = None
    original_number: str | None = None
    return_reference: str | None = None

    @property
    def party_text(self) -> str:
        return "code:" + self.party_code if self.party_code else "gstin:" + (self.party_gstin or "")


@dataclass(frozen=True, slots=True)
class Master:
    source_id: uuid.UUID
    source_version: int
    status: str


@dataclass(frozen=True, slots=True)
class AccountFacts:
    kind: str
    party_id: uuid.UUID | None
    party_role: str | None
    posting_policy: str | None
    currency: str | None


@dataclass(frozen=True, slots=True)
class OpenBill:
    item_id: uuid.UUID
    direction: str
    currency: str
    remaining: Decimal


@dataclass(frozen=True, slots=True)
class OriginalLine:
    line_key: uuid.UUID
    sequence: int
    account_id: uuid.UUID
    supply_kind: str
    untaxed: bool
    remaining: Decimal


@dataclass(frozen=True, slots=True)
class OriginalInvoice:
    source_id: uuid.UUID
    currency: str
    posting_date: dt.date
    returnable: bool
    lines: tuple[OriginalLine, ...]


@dataclass(frozen=True, slots=True)
class Resolution:
    """Exact master matches from the owner.

    The owner's codes are unique case-insensitively (collated), so codes match by casefold.
    """

    parties: Mapping[str, Master]
    gstin_parties: Mapping[str, tuple[uuid.UUID, ...]]
    party_ids: Mapping[uuid.UUID, Master]
    party_ledgers: Mapping[uuid.UUID, tuple[tuple[str, Master], ...]]
    accounts: Mapping[str, Master]
    ledger_roles: Mapping[uuid.UUID, str | None] = field(default_factory=dict)
    account_facts: Mapping[uuid.UUID, AccountFacts] = field(default_factory=dict)
    bills: Mapping[tuple[uuid.UUID, str], tuple[OpenBill, ...]] = field(default_factory=dict)
    invoices: Mapping[tuple[str, uuid.UUID, str], tuple[OriginalInvoice, ...]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        for name in ("parties", "accounts"):
            object.__setattr__(
                self, name, {code.casefold(): row for code, row in getattr(self, name).items()}
            )

    def party(self, code: str) -> Master | None:
        return self.parties.get(code.casefold())

    def account(self, code: str) -> Master | None:
        return self.accounts.get(code.casefold())

    def bill(self, account_id: uuid.UUID, reference: str) -> tuple[OpenBill, ...]:
        return self.bills.get((account_id, reference.casefold()), ())

    def invoice(
        self, kind: str, account_id: uuid.UUID, reference: str
    ) -> tuple[OriginalInvoice, ...]:
        return self.invoices.get((kind, account_id, reference.casefold()), ())


def template(
    denied: frozenset[str], header_custom: Iterable[CustomColumn] = (), kind: str = "PURCHASE"
) -> Template:
    """Columns the actor may write; a denied required native field refuses the template.

    Item-line custom fields belong to goods item lines, which this slice does not import.
    """
    if blocked := sorted(REQUIRED_NATIVE & denied):
        raise PermissionError("invoice import requires writable " + ", ".join(blocked))
    header, line = COLUMNS[kind]
    return Template(
        tuple(c for c in header if c.native not in denied) + tuple(header_custom),
        tuple(c for c in line if c.native not in denied),
    )


def instructions(shape: Template) -> list[list[str]]:
    rows = [["general", "", "Text cells only: ISO dates, plain decimals, no formulas."]]
    for part, columns in (("vouchers", shape.header), ("lines", shape.line)):
        for column in columns:
            rows.append(
                [
                    f"{part}.{label(column)}",
                    "yes" if column.required else "no",
                    column.description
                    if isinstance(column, Column)
                    else f"Custom field ({column.data_type})",
                ]
            )
    return rows


def examples(shape: Template) -> tuple[list[list[str]], list[list[str]]]:
    def row(columns: tuple[Column | CustomColumn, ...]) -> list[str]:
        return [column.example if isinstance(column, Column) else "" for column in columns]

    return [row(shape.header)], [row(shape.line)]


def flat_examples(shape: Template) -> list[list[str]]:
    header, line = examples(shape)
    names = shape.names("line")
    return [header[0] + [v for name, v in zip(names, line[0], strict=True) if name != "import_key"]]


def _clean(cells: Mapping[str, str]) -> dict[str, str]:
    return {key: value.strip() for key, value in cells.items() if value.strip()}


def _columns(names: Iterable[str], expected: list[str], sheet: str, number: int) -> list[Issue]:
    """Unknown (including policy-denied) columns are refused; absent ones are simply empty."""
    return [
        Issue(sheet, number, name, "unknown_column", "column is not in the template", "L1")
        for name in sorted(set(names) - set(expected))
    ]


def unexpected(item: Staged, shape: Template) -> list[Issue]:
    """Columns the live template no longer allows (e.g. a field denied after upload)."""
    sheet, number = item.rows[0]
    header = set(item.header) - set(shape.names("header"))
    lines = (
        {key for line in item.lines for key in line if not key.startswith("_")}
        - set(shape.names("line"))
        - set(shape.names("header"))
    )
    return [
        Issue(sheet, number, name, "unknown_column", "column is not in the template", "L1")
        for name in sorted(header | lines)
    ]


def _admit(
    staged: dict[str, Staged],
    key: str,
    header: dict[str, str],
    lines: list[dict[str, str]],
    sheet: str,
    number: int,
) -> Staged | None:
    """Add a voucher once; keys are compared case-insensitively, as the store does."""
    if (existing := staged.get(key.casefold())) is not None:
        existing.issues.append(
            Issue(sheet, number, "import_key", "duplicate_import_key", "import_key repeats", "L3")
        )
        return None
    item = staged[key.casefold()] = Staged(key, len(staged) + 1, header, lines, [(sheet, number)])
    return item


def group_sheets(
    tables: Mapping[str, list[tuple[int, dict[str, str]]]],
    headers: Mapping[str, list[str]],
    shape: Template,
) -> tuple[list[Staged], list[Issue]]:
    """XLSX: one ``vouchers`` row per voucher, ``lines`` rows join by import_key."""
    issues: list[Issue] = []
    for sheet in sorted((set(tables) | set(headers)) - {"vouchers", "lines", "instructions"}):
        issues.append(Issue(sheet, 1, None, "unknown_sheet", "sheet is not in the template", "L1"))
    for sheet, expected in (("vouchers", shape.names("header")), ("lines", shape.names("line"))):
        if sheet not in headers:
            issues.append(Issue(sheet, 1, None, "missing_sheet", "template sheet is missing", "L1"))
        else:
            issues.extend(_columns(headers[sheet], expected, sheet, 2))
    if issues:
        return [], issues
    staged: dict[str, Staged] = {}
    for number, cells in tables.get("vouchers", []):
        values = _clean(cells)
        _admit(staged, values.get("import_key", ""), values, [], "vouchers", number)
    for number, cells in tables.get("lines", []):
        values = _clean(cells)
        key = values.get("import_key", "").casefold()
        if key not in staged:
            issues.append(
                Issue(
                    "lines",
                    number,
                    "import_key",
                    "orphan_line",
                    "line has no matching voucher row",
                    "L3",
                )
            )
            continue
        staged[key].lines.append(values | {"_row": str(number), "_sheet": "lines"})
        staged[key].rows.append(("lines", number))
    return _bounded(list(staged.values()), issues)


def group_flat(
    rows: list[tuple[int, dict[str, str]]], headers: list[str], shape: Template, sheet: str = "CSV"
) -> tuple[list[Staged], list[Issue]]:
    """CSV: one row per line; repeated header columns must agree within a voucher."""
    issues = _columns(headers, shape.flat(), sheet, 2)
    if issues:
        return [], issues
    header_names = set(shape.names("header"))
    staged: dict[str, Staged] = {}
    for number, cells in rows:
        values = _clean(cells)
        key = values.get("import_key", "")
        head = {k: v for k, v in values.items() if k in header_names}
        line = {k: v for k, v in values.items() if k not in header_names or k == "import_key"}
        line |= {"_row": str(number), "_sheet": sheet}
        item = staged.get(key.casefold())
        if item is None:
            _admit(staged, key, head, [line], sheet, number)
            continue
        for name in sorted(header_names - {"import_key"}):
            if head.get(name, "") != item.header.get(name, ""):
                item.issues.append(
                    Issue(
                        sheet,
                        number,
                        name,
                        "header_mismatch",
                        "voucher columns differ between lines of one voucher",
                        "L3",
                    )
                )
        item.lines.append(line)
        item.rows.append((sheet, number))
    return _bounded(list(staged.values()), issues)


def group_json(payload: Any, shape: Template) -> tuple[list[Staged], list[Issue]]:
    """JSON: ``{"schema_version": 1, "vouchers": [{...header, "lines": [{...}]}]}``; text values."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "vouchers"}
        or payload["schema_version"] != SCHEMA_VERSION
        or not isinstance(payload["vouchers"], list)
    ):
        return [], [
            Issue(
                "JSON",
                1,
                None,
                "invalid_document",
                "JSON requires schema_version 1 and a vouchers list",
                "L1",
            )
        ]
    header_names, line_names = set(shape.names("header")), set(shape.names("line"))
    staged: dict[str, Staged] = {}
    issues: list[Issue] = []
    for index, voucher in enumerate(payload["vouchers"], 1):
        if not isinstance(voucher, dict) or not isinstance(voucher.get("lines"), list):
            issues.append(
                Issue(
                    "JSON",
                    index,
                    None,
                    "invalid_voucher",
                    "voucher must be an object with lines",
                    "L1",
                )
            )
            continue
        head = {k: v for k, v in voucher.items() if k != "lines"}
        bad = [k for k, v in head.items() if k not in header_names or not isinstance(v, str)]
        lines = []
        for line in voucher["lines"]:
            if not isinstance(line, dict) or any(
                k not in line_names - {"import_key"} or not isinstance(v, str)
                for k, v in line.items()
            ):
                bad.append("lines")
                break
            lines.append(line)
        if bad:
            issues.append(
                Issue(
                    "JSON",
                    index,
                    sorted(bad)[0],
                    "invalid_voucher",
                    "use template field names and text values only",
                    "L1",
                )
            )
            continue
        values = _clean(head)
        key = values.get("import_key", "")
        _admit(
            staged,
            key,
            values,
            [
                _clean(line) | {"import_key": key, "_row": str(index), "_sheet": "JSON"}
                for line in lines
            ],
            "JSON",
            index,
        )
    return _bounded(list(staged.values()), issues)


def _bounded(staged: list[Staged], issues: list[Issue]) -> tuple[list[Staged], list[Issue]]:
    if not staged and not issues:
        issues.append(Issue("file", 1, None, "empty_file", "file contains no vouchers", "L1"))
    if len(staged) > MAX_VOUCHERS:
        issues.append(
            Issue(
                "file",
                1,
                None,
                "too_many_vouchers",
                f"a job holds at most {MAX_VOUCHERS} vouchers",
                "L1",
            )
        )
    for item in staged:
        sheet, row = item.rows[0]
        if not KEY.fullmatch(item.import_key):
            item.issues.append(
                Issue(
                    sheet,
                    row,
                    "import_key",
                    "invalid_import_key",
                    "import_key must be 1-64 letters, digits, '.', '_' or '-'",
                    "L3",
                )
            )
        if not item.lines:
            item.issues.append(Issue(sheet, row, None, "no_lines", "voucher has no lines", "L3"))
        if len(item.lines) > MAX_LINES:
            item.issues.append(
                Issue(
                    sheet,
                    row,
                    None,
                    "too_many_lines",
                    f"a voucher holds at most {MAX_LINES} lines",
                    "L3",
                )
            )
    return staged, issues


class _Reader:
    def __init__(self, cells: Mapping[str, str], sheet: str, row: int, issues: list[Issue]):
        self.cells, self.sheet, self.row, self.issues = cells, sheet, row, issues

    def fail(self, column: str, code: str, message: str) -> None:
        self.issues.append(Issue(self.sheet, self.row, column, code, message))

    def text(self, column: str, *, required: bool = False, limit: int = 120) -> str | None:
        value = self.cells.get(column)
        if value is None:
            if required:
                self.fail(column, "required", "value is required")
            return None
        if len(value) > limit or any(ord(ch) < 32 for ch in value):
            self.fail(column, "invalid_text", f"text must be at most {limit} printable characters")
            return None
        return value

    def pattern(
        self, column: str, regex: re.Pattern[str], message: str, *, required: bool = False
    ) -> str | None:
        value = self.text(column, required=required)
        if value is not None and not regex.fullmatch(value):
            self.fail(column, "invalid_format", message)
            return None
        return value

    def date(self, column: str, *, required: bool = False) -> dt.date | None:
        value = self.text(column, required=required)
        if value is None:
            return None
        try:
            if not DATE.fullmatch(value):
                raise ValueError
            return dt.date.fromisoformat(value)
        except ValueError:
            self.fail(column, "invalid_date", "use an ISO date YYYY-MM-DD as text")
            return None

    def decimal(self, column: str, *, required: bool = False, rate: bool = False) -> Decimal | None:
        value = self.text(column, required=required)
        if value is None:
            return None
        if not (RATE if rate else AMOUNT).fullmatch(value):
            self.fail(
                column,
                "invalid_decimal",
                "use a plain non-negative decimal with at most "
                f"{8 if rate else 4} decimal places and no separators",
            )
            return None
        return Decimal(value)

    def choice(
        self,
        column: str,
        choices: frozenset[str],
        *,
        required: bool = False,
        default: str | None = None,
    ) -> str | None:
        value = self.text(column, required=required)
        if value is None:
            return default
        if value not in choices:
            self.fail(column, "invalid_choice", "allowed: " + ", ".join(sorted(choices)))
            return None
        return value


def custom_value(data_type: str, text: str) -> Any:
    """Typed custom-field cell; the native validator still applies every definition rule."""
    if data_type == "integer":
        if not re.fullmatch(r"-?[0-9]{1,18}", text):
            raise ValueError("integer required")
        return int(text)
    if data_type == "boolean":
        if text.lower() in TRUE:
            return True
        if text.lower() in FALSE:
            return False
        raise ValueError("boolean required")
    if data_type == "multi_select":
        return [part.strip() for part in text.split("|") if part.strip()]
    if data_type == "currency_amount":
        amount, _, currency = text.partition(" ")
        return {"amount": amount, "currency": currency}
    if data_type in {
        "text",
        "long_text",
        "select",
        "dynamic_select",
        "date",
        "datetime",
        "decimal",
    }:
        return text
    raise ValueError("custom field type cannot be imported")


def _custom(reader: _Reader, columns: Iterable[CustomColumn]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in columns:
        name = "cf." + column.key
        value = reader.text(name, limit=4000)
        if value is None:
            continue
        try:
            result[column.key] = custom_value(column.data_type, value)
        except ValueError:
            reader.fail(name, "invalid_custom_field", f"value must be a {column.data_type}")
    return result


def prefix(kind: str) -> str:
    return "supplier" if PARTY_ROLE[kind] == "SUPPLIER" else "customer"


def parse(
    item: Staged, shape: Template, kind: str = "PURCHASE"
) -> tuple[Parsed | None, list[Issue]]:
    """L2 lexical/type checks for one staged voucher; never coerces floats or dates."""
    issues = list(item.issues)
    sheet, number = item.rows[0]
    head = _Reader(item.header, sheet, number, issues)
    names = set(shape.names("header"))
    side = prefix(kind)
    note = kind in NOTE_KINDS
    document_date = head.date("document_date", required=True)
    posting_date = head.date("posting_date") if "posting_date" in names else None
    party_code = head.pattern(f"{side}_code", CODE, "codes are at most 40 characters")
    party_gstin = head.pattern(f"{side}_gstin", GSTIN, "GSTIN has 15 capital characters")
    if (party_code is None) == (party_gstin is None) and not any(
        issue.column in {f"{side}_code", f"{side}_gstin"} for issue in issues
    ):
        head.fail(
            f"{side}_code", f"{side}_required", f"give exactly one of {side}_code or {side}_gstin"
        )
    class_code = head.pattern("voucher_class_code", CODE, "codes are at most 40 characters")
    ledger_code = head.pattern(f"{side}_ledger_code", CODE, "codes are at most 40 characters")
    currency = head.pattern(
        "currency", re.compile(r"[A-Z]{3}"), "use an ISO 4217 code", required=True
    )
    narration = head.text("narration", limit=2000) if "narration" in names else None
    extra: dict[str, Any] = {}
    if kind == "PURCHASE":
        extra["supplier_invoice_number"] = head.text("supplier_invoice_number", required=True)
        extra["supplier_invoice_date"] = head.date("supplier_invoice_date", required=True)
        extra["declared_total"] = head.decimal("supplier_declared_total", required=True)
        extra["difference_reason"] = head.text("supplier_difference_reason", limit=500)
    if kind == "SALES":
        extra["source_reference"] = head.text("source_reference")
        extra["source_reference_date"] = head.date("source_reference_date")
        extra["order_number"] = head.text("customer_order_number")
        extra["order_date"] = head.date("customer_order_date")
    if note:
        original = "original_invoice_number" if kind == "CREDIT_NOTE" else "original_bill_number"
        extra["original_number"] = head.text(original, required=True)
        extra["return_reference"] = head.text("return_reference")
    else:
        extra["due_date"] = head.date("due_date")
        extra["exchange_rate"] = head.decimal("exchange_rate", rate=True)
        extra["place_of_supply"] = head.pattern(
            "place_of_supply", re.compile(r"IN-[A-Z0-9]{1,3}"), "use IN-<state code>"
        )
        extra["tax_profile"] = head.choice("tax_profile", TAX_PROFILES, required=True)
        if extra["exchange_rate"] == 0:
            head.fail("exchange_rate", "invalid_decimal", "exchange rate must be positive")
    custom = _custom(head, (c for c in shape.header if isinstance(c, CustomColumn)))
    lines: list[ParsedLine] = []
    seen: set[int] = set()
    originals: set[int] = set()
    line_names = set(shape.names("line"))
    for cells in item.lines:
        reader = _Reader(cells, cells.get("_sheet", sheet), int(cells.get("_row", number)), issues)
        raw_no = reader.pattern(
            "line_no", re.compile(r"[1-9][0-9]{0,2}"), "use 1-200", required=True
        )
        line_no = int(raw_no) if raw_no is not None else None
        if line_no is not None and (line_no > MAX_LINES or line_no in seen):
            reader.fail("line_no", "invalid_line_no", "line_no must be unique and at most 200")
        description = reader.text("description", required=True, limit=1000)
        amount = reader.decimal("amount", required=True)
        if amount == 0:
            reader.fail("amount", "invalid_decimal", "amount must be positive")
            amount = None
        if line_no is not None:
            seen.add(line_no)
        if note:
            raw = reader.pattern(
                "original_line_no",
                re.compile(r"[1-9][0-9]{0,2}"),
                "use the original line number",
                required=True,
            )
            original_no = int(raw) if raw is not None else None
            if original_no is not None and original_no in originals:
                reader.fail(
                    "original_line_no", "invalid_line_no", "return each original line once per note"
                )
            if original_no is not None:
                originals.add(original_no)
            if None not in (line_no, description, amount, original_no):
                lines.append(
                    ParsedLine(
                        line_no or 0,
                        None,
                        None,
                        description or "",
                        amount or Decimal(0),
                        "NET_EXCL_TAX",
                        None,
                        None,
                        original_no,
                    )
                )
            continue
        supply = reader.text("supply_kind", required=True)
        if supply == "GOODS":
            reader.fail(
                "supply_kind",
                "unsupported_supply_kind",
                "goods lines are not importable yet; use ACCOUNT or SERVICE",
            )
            supply = None
        elif supply is not None and supply not in SUPPLY_KINDS:
            reader.fail("supply_kind", "invalid_choice", "allowed: ACCOUNT, SERVICE")
            supply = None
        account = reader.pattern(
            "account_code", CODE, "codes are at most 40 characters", required=True
        )
        basis = reader.choice("price_basis", PRICE_BASES, default="NET_EXCL_TAX")
        pct = reader.decimal("discount_pct") if "discount_pct" in line_names else None
        fixed = reader.decimal("discount_amount") if "discount_amount" in line_names else None
        if pct is not None and pct > 100:
            reader.fail("discount_pct", "invalid_decimal", "discount percent exceeds 100")
        if pct is not None and fixed is not None:
            reader.fail(
                "discount_amount",
                "discount_conflict",
                "give discount_pct or discount_amount, not both",
            )
        if None not in (line_no, supply, account, description, amount, basis):
            lines.append(
                ParsedLine(
                    line_no or 0,
                    supply,
                    account,
                    description or "",
                    amount or Decimal(0),
                    basis or "",
                    pct,
                    fixed,
                )
            )
    required = (
        [document_date, currency]
        + [
            extra[key]
            for key in (
                ("supplier_invoice_number", "supplier_invoice_date", "declared_total")
                if kind == "PURCHASE"
                else ("original_number",)
                if note
                else ()
            )
        ]
        + ([] if note else [extra["tax_profile"]])
    )
    if issues or any(value is None for value in required):
        return None, issues
    assert document_date is not None and currency is not None
    if extra.get("tax_profile") is None:
        extra.pop("tax_profile", None)
    return (
        Parsed(
            import_key=item.import_key,
            class_code=class_code,
            document_date=document_date,
            posting_date=posting_date or document_date,
            party_code=party_code,
            party_gstin=party_gstin,
            party_ledger_code=ledger_code,
            currency=currency,
            narration=narration,
            custom=custom,
            lines=tuple(sorted(lines, key=lambda line: line.line_no)),
            kind=kind,
            **extra,
        ),
        [],
    )


DUPLICATE_RULES = ("DATE_NUMBER_PARTY", "DATE_NUMBER", "DATE_NUMBER_ACCOUNT")


def bill_key(
    rule: str, number: str, date: dt.date, *, party: str | None, account: str | None
) -> tuple[str, ...]:
    """Duplicate identity: same bill number and bill date, optionally the same supplier.

    ``DATE_NUMBER_PARTY`` (default) adds the supplier party, ``DATE_NUMBER_ACCOUNT`` the
    supplier's party ledger, and ``DATE_NUMBER`` matches any supplier.
    """
    if rule not in DUPLICATE_RULES:
        raise ValueError("unsupported duplicate rule")
    key = (number.strip().casefold(), date.isoformat())
    if rule == "DATE_NUMBER_PARTY":
        return (*key, "party:" + (party or ""))
    if rule == "DATE_NUMBER_ACCOUNT":
        return (*key, "account:" + (account or ""))
    return key


def duplicate_identity(parsed: Parsed, rule: str) -> tuple[str, ...]:
    """Textual within-file Purchase identity before masters are resolved."""
    assert parsed.supplier_invoice_number is not None
    assert parsed.supplier_invoice_date is not None
    return bill_key(
        rule,
        parsed.supplier_invoice_number,
        parsed.supplier_invoice_date,
        party=parsed.party_text,
        account=parsed.party_text + "/" + (parsed.party_ledger_code or "").casefold(),
    )


def file_identities(parsed: Parsed, rule: str) -> list[tuple[tuple[str, ...], str, str]]:
    """Textual identities checked inside the uploaded file: (key, column, code)."""
    if parsed.kind == "PURCHASE":
        return [
            (
                duplicate_identity(parsed, rule),
                "supplier_invoice_number",
                "duplicate_supplier_invoice",
            )
        ]
    if parsed.kind == "SALES" and parsed.source_reference:
        return [
            (
                ("external", parsed.source_reference.casefold()),
                "source_reference",
                "duplicate_reference",
            )
        ]
    if parsed.kind in NOTE_KINDS and parsed.return_reference:
        return [
            (
                ("external", parsed.party_text, parsed.return_reference.casefold()),
                "return_reference",
                "duplicate_reference",
            )
        ]
    return []


def resolve(
    parsed: Parsed, found: Resolution, sheet: str, row: int
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """L4: exact, active, unambiguous masters; nothing is ever created from a file."""
    issues: list[Issue] = []
    side = prefix(parsed.kind)
    role = PARTY_ROLE[parsed.kind]

    def fail(column: str, code: str, message: str) -> None:
        issues.append(Issue(sheet, row, column, code, message, "L4"))

    party: tuple[uuid.UUID, Master] | None = None
    if parsed.party_code is not None:
        match = found.party(parsed.party_code)
        if match is None:
            fail(f"{side}_code", "unknown_master", f"{side} code does not exist")
        else:
            party = (match.source_id, match)
    else:
        ids = found.gstin_parties.get(parsed.party_gstin or "", ())
        if len(ids) > 1:
            fail(f"{side}_gstin", "ambiguous_master", "GSTIN belongs to several parties")
        elif not ids or ids[0] not in found.party_ids:
            fail(f"{side}_gstin", "unknown_master", f"no {side} has this GSTIN")
        else:
            party = (ids[0], found.party_ids[ids[0]])
    if party is not None and party[1].status != "ACTIVE":
        fail(f"{side}_code", "inactive_master", f"{side} is not active")
    ledger: Master | None = None
    if party is not None:
        ledgers = [
            (code, row)
            for code, row in found.party_ledgers.get(party[0], ())
            if row.status == "ACTIVE" and found.ledger_roles.get(row.source_id) in {None, role}
        ]
        if parsed.party_ledger_code is not None:
            wanted = parsed.party_ledger_code.casefold()
            ledgers = [item for item in ledgers if item[0].casefold() == wanted]
        if not ledgers:
            fail(
                f"{side}_ledger_code",
                "unknown_master",
                f"{side} has no active {role.lower()} ledger",
            )
        elif len(ledgers) > 1:
            fail(
                f"{side}_ledger_code",
                "ambiguous_master",
                f"{side} has several ledgers; give {side}_ledger_code",
            )
        else:
            ledger = ledgers[0][1]
    accounts: dict[int, Master] = {}
    for line in parsed.lines:
        if line.account_code is None:
            continue
        account = found.account(line.account_code)
        if account is None:
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
        elif account.status != "ACTIVE":
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
        else:
            accounts[line.line_no] = account
    if issues or party is None or ledger is None:
        return None, issues
    return {"party": party, "ledger": ledger, "accounts": accounts}, []


def original(
    parsed: Parsed, masters: dict[str, Any], found: Resolution, sheet: str, row: int
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """A note's original invoice: posted, returnable, same party ledger and currency.

    Returned amounts never exceed what remains on each original line (owner-reported, before
    unposted drafts, which the caller subtracts).
    """
    issues: list[Issue] = []
    column = "original_invoice_number" if parsed.kind == "CREDIT_NOTE" else "original_bill_number"

    def fail(name: str, code: str, message: str) -> None:
        issues.append(Issue(sheet, row, name, code, message, "L4"))

    assert parsed.original_number is not None
    ledger: Master = masters["ledger"]
    matches = found.invoice(ORIGINAL_KIND[parsed.kind], ledger.source_id, parsed.original_number)
    if not matches:
        fail(column, "unknown_original", "no original invoice with this number for the party")
        return None, issues
    if len(matches) > 1:
        fail(column, "ambiguous_original", "several original invoices have this number")
        return None, issues
    source = matches[0]
    if not source.returnable:
        fail(
            column,
            "original_not_returnable",
            "only posted untaxed originals without discounts, charges or rounding can be "
            "returned by import",
        )
    if source.currency != parsed.currency:
        fail("currency", "currency_mismatch", "the note must use the original invoice currency")
    if parsed.posting_date < source.posting_date:
        fail("posting_date", "before_original", "the note cannot be posted before the original")
    lines = {line.sequence: line for line in source.lines}
    chosen: dict[int, OriginalLine] = {}
    for line in parsed.lines:
        match = lines.get(line.original_line_no or 0)
        if match is None:
            fail(
                "original_line_no",
                "unknown_original_line",
                f"line {line.line_no}: the original invoice has no such line",
            )
        elif not match.untaxed:
            fail(
                "original_line_no",
                "original_not_returnable",
                f"line {line.line_no}: the original line is taxed",
            )
        else:
            chosen[line.line_no] = match
    if issues:
        return None, issues
    return {"source_id": source.source_id, "lines": chosen}, []


def content(
    parsed: Parsed,
    masters: dict[str, Any],
    *,
    job_id: uuid.UUID,
    type_revision_id: uuid.UUID,
    class_id: uuid.UUID | None,
    payment_days: int,
    include: frozenset[str],
    versions: Mapping[uuid.UUID, int] | None = None,
    bill: OpenBill | None = None,
) -> dict[str, Any]:
    """Native ``VoucherInput`` JSON with deterministic line identities per job and key.

    Notes reuse the original line identities and ledgers (the owner matches them) and adjust
    the original party bill by up to its outstanding amount.
    """

    def key(suffix: str) -> str:
        return str(uuid.uuid5(job_id, f"{parsed.import_key}:{suffix}"))

    party_id, party = masters["party"]
    ledger: Master = masters["ledger"]
    note = parsed.kind in NOTE_KINDS
    supplies, components = [], []
    for line in parsed.lines:
        if note:
            source: OriginalLine = masters["original"]["lines"][line.line_no]
            supplies.append(
                {
                    "line_key": str(source.line_key),
                    "account_id": str(source.account_id),
                    "account_version": (versions or {})[source.account_id],
                    "supply_kind": source.supply_kind,
                    "description": line.description,
                    "amount": format(line.amount, "f"),
                }
            )
            continue
        account: Master = masters["accounts"][line.line_no]
        line_key = key(f"line:{line.line_no}")
        supplies.append(
            {
                "line_key": line_key,
                "account_id": str(account.source_id),
                "account_version": account.source_version,
                "supply_kind": line.supply_kind,
                "description": line.description,
                "amount": format(line.amount, "f"),
                "price_basis": line.price_basis,
            }
        )
        if line.discount_pct is not None or line.discount_amount is not None:
            components.append(
                {
                    "component_key": key(f"discount:{line.line_no}"),
                    "purpose": "DISCOUNT",
                    "scope": "LINE",
                    "effect": "DEDUCT",
                    "input_kind": "PERCENT" if line.discount_pct is not None else "FIXED",
                    "value": format(
                        line.discount_pct
                        if line.discount_pct is not None
                        else line.discount_amount or Decimal(0),
                        "f",
                    ),
                    "targets": [line_key],
                    "source_evidence": "Bill discount (import)",
                }
            )
    tax: dict[str, Any] = {"profile": parsed.tax_profile}
    if parsed.kind == "PURCHASE":
        assert parsed.supplier_invoice_date is not None
        tax |= {
            "supplier_invoice_number": parsed.supplier_invoice_number,
            "supplier_invoice_date": parsed.supplier_invoice_date.isoformat(),
        }
    if parsed.place_of_supply:
        tax["place_of_supply"] = parsed.place_of_supply
    reference = (
        parsed.supplier_invoice_number
        or parsed.source_reference
        or parsed.return_reference
        or "IMP-" + parsed.import_key
    )
    basis = parsed.supplier_invoice_date or parsed.document_date
    party_line = key("party")
    invoice: dict[str, Any] = {
        "party_line_key": party_line,
        "party_account_id": str(ledger.source_id),
        "party_account_version": ledger.source_version,
        "bill_reference": reference,
        "due_date": (parsed.due_date or basis + dt.timedelta(days=payment_days)).isoformat(),
        "exchange_rate": format(parsed.exchange_rate or Decimal(1), "f"),
        "tax": tax,
        "supplies": supplies,
        "components": components,
    }
    if note:
        invoice["source_invoice_id"] = str(masters["original"]["source_id"])
        total = sum((line.amount for line in parsed.lines), start=Decimal(0))
        if bill is not None and bill.remaining > 0:
            invoice["allocations"] = [
                {
                    "allocation_key": key("original-bill"),
                    "debt": {"item_id": str(bill.item_id)},
                    "credit": {"line_key": party_line},
                    "amount": format(min(total, bill.remaining), "f"),
                    "currency": parsed.currency,
                }
            ]
    if parsed.declared_total is not None:
        invoice["supplier_declared_total"] = format(parsed.declared_total, "f")
    if parsed.difference_reason:
        invoice["supplier_difference_reason"] = parsed.difference_reason
    body: dict[str, Any] = {
        "type_revision_id": str(type_revision_id),
        "document_date": parsed.document_date.isoformat(),
        "currency": parsed.currency,
        "invoice": invoice,
        "parties": [
            {
                "role": PARTY_ROLE[parsed.kind],
                "party_id": str(party_id),
                "source_version": party.source_version,
            }
        ],
        "custom_fields": parsed.custom,
    }
    if class_id is not None:
        body["class_id"] = str(class_id)
    if "posting_date" in include:
        body["posting_date"] = parsed.posting_date.isoformat()
    references: list[dict[str, Any]] = []
    if parsed.kind == "PURCHASE":
        references.append(
            {
                "purpose": "SUPPLIER_INVOICE",
                "reference": parsed.supplier_invoice_number,
                "reference_date": basis.isoformat(),
            }
        )
    for text, day in (
        (parsed.source_reference, parsed.source_reference_date),
        (parsed.return_reference, None),
    ):
        if text:
            references.append(
                {"purpose": "EXTERNAL", "reference": text}
                | ({"reference_date": day.isoformat()} if day else {})
            )
    if parsed.order_number:
        references.append(
            {"purpose": "CUSTOMER_ORDER", "reference": parsed.order_number}
            | ({"reference_date": parsed.order_date.isoformat()} if parsed.order_date else {})
        )
    if references and "references" in include:
        body["references"] = references
    if parsed.narration is not None and "narration" in include:
        body["narration"] = parsed.narration
    return body


def control(
    declared: Decimal,
    payable: Decimal,
    limit: Decimal,
    reason: str | None,
    *,
    sheet: str = "vouchers",
    row: int = 1,
) -> tuple[State, Decimal, Issue | None]:
    """L7: supplier total against the native payable and the policy tolerance."""
    difference = declared - payable
    if abs(difference) > limit:
        return (
            "INVALID",
            difference,
            Issue(
                sheet,
                row,
                "supplier_declared_total",
                "supplier_total_mismatch",
                "supplier total differs from the calculated payable beyond the tolerance",
                "L7",
            ),
        )
    if difference and not reason:
        return (
            "INVALID",
            difference,
            Issue(
                sheet,
                row,
                "supplier_difference_reason",
                "difference_reason_required",
                "a tolerated supplier difference requires a reason",
                "L7",
            ),
        )
    return ("WARNING" if difference else "VALID"), difference, None
