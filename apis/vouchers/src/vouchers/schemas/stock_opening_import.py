"""Opening imports produce reviewable drafts, never bypassing financial approvals."""

import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from vouchers.schemas.configuration import Contract
from vouchers.schemas.documents import VoucherInput


class OpeningImportDocument(Contract):
    vouchers: tuple[VoucherInput, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def opening_only(self) -> Self:
        keys: list[str] = []
        units: list[uuid.UUID] = []
        controls: set[uuid.UUID] = set()
        dates = set()
        prior: dict[tuple[uuid.UUID, uuid.UUID], tuple[dt.date, int, str]] = {}
        for voucher in self.vouchers:
            stock = voucher.stock
            if (
                stock is None
                or stock.action != "OPENING"
                or stock.opening_control_id is None
                or voucher.financial is not None
                or voucher.invoice is not None
                or voucher.mode != "ITEMS"
                or voucher.posting_date != stock.stock_date
                or voucher.stock_date != stock.stock_date
            ):
                raise ValueError("imports require native opening drafts with a reviewed cutover ID")
            controls.add(stock.opening_control_id)
            dates.add((stock.stock_date, stock.currency, stock.opening_mode))
            chunk_order: dict[tuple[uuid.UUID, uuid.UUID], list[tuple[dt.date, int, str]]] = {}
            for line in stock.lines:
                if line.opening is None:
                    raise ValueError("every imported cohort needs its stable opening evidence")
                keys.append(line.opening.source_key)
                units.extend(line.unit_ids)
                chunk_order.setdefault((line.item_id, line.warehouse_id), []).append(
                    (
                        line.opening.received_on or stock.stock_date,
                        line.opening.cohort_order,
                        line.opening.source_key,
                    )
                )
            for pool, order in chunk_order.items():
                if pool in prior and min(order) < prior[pool]:
                    raise ValueError(
                        "order opening chunks by receipt date, cohort order and source key "
                        "within each product/warehouse"
                    )
                prior[pool] = max(order)
        if len(controls) != 1 or len(dates) != 1:
            raise ValueError("one import belongs to one cutover, date, currency and GL mode")
        if len(keys) > 1000 or len(set(keys)) != len(keys):
            raise ValueError("import cohort keys must be distinct and bounded to one thousand")
        if len(units) > 10_000 or len(set(units)) != len(units):
            raise ValueError("import physical units must be distinct and bounded to ten thousand")
        return self


class OpeningImportStage(Contract):
    source_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    format: Literal["JSON", "CSV", "TSV", "XLSX"] = "JSON"
    document: OpeningImportDocument | None = None
    content_base64: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("source_key")
    @classmethod
    def canonical_key(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def single_source(self) -> Self:
        if (self.format == "JSON") != (self.document is not None) or (self.format != "JSON") != (
            self.content_base64 is not None
        ):
            raise ValueError("JSON supplies document; spreadsheets supply content_base64")
        return self


class OpeningImportVersion(Contract):
    expected_version: int = Field(strict=True, ge=1)


class OpeningImportCommit(OpeningImportVersion):
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class OpeningImportDetail(Contract):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    source_key: str
    state: str
    input_hash: str
    review_hash: str | None
    chunk_count: int
    validated_chunks: int
    created_chunks: int
    effects: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    posting_required: bool = True
    effect_kind: Literal["DRAFT_ONLY"] = "DRAFT_ONLY"
