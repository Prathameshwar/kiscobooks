"""Proposed v1 source contracts; parsers do not establish producer availability.

No source DTO accepts stock quantities, party financial data or actual costs.
Real producer adoption/authentication and complete snapshot barriers are required
before consumers may mark any dependent capability ready.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationInfo,
    field_validator,
    model_validator,
)

type SourceVersion = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
type SourceId = Annotated[uuid.UUID, Field()]


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: SourceId
    company_id: SourceId
    id: SourceId
    source_version: SourceVersion
    deleted: StrictBool

    @field_validator("tenant_id", "company_id", "id")
    @classmethod
    def real_id(cls, value: uuid.UUID) -> uuid.UUID:
        if value.int == 0:
            raise ValueError("source identifiers must be non-nil")
        return value


class PartyReference(SourceRecord):
    source: Literal["billing.party"] = "billing.party"
    display_name: str = Field(min_length=1, max_length=200)
    is_active: StrictBool
    is_customer: StrictBool
    is_supplier: StrictBool


class CustomerTypeReference(SourceRecord):
    source: Literal["billing.customer_type"] = "billing.customer_type"
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    is_active: StrictBool


class CustomerPricingReference(SourceRecord):
    source: Literal["billing.customer_pricing"] = "billing.customer_pricing"
    party_id: SourceId
    customer_type_id: SourceId | None
    is_active: StrictBool

    @field_validator("party_id", "customer_type_id")
    @classmethod
    def real_reference(cls, value: uuid.UUID | None) -> uuid.UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("reference must be null or a real identity")
        return value


class SourceBarrier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producer: Literal["identity", "billing"]
    stream: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.]*$")
    contract_version: Literal[1]
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    snapshot_id: uuid.UUID
    watermark: SourceVersion
    generated_at: dt.datetime
    complete: Literal[True]
    record_count: int = Field(strict=True, ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("contract_version", "complete", mode="before")
    @classmethod
    def strict_constants(cls, value: object, info: ValidationInfo) -> object:
        expected = bool if info.field_name == "complete" else int
        if type(value) is not expected:
            raise ValueError("source constants require their exact JSON types")
        return value

    @field_validator("tenant_id", "company_id", "snapshot_id")
    @classmethod
    def real_id(cls, value: uuid.UUID) -> uuid.UUID:
        return SourceRecord.real_id(value)

    @field_validator("generated_at")
    @classmethod
    def aware_time(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("source generation time must include an offset")
        return value.astimezone(dt.UTC)

    @model_validator(mode="after")
    def source_owner(self) -> Self:
        if not self.stream.startswith(self.producer + "."):
            raise ValueError("stream must belong to its producer")
        return self
