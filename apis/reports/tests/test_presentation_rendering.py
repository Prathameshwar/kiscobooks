import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from billing_platform.display import DisplayConfiguration
from pypdf import PdfReader

from reports.domain.reporting.contracts import Column
from reports.rendering.html import HtmlWriter
from reports.rendering.pdf import PdfWriter
from reports.rendering.presentation import Document, cell
from reports.rendering.tabular import Budget

FIXTURE = json.loads(
    (Path(__file__).parents[3] / "libs/platform/tests/fixtures/report-display.json").read_text(
        "utf-8"
    )
)
COLUMNS = (
    Column("id", "Document", "IDENTIFIER"),
    Column("name", "Account"),
    Column("amount", "Amount (INR)", "MONEY"),
    Column("date", "Posting date", "DATE"),
)
ROWS = [
    {
        "id": "00001",
        "name": "Accounts <script>alert(1)</script>",
        "amount": "1234567.8950",
        "date": "2026-03-05",
    },
    {"id": "00002", "name": "नमस्ते भारत", "amount": "-2.3450", "date": "2026-03-06"},
]


def document(layout="REGISTER"):
    return Document(
        "Account ledger",
        DisplayConfiguration(**FIXTURE["config"]),
        "01 Mar 2026 \u2013 31 Mar 2026",
        "31 Mar 2026 18:00 UTC",
        "example-run",
        layout,
        (("Basis", "Posting date"),),
    )


class Content(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.exact, self.text = [], [], []

    def handle_starttag(self, tag, attributes):
        self.tags.append(tag)
        for key, value in attributes:
            if key == "data-value":
                self.exact.append(value)

    def handle_data(self, value):
        self.text.append(value)


@pytest.mark.parametrize("layout", ["REGISTER", "STATEMENT", "SUMMARY", "RECONCILIATION"])
def test_standalone_html_escapes_business_text_and_preserves_exact_values(tmp_path, layout):
    output = tmp_path / "output"
    writer = HtmlWriter(output, COLUMNS, Budget(20000, 200000, 10000000, 60), document(layout))
    writer.append(ROWS)
    writer.finish()
    content = output.read_text("utf-8")
    parsed = Content()
    parsed.feed(content)
    assert not {"script", "img", "iframe", "a"}.intersection(parsed.tags)
    assert "https://fonts.googleapis" not in content and "@import" not in content
    assert "12,34,567.90" in parsed.text and "नमस्ते भारत" in parsed.text
    assert parsed.exact == [
        cell(column, row, document().display).exact for row in ROWS for column in COLUMNS
    ]
    assert "data:font/ttf;base64," in content


def test_isolated_pdf_contains_values_and_embedded_fonts(tmp_path):
    writer = PdfWriter(tmp_path / "output", COLUMNS, Budget(5000, 200000, 10000000, 60), document())
    writer.append(ROWS)
    writer.finish()
    pdf = PdfReader(tmp_path / "output")
    text = "".join(page.extract_text() for page in pdf.pages)
    assert "12,34,567.90" in text and "00001" in text and "05 Mar 2026" in text
    assert "<script>alert(1)</script>" in text
    assert len(pdf.pages) == 1
    fonts = pdf.pages[0]["/Resources"]["/Font"]
    assert any(
        "NotoSansDevanagari" in str(font.get_object().get("/BaseFont")) for font in fonts.values()
    )


def test_pdf_wide_bands_repeat_identity_and_cover_every_column(tmp_path):
    columns = (COLUMNS[0], *(Column(f"v{n}", f"Value {n}") for n in range(16)))
    row = {"id": "00001", **{f"v{n}": f"cell-{n:02d}" for n in range(16)}}
    writer = PdfWriter(tmp_path / "output", columns, Budget(5000, 200000, 10000000, 60), document())
    writer.append([row])
    writer.finish()
    pdf = PdfReader(tmp_path / "output")
    assert len(pdf.pages) == 3
    text = "".join(page.extract_text() for page in pdf.pages)
    for n in range(16):
        assert text.count(f"cell-{n:02d}") == 1
    assert text.count("00001") == 3


def test_pdf_page_and_memory_limits_reject_unpublishable_layouts(tmp_path):
    for name, options in (
        ("page", {"max_pages": 1}),
        ("memory", {"memory_bytes": 32 * 1024 * 1024}),
    ):
        directory = tmp_path / name
        directory.mkdir()
        writer = PdfWriter(
            directory / "output", COLUMNS, Budget(5000, 200000, 10000000, 60), document(), **options
        )
        writer.append(ROWS * 100)
        with pytest.raises(ValueError, match="layout failed"):
            writer.finish()
        writer.abort()


def test_html_empty_and_null_boolean_quantity_cells(tmp_path):
    writer = HtmlWriter(tmp_path / "output", COLUMNS, Budget(20, 200, 10000000, 60), document())
    writer.finish()
    assert "No rows" in (tmp_path / "output").read_text("utf-8")
    assert cell(Column("x", "X", "MONEY"), {}, document().display).text == "—"
    assert cell(Column("x", "X", "BOOLEAN"), {"x": True}, document().display).text == "Yes"
    assert cell(Column("x", "X", "DECIMAL"), {"x": "1.2345"}, document().display).text == "1.235"


def test_pdf_timeout_and_unsupported_glyph_fail_without_publishing(tmp_path, monkeypatch):
    import subprocess
    import sys

    output = tmp_path / "output"
    writer = PdfWriter(output, COLUMNS, Budget(5000, 200000, 10000000, 60), document())
    writer.append(ROWS)
    original = subprocess.run

    def hanging_child(args, **kwargs):
        kwargs["timeout"] = 0.2
        return original([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr("reports.rendering.pdf.subprocess.run", hanging_child)
        with pytest.raises(ValueError, match="time budget"):
            writer.finish()
    writer.abort()
    second = tmp_path / "unsupported"
    second.mkdir()
    writer = PdfWriter(second / "output", COLUMNS, Budget(5000, 200000, 10000000, 60), document())
    writer.append([ROWS[0] | {"name": "\U0001f914"}])
    with pytest.raises(ValueError, match="layout failed"):
        writer.finish()
    writer.abort()
