from decimal import Decimal
from typing import Any, Self

from pydantic import Field, field_validator, model_validator
from reporting_contract.gst_outward import GstOutwardRecord

from accounting.schemas.masters import Detail, Input


class GstOutwardCapture(Input):
    records: list[GstOutwardRecord] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        keys = [
            (row.registration_id, row.return_date, row.details.coverage_area)
            for row in self.records
            if row.kind == "COVERAGE"
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("one batch cannot contain conflicting coverage for the same area")
        return self


class GstOutwardDetail(GstOutwardRecord, Detail):
    @model_validator(mode="before")
    @classmethod
    def stored_header(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: format(item, ".4f") if isinstance(item, Decimal) else item
                for key, item in value.items()
            }
        return value

    @field_validator("invoice_value", "taxable", "igst", "cgst", "sgst", "cess", mode="before")
    @classmethod
    def native_money(cls, value: object) -> object:
        return format(value, ".4f") if isinstance(value, Decimal) else value
