"""Bounded migration staging and review receipts, independent of physical posting."""

import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import Field, model_validator

from accounting.schemas.financial_opening import OpeningDeclaration
from accounting.schemas.masters import ExpectedVersion, Input


class FinancialOpeningImportStage(Input):
    source_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    format: Literal["JSON", "CSV", "TSV", "XLSX"] = "JSON"
    document: OpeningDeclaration | None = None
    content_base64: str | None = Field(default=None, max_length=2796204)

    @model_validator(mode="after")
    def shape(self) -> "FinancialOpeningImportStage":
        if self.format == "JSON":
            if self.document is None or self.content_base64 is not None:
                raise ValueError("JSON opening imports require one typed document")
        elif self.document is not None or not self.content_base64:
            raise ValueError("spreadsheet opening imports require only encoded file bytes")
        return self


class FinancialOpeningImportCommit(ExpectedVersion):
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class FinancialOpeningImportDetail(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    source_key: str
    state: str
    input_hash: str
    review_hash: str | None
    batch_id: uuid.UUID | None
    issues: list[dict[str, Any]]
    journal_ids: list[uuid.UUID]
    drafts_complete: bool
    effect_kind: Literal["DECLARATION_AND_DRAFTS_ONLY"] = "DECLARATION_AND_DRAFTS_ONLY"
    posting_required: bool
    opening_status: str | None


class FinancialOpeningImportItem(Input):
    id: uuid.UUID
    source_key: str
    state: str
    row_version: int
    batch_id: uuid.UUID | None


class FinancialOpeningImportQuery(ListQuery):
    state: Literal["STAGED", "READY", "COMMITTED", "BLOCKED", "CANCELLED"] | None = None
