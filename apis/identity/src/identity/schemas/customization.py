from __future__ import annotations

import uuid
from typing import Any, Literal

from billing_platform.custom_fields import CustomDefinition
from pydantic import Field, field_validator

from identity.domain.accounting_fields import contracts
from identity.domain.document_fields import contracts as catalog_contracts
from identity.schemas.base import StrictModel


class DefinitionWrite(StrictModel):
    entity_type: Literal[
        "identity.company",
        "catalog.product_family",
        "catalog.item",
        "vouchers.voucher",
        "vouchers.voucher_item",
    ] = "identity.company"
    company_id: uuid.UUID | None = None
    label: str = Field(min_length=1, max_length=150)
    help_text: str | None = Field(default=None, max_length=500)
    placeholder: str | None = Field(default=None, max_length=150)
    display_order: int = Field(default=0, ge=-32768, le=32767, strict=True)
    display_group: str | None = Field(default=None, max_length=100)
    requires_feature: str | None = None
    expected_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    definition: CustomDefinition


class DefinitionItem(DefinitionWrite):
    id: uuid.UUID
    digest: str
    requires_adoption: bool = False


class LayoutWrite(StrictModel):
    is_visible: bool | None = Field(default=None, strict=True)
    is_required: bool | None = Field(default=None, strict=True)
    label_override: str | None = Field(default=None, min_length=1, max_length=150)
    display_order: int | None = Field(default=None, ge=-32768, le=32767, strict=True)
    display_group: str | None = Field(default=None, max_length=100)
    help_text_override: str | None = Field(default=None, max_length=500)


class LayoutItem(LayoutWrite):
    id: uuid.UUID
    entity_type: str
    field_key: str
    field_source: str


class PolicyWrite(StrictModel):
    entity_type: str = Field(
        default="identity.company",
        json_schema_extra={"enum": ["identity.company", *contracts(), *catalog_contracts()]},
    )
    subject_type: Literal["user", "user_group", "role"]
    subject_id: uuid.UUID
    field_key: str = Field(min_length=1, max_length=120)
    access: Literal["read", "write"]
    effect: Literal["deny", "allow"]
    scope_type: Literal["tenant", "company"] = "tenant"
    scope_id: uuid.UUID | None = None
    condition: dict[str, Any] | None = None
    reason: str = Field(min_length=1, max_length=500)
    is_active: bool = Field(default=True, strict=True)

    @field_validator("entity_type")
    @classmethod
    def registered_entity(cls, value: str) -> str:
        if (
            value != "identity.company"
            and value not in contracts()
            and value not in catalog_contracts()
        ):
            raise ValueError("entity field policy is not supported")
        return value


class PolicyItem(PolicyWrite):
    id: uuid.UUID


class CustomValues(StrictModel):
    values: dict[str, Any] = Field(max_length=128)


class DefinitionListItem(StrictModel):
    id: uuid.UUID
    key: str
    label: str
    entity_type: str
    data_type: str
    is_active: bool
    is_searchable: bool
