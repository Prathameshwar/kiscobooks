"""Opening file parsing preserves native identities and rejects ambiguous data."""

import base64
import copy
import uuid

import pytest
from billing_platform.bulk_files import csv_document, xlsx_workbook
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from vouchers.domain.stock_opening_import import MARKER, OPTIONAL, REQUIRED, decode
from vouchers.schemas.stock_opening_import import OpeningImportStage


def row():
    data = {key: "" for key in (*REQUIRED, *OPTIONAL)}
    data.update(
        {
            key: str(uuid.uuid4())
            for key in (
                "type_revision_id",
                "opening_control_id",
                "line_id",
                "item_id",
                "base_unit_id",
                "warehouse_id",
                "entered_unit_id",
                "unit_revision_id",
            )
        }
    )
    data.update(
        stock_date="2026-04-01",
        currency="INR",
        opening_mode="COMBINED",
        reason="Reviewed migration evidence",
        quantity="2",
        received_value="25.50",
        source_key="COHORT-A",
        entered_quantity="2",
        cost_mode="VALUE",
        history_known="false",
        item_version="1",
    )
    return data


def upload(data=None, *, file_format="CSV", marker=MARKER, count=1):
    data = data or row()
    columns = list(data)
    rows = [[data[column] for column in columns] for _ in range(count)]
    if file_format == "XLSX":
        raw = xlsx_workbook([("openings", columns, rows)], marker=marker)
    else:
        raw = csv_document(
            columns,
            rows,
            marker=marker,
            template=True,
            delimiter="\t" if file_format == "TSV" else ",",
        )
    return OpeningImportStage(
        source_key="source-a", format=file_format, content_base64=base64.b64encode(raw).decode()
    )


@pytest.mark.parametrize("file_format", ["CSV", "TSV", "XLSX"])
def test_text_native_allocations_round_trip_with_normalized_source_keys(file_format):
    result = decode(upload(file_format=file_format))
    assert len(result.vouchers) == 1
    body = result.vouchers[0]
    assert body.stock.lines[0].opening.source_key == "cohort-a"
    assert body.stock.lines[0].received_value == 25.5
    assert not body.stock.lines[0].opening.history_known


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "1e2"},
        {"quantity": "NaN"},
        {"quantity": "-1"},
        {"item_version": "1.5"},
        {"item_version": ""},
        {"item_id": "a product name"},
        {"history_known": "yes"},
        {"history_known": "true"},
        {"cost_mode": "RATE"},
        {"cost_mode": "VALUE", "unit_cost": "2"},
        {"warehouse_id": "Main warehouse"},
        {"unexpected": "value"},
        {"received_on": "2026-05-01", "history_known": "false"},
        {"unit_ids": "bad-unit-reference"},
        {"cohort_order": "not-a-number"},
    ],
)
def test_invalid_native_mapping_has_safe_field_errors(change):
    with pytest.raises(ValidationFailedError) as found:
        decode(upload(row() | change))
    assert "document" in found.value.extra["fields"]


def test_bad_marker_base64_empty_and_duplicate_rows_are_refused():
    for body in (
        upload(marker="wrong"),
        upload(count=2),
        OpeningImportStage(source_key="bad", format="CSV", content_base64="!!!!"),
        OpeningImportStage(source_key="empty", format="CSV", content_base64=""),
    ):
        with pytest.raises(ValidationFailedError):
            decode(body)


def test_json_uses_the_same_typed_native_contract_and_does_not_mutate():
    original = decode(upload()).model_dump(mode="json")
    before = copy.deepcopy(original)
    result = decode(OpeningImportStage(source_key="JSON-A", document=original))
    assert result.model_dump(mode="json") == before
    assert original == before
    with pytest.raises(ValidationError):
        OpeningImportStage(
            source_key="duplicate-source", document=original, format="CSV", content_base64="abcd"
        )


def test_conversion_rate_and_known_age_evidence_are_preserved_as_exact_text():
    data = row() | {
        "cost_mode": "RATE",
        "unit_cost": "12.7500",
        "priced_quantity": "1",
        "history_known": "true",
        "received_on": "2025-12-01",
        "cohort_order": "2",
    }
    result = decode(upload(data)).vouchers[0].stock.lines[0].opening
    assert result.received_on.isoformat() == "2025-12-01"
    assert result.cohort_order == 2 and result.unit_cost == 12.75


def test_chunks_cannot_change_reviewed_fifo_tie_order():
    original = decode(upload()).model_dump(mode="json")
    later = copy.deepcopy(original["vouchers"][0])
    later["stock"]["lines"][0]["opening"]["source_key"] = "cohort-0"
    later["stock"]["lines"][0]["line_id"] = str(uuid.uuid4())
    later["lines"][0]["line_key"] = later["stock"]["lines"][0]["line_id"]
    with pytest.raises(ValidationError, match="order opening chunks"):
        OpeningImportStage(
            source_key="bad-order", document={"vouchers": [*original["vouchers"], later]}
        )


def test_oversized_native_json_returns_validation_error_before_database_work():
    data = row()
    columns = list(data)
    rows = []
    for index in range(1000):
        entry = data | {
            "line_id": str(uuid.uuid4()),
            "source_key": f"source-{index:04d}",
            "cohort_order": str(index + 1),
            "quantity": "10",
            "entered_quantity": "10",
            "unit_ids": ";".join(str(uuid.uuid4()) for _ in range(10)),
        }
        rows.append([entry[key] for key in columns])
    raw = csv_document(columns, rows, marker=MARKER, template=True)
    document = decode(
        OpeningImportStage(
            source_key="large-file", format="CSV", content_base64=base64.b64encode(raw).decode()
        )
    ).model_dump(mode="json")
    for voucher in document["vouchers"]:
        for line in voucher["lines"]:
            line["description"] = "x" * 1000
    stage = OpeningImportStage(source_key="oversized-json", document=document)
    with pytest.raises(ValidationFailedError, match="two MiB"):
        decode(stage)
