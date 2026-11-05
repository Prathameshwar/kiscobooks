"""Standalone trusted HTML; no user templates, scripts or external asset resolution."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from reports.domain.reporting.contracts import Column
from reports.rendering.presentation import ASSETS, Document, cell, row_style, stylesheet
from reports.rendering.tabular import BoundedWriter, Budget


class HtmlWriter(BoundedWriter):
    def __init__(self, path: Path, columns: tuple[Column, ...], budget: Budget, document: Document):
        super().__init__(path, columns, budget)
        self.document = document
        self.environment = Environment(
            loader=FileSystemLoader(ASSETS), autoescape=True, undefined=StrictUndefined
        )
        self.stream = path.open("x", encoding="utf-8", newline="\n")
        self.written_bytes = 0
        # Only the packaged, verified stylesheet bypasses escaping; no business field does.
        self.write(
            self.environment.get_template("header.html").render(
                document=document,
                columns=columns,
                css=Markup(stylesheet()),
            )
        )
        self.row_template = self.environment.get_template("row.html")

    def write(self, text: str) -> None:
        self.written_bytes += len(text.encode("utf-8"))
        if self.written_bytes > self.budget.bytes:
            raise ValueError("export exceeds its disk budget")
        self.stream.write(text)

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            if (
                self.count + 1 > self.budget.rows
                or (self.count + 1) * len(self.columns) > self.budget.cells
            ):
                raise ValueError("export exceeds its row or cell budget")
            self.write(
                self.row_template.render(
                    cells=[cell(column, row, self.document.display) for column in self.columns],
                    style=row_style(row),
                )
            )
            self.count += 1
        self.stream.flush()
        self.check()

    def finish(self) -> None:
        self.write(
            self.environment.get_template("footer.html").render(
                count=self.count,
                columns=self.columns,
                document=self.document,
            )
        )
        self.stream.close()
        self.check()

    def abort(self) -> None:
        self.stream.close()
