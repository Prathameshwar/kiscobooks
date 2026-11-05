"""Opening declarations retain exact source amounts, dates and bounded native chunks."""

import base64
import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from accounting.domain.financial_opening import declaration_hash, execution_chunks
from accounting.domain.financial_opening_import import MARKER, REQUIRED, decode
from accounting.schemas.financial_opening import OpeningDeclaration
from accounting.schemas.financial_opening_import import FinancialOpeningImportStage

ACCOUNT = uuid.UUID("01990000-0000-7000-8000-000000000001")
OFFSET = uuid.UUID("01990000-0000-7000-8000-000000000002")


def declaration() -> dict:
    return {
        "posting_date": "2026-04-01",
        "currency": "INR",
        "source_system": "legacy",
        "source_id": "migration-1",
        "covered_through": "2026-03-31",
        "reason": "Reviewed migration",
        "entries": [
            {
                "source_key": "bank",
                "account_id": str(ACCOUNT),
                "side": "DEBIT",
                "currency": "INR",
                "amount": "100.2500",
                "exchange_rate": "1",
            },
            {
                "source_key": "capital",
                "account_id": str(OFFSET),
                "side": "CREDIT",
                "currency": "INR",
                "amount": "100.2500",
                "exchange_rate": "1",
            },
        ],
    }


def test_exact_declaration_and_stable_fingerprint() -> None:
    body = OpeningDeclaration.model_validate(declaration())
    assert body.posting_date == dt.date(2026, 4, 1)
    assert isinstance(body.entries[0].amount, Decimal)
    assert len(declaration_hash(body)) == 64
    assert declaration_hash(body) == declaration_hash(body.model_copy(deep=True))


def test_duplicate_source_keys_and_float_amounts_are_rejected() -> None:
    body = declaration()
    body["entries"][1]["source_key"] = "bank"
    with pytest.raises(ValidationError):
        OpeningDeclaration.model_validate(body)
    body = declaration()
    body["entries"][0]["amount"] = 1.25
    with pytest.raises(ValidationError):
        OpeningDeclaration.model_validate(body)


def test_small_execution_is_a_single_native_balanced_opening() -> None:
    body = OpeningDeclaration.model_validate(declaration())
    chunks = execution_chunks(body, "INR", 2, "half_up")
    assert len(chunks) == 1
    assert len(chunks[0].lines) == 2
    assert chunks[0].posting_date == body.posting_date


def test_unbalanced_declaration_cannot_be_hidden_by_a_counterpart() -> None:
    raw = declaration()
    raw["entries"][1]["amount"] = "100"
    with pytest.raises(ValidationFailedError, match="balance"):
        execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")


def test_historical_carrying_value_is_authoritative_and_base_money_cannot_be_overridden() -> None:
    body = declaration()
    body["entries"][0].update(currency="USD", amount="10", exchange_rate="90", base_amount="850")
    body["entries"][1]["amount"] = "850"
    plan = execution_chunks(OpeningDeclaration.model_validate(body), "INR", 2, "half_up")
    assert plan[0].lines[0].opening_base_amount == Decimal("850")
    body["entries"][0]["currency"] = "INR"
    with pytest.raises(ValidationFailedError):
        execution_chunks(OpeningDeclaration.model_validate(body), "INR", 2, "half_up")


def test_same_day_coverage_requires_review_and_documents_cannot_exceed_coverage() -> None:
    raw = declaration() | {"covered_through": "2026-04-01"}
    with pytest.raises(ValidationError):
        OpeningDeclaration.model_validate(raw)
    assert OpeningDeclaration.model_validate(raw | {"same_day_reviewed": True}).same_day_reviewed
    raw = declaration()
    raw["entries"][0]["documents"] = [
        {
            "reference": "OLD",
            "amount": "100.25",
            "document_date": "2026-04-01",
            "due_date": "2026-04-10",
        }
    ]
    with pytest.raises(ValidationError):
        OpeningDeclaration.model_validate(raw)


def test_typed_json_and_versioned_csv_import_retain_exact_values() -> None:
    import csv
    import io

    raw = declaration()
    original = OpeningDeclaration.model_validate(raw)
    assert decode(FinancialOpeningImportStage(source_key="one", document=original)) == original
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow([MARKER, "1"])
    writer.writerow(REQUIRED)
    header = {key: value for key, value in raw.items() if key != "entries" and key != "currency"}
    for line in raw["entries"]:
        row = header | line | {"base_currency": "INR"}
        writer.writerow([row[key] for key in REQUIRED])
    encoded = base64.b64encode(content.getvalue().encode()).decode()
    assert (
        decode(FinancialOpeningImportStage(source_key="two", format="CSV", content_base64=encoded))
        == original
    )
    with pytest.raises(ValidationFailedError):
        decode(FinancialOpeningImportStage(source_key="three", format="CSV", content_base64="%%%"))


def test_legacy_payloads_keep_their_original_shapes() -> None:
    from accounting.schemas.ledger import JournalLineCreate
    from accounting.schemas.subledger import OpeningBill

    line = JournalLineCreate(
        account_id=ACCOUNT, side="DEBIT", currency="INR", amount="1", exchange_rate="1"
    )
    assert "opening_base_amount" not in line.model_dump(mode="json")
    bill = OpeningBill(
        line_sequence=1,
        reference="OLD",
        amount="1",
        document_date="2026-03-01",
        due_date="2026-03-31",
    )
    assert set(bill.model_dump(mode="json")) == {
        "line_sequence",
        "reference",
        "amount",
        "document_date",
        "due_date",
    }


def test_currency_execution_limits_and_declaration_byte_bound() -> None:
    raw = declaration()
    with pytest.raises(ValidationFailedError, match="base currency"):
        execution_chunks(
            OpeningDeclaration.model_validate(raw | {"currency": "USD"}), "INR", 2, "half_up"
        )
    raw["entries"] = [
        line | {"source_key": f"line-{index}-{side}"}
        for index in range(101)
        for side, line in enumerate(declaration()["entries"])
    ]
    with pytest.raises(ValidationFailedError, match="clearing"):
        execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")
    raw["entries"] = [
        raw["entries"][index % 202] | {"source_key": f"line-{index}", "description": "x" * 500}
        for index in range(4000)
    ]
    with pytest.raises(ValidationFailedError, match="two MiB"):
        declaration_hash(OpeningDeclaration.model_validate(raw))


@pytest.mark.parametrize("format_name", ["CSV", "TSV", "XLSX"])
def test_file_import_groups_bill_rows_without_losing_dates_or_values(format_name: str) -> None:
    from billing_platform.bulk_files import csv_document, xlsx_document

    raw = declaration()
    columns = [
        *REQUIRED,
        "document_source_key",
        "document_kind",
        "document_reference",
        "document_amount",
        "document_date",
        "due_date",
    ]
    header = {key: value for key, value in raw.items() if key not in {"entries", "currency"}}
    rows = []
    for index in range(2):
        data = (
            header
            | raw["entries"][0]
            | {
                "base_currency": "INR",
                "document_source_key": f"doc-{index}",
                "document_kind": "INVOICE",
                "document_reference": f"OLD-{index}",
                "document_amount": "50.125",
                "document_date": "2026-03-01",
                "due_date": "2026-04-15",
            }
        )
        rows.append([data[key] for key in columns])
    data = header | raw["entries"][1] | {"base_currency": "INR"}
    rows.append([data.get(key, "") for key in columns])
    content = (
        xlsx_document(columns, rows, marker=MARKER)
        if format_name == "XLSX"
        else csv_document(
            columns,
            rows,
            template=True,
            marker=MARKER,
            delimiter="\t" if format_name == "TSV" else ",",
        )
    )
    parsed = decode(
        FinancialOpeningImportStage(
            source_key="file", format=format_name, content_base64=base64.b64encode(content).decode()
        )
    )
    assert len(parsed.entries) == 2 and len(parsed.entries[0].documents) == 2
    plan = execution_chunks(parsed, "INR", 2, "half_up")
    assert len(plan[0].bills) == 2 and plan[0].bills[1].reference == "OLD-1"


@pytest.mark.parametrize("problem", ["empty", "missing", "header", "review", "entry"])
def test_file_import_rejects_inconsistent_or_incomplete_evidence(problem: str) -> None:
    from billing_platform.bulk_files import csv_document

    raw = declaration()
    header = {key: value for key, value in raw.items() if key not in {"entries", "currency"}}
    data = [
        header | line | {"base_currency": "INR", "same_day_reviewed": "false"}
        for line in raw["entries"]
    ]
    columns = [*REQUIRED, "same_day_reviewed"]
    if problem == "missing":
        data[0]["account_id"] = ""
    if problem == "header":
        data[1]["source_id"] = "different-source"
    if problem == "review":
        data[0]["same_day_reviewed"] = "yes"
    if problem == "entry":
        data[1]["source_key"] = data[0]["source_key"]
    content = csv_document(
        columns,
        [] if problem == "empty" else [[row[key] for key in columns] for row in data],
        marker=MARKER,
        template=True,
    )
    with pytest.raises(ValidationFailedError):
        decode(
            FinancialOpeningImportStage(
                source_key="invalid",
                format="CSV",
                content_base64=base64.b64encode(content).decode(),
            )
        )


def test_file_upload_enforces_its_decoded_byte_limit() -> None:
    with pytest.raises(ValidationFailedError):
        decode(
            FinancialOpeningImportStage(
                source_key="large",
                format="CSV",
                content_base64=base64.b64encode(b"x" * 2097153).decode(),
            )
        )


def test_clearing_chunks_are_individually_balanced_and_net_to_zero() -> None:
    raw = declaration()
    clear = uuid.UUID("01990000-0000-7000-8000-000000000003")
    raw["clearing_account_id"] = str(clear)
    raw["entries"] = [
        entry | {"source_key": f"line-{index}-{side}"}
        for index in range(201)
        for side, entry in enumerate(declaration()["entries"])
    ]
    plans = execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")
    assert len(plans) == 3 and all(2 <= len(plan.lines) <= 200 for plan in plans)
    assert (
        sum(
            (
                line.amount if line.side == "DEBIT" else -line.amount
                for plan in plans
                for line in plan.lines
                if line.account_id == clear
            ),
            Decimal(0),
        )
        == 0
    )
    for plan in plans:
        assert (
            sum(
                (
                    line.opening_base_amount if line.side == "DEBIT" else -line.opening_base_amount
                    for line in plan.lines
                ),
                Decimal(0),
            )
            == 0
        )
    raw["clearing_account_id"] = str(ACCOUNT)
    with pytest.raises(ValidationFailedError, match="declared"):
        execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")


def test_document_budgets_and_monetary_limits_split_without_truncation() -> None:
    raw = declaration()
    raw["clearing_account_id"] = "01990000-0000-7000-8000-000000000003"
    for index, entry in enumerate(raw["entries"]):
        entry["amount"] = "1000"
        entry["documents"] = [
            {
                "reference": f"old-{index}-{number}",
                "amount": "1",
                "document_date": "2026-03-01",
                "due_date": "2026-03-31",
            }
            for number in range(1000)
        ]
    plans = execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")
    assert len(plans) == 2 and sum(len(plan.bills) for plan in plans) == 2000
    raw = declaration()
    raw["clearing_account_id"] = "01990000-0000-7000-8000-000000000003"
    raw["entries"] = [
        entry | {"source_key": f"max-{index}-{side}", "amount": "999999999999999.9999"}
        for index in range(2)
        for side, entry in enumerate(raw["entries"])
    ]
    with pytest.raises(ValidationFailedError, match="monetary range"):
        execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")


@pytest.mark.parametrize("invalid", [None, "partial", "inconsistent", "post_only"])
def test_versioned_files_retain_explicit_ytd_and_reject_ambiguous_summaries(
    invalid: str | None,
) -> None:
    from billing_platform.bulk_files import csv_document

    raw = declaration() | {
        "posting_date": "2026-04-02",
        "covered_through": "2026-04-01",
        "originating_year_start": "2026-04-01",
        "coverage_mode": "YTD_SUMMARY",
    }
    headers = [
        *REQUIRED,
        "originating_year_start",
        "coverage_mode",
        "ytd_side",
        "ytd_amount",
        "ytd_base_amount",
    ]
    common = {key: value for key, value in raw.items() if key not in {"entries", "currency"}}
    rows = [common | entry | {"base_currency": "INR"} for entry in raw["entries"]]
    rows[1].update(ytd_side="CREDIT", ytd_amount="100.25", ytd_base_amount="100.25")
    if invalid == "partial":
        rows[1]["ytd_base_amount"] = ""
    if invalid == "inconsistent":
        rows.append(rows[1] | {"ytd_amount": "90"})
    if invalid == "post_only":
        for row in rows:
            row["coverage_mode"] = "POST_CUTOVER_ONLY"
    content = csv_document(
        headers,
        [[row.get(key, "") for key in headers] for row in rows],
        template=True,
        marker=MARKER,
    )
    body = FinancialOpeningImportStage(
        source_key="ytd", format="CSV", content_base64=base64.b64encode(content).decode()
    )
    if invalid:
        with pytest.raises(ValidationFailedError):
            decode(body)
    else:
        parsed = decode(body)
        assert parsed.ytd_summary is not None and len(parsed.ytd_summary) == 1
        assert parsed.ytd_summary[0].base_amount == Decimal("100.25")


def test_clearing_turnover_cannot_exceed_native_financial_bounds() -> None:
    raw = declaration()
    raw["clearing_account_id"] = "01990000-0000-7000-8000-000000000003"
    raw["entries"] = [
        entry | {"source_key": f"block-{side}-{index}", "amount": "4000000000000"}
        for side, entry in enumerate(declaration()["entries"])
        for index in range(199)
    ]
    with pytest.raises(ValidationFailedError, match="including clearing"):
        execution_chunks(OpeningDeclaration.model_validate(raw), "INR", 2, "half_up")


async def test_capture_metadata_links_resolve_to_native_financial_fields() -> None:
    from billing_platform.company_context import verify_company_context
    from starlette.requests import Request

    from accounting.api.auth import Access, decode_actor_context
    from accounting.api.financial_opening import field_set
    from accounting.api.fiscal import fields
    from tests.conftest import COMPANY, SECRET
    from tests.test_ledger_api import ledger_headers

    headers = ledger_headers()
    actor = decode_actor_context(
        headers["X-Actor-Context"], headers["X-Actor-Signature"], SECRET.encode()
    )
    context = verify_company_context(
        headers["X-Company-Context"], headers["X-Company-Signature"], SECRET.encode()
    )
    current = Access(actor, context)
    request = Request({"type": "http", "query_string": b""})
    metadata = await field_set(COMPANY, request, current)
    for path in metadata["native_field_sets"]:
        assert "/finance/field-sets/" in path
        result = await fields(COMPANY, path.rsplit("/", 1)[1], request, current)
        assert result.resource == path.rsplit("/", 1)[1]
        if result.resource != "open-items":
            assert result.fields
