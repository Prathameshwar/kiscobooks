import csv
import datetime as dt
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from reports.domain.reporting.contracts import Column
from reports.rendering.tabular import Budget, CsvWriter, XlsxWriter, safe_number, value

BUDGET = Budget(100, 10000, 10000000, 60)
COLUMNS = (
    Column("account", "Account", "IDENTIFIER"),
    Column("text", "Description"),
    Column("amount", "Amount", "MONEY"),
    Column("date", "Date", "DATE"),
    Column("count", "Count", "INTEGER"),
)
NAMESPACE = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def test_csv_keeps_exact_money_unicode_and_identifiers_and_escapes_untrusted_text(tmp_path):
    path = tmp_path / "report.csv"
    writer = CsvWriter(path, COLUMNS, BUDGET)
    writer.append(
        [
            {
                "account": "000123",
                "text": "=SUM(1,2)\nहिन्दी",
                "amount": "-999999999999999.9999",
                "date": "2026-04-01",
                "count": 3,
            }
        ]
    )
    writer.finish()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1] == ["000123", "'=SUM(1,2)\nहिन्दी", "-999999999999999.9999", "2026-04-01", "3"]


def test_xlsx_splits_complete_sheets_and_keeps_unsafe_precision_as_exact_text(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("reports.rendering.tabular.EXCEL_ROWS", 4)
    path = tmp_path / "report.xlsx"
    writer = XlsxWriter(path, COLUMNS, BUDGET)
    amounts = ["1234567890123.45", "999999999999999.9999", "-0.0100", "1", "2", "3", "4"]
    writer.append(
        {
            "account": "000123",
            "text": '=HYPERLINK("https://invalid")',
            "amount": amount,
            "date": "2026-04-01",
            "count": index,
        }
        for index, amount in enumerate(amounts)
    )
    writer.finish()
    assert writer.count == 7
    with zipfile.ZipFile(path) as archive:
        sheets = [
            # Only this test's locally generated workbook is parsed; no uploaded XML.
            ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))  # noqa: S314
            for index in (1, 2, 3)
        ]
        assert [len(sheet.findall("s:sheetData/s:row", NAMESPACE)) for sheet in sheets] == [4, 4, 2]
        assert not any(sheet.findall(".//s:f", NAMESPACE) for sheet in sheets)
        assert not any("hyperlink" in name for name in archive.namelist())
        cells = {cell.attrib["r"]: cell for cell in sheets[0].findall(".//s:c", NAMESPACE)}
        assert cells["A2"].find("s:is/s:t", NAMESPACE).text == "000123"
        assert Decimal(cells["C2"].find("s:v", NAMESPACE).text) == Decimal("1234567890123.45")
        assert cells["C3"].attrib["t"] == "inlineStr"
        assert cells["C3"].find("s:is/s:t", NAMESPACE).text == amounts[1]


@pytest.mark.parametrize("writer_type", [CsvWriter, XlsxWriter])
def test_export_never_silently_truncates_rows_or_overlong_cells(tmp_path, writer_type):
    writer = writer_type(tmp_path / "output", COLUMNS, Budget(1, 100, 1000000, 60))
    with pytest.raises(ValueError, match="budget"):
        writer.append([{}, {}])
    writer.abort()
    writer = writer_type(tmp_path / "other", COLUMNS, BUDGET)
    with pytest.raises(ValueError, match="text limit"):
        writer.append([{"text": "a" * 32768}])
    writer.abort()


def test_typed_export_values_reject_loss_and_missing_required_data():
    assert value(Column("v", "v", "MONEY"), {"v": "1.2300"}) == Decimal("1.2300")
    assert value(Column("v", "v", "DATE"), {"v": "2026-04-01"}) == dt.date(2026, 4, 1)
    assert safe_number(Decimal("1234567890123.45"))
    assert not safe_number(Decimal("12345678901234.56"))
    for column, raw in (
        (Column("v", "v", "MONEY"), 1.2),
        (Column("v", "v", "INTEGER"), "1.2"),
        (Column("v", "v", "BOOLEAN"), "false"),
        (Column("v", "v"), {"nested": "object"}),
        (Column("v", "v", nullable=False), None),
    ):
        with pytest.raises(ValueError):
            value(column, {"v": raw})


def test_aggregate_exports_keep_wide_exact_totals(tmp_path):
    total = "123456789012345678901234567890.1234"
    columns = (Column("total", "Total", "MONEY"),)
    assert value(columns[0], {"total": total}) == Decimal(total)
    writer = CsvWriter(tmp_path / "aggregate.csv", columns, BUDGET)
    writer.append([{"total": total}])
    writer.finish()
    assert total in (tmp_path / "aggregate.csv").read_text(encoding="utf-8-sig")
    for invalid in ("1.00001", "1e100", "0e-1000000000", True, "NaN", "Infinity"):
        with pytest.raises(ValueError):
            value(columns[0], {"total": invalid})
