"""Closed native Accounting editor and searchable reference contracts."""

import uuid
from typing import Any, Literal

from billing_platform.listing import ListQuery
from pydantic import BaseModel, ConfigDict, Field

from accounting.schemas.query import FieldDescription

ConfigurationResource = Literal[
    "accounts",
    "account-heads",
    "account-groups",
    "account-group-aliases",
    "account-aliases",
    "account-external-keys",
    "account-tax-profiles",
    "account-bank-profiles",
    "account-tax-defaults",
    "posting-mappings",
    "parties",
    "party-roles",
    "party-addresses",
    "party-address-uses",
    "party-contacts",
    "party-contact-uses",
    "party-identifiers",
    "party-tax-registrations",
    "party-registration-addresses",
    "party-bank-accounts",
    "party-commercial-types",
    "party-commercial-type-memberships",
    "party-accounting-policies",
    "party-credit-policies",
    "party-withholding-profiles",
    "withholding-sections",
    "withholding-rates",
    "withholding-certificates",
    "payment-terms",
    "payment-term-lines",
    "accounting-setup",
    "template-installations",
    "template-bindings",
    "charge-policies",
]
OptionSource = Literal[
    "accounts",
    "account-heads",
    "account-groups",
    "parties",
    "party-addresses",
    "party-contacts",
    "party-identifiers",
    "party-tax-registrations",
    "party-commercial-types",
    "payment-terms",
    "withholding-sections",
    "withholding-rates",
    "countries",
    "states",
    "currencies",
]


ControlKind = Literal[
    "text", "boolean", "select", "integer", "decimal", "date", "datetime", "reference"
]


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ControlKind
    nullable: bool = False
    choices: list[str] = Field(default_factory=list, max_length=64)
    reference: str | None = None
    write_only: bool = False
    decimal_bounds: dict[str, str] | None = Field(default=None, max_length=4)
    disabled_reason: str | None = Field(default=None, max_length=300)
    depends_on: dict[str, list[str]] = Field(default_factory=dict, max_length=4)
    required_when_active: bool = False
    reference_filters: dict[str, str] = Field(default_factory=dict, max_length=4)
    reference_values: list[str] | None = Field(default=None, max_length=200)
    choice_dependencies: dict[str, dict[str, list[str]]] = Field(
        default_factory=dict, max_length=64
    )


class ConfigurationField(FieldDescription):
    control: Control
    editable: bool
    conditional_access: bool = False
    initial: Any = None


class ConfigurationForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: uuid.UUID
    resource: ConfigurationResource
    operation: Literal["create", "update", "read"]
    lifecycle: str
    can_create: bool
    can_manage: bool
    fields: list[ConfigurationField] = Field(max_length=64)
    filter_keys: list[str] = Field(default_factory=list, max_length=32)
    searchable: bool = False
    unavailable_reason: str | None = Field(default=None, max_length=300)
    notices: list[str] = Field(default_factory=list, max_length=8)


class FormQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create", "update", "read"] = "read"
    object_id: uuid.UUID | None = None


class OptionQuery(ListQuery):
    value: str | None = Field(None, min_length=1, max_length=36)
    party_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    kind: str | None = Field(None, min_length=1, max_length=40)
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] | None = None
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = None
    currency_mode: Literal["BASE", "FIXED", "MULTI"] | None = None
    company_currency: bool = False
    base_only: bool = False
    scheme: str | None = Field(default=None, min_length=1, max_length=40)


class ReferenceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str
    code: str | None = None
