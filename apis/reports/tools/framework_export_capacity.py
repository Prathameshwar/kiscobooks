"""Full synthetic 20-column exports with actual durable files and own-process RSS.

This measures the renderer/storage boundary, not DB query, HTTP, queue or production SLOs.
Completed artifacts and the JSON evidence are retained under the explicit output directory.
"""

import argparse
import csv
import datetime as dt
import hashlib
import itertools
import json
import platform
import time
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from billing_platform.process_memory import peak_rss

from reports.domain.reporting.contracts import Column
from reports.rendering.tabular import Budget, CsvWriter, XlsxWriter
from reports.storage.filesystem import LocalArtifactStore

COLUMNS = (
    Column("id", "Transaction", "IDENTIFIER"),
    Column("date", "Date", "DATE"),
    Column("description", "Description"),
    Column("currency", "Currency"),
    *(Column(f"value_{index}", f"Value {index}", "MONEY") for index in range(16)),
)


def rows(count: int):
    for index in range(count):
        yield {
            "id": f"{index:012d}",
            "date": "2026-04-01",
            "description": "Posted transaction",
            "currency": "INR",
            **{f"value_{column}": f"{index % 1000}.1234" for column in range(16)},
        }


def validate(path: Path, format_name: str, expected: int) -> dict:
    if format_name == "CSV":
        count = 0
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            assert next(reader) == [column.title for column in COLUMNS]
            for count, row in enumerate(reader, 1):
                assert len(row) == 20
                assert row[0] == f"{count - 1:012d}" and row[4] == f"{(count - 1) % 1000}.1234"
        assert count == expected
        return {"verified_rows": count, "sheets": None}
    count, lengths = 0, []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            (
                name
                for name in archive.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            ),
            key=lambda name: int(name.rsplit("sheet", 1)[1].split(".")[0]),
        )
        for name in names:
            length, container = 0, None
            with archive.open(name) as stream:
                # This tool reads only the workbook it just generated, never uploaded XML.
                for event, element in ET.iterparse(stream, events=("start", "end")):  # noqa: S314
                    if event == "start" and element.tag == namespace + "sheetData":
                        container = element
                    if event == "end" and element.tag == namespace + "row":
                        length += 1
                        cells = element.findall(namespace + "c")
                        assert len(cells) == 20
                        if length > 1:
                            assert (
                                cells[0].find(namespace + "is/" + namespace + "t").text
                                == f"{count:012d}"
                            )
                            assert cells[4].find(namespace + "v").text == f"{count % 1000}.1234"
                            count += 1
                        assert container is not None
                        container.clear()
            assert 1 <= length <= 1048576
            lengths.append(length)
    assert count == expected
    return {"verified_rows": count, "sheet_rows_including_header": lengths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000000)
    parser.add_argument("--format", choices=("CSV", "XLSX"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.rows <= 10000000:
        parser.error("capacity fixture must contain 1 to 10 million rows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    storage = LocalArtifactStore(output / "private")
    key = uuid.uuid4().hex
    path = storage.begin(key)
    budget = Budget(args.rows, args.rows * 20, 40 * 1024**3, 7200)
    started = time.perf_counter()
    cpu_started = time.process_time()
    renderer_source_hash = hashlib.sha256(
        (Path(__file__).resolve().parents[1] / "src/reports/rendering/tabular.py").read_bytes()
    ).hexdigest()
    writer = (CsvWriter if args.format == "CSV" else XlsxWriter)(path, COLUMNS, budget)
    for batch in itertools.batched(rows(args.rows), 1000):
        writer.append(batch)
        if writer.count % 100000 == 0:
            print(
                json.dumps(
                    {
                        "rows": writer.count,
                        "seconds": time.perf_counter() - started,
                        "peak_rss_bytes": peak_rss(),
                    }
                ),
                flush=True,
            )
    writer.finish()
    artifact = storage.publish(key, budget.bytes)
    elapsed, rendering_rss = time.perf_counter() - started, peak_rss()
    cpu_seconds = time.process_time() - cpu_started
    storage.discard_temporary(key)
    verified = validate(storage.root / "objects" / key, args.format, args.rows)
    result = {
        "boundary": "synthetic frozen rows to durable filesystem artifact; no database or HTTP",
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
        "platform": platform.platform(),
        "format": args.format,
        "rows": args.rows,
        "columns": 20,
        "seconds": elapsed,
        "cpu_seconds": cpu_seconds,
        "renderer_source_hash": renderer_source_hash,
        "peak_render_rss_bytes": rendering_rss,
        "peak_total_rss_bytes": peak_rss(),
        "byte_count": artifact.byte_count,
        "content_hash": artifact.content_hash,
        "artifact_key": key,
        **verified,
    }
    (output / (args.format.lower() + ".json")).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
