"""A bounded spool and an expendable PDF process; no PDF layout in the worker."""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from reports.domain.reporting.contracts import Column
from reports.rendering.presentation import Document
from reports.rendering.tabular import BoundedWriter, Budget, value


class PdfWriter(BoundedWriter):
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        document: Document,
        *,
        max_pages: int = 200,
        memory_bytes: int = 1073741824,
    ):
        super().__init__(path, columns, budget)
        self.spool = path.with_name("document.ndjson")
        self.metrics: dict[str, Any] = {}
        self.stream = self.spool.open("x", encoding="utf-8", newline="\n")
        self.written_bytes = 0
        self.write(
            json.dumps(
                {
                    "document": document.wire(),
                    "columns": [asdict(column) for column in columns],
                    "rows": min(5000, budget.rows),
                    "cells": min(200000, budget.cells),
                    "pages": min(200, max_pages),
                    "memory_bytes": min(1073741824, memory_bytes),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    def write(self, text: str) -> None:
        self.written_bytes += len(text.encode("utf-8"))
        if self.written_bytes > min(self.budget.bytes, 64 * 1024 * 1024):
            raise ValueError("PDF input exceeds its bounded layout capacity")
        self.stream.write(text)

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            if (
                self.count + 1 > self.budget.rows
                or (self.count + 1) * len(self.columns) > self.budget.cells
            ):
                raise ValueError("export exceeds its row or cell budget")
            for column in self.columns:
                value(column, row)  # Fail before process creation on malformed frozen values.
            self.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            self.count += 1
        self.stream.flush()
        if self.spool.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("PDF input exceeds its bounded layout capacity")
        self.check()

    def finish(self) -> None:
        self.stream.close()
        self.check()
        remaining = min(60, self.budget.seconds - (time.monotonic() - self.started))
        if remaining <= 0:
            raise ValueError("PDF rendering time budget exceeded")
        environment = {
            key: val
            for key, val in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        environment["PYTHONUTF8"] = "1"
        if sys.platform == "win32":
            environment["__PYVENV_LAUNCHER__"] = sys.executable
        try:
            # Fixed executable/module and internal private paths; business text is only JSON.
            result = subprocess.run(  # noqa: S603 -- no shell or caller-controlled command.
                [
                    str(getattr(sys, "_base_executable", sys.executable))
                    if sys.platform == "win32"
                    else sys.executable,
                    "-m",
                    "reports.rendering.pdf_child",
                    str(self.spool),
                    str(self.path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=remaining,
                check=False,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF rendering time budget exceeded") from exc
        # Native Windows libraries may write diagnostics to stdout. The dedicated entry
        # point returns zero only after doc.build succeeds; stdout is not a protocol.
        if result.returncode != 0:
            reason = {2: "layout", 3: "memory", 4: "filesystem"}.get(result.returncode, "process")
            raise ValueError(
                "PDF layout failed or exceeded its page or memory budget (" + reason + ")"
            )
        self.metrics = json.loads(self.spool.with_name("render-metrics.json").read_text("utf-8"))
        if self.metrics.get("rows") != self.count:
            raise ValueError("PDF renderer did not consume the complete result")
        self.check()

    def abort(self) -> None:
        self.stream.close()
