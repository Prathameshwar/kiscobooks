"""Catalog's independent, minimal Identity v1 wire contract.

No Identity ORM import and no owner-specific rules in the shared transport.
Unknown fields/types fail closed rather than being silently dropped.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any, Literal, Self

from billing_platform.constants import SCOPE_ALL
from billing_platform.snapshots import SnapshotManifest, SnapshotRecord
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

CONTRACT: Literal["identity.catalog_context.v2"] = "identity.catalog_context.v2"
type RealId = Annotated[uuid.UUID, Field()]
type SmallOrder = Annotated[int, Field(strict=True, ge=-32768, le=32767)]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def aware_dates(cls, value: Any) -> Any:
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                raise ValueError("source timestamps must include timezone")
            return value.astimezone(dt.UTC)
        return value


class CompanyFact(Fact):
    code: str = Field(min_length=1, max_length=20)
    display_name: str = Field(min_length=1, max_length=120)
    status: Literal["active", "suspended", "closed"]
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    state_code: str = Field(min_length=1, max_length=6)
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    reporting_currency: str | None = Field(pattern=r"^[A-Z]{3}$")
    fiscal_year_start_month: int = Field(strict=True, ge=1, le=12)
    fiscal_year_start_day: int = Field(strict=True, ge=1, le=31)
    amount_precision: int = Field(strict=True, ge=0, le=4)
    quantity_precision: int = Field(strict=True, ge=0, le=4)
    rounding_mode: Literal["half_up", "half_even", "down"]
    default_tax_system: str = Field(min_length=1, max_length=20)
    timezone: str = Field(min_length=1, max_length=64)
    first_posted_at: dt.datetime | None

    @model_validator(mode="after")
    def valid_calendar(self) -> Self:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        dt.date(2000, self.fiscal_year_start_month, self.fiscal_year_start_day)
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unsupported source timezone") from exc
        return self


class CompanyScopeFact(Fact):
    company_id: uuid.UUID


class FeatureFact(CompanyScopeFact):
    feature_key: str = Field(min_length=1, max_length=60)
    is_enabled: StrictBool
    locked_at: dt.datetime | None

    @model_validator(mode="after")
    def locked_enabled(self) -> Self:
        if self.locked_at is not None and not self.is_enabled:
            raise ValueError("locked capability cannot be disabled")
        return self


class CurrencyAllowanceFact(CompanyScopeFact):
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    is_active: StrictBool


class DefinitionFact(CompanyScopeFact):
    entity_type: str = Field(pattern=r"^catalog\.[a-z][a-z0-9_]{0,70}$", max_length=80)
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=150)
    help_text: str | None = Field(max_length=500)
    placeholder: str | None = Field(max_length=150)
    data_type: Literal[
        "text",
        "long_text",
        "integer",
        "decimal",
        "date",
        "datetime",
        "boolean",
        "currency_amount",
        "select",
        "multi_select",
        "dynamic_select",
        "auto_number",
    ]
    display_order: SmallOrder
    display_group: str | None = Field(max_length=100)
    is_active: StrictBool
    is_searchable: StrictBool
    requires_adoption: StrictBool = False
    is_immutable_after_create: StrictBool
    requires_feature: str | None = Field(max_length=60)
    validation: dict[str, Any] | None
    options: dict[str, Any] | None
    option_source_key: str | None = Field(max_length=80)
    depends_on_key: str | None = Field(max_length=60)
    visibility: dict[str, Any] | None
    sequence_config: dict[str, Any] | None
    default_value: str | None = Field(max_length=500)


class LayoutFact(CompanyScopeFact):
    entity_type: str = Field(pattern=r"^catalog\.[a-z][a-z0-9_]{0,70}$", max_length=80)
    field_source: Literal["native", "custom"]
    field_key: str = Field(min_length=1, max_length=120)
    definition_id: uuid.UUID | None
    is_visible: StrictBool | None
    is_required: StrictBool | None
    display_order: SmallOrder | None
    display_group: str | None = Field(max_length=100)
    label_override: str | None = Field(max_length=150)
    help_text_override: str | None = Field(max_length=500)
    default_value: str | None = Field(max_length=500)


class SubjectScopeFact(Fact):
    subject_id: uuid.UUID
    scope_type: Literal["tenant", "company", "department"]
    scope_id: uuid.UUID

    @model_validator(mode="after")
    def consistent_scope(self) -> Self:
        if self.subject_id == SCOPE_ALL or (self.scope_type == "tenant") != (
            self.scope_id == SCOPE_ALL
        ):
            raise ValueError("invalid subject or source scope")
        return self


class PolicyFact(SubjectScopeFact):
    subject_type: Literal["user", "user_group", "role"]
    entity_type: str = Field(pattern=r"^catalog\.[a-z][a-z0-9_]{0,70}$", max_length=80)
    field_key: str = Field(min_length=1, max_length=120)
    access: Literal["read", "write"]
    effect: Literal["allow", "deny"]
    condition: dict[str, Any] | None
    is_active: StrictBool


class AssignmentFact(SubjectScopeFact):
    subject_type: Literal["user", "user_group"]
    role_id: uuid.UUID
    is_active: StrictBool
    valid_from: dt.date
    valid_to: dt.date | None

    @model_validator(mode="after")
    def valid_assignment(self) -> Self:
        if self.role_id == SCOPE_ALL or (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("invalid role or assignment dates")
        return self


class MemberFact(Fact):
    user_group_id: uuid.UUID
    user_id: uuid.UUID

    @model_validator(mode="after")
    def real_members(self) -> Self:
        if self.user_group_id == SCOPE_ALL or self.user_id == SCOPE_ALL:
            raise ValueError("real membership identities required")
        return self


class UserFact(Fact):
    status: Literal["invited", "active", "suspended", "deactivated"]


class ActiveFact(Fact):
    is_active: StrictBool


FACTS: dict[str, type[Fact]] = {
    "company": CompanyFact,
    "feature": FeatureFact,
    "currency_allowance": CurrencyAllowanceFact,
    "custom_definition": DefinitionFact,
    "field_config": LayoutFact,
    "field_policy": PolicyFact,
    "role_assignment": AssignmentFact,
    "group_member": MemberFact,
    "user": UserFact,
    "group": ActiveFact,
    "role": ActiveFact,
}


def validate_facts(manifest: SnapshotManifest, records: tuple[SnapshotRecord, ...]) -> None:
    if manifest.contract != CONTRACT or set(manifest.stream_counts) != set(FACTS):
        raise ValueError("incomplete or unsupported Identity source contract")
    if manifest.stream_counts["company"] != 1:
        raise ValueError("source must contain its exact company")
    for record in records:
        if record.deleted or record.kind not in FACTS:
            raise ValueError("complete snapshot requires current supported facts")
        fact = FACTS[record.kind].model_validate(record.data)
        if record.kind == "company" and record.id != manifest.company_id:
            raise ValueError("source company differs from requested scope")
        if isinstance(fact, CompanyScopeFact):
            allowed = (
                {manifest.company_id}
                if isinstance(fact, FeatureFact)
                else {SCOPE_ALL, manifest.company_id}
            )
            if fact.company_id not in allowed:
                raise ValueError("source fact belongs to another company")
        if isinstance(fact, SubjectScopeFact) and (
            fact.scope_type == "department" or fact.scope_id not in {SCOPE_ALL, manifest.company_id}
        ):
            raise ValueError("source subject scope differs from requested company")


class IdentityChange(Fact):
    contract: Literal["identity.catalog_context.v2"]
    tenant_id: uuid.UUID
    source_version: int = Field(strict=True, ge=2, le=2**63 - 1)
    previous_version: int = Field(strict=True, ge=1, le=2**63 - 2)
    generated_at: dt.datetime
    records: tuple[SnapshotRecord, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def complete_change(self) -> Self:
        from billing_platform.idempotency import canonical_json

        if self.tenant_id == SCOPE_ALL or self.previous_version != self.source_version - 1:
            raise ValueError("invalid source change scope or sequence")
        seen = set()
        for record in self.records:
            identity = (record.kind, record.id)
            if record.kind not in FACTS or identity in seen:
                raise ValueError("unknown or duplicate source change record")
            seen.add(identity)
            if not record.deleted:
                FACTS[record.kind].model_validate(record.data)
        canonical_json(self.model_dump(mode="json"), maximum_bytes=512 * 1024)
        return self
