"""Independently inspect retained synthetic presentation fixtures, including every row."""

import argparse
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader


class Values(HTMLParser):
    def __init__(self, columns: int):
        super().__init__()
        self.columns, self.cells = columns, 0

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key != "data-value":
                continue
            row, column = divmod(self.cells, self.columns)
            expected = (
                f"DOC-{row:08d}"
                if column == 0
                else "Services / सेवाएं"
                if column == 1
                else "2026-04-15"
                if column == 2
                else "-1234567.8950"
                if column == 3 and row % 2
                else "1234.5678"
            )
            assert value == expected, (row, column, value, expected)
            self.cells += 1


def verify(metadata: Path):
    result = json.loads(metadata.read_text("utf-8"))
    artifact = metadata.parent / "objects" / result["artifact_key"]
    rows, columns = result["rows"], result["columns"]
    if result["format"] == "HTML":
        parsed = Values(columns)
        with artifact.open(encoding="utf-8") as stream:
            for block in iter(lambda: stream.read(65536), ""):
                parsed.feed(block)
        parsed.close()
        assert parsed.cells == rows * columns
        verified = {"cells": parsed.cells}
    else:
        pdf = PdfReader(artifact)
        identities, negatives, positives, dates = Counter(), 0, 0, 0
        for page in pdf.pages:
            text = page.extract_text()
            identities.update(re.findall(r"DOC-\d{8}", text))
            negatives += text.count("(12,34,567.90)")
            positives += text.count("1,234.57")
            dates += text.count("15 Apr 2026")
        bands = (columns - 2) // 7 + 1 if columns > 8 else 1
        assert identities == Counter({f"DOC-{index:08d}": bands for index in range(rows)})
        assert negatives == rows // 2
        assert positives == rows - rows // 2 + (columns - 4) * rows
        assert dates == rows
        verified = {
            "pages": len(pdf.pages),
            "row_occurrences": sum(identities.values()),
            "amounts": negatives + positives,
        }
    return {
        "artifact": result["artifact_key"],
        "format": result["format"],
        "rows": rows,
        "columns": columns,
        "verified": verified,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.metadata:
        print(json.dumps(verify(path)))


if __name__ == "__main__":
    main()
