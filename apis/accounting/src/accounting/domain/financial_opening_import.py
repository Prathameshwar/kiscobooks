"""Exact native opening worksheets from bounded text-cell files; no master guessing."""

import base64
import binascii
from typing import Any

from billing_platform.bulk_files import read_csv, read_xlsx
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from accounting.schemas.financial_opening import OpeningDeclaration
from accounting.schemas.financial_opening_import import FinancialOpeningImportStage

MARKER = "_financial_opening_schema_version"
REQUIRED = (
    "posting_date",
    "base_currency",
    "source_system",
    "source_id",
    "covered_through",
    "reason",
    "source_key",
    "account_id",
    "side",
    "currency",
    "amount",
    "exchange_rate",
)
OPTIONAL = (
    "base_amount",
    "description",
    "coverage_mode",
    "originating_year_start",
    "same_day_reviewed",
    "credit_cash_reviewed",
    "credit_cash_reason",
    "clearing_account_id",
    "replacement_of_id",
    "ytd_side",
    "ytd_amount",
    "ytd_base_amount",
    "document_source_key",
    "document_kind",
    "document_reference",
    "document_amount",
    "document_original_amount",
    "document_base_amount",
    "document_date",
    "due_date",
)


def decode(body: FinancialOpeningImportStage) -> OpeningDeclaration:
    if body.document is not None:
        from accounting.domain.financial_opening import declaration_hash

        declaration_hash(body.document)
        return body.document
    try:
        raw = base64.b64decode(body.content_base64 or "", validate=True)
        if not raw or len(raw) > 2097152:
            raise ValueError("opening file requires one byte to two MiB")
        rows = (
            read_xlsx(raw, marker=MARKER)
            if body.format == "XLSX"
            else read_csv(raw, marker=MARKER, delimiter="\t" if body.format == "TSV" else ",")
        )
        if not rows or len(rows) > 10000:
            raise ValueError("opening file requires one to ten thousand rows")
        header: dict[str, Any] | None = None
        entries: dict[str, dict[str, Any]] = {}
        summaries: dict[str, dict[str, Any]] = {}
        header_keys = (
            "posting_date",
            "source_system",
            "source_id",
            "covered_through",
            "reason",
            "coverage_mode",
            "originating_year_start",
            "clearing_account_id",
            "replacement_of_id",
            "credit_cash_reason",
        )
        for row in rows:
            data = {key: cell.value.strip() for key, cell in row.cells.items()}
            if set(data) - set(REQUIRED + OPTIONAL) or any(not data.get(key) for key in REQUIRED):
                raise ValueError(f"row {row.number}: missing or unsupported opening columns")
            if any(cell.value and cell.kind != "text" for cell in row.cells.values()):
                raise ValueError(f"row {row.number}: use text cells for exact native values")
            candidate: dict[str, Any] = {key: data[key] for key in header_keys if data.get(key)}
            candidate["currency"] = data["base_currency"]
            if data.get("same_day_reviewed") not in {None, "", "true", "false"}:
                raise ValueError(f"row {row.number}: use true/false for same-day review")
            candidate["same_day_reviewed"] = data.get("same_day_reviewed") == "true"
            if data.get("credit_cash_reviewed") not in {None, "", "true", "false"}:
                raise ValueError(f"row {row.number}: use true/false for credit-cash review")
            candidate["credit_cash_reviewed"] = data.get("credit_cash_reviewed") == "true"
            if header is None:
                header = candidate
            elif header != candidate:
                raise ValueError(
                    f"row {row.number}: all entries must share one company cutover and source"
                )
            incoming = {
                key: data[key]
                for key in (
                    "source_key",
                    "account_id",
                    "side",
                    "currency",
                    "amount",
                    "exchange_rate",
                    "base_amount",
                    "description",
                )
                if data.get(key)
            }
            key = data["source_key"].casefold()
            if key in entries:
                if {k: v for k, v in entries[key].items() if k != "documents"} != incoming:
                    raise ValueError(
                        f"row {row.number}: entry source key has inconsistent account or amounts"
                    )
            else:
                entries[key] = incoming | {"documents": []}
            ytd = {name: data.get("ytd_" + name) for name in ("side", "amount", "base_amount")}
            if any(ytd.values()):
                if not all(ytd.values()):
                    raise ValueError(f"row {row.number}: complete all three YTD amount columns")
                ytd = ytd | {"account_id": data["account_id"], "currency": data["currency"]}
                if key in summaries and summaries[key] != ytd:
                    raise ValueError(f"row {row.number}: YTD summary differs between bill rows")
                summaries[key] = ytd
            document_keys = {
                "source_key": "document_source_key",
                "document_kind": "document_kind",
                "reference": "document_reference",
                "amount": "document_amount",
                "original_amount": "document_original_amount",
                "base_amount": "document_base_amount",
                "document_date": "document_date",
                "due_date": "due_date",
            }
            document = {key: data[value] for key, value in document_keys.items() if data.get(value)}
            if document:
                entries[key]["documents"].append(document)
        if header and header.get("coverage_mode") == "YTD_SUMMARY":
            header["ytd_summary"] = list(summaries.values())
        elif summaries:
            raise ValueError("YTD amounts require YTD_SUMMARY source coverage")
        return OpeningDeclaration.model_validate(
            (header or {}) | {"entries": list(entries.values())}
        )
    except (ValueError, binascii.Error, ValidationError) as exc:
        raise ValidationFailedError(
            "opening import requires valid versioned native allocation data",
            fields={
                "document": (
                    "Check exact decimal text, account IDs, dates, unique references "
                    "and column consistency."
                )
            },
        ) from exc
