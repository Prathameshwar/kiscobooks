"""Bounded UTF-8 CSV and SpreadsheetML, with lexical numbers and no evaluation.

Spreadsheet structure: https://learn.microsoft.com/office/open-xml/spreadsheet/structure-of-a-spreadsheetml-document
Each sheet/table starts with a version marker row (default _catalog_schema_version,1;
services pass their own marker) followed by the typed header.
No package content is extracted to disk. XML must be UTF-8 and cannot declare entities.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from typing import cast
from xml.etree import ElementTree as ET

from billing_platform.bulk import MAX_BYTES, MAX_ROWS

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAX_COLUMNS = 128
MAX_CELL = 16384
MAX_EXPANDED = 48 * 1024 * 1024
MARKER = "_catalog_schema_version"


@dataclass(frozen=True, slots=True)
class Cell:
    value: str
    kind: str = "text"


@dataclass(frozen=True, slots=True)
class TableRow:
    sheet: str
    number: int
    cells: dict[str, Cell]


def bounded(raw: bytes) -> None:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("upload must contain between 1 byte and 8 MiB")


def table(rows: list[list[Cell]], name: str, *, marker: str = MARKER) -> list[TableRow]:
    if len(rows) < 2 or [cell.value for cell in rows[0]] != [marker, "1"]:
        raise ValueError("table requires the version 1 template marker")
    headers = [cell.value for cell in rows[1]]
    if (
        not headers
        or len(headers) > MAX_COLUMNS
        or len(set(headers)) != len(headers)
        or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,119}", key) for key in headers)
    ):
        raise ValueError("table headers must be unique bounded field names")
    result = []
    for number, values in enumerate(rows[2:], 3):
        if len(values) > len(headers) or any(len(cell.value) > MAX_CELL for cell in values):
            raise ValueError("table row exceeds its column or cell bound")
        if not any(cell.value for cell in values):
            continue
        if number > MAX_ROWS + 2:
            raise ValueError("table exceeds 2000 source rows")
        result.append(TableRow(name, number, dict(zip(headers, values, strict=False))))
    return result


def read_csv(raw: bytes, *, marker: str = MARKER, delimiter: str = ",") -> list[TableRow]:
    if delimiter not in {",", "\t"}:
        raise ValueError("unsupported delimiter")
    bounded(raw)
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("CSV must be UTF-8 text")
        rows: list[list[Cell]] = []
        for row in csv.reader(io.StringIO(text, newline=""), strict=True, delimiter=delimiter):
            if len(rows) >= MAX_ROWS + 2 or len(row) > MAX_COLUMNS:
                raise ValueError("CSV row or column limit exceeded")
            rows.append([Cell(value) for value in row])
        return table(rows, "CSV", marker=marker)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("invalid UTF-8 CSV") from exc


def xml(raw: bytes) -> ET.Element:
    text = raw.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("XML entities and document types are forbidden")
    # The caller bounds expanded bytes; declarations/entities and non-UTF-8 input
    # are refused above, preventing entity expansion and external resolution.
    return ET.fromstring(text)  # noqa: S314


def column(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", reference)
    if match is None:
        raise ValueError("worksheet cell requires an explicit coordinate")
    value = 0
    for letter in match[1]:
        value = value * 26 + ord(letter) - ord("A") + 1
    if value > MAX_COLUMNS or int(match[2]) > MAX_ROWS + 2:
        raise ValueError("worksheet coordinate exceeds import limits")
    return value - 1


def worksheet(tree: ET.Element, strings: list[str]) -> list[list[Cell]]:
    result: list[list[Cell]] = []
    previous = 0
    for row in tree.findall(f"{{{NS}}}sheetData/{{{NS}}}row"):
        number = int(row.attrib["r"])
        if number <= previous or number > MAX_ROWS + 2:
            raise ValueError("worksheet rows must be ordered and bounded")
        while len(result) < number - 1:
            result.append([])
        cells: dict[int, Cell] = {}
        for cell in row.findall(f"{{{NS}}}c"):
            coordinate = cell.attrib["r"]
            position = column(coordinate)
            if int(re.sub(r"^[A-Z]+", "", coordinate)) != number or position in cells:
                raise ValueError("worksheet cell coordinates conflict")
            kind = cell.get("t", "n")
            value = cell.findtext(f"{{{NS}}}v", default="")
            if kind == "inlineStr":
                value = "".join(node.text or "" for node in cell.iter(f"{{{NS}}}t"))
                kind = "text"
            elif kind == "s":
                if not value.isascii() or not value.isdecimal() or int(value) >= len(strings):
                    raise ValueError("invalid shared-string reference")
                value, kind = strings[int(value)], "text"
            elif kind == "str":
                kind = "text"
            elif kind not in {"n", "b"}:
                raise ValueError("use text dates and supported scalar cell types")
            if len(value) > MAX_CELL:
                raise ValueError("worksheet cell exceeds its text bound")
            cells[position] = Cell(value, kind)
        result.append([cells.get(index, Cell("")) for index in range(max(cells, default=-1) + 1)])
        previous = number
    return result


def read_xlsx(
    raw: bytes, *, marker: str = MARKER, ignored_sheets: frozenset[str] = frozenset()
) -> list[TableRow]:
    bounded(raw)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [entry.filename for entry in members]
            if len(members) > 128 or len(names) != len(set(names)):
                raise ValueError("workbook package has too many or duplicate parts")
            if sum(entry.file_size for entry in members) > MAX_EXPANDED:
                raise ValueError("expanded workbook exceeds 48 MiB")
            parts = {}
            for entry in members:
                name = entry.filename
                if (
                    name.startswith(("/", "\\"))
                    or "\\" in name
                    or ".." in name.split("/")
                    or entry.flag_bits & 1
                    or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or entry.file_size > max(entry.compress_size * 200, 1024 * 1024)
                    or not name.endswith((".xml", ".rels"))
                    or any(
                        word in name.lower()
                        for word in ("externallink", "vba", "macrosheet", "embedding", "activex")
                    )
                ):
                    raise ValueError("unsafe or unsupported workbook package part")
                tree = xml(archive.read(entry))
                for node in tree.iter():
                    if any("macroenabled" in value.lower() for value in node.attrib.values()):
                        raise ValueError("macro-enabled workbooks are forbidden")
                    if node.tag.rsplit("}", 1)[-1] in {"f", "externalReference", "oleObject"}:
                        raise ValueError("workbook formulas and external objects are forbidden")
                    if node.get("TargetMode", "").strip().lower() == "external":
                        raise ValueError("workbook external relationships are forbidden")
                parts[name] = tree
            workbook = parts["xl/workbook.xml"]
            relationships = {
                node.attrib["Id"]: node.attrib["Target"]
                for node in parts["xl/_rels/workbook.xml.rels"]
            }
            strings = []
            if "xl/sharedStrings.xml" in parts:
                strings = [
                    "".join(node.text or "" for node in item.iter(f"{{{NS}}}t"))
                    for item in parts["xl/sharedStrings.xml"]
                ]
                if len(strings) > MAX_ROWS * MAX_COLUMNS or any(
                    len(value) > MAX_CELL for value in strings
                ):
                    raise ValueError("shared strings exceed workbook bounds")
            result = []
            seen = set()
            for sheet in workbook.findall(f"{{{NS}}}sheets/{{{NS}}}sheet"):
                name = sheet.attrib["name"]
                target = relationships[sheet.attrib[f"{{{DOC_REL}}}id"]]
                path = target.lstrip("/") if target.startswith("/") else "xl/" + target
                if path in seen or not re.fullmatch(r"xl/worksheets/[A-Za-z0-9_.-]+\.xml", path):
                    raise ValueError("invalid or duplicate worksheet relationship")
                if not name or len(name) > 100:
                    raise ValueError("invalid worksheet name")
                seen.add(path)
                if name in ignored_sheets:
                    continue
                result.extend(table(worksheet(parts[path], strings), name, marker=marker))
                if len(result) > MAX_ROWS:
                    raise ValueError("workbook exceeds 2000 records")
            if not result:
                raise ValueError("workbook contains no import records")
            return result
    except (
        UnicodeError,
        ET.ParseError,
        KeyError,
        IndexError,
        zipfile.BadZipFile,
        RuntimeError,
    ) as exc:
        raise ValueError("invalid or unsupported XLSX workbook") from exc


NUMBER = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def safe_spreadsheet_text(value: str) -> str:
    """Neutralise formula-leading text; a plain (negative) decimal is data, not a formula."""
    if NUMBER.fullmatch(value):
        return value
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))
        else value
    )


def csv_document(
    headers: list[str],
    rows: list[list[str]],
    *,
    template: bool = False,
    marker: str = MARKER,
    delimiter: str = ",",
) -> bytes:
    if delimiter not in {",", "\t"}:
        raise ValueError("unsupported delimiter")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n", delimiter=delimiter)
    if template:
        writer.writerow([marker, "1"])
    writer.writerow(headers)
    writer.writerows([safe_spreadsheet_text(value) for value in row] for row in rows)
    return output.getvalue().encode("utf-8")


def xlsx_document(headers: list[str], rows: list[list[str]], *, marker: str = MARKER) -> bytes:
    return xlsx_workbook([("Records", headers, rows)], marker=marker)


def _worksheet_xml(contents: list[list[str]]) -> bytes:
    sheet = ET.Element("worksheet", xmlns=NS)
    # Apply Text to blank input cells too, so Excel preserves leading-zero codes,
    # long identifiers and exact decimal text when users fill in a template.
    columns = ET.SubElement(sheet, "cols")
    ET.SubElement(columns, "col", min="1", max=str(len(contents[1])), style="1")
    data = ET.SubElement(sheet, "sheetData")
    for number, values in enumerate(contents, 1):
        row = ET.SubElement(data, "row", r=str(number))
        for position, value in enumerate(values, 1):
            letters, remaining = "", position
            while remaining:
                remaining, digit = divmod(remaining - 1, 26)
                letters = chr(65 + digit) + letters
            cell = ET.SubElement(row, "c", r=letters + str(number), t="inlineStr", s="1")
            text = ET.SubElement(ET.SubElement(cell, "is"), "t")
            # XML 1.0 cannot carry these controls; a workbook containing them will not open.
            text.text = XML_INVALID.sub("", value)
    return cast(bytes, ET.tostring(sheet, encoding="utf-8"))


def xlsx_workbook(
    sheets: list[tuple[str, list[str], list[list[str]]]], *, marker: str = MARKER
) -> bytes:
    """Inline-string worksheets (never formulas), each led by the version marker row."""
    names = [name for name, _, _ in sheets]
    if (
        not sheets
        or len(sheets) > 16
        or len(set(names)) != len(names)
        or any(not re.fullmatch(r"[A-Za-z0-9_]{1,31}", name) for name in names)
    ):
        raise ValueError("workbook requires 1-16 uniquely and plainly named sheets")
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{number}.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for number in range(1, len(sheets) + 1)
    )
    listed = "".join(
        f'<sheet name="{name}" sheetId="{number}" r:id="r{number}"/>'
        for number, name in enumerate(names, 1)
    )
    related = "".join(
        f'<Relationship Id="r{number}" Type="{DOC_REL}/worksheet" '
        f'Target="worksheets/sheet{number}.xml"/>'
        for number in range(1, len(sheets) + 1)
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
            f'officedocument.spreadsheetml.styles+xml"/>{overrides}</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{REL}"><Relationship Id="r1" '
            f'Type="{DOC_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{NS}" xmlns:r="{DOC_REL}"><sheets>{listed}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{REL}">{related}'
            f'<Relationship Id="styles" Type="{DOC_REL}/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            f'<styleSheet xmlns="{NS}">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/>'
            "</border></borders>"
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
            "</cellStyleXfs>"
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
            "</cellStyles></styleSheet>",
        )
        for number, (_, headers, rows) in enumerate(sheets, 1):
            archive.writestr(
                f"xl/worksheets/sheet{number}.xml",
                _worksheet_xml([[marker, "1"], headers, *rows]),
            )
    return output.getvalue()
