"""Owner-selected flat templates retain the normal import audit and file bounds."""

import base64

import pytest

from billing_platform.bulk_files import read_csv, read_xlsx
from billing_platform.import_contracts import MARKER, SourceFile
from billing_platform.import_files import decode_files, document, template_document


def snapshot():
    return {
        "tabular": {"resource": "ready_thing", "action": "CREATE"},
        "schemas": {
            "ready_thing:CREATE": {
                "properties": {"name": {"type": "string"}, "kind": {"enum": ["GOODS"]}},
                "required": ["name"],
            }
        },
    }


@pytest.mark.parametrize("file_format", ["CSV", "TSV", "XLSX"])
def test_flat_template_and_input_do_not_require_internal_commands(file_format):
    raw_template = template_document(snapshot(), "ready_thing", "CREATE", file_format)
    if file_format != "XLSX":
        assert b"_resource" not in raw_template and b"_set" not in raw_template
    raw = document(
        file_format, [("Records", ["name", "kind"], [["One", "GOODS"], ["Two", "WRONG"]])]
    )
    source = SourceFile(
        filename="input." + file_format.lower(),
        format=file_format,
        content_base64=base64.b64encode(raw).decode(),
    )
    options = {"mode": "CREATE_ONLY", "atomicity": "CHANGE_SET", "on_error": "CONTINUE_INDEPENDENT"}
    batch, originals, locations = decode_files([source], snapshot(), options)
    assert len(batch.records) == 2 and originals[0][1] == raw
    assert len({row.key for row in batch.records}) == 2
    assert all(row.resource == "ready_thing" and row.change_set == row.key for row in batch.records)
    assert set(locations.values()) == {source.filename}
    # Domain values are validated per row, so one bad value has retained diagnostics.
    assert batch.records[1].data["kind"] == "WRONG"
    assert decode_files([source], snapshot(), options)[0] == batch
    rows = (
        read_xlsx(raw, marker=MARKER)
        if file_format == "XLSX"
        else read_csv(raw, marker=MARKER, delimiter="\t" if file_format == "TSV" else ",")
    )
    assert batch.records[0].source_row == rows[0].number


@pytest.mark.parametrize(
    "control,value", [("_resource", "other"), ("_action", "UPDATE"), ("_id", "x"), ("_set", "all")]
)
def test_flat_input_cannot_change_native_execution_semantics(control, value):
    raw = document("CSV", [("Records", ["name", control], [["One", value]])])
    source = SourceFile(
        filename="input.csv", format="CSV", content_base64=base64.b64encode(raw).decode()
    )
    with pytest.raises(ValueError, match="independent create"):
        decode_files(
            [source],
            snapshot(),
            {"mode": "CREATE_ONLY", "atomicity": "CHANGE_SET", "on_error": "CONTINUE_INDEPENDENT"},
        )
