"""Translate bounded transport files to the same exact command envelope as JSON."""

import base64
import binascii

from billing_platform.bulk import BulkBatch, BulkRecord
from billing_platform.bulk_files import Cell, read_csv, read_xlsx
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.import_files import cell_value, exact_json
from billing_platform.import_files import schema_kinds as schema_kinds

from catalog.domain.stock_facts import assert_no_stock_fact_columns
from catalog.schemas.bulk import FileStage, JsonStage
from catalog.tasks.bulk_registry import operation

CONTROLS = (
    "_key",
    "_set",
    "_resource",
    "_action",
    "_id",
    "_code",
    "_external_system",
    "_external_key",
    "_target_record",
    "_target_field",
    "_depends_on",
    "_clear_fields",
)


def decode_stage(body: JsonStage | FileStage) -> tuple[BulkBatch, bytes, str]:
    if isinstance(body, JsonStage):
        batch = BulkBatch.model_validate(body.model_dump(exclude={"format"}))
        return (
            batch,
            canonical_json(batch.model_dump(mode="json"), maximum_bytes=8 * 1024 * 1024),
            "application/json",
        )
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
        rows = read_csv(raw) if body.format == "CSV" else read_xlsx(raw)
        # Before any row is interpreted: a header naming a stock fact is refused by name, not
        # as one more "invalid bulk file". The whole file is rejected either way, so the only
        # thing at stake is whether the author can tell which column to delete (C7.11).
        assert_no_stock_fact_columns(tuple(dict.fromkeys(key for row in rows for key in row.cells)))
        records: list[BulkRecord] = []
        for row in rows:
            cells = row.cells
            controls = {key: cell.value for key, cell in cells.items() if key in CONTROLS}
            if any(cells[key].kind != "text" for key in controls):
                raise ValueError("control columns require text cells")
            resource = controls.get("_resource", "")
            action = controls.get("_action") or "AUTO"
            # AUTO shares the create/update field vocabulary; final selection happens
            # under current object authority in the worker.
            op = operation(
                resource,
                ("UPDATE" if body.mode == "UPDATE_ONLY" else "CREATE")
                if action == "AUTO"
                else action,
            )
            document = op.schema.model_json_schema()
            properties = document.get("properties", {})
            data = exact_json(cells["data"].value) if cells.get("data", Cell("")).value else {}
            if not isinstance(data, dict):
                raise ValueError("data requires an object")
            for key, cell in cells.items():
                if key in CONTROLS or key == "data" or cell.value == "":
                    continue
                if key not in properties or key in data:
                    raise ValueError("unknown or duplicate command column")
                data[key] = cell_value(cell, properties[key], document.get("$defs", {}))
            target = {
                name: controls[column]
                for column, name in (
                    ("_id", "id"),
                    ("_code", "code"),
                    ("_external_system", "external_system"),
                    ("_external_key", "external_key"),
                    ("_target_record", "record"),
                    ("_target_field", "field"),
                )
                if controls.get(column)
            }
            records.append(
                BulkRecord.model_validate(
                    {
                        "key": controls.get("_key", ""),
                        "change_set": controls.get("_set", ""),
                        "resource": resource,
                        "action": action,
                        "target": target,
                        "data": data,
                        "depends_on": controls.get("_depends_on", "").split(",")
                        if controls.get("_depends_on")
                        else [],
                        "clear_fields": controls.get("_clear_fields", "").split(",")
                        if controls.get("_clear_fields")
                        else [],
                        "source_sheet": row.sheet,
                        "source_row": row.number,
                    }
                )
            )
        batch = BulkBatch(
            schema_version=body.schema_version,
            mode=body.mode,
            atomicity=body.atomicity,
            on_error=body.on_error,
            records=records,
        )
        return (
            batch,
            raw,
            "text/csv"
            if body.format == "CSV"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except (ValueError, TypeError, KeyError, binascii.Error, RecursionError) as exc:
        raise ValidationFailedError(
            "invalid bulk file; use the versioned template and exact text identifiers"
        ) from exc
