"""Versioned future effect-owner contract; no financial profile is activated by it."""

import datetime as dt
import uuid
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EffectReference(Contract):
    owner: Literal["accounting"]
    effect_kind: Literal[
        "JOURNAL", "STOCK", "TAX", "OPEN_ITEM", "ALLOCATION", "NUMBER", "SOURCE_RECEIPT", "BANK_INSTRUMENT"
    ]
    effect_id: uuid.UUID


class DelegatedAuthority(Contract):
    actor_context: str = Field(min_length=1, max_length=65536, repr=False)
    actor_signature: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    company_context: str = Field(min_length=1, max_length=32768, repr=False)
    company_signature: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class ExecutionCommand(Contract):
    protocol_version: Literal[1, 2] = 1
    authority: DelegatedAuthority | None = Field(default=None, repr=False)
    configuration_evidence: dict[str, Any] | None = Field(default=None, max_length=20)
    reversal_of_execution_id: uuid.UUID | None = None
    correction_reason: str | None = Field(default=None, min_length=3, max_length=500)
    # Owner-issued metadata is signed without modifying the immutable revision hash.
    voucher_number: str | None = Field(default=None, min_length=1, max_length=100)

    @model_serializer(mode="wrap")
    def compatible_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        values: dict[str, Any] = handler(self)
        for key in ("authority", "configuration_evidence", "reversal_of_execution_id", "correction_reason", "voucher_number"):
            if getattr(self, key) is None:
                values.pop(key, None)
        return values

    tenant_id: uuid.UUID
    company_id: uuid.UUID
    voucher_id: uuid.UUID
    revision_id: uuid.UUID
    operation_id: uuid.UUID
    execution_id: uuid.UUID
    purpose: Literal["POST", "CANCEL", "REVERSE"]
    kind: str = Field(default="JOURNAL", pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    profile: str = Field(default="STANDARD", pattern=r"^[A-Z][A-Z0-9_]{0,39}$")
    company_configuration_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_payload: dict[str, object] = Field(default_factory=dict, max_length=32)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    posting_date: dt.date | None = None
    stock_date: dt.date | None = None
    statutory_date: dt.date | None = None
    period_versions: dict[uuid.UUID, int] = Field(default_factory=dict, max_length=12)
    actor_user_id: uuid.UUID
    approval_ids: tuple[uuid.UUID, ...] = Field(default=(), max_length=20)
    authority_expires_at: dt.datetime

    @model_validator(mode="after")
    def bounded_authority(self) -> Self:
        if self.purpose == "REVERSE" and self.reversal_of_execution_id is None:
            raise ValueError("reversal must identify the original execution")
        if self.purpose == "POST" and self.reversal_of_execution_id is not None:
            raise ValueError("posting cannot replace a reversal execution")
        if self.authority_expires_at.tzinfo is None or any(
            version < 1 for version in self.period_versions.values()
        ):
            raise ValueError("current aware authority and positive period versions required")
        return self


class ExecutionResult(Contract):
    protocol_version: Literal[1, 2] = 1
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    operation_id: uuid.UUID
    execution_id: uuid.UUID
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["PENDING", "COMMITTED", "REJECTED", "CANCELLED"]
    effects: tuple[EffectReference, ...] = Field(default=(), max_length=1000)
    committed_at: dt.datetime | None = None
    committed_generation: int | None = Field(default=None, strict=True, ge=1)
    rejection_code: (
        Literal[
            "STALE_AUTHORITY",
            "CLOSED_PERIOD",
            "CONFIGURATION_CHANGED",
            "SOURCE_CONFLICT",
            "UNSUPPORTED_PROFILE",
            "CONTENT_REJECTED",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.outcome != "COMMITTED" and (
            self.effects or self.committed_at or self.committed_generation
        ):
            raise ValueError("only committed results carry effects")
        if self.outcome == "COMMITTED" and (
            self.committed_generation is None
            or self.committed_at is None
            or self.committed_at.tzinfo is None
            or not any(effect.effect_kind == "SOURCE_RECEIPT" for effect in self.effects)
        ):
            raise ValueError("committed result requires aware commit time")
        if self.outcome != "REJECTED" and self.rejection_code is not None:
            raise ValueError("only rejected results carry a rejection code")
        if self.outcome == "REJECTED" and not self.rejection_code:
            raise ValueError("rejection code required")
        if len({(effect.effect_kind, effect.effect_id) for effect in self.effects}) != len(
            self.effects
        ):
            raise ValueError("duplicate effect references")
        return self
