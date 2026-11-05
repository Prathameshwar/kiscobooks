"""Bounded metadata for dynamic forms; field layout never grants authorization."""

import uuid
from typing import Literal

from billing_platform.custom_fields import CustomDefinition
from pydantic import BaseModel, ConfigDict, Field


class ConfigurationChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str


class ConfigurationControl(BaseModel):
    """Closed native editor hints; authority still comes from FieldMetadata."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["select", "boolean", "text", "date", "integer", "decimal", "reference"]
    label: str
    choices: list[ConfigurationChoice] = Field(default_factory=list, max_length=64)
    nullable: bool = False
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    reference_source: str | None = None
    reference_kind: Literal["GOODS", "SERVICE"] | None = None
    depends_on: str | None = None
    show_when: str | None = None
    disabled_reason: str | None = Field(default=None, max_length=300)


class FieldMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    source: Literal["native", "custom"]
    label: str
    required: bool
    visible: bool
    order: int
    writable: bool
    conditional_access: bool
    help_text: str | None = None
    placeholder: str | None = None
    display_group: str | None = None
    suggested_value: str | None = None
    custom: CustomDefinition | None = None
    control: ConfigurationControl | None = None


class FieldSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    entity_type: str
    source_version: int
    adoption_version: int = 0
    configuration_complete: bool | None = None
    fields: list[FieldMetadata] = Field(max_length=512)
