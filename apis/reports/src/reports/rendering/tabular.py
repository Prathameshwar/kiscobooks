"""Bounded sequential CSV/XLSX writers with explicit exact-value policies."""

import csv
import datetime as dt
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import xlsxwriter  # type: ignore[import-untyped]  # Upstream 3.2.9 has no PEP 561 marker.
from billing_platform.bulk_files import safe_spreadsheet_text

from reports.domain.reporting.contracts import Column

if TYPE_CHECKING:
    from reports.rendering.presentation import Document

EXCEL_ROWS = 1048576
EXACT_POLICY = "Decimal values above 15 digits are exact text; identifiers are always text."


@dataclass(frozen=True)
class Budget:
    rows: int
    cells: int
    bytes: int
    seconds: int
    scratch_bytes: int | None = None


class Writer(Protocol):
    count: int

    def append(self, rows: Iterable[dict[str, Any]]) -> None: ...

    def finish(self) -> None: ...

    def abort(self) -> None: ...


def exact_number(raw: Any) -> Decimal:
    """Frozen aggregate values may exceed a single DECIMAL(19,4) posting line."""
    if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal):
        raise ValueError("export numbers require exact decimal values")
    if isinstance(raw, str) and len(raw) > 128:
        raise ValueError("export number exceeds its text bound")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("export number is invalid") from exc
    if not number.is_finite() or number.adjusted() >= 34:
        raise ValueError("export aggregate exceeds DECIMAL(38,4)")
    exponent = number.as_tuple().exponent
    assert isinstance(exponent, int)
    if exponent < -18:
        raise ValueError("export number exceeds its scale bound")
    if exponent < -4:
        with localcontext() as arithmetic:
            arithmetic.prec = 38
            rounded = number.quantize(Decimal("0.0001"))
        if rounded != number:
            raise ValueError("export number exceeds its exact scale")
        return rounded
    return number


def value(
    column: Column,
    row: dict[str, Any],
    parse: Callable[[Any], Decimal] = exact_number,
) -> str | int | Decimal | dt.date | bool | None:
    raw = row.get(column.key)
    if raw is None:
        if not column.nullable:
            raise ValueError("non-null export column is absent")
        return None
    if column.kind in {"MONEY", "DECIMAL"}:
        if isinstance(raw, bool) or not isinstance(raw, str | int | Decimal):
            raise ValueError("export numbers require exact decimal values")
        result = parse(raw)
        if not result.is_finite():
            raise ValueError("export number must be finite")
        return result
    if column.kind == "INTEGER":
        number = exact_number(raw)
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError("export integer is invalid")
        return int(number)
    if column.kind == "DATE":
        return dt.date.fromisoformat(str(raw))
    if column.kind == "BOOLEAN":
        if type(raw) is not bool:
            raise ValueError("export boolean is invalid")
        return raw
    if not isinstance(raw, str | int):
        raise ValueError("export text must be scalar")
    text = str(raw)
    if len(text) > 32767:
        raise ValueError("export cell exceeds the portable text limit")
    return text


def safe_number(number: Decimal | int) -> bool:
    decimal = number if isinstance(number, Decimal) else Decimal(number)
    digits = decimal.as_tuple().digits
    significant = len(digits)
    while significant > 1 and digits[significant - 1] == 0:
        significant -= 1
    return significant <= 15 and -300 <= decimal.adjusted() <= 14


class BoundedWriter:
    def __init__(self, path: Path, columns: tuple[Column, ...], budget: Budget):
        if not columns or len(columns) > 200:
            raise ValueError("export requires between one and 200 registered columns")
        self.path, self.columns, self.budget = path, columns, budget
        self.count, self.started = 0, time.monotonic()
        # Per-export bounded caches share repeated amounts across metric columns; no rows or
        # tenant payloads are retained between jobs. typed=True keeps bool/float rejection intact.
        self.decimals = lru_cache(maxsize=4096, typed=True)(exact_number)
        self.numeric_cell = lru_cache(maxsize=4096, typed=True)(safe_number)

    def check(self, added: int = 0) -> None:
        if (
            self.count + added > self.budget.rows
            or (self.count + added) * len(self.columns) > self.budget.cells
        ):
            raise ValueError("export exceeds its row or cell budget")
        if time.monotonic() - self.started > self.budget.seconds:
            raise ValueError("export exceeds its time budget")
        # XLSX's uncompressed sheets and ZIP can coexist. Bound total scratch as well as output.
        if sum(path.stat().st_size for path in self.path.parent.iterdir() if path.is_file()) > (
            self.budget.scratch_bytes or self.budget.bytes
        ):
            raise ValueError("export exceeds its disk budget")


class CsvWriter(BoundedWriter):
    def __init__(self, path: Path, columns: tuple[Column, ...], budget: Budget):
        super().__init__(path, columns, budget)
        self.stream = path.open("x", encoding="utf-8-sig", newline="")
        self.writer = csv.writer(self.stream, lineterminator="\r\n")
        self.writer.writerow([column.title for column in columns])

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            self.count += 1
            if self.count > self.budget.rows or self.count * len(self.columns) > self.budget.cells:
                raise ValueError("export exceeds its row or cell budget")
            values = []
            for column in self.columns:
                cell = value(column, row, self.decimals)
                if isinstance(cell, Decimal):
                    cell = format(cell, "f")
                elif isinstance(cell, str):
                    cell = safe_spreadsheet_text(cell)
                values.append(cell)
            self.writer.writerow(values)
        self.stream.flush()
        self.check()

    def finish(self) -> None:
        self.stream.close()
        self.check()

    def abort(self) -> None:
        self.stream.close()


class XlsxWriter(BoundedWriter):
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        document: "Document | None" = None,
    ):
        super().__init__(path, columns, budget)
        from reports.rendering.presentation import bundle

        self.document = document
        tokens = bundle()["tokens"]
        self.book = xlsxwriter.Workbook(
            str(path),
            {
                "constant_memory": True,
                "tmpdir": str(path.parent),
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "strings_to_numbers": False,
                "use_zip64": True,
            },
        )
        self.book.set_properties({"comments": EXACT_POLICY})
        common = {
            "font_name": "Noto Sans",
            "font_size": float(tokens["--report-xlsx-body-size"]),
            "font_color": tokens["--janso-ink"],
        }
        self.header = self.book.add_format(
            common
            | {
                "bold": True,
                "text_wrap": True,
                "bottom": 1,
                "bottom_color": tokens["--janso-brand"],
                "bg_color": tokens["--janso-brand-tint"],
                "font_color": tokens["--janso-brand-ink"],
            }
        )
        # Data exports retain storage scale, independent of Excel's rounding/locale rules.
        # The About sheet identifies this policy; HTML/PDF apply company display rounding.
        self.numeric = self.book.add_format(common | {"num_format": "0.0000;-0.0000"})
        self.date = self.book.add_format(common | {"num_format": "yyyy-mm-dd"})
        self.text = self.book.add_format(common | {"num_format": "@"})
        self.sheet_number, self.sheet_row = 0, 0
        self.sheet: Any
        self.new_sheet()

    def new_sheet(self) -> None:
        if self.sheet_number:
            self.sheet.autofilter(0, 0, self.sheet_row - 1, len(self.columns) - 1)
        self.sheet_number += 1
        self.sheet = self.book.add_worksheet(f"Report {self.sheet_number}")
        self.sheet.freeze_panes(1, 0)
        self.sheet.repeat_rows(0)
        self.sheet.set_row(0, 32)
        self.sheet.set_landscape()
        self.sheet.fit_to_pages(1, 0)
        if self.document is not None:
            self.sheet.set_header(
                "&L" + self.document.display.company_label.replace("&", "&&")[:100]
            )
            self.sheet.set_footer("&LReport " + self.document.run_id + "&RPage &P")
        for index, column in enumerate(self.columns):
            self.sheet.set_column(index, index, min(36, max(16, len(column.title) + 2)))
            self.sheet.write_string(0, index, column.title, self.header)
        self.sheet_row = 1

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            self.count += 1
            if self.count > self.budget.rows or self.count * len(self.columns) > self.budget.cells:
                raise ValueError("export exceeds its row or cell budget")
            if self.sheet_row >= EXCEL_ROWS:
                self.new_sheet()
            if "node_key" in row and row.get("row_kind") in {"HEAD", "GROUP", "ACCOUNT"}:
                self.sheet.set_row(self.sheet_row, None, None, {"level": min(7, row["depth"])})
            for index, column in enumerate(self.columns):
                cell = value(column, row, self.decimals)
                if cell is None:
                    continue
                if isinstance(cell, bool):
                    status = self.sheet.write_boolean(self.sheet_row, index, cell)
                elif isinstance(cell, dt.date) and cell >= dt.date(1900, 1, 1):
                    status = self.sheet.write_datetime(self.sheet_row, index, cell, self.date)
                elif isinstance(cell, Decimal | int) and self.numeric_cell(cell):
                    status = self.sheet.write_number(
                        self.sheet_row,
                        index,
                        cell,
                        self.numeric if isinstance(cell, Decimal) else None,
                    )
                else:
                    text = format(cell, "f") if isinstance(cell, Decimal) else str(cell)
                    status = self.sheet.write_string(self.sheet_row, index, text, self.text)
                if status != 0:
                    raise ValueError("spreadsheet cell could not be written without loss")
            self.sheet_row += 1
        self.check()

    def finish(self) -> None:
        self.sheet.autofilter(0, 0, self.sheet_row - 1, len(self.columns) - 1)
        if self.document is not None:
            sheet = self.book.add_worksheet("About this report")
            sheet.set_column(0, 0, 24)
            sheet.set_column(1, 1, 80)
            metadata = (
                ("Report", self.document.title),
                ("Company", self.document.display.company_label),
                ("Period", self.document.period),
                ("Source as of", self.document.source_as_of),
                ("Report ID", self.document.run_id),
                ("Precision", EXACT_POLICY),
                (
                    "Display",
                    "Canonical values retain four stored decimals and ISO dates. "
                    "HTML/PDF use company display rounding. "
                    "Spreadsheet applications may localize separators.",
                ),
            )
            for index, (label, text) in enumerate(metadata + self.document.filters):
                sheet.write_string(index, 0, label, self.header)
                sheet.write_string(index, 1, text, self.text)
        self.book.close()
        self.check()

    def abort(self) -> None:
        self.book.close()
