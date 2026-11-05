import io
import zipfile
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from billing_platform.bulk_files import NS, Cell, read_csv, read_xlsx, table, worksheet, xml
from tests.test_bulk_files import sample, workbook_part


def package(parts: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_table_bounds_and_empty_rows() -> None:
    marker = [Cell("_catalog_schema_version"), Cell("1")]
    assert table([marker, [Cell("code")], [], [Cell("")], [Cell("0001")]], "CSV")[0].number == 5
    for headers in ([], [Cell("bad name")], [Cell("f" + str(i)) for i in range(129)]):
        with pytest.raises(ValueError):
            table([marker, headers], "CSV")
    for rows in ([[Cell("x" * 16385)]], [[Cell("x")]] * 2001):
        with pytest.raises(ValueError):
            table([marker, [Cell("code")], *rows], "CSV")
    for raw in (b"_catalog_schema_version,1\ncode\n" + b"x\n" * 2001, b"," * 128):
        with pytest.raises(ValueError):
            read_csv(raw)


def sheet(rows: str) -> Element:
    return xml(f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>'.encode())


def test_workbook_supported_scalars_shared_strings_and_sparse_cells() -> None:
    rows = worksheet(
        sheet(
            '<row r="2"><c r="B2" t="s"><v>0</v></c>'
            '<c r="C2" t="str"><v>0007</v></c>'
            '<c r="D2" t="b"><v>1</v></c><c r="E2"><v>2</v></c></row>'
        ),
        ["0012"],
    )
    assert rows == [[], [Cell(""), Cell("0012"), Cell("0007"), Cell("1", "b"), Cell("2", "n")]]


@pytest.mark.parametrize(
    "rows,strings",
    [
        ('<row r="0"/>', []),
        ('<row r="2003"/>', []),
        ('<row r="1"/><row r="1"/>', []),
        ('<row r="1"><c r="A2"/></row>', []),
        ('<row r="1"><c r="A1"/><c r="A1"/></row>', []),
        ('<row r="1"><c r="A1" t="s"><v>-1</v></c></row>', ["x"]),
        ('<row r="1"><c r="A1" t="s"><v>1</v></c></row>', ["x"]),
        ('<row r="1"><c r="A1" t="d"><v>2026-01-01</v></c></row>', []),
    ],
)
def test_ambiguous_and_invalid_cells_are_rejected(rows: str, strings: list[str]) -> None:
    with pytest.raises(ValueError):
        worksheet(sheet(rows), strings)
    with pytest.raises(ValueError):
        worksheet(sheet('<row r="1"><c r="A1" t="str"><v>' + "x" * 16385 + "</v></c></row>"), [])


@pytest.mark.parametrize(
    "name", ["/root.xml", "../root.xml", "xl/vba.xml", "xl/embedding.xml", "x.bin", "a\\b.xml"]
)
def test_unsafe_package_paths_are_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        read_xlsx(package({name: b"<x/>"}))


def test_package_size_part_count_and_compression_bounds() -> None:
    with pytest.raises(ValueError):
        read_xlsx(package({f"p{i}.xml": b"<x/>" for i in range(129)}))
    with pytest.raises(ValueError):
        read_xlsx(package({"x.xml": b"<x/>"}, compression=zipfile.ZIP_BZIP2))
    with pytest.raises(ValueError):
        read_xlsx(package({"x.xml": b"x" * (2 * 1024 * 1024)}))
    with pytest.raises(ValueError):
        read_xlsx(package({"x.xml": b"x" * (49 * 1024 * 1024)}))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("x.xml", "<x/>")
        with pytest.warns(UserWarning):
            archive.writestr("x.xml", "<x/>")
    with pytest.raises(ValueError):
        read_xlsx(output.getvalue())


def test_workbook_shared_strings_and_invalid_relationships() -> None:
    raw = sample()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        parts = {info.filename: archive.read(info) for info in archive.infolist()}
    parts["xl/sharedStrings.xml"] = f'<sst xmlns="{NS}"><si><t>0001</t></si></sst>'.encode()
    sheet = xml(parts["xl/worksheets/sheet1.xml"])
    cell = sheet.find(f'.//{{{NS}}}c[@r="B3"]')
    assert cell is not None
    cell.set("t", "s")
    for child in list(cell):
        cell.remove(child)
    SubElement(cell, f"{{{NS}}}v").text = "0"
    parts["xl/worksheets/sheet1.xml"] = tostring(sheet, encoding="utf-8")
    assert read_xlsx(package(parts))[0].cells["code"].value == "0001"
    parts["xl/sharedStrings.xml"] = (
        f'<sst xmlns="{NS}"><si><t>{"x" * 16385}</t></si></sst>'.encode()
    )
    with pytest.raises(ValueError):
        read_xlsx(package(parts))
    workbook = parts["xl/workbook.xml"]
    relationship = parts["xl/_rels/workbook.xml.rels"]
    for path, content in (
        ("xl/workbook.xml", workbook.replace(b'name="Records"', b'name=""')),
        (
            "xl/workbook.xml",
            workbook.replace(b'<sheet name="Records" sheetId="1" r:id="r1"/>', b""),
        ),
        (
            "xl/_rels/workbook.xml.rels",
            relationship.replace(b"worksheets/sheet1.xml", b"../other.xml"),
        ),
        ("xl/worksheets/sheet1.xml", b"<broken>"),
    ):
        with pytest.raises(ValueError):
            read_xlsx(workbook_part(raw, path, content))
    assert read_xlsx(
        workbook_part(
            raw,
            "xl/_rels/workbook.xml.rels",
            relationship.replace(b'Target="worksheets/', b'Target="/xl/worksheets/'),
        )
    )
