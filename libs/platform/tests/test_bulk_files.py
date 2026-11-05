import io
import zipfile

import pytest

from billing_platform.bulk import MAX_BYTES
from billing_platform.bulk_files import (
    Cell,
    column,
    csv_document,
    read_csv,
    read_xlsx,
    safe_spreadsheet_text,
    table,
    xlsx_document,
    xml,
)


def workbook_part(raw: bytes, path: str, content: bytes) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(result, "w") as output:
        for item in original.infolist():
            output.writestr(
                item.filename, content if item.filename == path else original.read(item)
            )
    return result.getvalue()


def sample() -> bytes:
    return xlsx_document(["_key", "code", "amount"], [["first", "0000012345678", "12.5000"]])


def test_csv_xlsx_preserve_text_codes_and_exact_lexical_amounts() -> None:
    headers, rows = ["_key", "code", "amount"], [["first", "0000012345678", "12.5000"]]
    csv_rows = read_csv(csv_document(headers, rows, template=True))
    excel_rows = read_xlsx(sample())
    assert csv_rows[0].cells == excel_rows[0].cells
    assert excel_rows[0].number == 3 and excel_rows[0].cells["amount"].value == "12.5000"
    assert column("DX2002") == 127
    for value in ("=1+1", "+cmd", "-cmd", "@SUM(1)", "\ttext", "\rtext", "  =1"):
        assert safe_spreadsheet_text(value).startswith("'")
    assert safe_spreadsheet_text("000001") == "000001"
    assert csv_document(["error"], [["=1+1"]]).decode("utf-8") == "error\r\n'=1+1\r\n"


@pytest.mark.parametrize(
    "raw",
    [b"", b"x" * (MAX_BYTES + 1), b"\xff", b"\x00", b'"unterminated'],
    ids=["empty", "oversized", "encoding", "nul", "quote"],
)
def test_invalid_csv_is_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        read_csv(raw)


def test_malformed_tables_coordinates_and_xml_are_rejected() -> None:
    for rows in (
        [],
        [[Cell("wrong")]],
        [[Cell("_catalog_schema_version"), Cell("1")], [Cell("x"), Cell("x")]],
        [[Cell("_catalog_schema_version"), Cell("1")], [Cell("x")], [Cell("a"), Cell("b")]],
    ):
        with pytest.raises(ValueError):
            table(rows, "CSV")
    for coordinate in ("A0", "a1", "DXY3", "A2003", "not-a-cell"):
        with pytest.raises(ValueError):
            column(coordinate)
    for raw in (b'<!DOCTYPE foo [<!ENTITY x "y">]><foo/>', b"<foo>\x00</foo>"):
        with pytest.raises(ValueError):
            xml(raw)
    with pytest.raises(ValueError):
        read_xlsx(b"not a zip file")


def test_workbook_formula_external_relationship_and_macro_types_are_refused() -> None:
    raw = sample()
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        sheet = original.read("xl/worksheets/sheet1.xml")
        relationships = original.read("xl/_rels/workbook.xml.rels")
        content_types = original.read("[Content_Types].xml")
    formula = sheet.replace(b'<c r="A3"', b'<c r="A3"', 1).replace(
        b"<is><t>first</t></is>", b"<f>1+1</f><v>2</v>"
    )
    for path, content in (
        ("xl/worksheets/sheet1.xml", formula),
        (
            "xl/_rels/workbook.xml.rels",
            relationships.replace(
                b'Target="worksheets', b'TargetMode="External" Target="worksheets'
            ),
        ),
        (
            "[Content_Types].xml",
            content_types.replace(
                b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml"
            ),
        ),
    ):
        with pytest.raises(ValueError):
            read_xlsx(workbook_part(raw, path, content))


def test_service_marker_and_multi_sheet_workbook_round_trip() -> None:
    from billing_platform.bulk_files import xlsx_workbook

    marker = "_voucher_schema_version"
    raw = xlsx_workbook(
        [
            ("vouchers", ["import_key", "total"], [["v1", "10.0000"]]),
            ("lines", ["import_key", "line_no"], [["v1", "1"], ["v1", "2"]]),
        ],
        marker=marker,
    )
    rows = read_xlsx(raw, marker=marker)
    assert [(row.sheet, row.number) for row in rows] == [
        ("vouchers", 3), ("lines", 3), ("lines", 4)
    ]
    assert rows[0].cells["total"].value == "10.0000"
    with pytest.raises(ValueError, match="marker"):
        read_xlsx(raw)
    text = csv_document(["code"], [["=cmd"]], template=True, marker=marker)
    assert read_csv(text, marker=marker)[0].cells["code"].value == "'=cmd"
    with pytest.raises(ValueError, match="marker"):
        read_csv(text)
    for sheets in ([], [("a", [], [])] * 2, [("bad/name", ["x"], [])]):
        with pytest.raises(ValueError, match="sheets"):
            xlsx_workbook(sheets)


def test_plain_negative_numbers_stay_numeric_and_workbook_text_is_valid_xml() -> None:
    from billing_platform.bulk_files import xlsx_workbook

    assert safe_spreadsheet_text("-5.0000") == "-5.0000"
    assert safe_spreadsheet_text("-5+1").startswith("'")
    raw = xlsx_workbook([("data", ["text"], [["bad\x0bvalue\x00"]])])
    assert read_xlsx(raw)[0].cells["text"].value == "badvalue"
