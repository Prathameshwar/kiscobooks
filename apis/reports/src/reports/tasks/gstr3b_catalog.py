"""GSTR-3B uses the existing frozen job and private artifact pipeline."""

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ValidationFailedError
from reporting_contract.contract import Control, Fact

from reports.domain.gstr3b import FIELDS, applicable, calculate, period_bounds
from reports.domain.reporting.contracts import (
    Column,
    DatasetDefinition,
    ReportDefinition,
    View,
    fingerprint,
)
from reports.domain.reporting.registry import Registration
from reports.schemas.gstr3b import Gstr3bParameters
from reports.tasks.access import INPUT_PERMISSIONS
from reports.tasks.report_catalog import ReferenceAdapter

DATASET = DatasetDefinition(
    "gst_return",
    1,
    "one immutable statutory source allocation",
    ("source_id",),
    ("source_id", "registration_id", "return_date", "category"),
    FIELDS,
    ("RETURN_PERIOD",),
)
COLUMNS = (
    Column("category", "Table / allocation"),
    Column("return_date", "Return date", "DATE"),
    Column("event_date", "Source date", "DATE"),
    Column("reference", "Source reference", "IDENTIFIER"),
    Column("currency", "Currency"),
    *(Column(head, head.upper(), "MONEY", "currency") for head in FIELDS),
    Column("source_entity", "Source"),
    Column("source_id", "Source ID", "IDENTIFIER"),
    Column("explanation", "Explanation"),
)


def context(registrations: tuple[dict[str, Any], ...], values: dict[str, Any]) -> dict[str, Any]:
    registration = next(
        (
            row
            for row in registrations
            if row["id"] == values["registration_id"] and applicable(row)
        ),
        None,
    )
    if registration is None:
        raise ValidationFailedError("select an eligible company GSTIN")
    frequency = "QRMP" if "-Q" in values["period"] else "MONTHLY"
    try:
        start, end = period_bounds(values["period"], frequency)
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    profiles = [
        row
        for row in registration.get("filing_preferences", [])
        if row["frequency"] == frequency
        and row["valid_from"] <= start.isoformat()
        and (row.get("valid_to") is None or row["valid_to"] > end.isoformat())
    ]
    if len(profiles) != 1:
        raise ValidationFailedError(
            "configure one dated GST filing preference covering the complete return period"
        )
    if registration["valid_from"] > end.isoformat() or (
        registration.get("valid_to") and registration["valid_to"] <= start.isoformat()
    ):
        raise ValidationFailedError("GSTIN was not valid during the selected return period")
    return {
        "registration": registration,
        "frequency": frequency,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
    }


def result(
    records: list[dict[str, Any]],
    values: Mapping[str, Any],
    sequence: int | None = None,
    unresolved: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    captured = values["_gst_context"]
    registration = captured["registration"]
    start, end = (
        dt.date.fromisoformat(captured["date_from"]),
        dt.date.fromisoformat(captured["date_to"]),
    )
    evidence = calculate(
        records, registration, start, end, sequence=sequence, unresolved_sources=unresolved
    )
    selected = [
        row
        for row in records
        if str(row["registration_id"]) == registration["id"]
        and start.isoformat() <= row["return_date"] <= end.isoformat()
    ]
    selected.sort(
        key=lambda row: (row["return_date"], row["category"], row["reference"], row["id"])
    )
    return selected, {"gstr3b": evidence, "row_count": len(selected)}


class GstAdapter(ReferenceAdapter):
    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        records = [
            row.data | {"id": str(row.source_id)}
            for row in facts
            if row.entity == "gst_return_record" and row.data
        ]
        return result(records, values)


def registration(implementation_hash: str) -> Registration[ReferenceAdapter]:
    handler = GstAdapter("GSTR3B", Gstr3bParameters)
    definition = ReportDefinition(
        "GSTR3B",
        1,
        "GSTR-3B",
        "GSTIN and period return preparation, source reconciliation and payment workings.",
        implementation_hash,
        fingerprint(handler.parameters()),
        ("gst_return",),
        (),
        tuple(sorted(INPUT_PERMISSIONS)),
        (View("default", "Contributing records", COLUMNS),),
        resource_class="BULK",
    )
    return Registration(definition, handler)
