"""Bounded standalone HTML/PDF capacity and visual fixtures; no database/HTTP claim."""

import argparse
import datetime as dt
import json
import platform
import time
import uuid
from pathlib import Path

from billing_platform.display import DisplayConfiguration
from billing_platform.process_memory import peak_rss

from reports.domain.reporting.contracts import Column
from reports.rendering.html import HtmlWriter
from reports.rendering.pdf import PdfWriter
from reports.rendering.presentation import Document, renderer_identity
from reports.rendering.tabular import Budget
from reports.storage.filesystem import LocalArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("HTML", "PDF"), required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument(
        "--layout",
        choices=("REGISTER", "STATEMENT", "SUMMARY", "RECONCILIATION"),
        default="REGISTER",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    limit = 5000 if args.format == "PDF" else 20000
    if (
        not 0 <= args.rows <= limit
        or not 4 <= args.columns <= 40
        or args.rows * args.columns > 200000
    ):
        parser.error("fixture exceeds the supported presentation envelope")
    store = LocalArtifactStore(args.output.resolve())
    key = uuid.uuid4().hex
    path = store.begin(key)
    config = DisplayConfiguration(
        company_label="Example Engineering and Services Private Limited · भारत",
        base_currency="INR",
        amount_precision=2,
        quantity_precision=3,
        rounding_mode="half_even",
        date_format="dd MMM yyyy",
        datetime_format="dd MMM yyyy HH:mm",
        digit_grouping="indian",
        decimal_separator=".",
        thousands_separator=",",
        negative_format="parentheses",
        currency_display="code",
        currency_symbol_position="prefix",
        timezone="Asia/Kolkata",
        locale="en-IN",
    )
    columns = (
        Column("id", "Document", "IDENTIFIER"),
        Column("name", "Account"),
        Column("date", "Posting date", "DATE"),
        Column("amount", "Amount (INR)", "MONEY"),
        *(Column(f"value{n}", f"Measure {n} (INR)", "MONEY") for n in range(args.columns - 4)),
    )
    document = Document(
        "Financial reporting schedule",
        config,
        "01 Apr 2026 - 30 Apr 2026",
        "Synthetic verified fixture",
        key,
        args.layout,
        (("Basis", "Posting date"),),
    )
    renderer_hash = renderer_identity()
    started = time.monotonic()
    writer = (PdfWriter if args.format == "PDF" else HtmlWriter)(
        path, columns, Budget(limit, 200000, 64 * 1024 * 1024, 60), document
    )
    try:
        for start in range(0, args.rows, 200):
            rows = [
                {
                    "id": f"DOC-{index:08d}",
                    "name": "Services / सेवाएं",
                    "date": "2026-04-15",
                    "amount": "-1234567.8950" if index % 2 else "1234.5678",
                    **{f"value{n}": "1234.5678" for n in range(args.columns - 4)},
                }
                for index in range(start, min(start + 200, args.rows))
            ]
            writer.append(rows)
        writer.finish()
        artifact = store.publish(key, 64 * 1024 * 1024)
        seconds = time.monotonic() - started
        report = {
            "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
            "platform": platform.platform(),
            "boundary": "synthetic frozen rows to durable local artifact; no database or HTTP",
            "format": args.format,
            "layout": args.layout,
            "rows": writer.count,
            "columns": len(columns),
            "seconds": seconds,
            "parent_peak_rss_bytes": peak_rss(),
            "renderer_hash": renderer_hash,
            "artifact_key": key,
            "byte_count": artifact.byte_count,
            "content_hash": artifact.content_hash,
            "child": writer.metrics if isinstance(writer, PdfWriter) else None,
        }
        (args.output / f"{key}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        writer.abort()
        store.discard_temporary(key)


if __name__ == "__main__":
    main()
