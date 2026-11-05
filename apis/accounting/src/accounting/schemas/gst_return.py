from decimal import Decimal

from pydantic import Field, field_validator
from reporting_contract.gst import GstReturnRecord

from accounting.schemas.masters import Detail, Input


class GstCapture(Input):
    records: list[GstReturnRecord] = Field(min_length=1, max_length=200)


class GstRecordDetail(GstReturnRecord, Detail):
    @field_validator("conversion_rate", mode="before")
    @classmethod
    def native_conversion(cls, value: object) -> object:
        return format(value, ".8f") if isinstance(value, Decimal) else value

    @field_validator("taxable", "igst", "cgst", "sgst", "cess", mode="before")
    @classmethod
    def native_money(cls, value: object) -> object:
        return format(value, ".4f") if isinstance(value, Decimal) else value
