import base64

from billing_platform.bulk_files import read_xlsx
from billing_platform.import_contracts import MARKER, SourceFile
from billing_platform.import_files import decode_files, document, template_document
from tests.test_import_framework import ThingInput


def test_workbook_metadata_sheets_do_not_become_import_commands() -> None:
    snapshot = {
        "schemas": {"thing:CREATE": ThingInput.model_json_schema()},
        "options": {"things": {"items": [{"id": "0001", "code": "ACTIVE"}]}},
        "instructions": "Enter exact text values.",
    }
    assert template_document(snapshot, "thing", "CREATE", "XLSX").startswith(b"PK")
    raw = document(
        "XLSX",
        [
            ("Records", ["_key", "_set", "_resource", "name"], [["one", "one", "thing", "One"]]),
            ("Import_Instructions", ["key", "value"], [["help", "Instructions"]]),
            ("Import_Options", ["id", "code"], [["0001", "ACTIVE"]]),
            ("Import_Definitions", ["definition", "schema"], [["Nested", '{"type":"object"}']]),
        ],
    )
    batch, _, _ = decode_files(
        [
            SourceFile(
                filename="template.xlsx",
                format="XLSX",
                content_base64=base64.b64encode(raw).decode(),
            )
        ],
        snapshot,
        {"mode": "CREATE_ONLY", "on_error": "STOP", "atomicity": "CHANGE_SET"},
    )
    assert len(batch.records) == 1 and batch.records[0].data == {"name": "One"}


def test_workbook_exports_resolvable_nested_field_definitions():
    snapshot = {
        "schemas": {
            "thing:CREATE": {
                "properties": {"name": {"type": "string"}, "setup": {"$ref": "#/$defs/Setup"}},
                "$defs": {"Setup": {"type": "object", "properties": {"code": {"type": "string"}}}},
            }
        }
    }
    raw = template_document(snapshot, "thing", "CREATE", "XLSX")
    rows = read_xlsx(raw, marker=MARKER)
    definitions = [row for row in rows if row.sheet == "Import_Definitions"]
    assert len(definitions) == 1
    assert definitions[0].cells["definition"].value == "Setup"
    assert '"code"' in definitions[0].cells["schema"].value
