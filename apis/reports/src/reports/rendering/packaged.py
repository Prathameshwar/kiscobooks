"""Sequential bounded document parts published as one verified ZIP artifact."""

import hashlib
import json
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from reports.domain.reporting.contracts import Column
from reports.rendering.tabular import Budget, Writer


class PackageWriter:
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        part_budget: Budget,
        format_name: str,
        factory: Callable[[Path, Budget, int], Writer],
        metadata: dict[str, Any],
        max_parts: int,
    ):
        self.path, self.columns, self.budget = path, columns, budget
        self.part_budget, self.format, self.factory = part_budget, format_name, factory
        self.metadata, self.max_parts = metadata, max_parts
        self.count, self.started = 0, time.monotonic()
        self.parts: list[dict[str, Any]] = []
        self.writer: Writer | None = None
        self.part_path: Path | None = None
        self.archive: zipfile.ZipFile | None = None
        self.part_rows = min(part_budget.rows, part_budget.cells // len(columns))
        if self.part_rows < 1 or max_parts < 1:
            raise ValueError("package part budget is too small")

    def check(self) -> None:
        if self.count > self.budget.rows or self.count * len(self.columns) > self.budget.cells:
            raise ValueError("package exceeds its row or cell budget")
        if time.monotonic() - self.started > self.budget.seconds:
            raise ValueError("package exceeds its time budget")
        if (
            sum(file.stat().st_size for file in self.path.parent.iterdir() if file.is_file())
            > self.budget.bytes
        ):
            raise ValueError("package exceeds its disk budget")

    def start(self) -> None:
        if len(self.parts) >= self.max_parts:
            raise ValueError("package exceeds its part budget")
        filename = f"part-{len(self.parts) + 1:04d}.{self.format.lower()}"
        self.part_path = self.path.with_name(filename)
        remaining = self.budget.seconds - (time.monotonic() - self.started)
        budget = replace(
            self.part_budget,
            seconds=max(1, int(min(remaining, self.part_budget.seconds))),
            scratch_bytes=self.budget.bytes,
        )
        self.writer = self.factory(self.part_path, budget, self.count + 1)

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            self.check()
            if self.count >= self.budget.rows:
                raise ValueError("package exceeds its row budget")
            if self.writer is None:
                self.start()
            assert self.writer is not None
            self.writer.append([row])
            self.count += 1
            if self.writer.count >= self.part_rows:
                self.close_part()
            self.check()

    def close_part(self) -> None:
        assert self.writer is not None and self.part_path is not None
        self.writer.finish()
        digest = hashlib.sha256()
        with self.part_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(256 * 1024), b""):
                digest.update(chunk)
        size, rows = self.part_path.stat().st_size, self.writer.count
        scratch_size = sum(
            file.stat().st_size for file in self.path.parent.iterdir() if file.is_file()
        )
        if scratch_size + size + 1024 > self.budget.bytes:
            raise ValueError("package exceeds its disk budget while assembling a part")
        if self.archive is None:
            self.archive = zipfile.ZipFile(
                self.path, "x", compression=zipfile.ZIP_STORED, allowZip64=True
            )
        self.archive.write(self.part_path, self.part_path.name)
        self.check()
        self.parts.append(
            {
                "filename": self.part_path.name,
                "first_ordinal": self.count - rows + 1,
                "row_count": rows,
                "byte_count": size,
                "content_hash": digest.hexdigest(),
            }
        )
        self.writer = None
        self.part_path.unlink()
        # Private flat scratch only. Renderers use the same two fixed scratch names.
        for name in ("document.ndjson", "render-metrics.json"):
            scratch = self.path.with_name(name)
            if scratch.exists():
                scratch.unlink()
        self.check()

    def finish(self) -> None:
        if self.writer is None and not self.parts:
            self.start()
        if self.writer is not None:
            self.close_part()
        assert self.archive is not None
        self.archive.writestr(
            "manifest.json",
            json.dumps(
                self.metadata
                | {
                    "version": 1,
                    "format": self.format,
                    "row_count": self.count,
                    "parts": self.parts,
                },
                sort_keys=True,
                ensure_ascii=False,
            ),
        )
        self.archive.close()
        self.check()

    def abort(self) -> None:
        if self.writer is not None:
            self.writer.abort()
        if self.archive is not None:
            self.archive.close()
