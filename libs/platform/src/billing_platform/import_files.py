"""Lossless bounded file normalization; owner adapters provide field schemas."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from billing_platform.bulk import MAX_BYTES, BulkRecord, BulkTarget
from billing_platform.bulk_files import Cell, csv_document, read_csv, read_xlsx, xlsx_workbook
from billing_platform.import_contracts import CONTROLS, MARKER, FileFormat, ImportBatch, SourceFile

TEMPLATE_SHEETS = frozenset(
    {"Import_Instructions", "Import_Fields", "Import_Options", "Import_Definitions"}
)


def exact_json(raw: str) -> Any:
    def reject(value: str) -> None:
        raise ValueError("JSON decimals must be quoted text")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON property")
            result[key] = value
        return result

    return json.loads(raw, parse_float=reject, parse_constant=reject, object_pairs_hook=unique)


def schema_kinds(schema: dict[str, Any], definitions: dict[str, Any], depth: int = 0) -> set[str]:
    if depth > 16:
        raise ValueError("template schema nesting exceeds its bound")
    if "$ref" in schema:
        return schema_kinds(definitions[schema["$ref"].rsplit("/", 1)[1]], definitions, depth + 1)
    if "anyOf" in schema:
        return set().union(
            *(schema_kinds(item, definitions, depth + 1) for item in schema["anyOf"])
        )
    return {schema["type"]} if "type" in schema else set()


def cell_value(cell: Cell, schema: dict[str, Any], definitions: dict[str, Any]) -> Any:
    if cell.value.startswith("{") and "$ref" in cell.value:
        return exact_json(cell.value)
    kinds = schema_kinds(schema, definitions)
    if cell.kind != "text" and "string" in kinds:
        raise ValueError("identifiers and decimals require text cells")
    if "integer" in kinds and cell.value.lstrip("-").isdigit():
        return int(cell.value)
    if "boolean" in kinds:
        if cell.kind == "b" and cell.value in {"0", "1"}:
            return cell.value == "1"
        if cell.value in {"true", "false"}:
            return cell.value == "true"
    if "object" in kinds or "array" in kinds:
        return exact_json(cell.value)
    return cell.value


def decode_files(
    files: list[SourceFile], snapshot: dict[str, Any], options: dict[str, Any]
) -> tuple[ImportBatch, list[tuple[SourceFile, bytes]], dict[str, str]]:
    if len({item.filename for item in files}) != len(files):
        raise ValueError("source filenames must be unique")
    sources, records, locations = [], [], {}
    tabular = snapshot.get("tabular")
    if tabular and (options["mode"] != "CREATE_ONLY" or options["atomicity"] != "CHANGE_SET"):
        raise ValueError("flat templates require independent create rows")
    total = 0
    for file in files:
        raw = base64.b64decode(file.content_base64, validate=True)
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError("combined source files exceed 8 MiB")
        rows = (
            read_xlsx(raw, marker=MARKER, ignored_sheets=TEMPLATE_SHEETS)
            if file.format == "XLSX"
            else read_csv(raw, marker=MARKER, delimiter="\t" if file.format == "TSV" else ",")
        )
        sources.append((file, raw))
        for row in rows:
            controls = {key: cell.value for key, cell in row.cells.items() if key in CONTROLS}
            if any(row.cells[key].kind != "text" for key in controls):
                raise ValueError("control columns require text")
            if tabular:
                if any(value for key, value in controls.items() if key != "_key"):
                    raise ValueError("flat templates require independent create rows")
                identity = hashlib.sha256(
                    (file.filename + "\0" + row.sheet + "\0" + str(row.number)).encode()
                ).hexdigest()[:24]
                key = controls.get("_key") or "row_" + identity
                controls = {
                    "_key": key,
                    "_set": key,
                    "_resource": tabular["resource"],
                    "_action": tabular["action"],
                }
            resource = controls.get("_resource", "")
            action = controls.get("_action") or "AUTO"
            schema_action = (
                ("UPDATE" if options["mode"] == "UPDATE_ONLY" else "CREATE")
                if action == "AUTO"
                else action
            )
            schema = snapshot["schemas"][resource + ":" + schema_action]
            props = schema["properties"]
            values = (
                exact_json(row.cells["_payload"].value)
                if row.cells.get("_payload", Cell("")).value
                else {}
            )
            if not isinstance(values, dict) or not values.keys() <= props.keys():
                raise ValueError("payload requires configured fields")
            for key, cell in row.cells.items():
                if key in CONTROLS or key == "_payload":
                    continue
                if key not in props:
                    raise ValueError("unknown native field")
                if cell.value != "":
                    if key in values:
                        raise ValueError("duplicate command field")
                    values[key] = cell_value(cell, props[key], schema.get("$defs", {}))
            if tabular:
                for field, default in tabular.get("defaults", {}).items():
                    if field in props:
                        values.setdefault(field, default)
            record = BulkRecord(
                key=controls.get("_key", ""),
                change_set=controls.get("_set", ""),
                resource=resource,
                action=action,
                data=values,
                target=BulkTarget.model_validate(
                    {
                        name: controls[column]
                        for column, name in (
                            ("_id", "id"),
                            ("_code", "code"),
                            ("_target_record", "record"),
                            ("_target_field", "field"),
                        )
                        if controls.get(column)
                    }
                ),
                depends_on=controls.get("_depends_on", "").split(",")
                if controls.get("_depends_on")
                else [],
                clear_fields=controls.get("_clear_fields", "").split(",")
                if controls.get("_clear_fields")
                else [],
                source_sheet=row.sheet,
                source_row=row.number,
            )
            for field, value in values.items():
                if not tabular and "enum" in props[field] and value not in props[field]["enum"]:
                    raise ValueError("value differs from template options")
            records.append(record)
            locations[record.key] = file.filename
    return ImportBatch(**options, records=records), sources, locations


def document(
    file_format: FileFormat, sheets: list[tuple[str, list[str], list[list[str]]]]
) -> bytes:
    if file_format == "XLSX":
        return xlsx_workbook(sheets, marker=MARKER)
    if len(sheets) != 1:
        raise ValueError("CSV/TSV downloads require one table")
    _, columns, rows = sheets[0]
    return csv_document(
        columns, rows, template=True, marker=MARKER, delimiter="\t" if file_format == "TSV" else ","
    )


def template_document(
    snapshot: dict[str, Any], resource: str, action: str, file_format: FileFormat
) -> bytes:
    schema = snapshot["schemas"][resource + ":" + action]
    tabular = snapshot.get("tabular")
    if tabular and (resource != tabular["resource"] or action != tabular["action"]):
        raise ValueError("flat templates require independent create rows")
    sheets: list[tuple[str, list[str], list[list[str]]]] = [
        ("Records", [*([] if tabular else CONTROLS), *schema["properties"]], [])
    ]
    if file_format == "XLSX":
        instructions = [
            ["instructions", snapshot.get("instructions", "Use the versioned native template.")],
            ["resource", resource],
            ["action", action],
            [
                "blank_cells",
                "Use the stated defaults."
                if tabular
                else "Omit fields; use _clear_fields for explicit clearing.",
            ],
            ["types", "Identifiers, dates and decimals are text; nested values use exact JSON."],
            [
                "nested_fields",
                "Resolve nested field references using Import_Definitions; "
                "enter those values as JSON text.",
            ],
        ]
        fields = [
            [
                name,
                str(value.get("title", name)),
                "true" if name in schema.get("required", []) else "false",
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            ]
            for name, value in schema["properties"].items()
        ]
        options = [
            [
                source,
                str(item.get("id", "")),
                str(item.get("code", "")),
                str(item.get("name", item.get("label", ""))),
            ]
            for source, values in snapshot.get("options", {}).items()
            for item in values.get("items", [])
        ][:1000]
        sheets.extend(
            [
                ("Import_Instructions", ["key", "value"], instructions),
                ("Import_Fields", ["field", "label", "required", "schema"], fields),
                ("Import_Options", ["source", "id", "code", "label"], options),
                (
                    "Import_Definitions",
                    ["definition", "schema"],
                    [
                        [name, json.dumps(value, ensure_ascii=False, separators=(",", ":"))]
                        for name, value in schema.get("$defs", {}).items()
                    ],
                ),
            ]
        )
    return document(file_format, sheets)
