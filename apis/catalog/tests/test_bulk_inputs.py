import base64

import pytest
from billing_platform.bulk_files import Cell, csv_document, xlsx_document
from billing_platform.errors import ValidationFailedError

from catalog.schemas.bulk import FileStage
from catalog.tasks.bulk_inputs import cell_value, decode_stage, exact_json, schema_kinds


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":1.2}', '{"x":NaN}', '{"x":Infinity}'])
def test_file_json_never_accepts_duplicate_or_inexact_values(raw: str) -> None:
    with pytest.raises(ValueError):
        exact_json(raw)


def test_native_cells_preserve_exact_values_and_nullable_shapes() -> None:
    assert cell_value(Cell("-2", "n"), {"type": "integer"}, {}) == -2
    assert cell_value(Cell("true"), {"type": "boolean"}, {}) is True
    assert cell_value(Cell("false"), {"type": "boolean"}, {}) is False
    assert cell_value(Cell("1", "b"), {"type": "boolean"}, {}) is True
    assert cell_value(Cell("0", "b"), {"type": "boolean"}, {}) is False
    assert cell_value(Cell('{"price":"1.2000"}'), {"type": "object"}, {}) == {"price": "1.2000"}
    assert cell_value(Cell('["001"]'), {"type": "array"}, {}) == ["001"]
    assert schema_kinds(
        {"anyOf": [{"$ref": "#/$defs/Amount"}, {"type": "null"}]}, {"Amount": {"type": "string"}}
    ) == {"string", "null"}
    assert schema_kinds({}, {}) == set()
    with pytest.raises(ValueError):
        cell_value(Cell("001", "n"), {"type": "string"}, {})
    with pytest.raises(ValueError):
        schema_kinds({"$ref": "#/$defs/Cycle"}, {"Cycle": {"$ref": "#/$defs/Cycle"}})


@pytest.mark.parametrize(
    "extra,value", [("data", "[]"), ("unknown", "x"), ("data", '{"name":"A","name":"B"}')]
)
def test_unknown_duplicate_or_non_object_command_columns_are_rejected(
    extra: str, value: str
) -> None:
    raw = csv_document(
        ["_key", "_set", "_resource", extra],
        [["row", "row", "unit_of_measure", value]],
        template=True,
    )
    with pytest.raises(ValidationFailedError):
        decode_stage(FileStage(format="CSV", content_base64=base64.b64encode(raw).decode()))


def test_duplicate_data_column_and_explicit_column_cannot_overwrite() -> None:
    raw = csv_document(
        ["_key", "_set", "_resource", "data", "name"],
        [["row", "row", "unit_of_measure", '{"name":"A"}', "B"]],
        template=True,
    )
    with pytest.raises(ValidationFailedError):
        decode_stage(FileStage(format="CSV", content_base64=base64.b64encode(raw).decode()))


def test_update_file_preserves_blank_vs_explicit_clear_and_dependencies() -> None:
    raw = xlsx_document(
        ["_key", "_set", "_resource", "_code", "name", "symbol", "_clear_fields"],
        [["row", "row", "unit_of_measure", "EA", "", "pc", "name"]],
    )
    batch, original, mime = decode_stage(
        FileStage(format="XLSX", mode="UPDATE_ONLY", content_base64=base64.b64encode(raw).decode())
    )
    assert original == raw and mime.endswith("sheet")
    assert batch.records[0].data == {"symbol": "pc"} and batch.records[0].clear_fields == ["name"]
    assert batch.records[0].target.code == "EA"
