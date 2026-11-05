"""Immutable, versioned report contracts; documents refer to rows, never own them."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from typing import Any, Literal

ValueKind = Literal["TEXT", "IDENTIFIER", "DATE", "INTEGER", "DECIMAL", "MONEY", "BOOLEAN"]
Layout = Literal["REGISTER", "STATEMENT", "RECONCILIATION", "SUMMARY"]
Format = Literal["CSV", "XLSX", "HTML", "PDF"]
ResultMode = Literal["MATERIALIZED", "PINNED_QUERY"]


def fingerprint(value: Any) -> str:
    """Hash normalized JSON only; financial decimals must already be exact strings."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    kind: ValueKind = "TEXT"
    currency_key: str | None = None
    metric: str | None = None
    nullable: bool = True


@dataclass(frozen=True)
class View:
    key: str
    title: str
    columns: tuple[Column, ...]
    layout: Layout = "REGISTER"
    # A named view is an ordered projection, not an arbitrary client field list.
    order: tuple[str, ...] = ("ordinal",)
    calculation: str = "detail"
    orientation: Literal["AUTO", "PORTRAIT", "LANDSCAPE"] = "AUTO"


@dataclass(frozen=True)
class Join:
    target: str
    local_key: str
    remote_key: str
    cardinality: Literal["ONE_TO_ONE", "MANY_TO_ONE", "ONE_TO_MANY"]
    preaggregate: bool = False


@dataclass(frozen=True)
class DatasetDefinition:
    key: str
    version: int
    grain: str
    identity: tuple[str, ...]
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    date_bases: tuple[str, ...]
    joins: tuple[Join, ...] = ()
    scope: str = "TENANT_COMPANY_GENERATION"


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    version: int
    meaning: str
    behavior: Literal["ADDITIVE", "BALANCE", "RATIO"]
    currency_rule: Literal["SINGLE_CURRENCY", "UNITLESS"]
    date_semantics: str
    sign: str
    dependencies: tuple[str, ...] = ()
    storage_scale: int = 4


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Ratios recompute from aggregated operands; zero is explicitly undefined."""
    if not numerator.is_finite() or not denominator.is_finite():
        raise ValueError("metric operands must be finite")
    with localcontext() as context:
        context.prec = 48
        return None if denominator == 0 else numerator / denominator


def exact_storage(value: Decimal) -> Decimal:
    """Reject overflow or implicit rounding at the DECIMAL(19,4) boundary."""
    if not value.is_finite() or abs(value) >= Decimal("1000000000000000"):
        raise ValueError("amount exceeds DECIMAL(19,4)")
    with localcontext() as context:
        context.prec = 48
        quantized = value.quantize(Decimal("0.0001"))
    if quantized != value:
        raise ValueError("amount requires explicit rounding")
    return quantized


@dataclass(frozen=True)
class Drilldown:
    key: str
    title: str
    target: str
    version: int = 1


@dataclass(frozen=True)
class ReportDefinition:
    code: str
    version: int
    title: str
    description: str
    implementation_hash: str
    parameter_schema_hash: str
    datasets: tuple[str, ...]
    metrics: tuple[str, ...]
    permissions: tuple[str, ...]
    views: tuple[View, ...]
    resource_class: Literal["SHORT", "BULK"] = "SHORT"
    financial_statement: bool = False
    drilldowns: tuple[Drilldown, ...] = ()

    @property
    def identity(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class QueryPlan:
    key: str
    version: int
    generation_id: str
    mode: ResultMode
    datasets: tuple[str, ...]
    parameter_hash: str
    permission_hash: str
    order: tuple[str, ...]
    max_rows: int
    batch_rows: int = 200

    def __post_init__(self) -> None:
        if self.version < 1 or self.max_rows < 1 or not 1 <= self.batch_rows <= 200:
            raise ValueError("invalid query budget or version")
        if not self.order:
            raise ValueError("a report plan requires deterministic ordering")

    @property
    def identity(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class ResultManifest:
    run_id: str
    definition_identity: str
    generation_id: str
    plan: QueryPlan
    schema_hash: str
    row_count: int | None = None
    content_hash: str | None = None

    @property
    def logical_fingerprint(self) -> str:
        # Actual bytes and exact counts are deliberately separate from logical identity.
        return fingerprint(
            {
                "definition": self.definition_identity,
                "generation": self.generation_id,
                "plan": self.plan.identity,
                "schema": self.schema_hash,
            }
        )


@dataclass(frozen=True)
class DisplayConfiguration:
    amount_precision: int
    quantity_precision: int
    rounding_mode: Literal["half_up", "half_even", "down"]
    date_format: str
    version: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.amount_precision <= 4 or not 0 <= self.quantity_precision <= 4:
            raise ValueError("display precision must be between zero and four")
        if self.date_format not in {"DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD", "DD-MM-YYYY"}:
            raise ValueError("unsupported date display format")


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    view: View
    result_id: str


@dataclass(frozen=True)
class ReportDocument:
    title: str
    company_label: str
    period_label: str
    result: ResultManifest
    display: DisplayConfiguration
    sections: tuple[Section, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExportDefinition:
    format: Format
    media_type: str
    renderer_version: str
    template_version: str
    font_version: str
    max_rows: int
    max_cells: int
    max_bytes: int
    timeout_seconds: int
    exact_value_policy: str
    max_pages: int | None = None

    @property
    def identity(self) -> str:
        return fingerprint(asdict(self))
