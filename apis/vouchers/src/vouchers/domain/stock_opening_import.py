"""Bounded opening spreadsheet mapping into ordinary native voucher inputs."""

import base64
import binascii
from typing import Any

from billing_platform.bulk_files import read_csv, read_xlsx
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from pydantic import ValidationError

from vouchers.schemas.stock_opening_import import OpeningImportDocument, OpeningImportStage

MARKER = "_stock_opening_schema_version"
REQUIRED = (
    "type_revision_id",
    "opening_control_id",
    "stock_date",
    "currency",
    "opening_mode",
    "reason",
    "line_id",
    "item_id",
    "item_version",
    "base_unit_id",
    "warehouse_id",
    "quantity",
    "received_value",
    "source_key",
    "entered_unit_id",
    "unit_revision_id",
    "entered_quantity",
    "cost_mode",
    "history_known",
)
OPTIONAL = (
    "measured_base_quantity",
    "class_id",
    "bin_id",
    "lot_id",
    "unit_ids",
    "unit_cost",
    "priced_quantity",
    "received_on",
    "cohort_order",
    "zero_value_reason",
    "opening_journal_line_id",
)


def decode(body: OpeningImportStage) -> OpeningImportDocument:
    if body.document is not None:
        try:
            canonical_json(body.document.model_dump(mode="json"), maximum_bytes=2_097_152)
        except ValueError as error:
            raise ValidationFailedError("opening import exceeds two MiB") from error
        return body.document
    try:
        raw = base64.b64decode(body.content_base64 or "", validate=True)
        if not raw or len(raw) > 2_097_152:
            raise ValueError("opening file requires one byte to two MiB")
        rows = (
            read_xlsx(raw, marker=MARKER)
            if body.format == "XLSX"
            else read_csv(raw, marker=MARKER, delimiter="\t" if body.format == "TSV" else ",")
        )
        if not rows or len(rows) > 1000:
            raise ValueError("opening import requires one to one thousand allocation rows")
        drafts: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        common: tuple[str, ...] | None = None
        unit_count = 0
        for row in rows:
            data = {key: cell.value.strip() for key, cell in row.cells.items()}
            if (
                set(data) - set(REQUIRED + OPTIONAL)
                or any(not data.get(key) for key in REQUIRED)
                or any(cell.value and cell.kind != "text" for cell in row.cells.values())
            ):
                raise ValueError(f"row {row.number}: use required native columns and text cells")
            if data["history_known"] not in {"true", "false"} or not data["item_version"].isdigit():
                raise ValueError(
                    f"row {row.number}: use true/false history and an integer item version"
                )
            header = tuple(
                data.get(key, "")
                for key in (
                    "type_revision_id",
                    "class_id",
                    "opening_control_id",
                    "stock_date",
                    "currency",
                    "opening_mode",
                    "reason",
                )
            )
            members = [
                value.strip() for value in data.get("unit_ids", "").split(";") if value.strip()
            ]
            if (
                current is None
                or header != common
                or len(current["lines"]) == 100
                or unit_count + len(members) > 1000
            ):
                current = {
                    "type_revision_id": data["type_revision_id"],
                    "document_date": data["stock_date"],
                    "posting_date": data["stock_date"],
                    "stock_date": data["stock_date"],
                    "currency": data["currency"],
                    "mode": "ITEMS",
                    "narration": data["reason"],
                    "lines": [],
                    "stock": {
                        "action": "OPENING",
                        "stock_date": data["stock_date"],
                        "currency": data["currency"],
                        "opening_mode": data["opening_mode"],
                        "opening_control_id": data["opening_control_id"],
                        "reason": data["reason"],
                        "lines": [],
                    },
                }
                if data.get("class_id"):
                    current["class_id"] = data["class_id"]
                drafts.append(current)
                common, unit_count = header, 0
            capture: dict[str, Any] = {
                key: data[key]
                for key in (
                    "source_key",
                    "entered_unit_id",
                    "unit_revision_id",
                    "entered_quantity",
                    "measured_base_quantity",
                    "cost_mode",
                )
            }
            capture["history_known"] = data["history_known"] == "true"
            capture.update(
                {
                    key: data[key]
                    for key in ("unit_cost", "priced_quantity", "received_on")
                    if data.get(key)
                }
            )
            if data.get("cohort_order"):
                capture["cohort_order"] = int(data["cohort_order"])
            allocation = {
                "line_id": data["line_id"],
                "item_id": data["item_id"],
                "warehouse_id": data["warehouse_id"],
                "quantity": data["quantity"],
                "received_value": data["received_value"],
                "opening": capture,
                "unit_ids": members,
            }
            allocation.update(
                {
                    key: data[key]
                    for key in ("bin_id", "lot_id", "zero_value_reason", "opening_journal_line_id")
                    if data.get(key)
                }
            )
            current["stock"]["lines"].append(allocation)
            current["lines"].append(
                {
                    "line_key": data["line_id"],
                    "item": {
                        "item_id": data["item_id"],
                        "item_version": int(data["item_version"]),
                        "unit_id": data["base_unit_id"],
                        "actual_quantity": data["quantity"],
                        "billed_quantity": "0",
                    },
                }
            )
            unit_count += len(members)
        return OpeningImportDocument.model_validate({"vouchers": drafts})
    except (ValueError, binascii.Error, ValidationError) as error:
        raise ValidationFailedError(
            "opening import requires valid versioned native allocation data",
            fields={
                "document": "Check columns, decimal text, dates, units and distinct source keys."
            },
        ) from error
