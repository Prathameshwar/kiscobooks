"""Trusted local presentation assets and one typed cell formatter for HTML/PDF."""

import base64
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from billing_platform.display import DisplayConfiguration, date, number

from reports.domain.reporting.contracts import Column, Layout
from reports.rendering.identity import implementation
from reports.rendering.tabular import value

ASSETS = Path(__file__).parent / "assets"


@lru_cache(maxsize=1)
def bundle() -> dict[str, Any]:
    result: dict[str, Any] = json.loads((ASSETS / "presentation-v1.json").read_text("utf-8"))
    for name, expected in result["fonts"].items():
        if (
            Path(name).name != name
            or hashlib.sha256((ASSETS / "fonts" / name).read_bytes()).hexdigest() != expected
        ):
            raise ValueError("packaged report font verification failed")
    return result


def identity() -> str:
    return hashlib.sha256((ASSETS / "presentation-v1.json").read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def renderer_identity() -> str:
    bundle()
    return "presentation-v1:" + implementation()


@lru_cache(maxsize=1)
def stylesheet() -> str:
    css = bundle()["css"]
    for family, prefix in (
        ("Report Sans", "NotoSans"),
        ("Report Devanagari", "NotoSansDevanagari"),
    ):
        for weight, suffix in ((400, "Regular"), (700, "Bold")):
            encoded = base64.b64encode(
                (ASSETS / "fonts" / f"{prefix}-{suffix}.ttf").read_bytes()
            ).decode("ascii")
            css += (
                f"\n@font-face{{font-family:'{family}';font-weight:{weight};"
                f"src:url(data:font/ttf;base64,{encoded}) format('truetype');}}"
            )
    return str(css)


@dataclass(frozen=True)
class Document:
    title: str
    display: DisplayConfiguration
    period: str
    source_as_of: str
    run_id: str
    layout: Layout
    filters: tuple[tuple[str, str], ...] = ()
    orientation: str = "AUTO"
    first_ordinal: int = 1
    category: str = "Financial report"
    column_groups: tuple[tuple[str, int], ...] = ()

    def wire(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "display": self.display.model_dump(mode="json"),
            "period": self.period,
            "source_as_of": self.source_as_of,
            "run_id": self.run_id,
            "layout": self.layout,
            "filters": self.filters,
            "orientation": self.orientation,
            "first_ordinal": self.first_ordinal,
            "category": self.category,
            "column_groups": self.column_groups,
        }


@dataclass(frozen=True)
class Cell:
    exact: str
    text: str
    numeric: bool


def cell(column: Column, row: dict[str, Any], config: DisplayConfiguration) -> Cell:
    raw = value(column, row)
    numeric = column.kind in {"MONEY", "DECIMAL", "INTEGER"}
    if raw is None:
        return Cell("", "\u2014", numeric)
    if isinstance(raw, Decimal):
        return Cell(format(raw, "f"), number(raw, config, quantity=column.kind == "DECIMAL"), True)
    if isinstance(raw, dt.date):
        return Cell(raw.isoformat(), date(raw, config), False)
    if isinstance(raw, bool):
        return Cell(str(raw).lower(), "Yes" if raw else "No", False)
    return Cell(str(raw), str(raw), numeric)


def row_style(row: dict[str, Any]) -> str:
    kind = str(row.get("row_kind", ""))
    if kind.endswith("_CONTROL"):
        return "report-control"
    if kind in {
        "HEAD",
        "GROUP",
        "TOTAL",
        "SUBTOTAL",
        "NET_PROFIT",
        "SURPLUS",
        "DEFICIT",
        "CLOSING",
    }:
        return "report-total"
    return ""
