"""Typed public accounting master inputs and sparse field-policy outputs."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, field_validator, model_validator

from accounting.domain.master_codes import CODE_DESCRIPTION, optional_code

DecimalInput = Annotated[Decimal, WithJsonSchema({"type": "string"}, mode="validation")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @field_validator("*", mode="before")
    @classmethod
    def no_float(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError("decimal values must be strings")
        return value


class ExpectedVersion(Input):
    expected_version: int = Field(ge=1)


class Detail(Input):
    id: uuid.UUID
    company_id: uuid.UUID
    row_version: int
    created_at: dt.datetime
    updated_at: dt.datetime


class AccountHeadCreate(Input):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    nature: Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"] = Field(...)


class AccountHeadUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    nature: Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"] | None = Field(None)


class AccountHeadDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    nature: Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"] | None = Field(None)


class AccountingSetupCreate(Input):
    base_currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    generation: int = Field(1, strict=True, ge=0, le=1000000)
    template_version: str | None = Field(None, min_length=1, max_length=30)


class AccountingSetupUpdate(ExpectedVersion):
    base_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    generation: int | None = Field(None, strict=True, ge=0, le=1000000)
    template_version: str | None = Field(None, min_length=1, max_length=30)


class AccountingSetupDetail(Detail):
    base_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    generation: int | None = Field(None, strict=True, ge=0, le=1000000)
    template_version: str | None = Field(None, min_length=1, max_length=30)
    metadata_version: int | None = Field(None, strict=True, ge=0)


class AccountGroupCreate(Input):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    head_id: uuid.UUID = Field(...)
    parent_id: uuid.UUID | None = Field(None)
    affects_gross_profit: bool | None = Field(None, strict=True)
    sub_ledger_behaviour: bool = Field(False, strict=True)
    nett_balances: bool = Field(False, strict=True)
    used_for_calculation: bool = Field(False, strict=True)
    allocation_method: Literal["NOT_APPLICABLE", "BY_QTY", "BY_VALUE"] = Field("NOT_APPLICABLE")
    sort_order: int = Field(0, strict=True, ge=0, le=1000000)


class AccountGroupUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    head_id: uuid.UUID | None = Field(None)
    parent_id: uuid.UUID | None = Field(None)
    affects_gross_profit: bool | None = Field(None, strict=True)
    sub_ledger_behaviour: bool | None = Field(None, strict=True)
    nett_balances: bool | None = Field(None, strict=True)
    used_for_calculation: bool | None = Field(None, strict=True)
    allocation_method: Literal["NOT_APPLICABLE", "BY_QTY", "BY_VALUE"] | None = Field(None)
    sort_order: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountGroupDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    head_id: uuid.UUID | None = Field(None)
    parent_id: uuid.UUID | None = Field(None)
    system_key: str | None = Field(None, min_length=1, max_length=60)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    affects_gross_profit: bool | None = Field(None, strict=True)
    sub_ledger_behaviour: bool | None = Field(None, strict=True)
    nett_balances: bool | None = Field(None, strict=True)
    used_for_calculation: bool | None = Field(None, strict=True)
    allocation_method: Literal["NOT_APPLICABLE", "BY_QTY", "BY_VALUE"] | None = Field(None)
    sort_order: int | None = Field(None, strict=True, ge=0, le=1000000)
    is_primary: bool | None = Field(None, strict=True)
    is_reserved: bool | None = Field(None, strict=True)
    is_revenue: bool | None = Field(None, strict=True)
    is_deemed_positive: bool | None = Field(None, strict=True)


class AccountGroupClosureCreate(Input):
    ancestor_id: uuid.UUID = Field(...)
    descendant_id: uuid.UUID = Field(...)
    depth: int = Field(0, strict=True, ge=0, le=1000000)


class AccountGroupClosureUpdate(ExpectedVersion):
    ancestor_id: uuid.UUID | None = Field(None)
    descendant_id: uuid.UUID | None = Field(None)
    depth: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountGroupClosureDetail(Detail):
    ancestor_id: uuid.UUID | None = Field(None)
    descendant_id: uuid.UUID | None = Field(None)
    depth: int | None = Field(None, strict=True, ge=0, le=1000000)


class PartyCreate(Input):
    code: str | None = Field(None, min_length=1, max_length=40, description=CODE_DESCRIPTION)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> str | None:
        return optional_code(value)

    name: str = Field(..., min_length=1, max_length=160)
    legal_name: str = Field(..., min_length=1, max_length=200)
    party_type: Literal["ORGANISATION", "PERSON"] = Field("ORGANISATION")
    country_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    notes: str | None = Field(None, min_length=1, max_length=1000)


class PartyUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    legal_name: str | None = Field(None, min_length=1, max_length=200)
    party_type: Literal["ORGANISATION", "PERSON"] | None = Field(None)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    notes: str | None = Field(None, min_length=1, max_length=1000)


class PartyDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    legal_name: str | None = Field(None, min_length=1, max_length=200)
    party_type: Literal["ORGANISATION", "PERSON"] | None = Field(None)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    notes: str | None = Field(None, min_length=1, max_length=1000)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyRoleCreate(Input):
    party_id: uuid.UUID = Field(...)
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] = Field(...)


class PartyRoleUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] | None = Field(None)


class PartyRoleDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PaymentTermCreate(Input):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(None, min_length=1, max_length=500)


class PaymentTermUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, min_length=1, max_length=500)


class PaymentTermDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, min_length=1, max_length=500)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PaymentTermLineCreate(Input):
    payment_term_id: uuid.UUID = Field(...)
    sequence: int = Field(..., strict=True, ge=0, le=1000000)
    percentage: DecimalInput = Field(..., gt=0, le=100, max_digits=7, decimal_places=4)
    basis: Literal["INVOICE_DATE", "MONTH_END"] = Field("INVOICE_DATE")
    days: int = Field(0, strict=True, ge=0, le=1000000)


class PaymentTermLineUpdate(ExpectedVersion):
    payment_term_id: uuid.UUID | None = Field(None)
    sequence: int | None = Field(None, strict=True, ge=0, le=1000000)
    percentage: DecimalInput | None = Field(None, gt=0, le=100, max_digits=7, decimal_places=4)
    basis: Literal["INVOICE_DATE", "MONTH_END"] | None = Field(None)
    days: int | None = Field(None, strict=True, ge=0, le=1000000)


class PaymentTermLineDetail(Detail):
    payment_term_id: uuid.UUID | None = Field(None)
    sequence: int | None = Field(None, strict=True, ge=0, le=1000000)
    percentage: DecimalInput | None = Field(None, gt=0, le=100, max_digits=7, decimal_places=4)
    basis: Literal["INVOICE_DATE", "MONTH_END"] | None = Field(None)
    days: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountCreate(Input):
    code: str | None = Field(None, min_length=1, max_length=40, description=CODE_DESCRIPTION)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: Any) -> str | None:
        return optional_code(value)

    name: str = Field(..., min_length=1, max_length=160)
    group_id: uuid.UUID = Field(...)
    kind: Literal[
        "GENERAL", "CASH", "BANK", "PARTY", "TAX", "INVENTORY_CONTROL", "ASSET_CONTROL"
    ] = Field("GENERAL")
    party_id: uuid.UUID | None = Field(None)
    party_role: Literal["CUSTOMER", "SUPPLIER", "OTHER"] | None = Field(None)
    currency_mode: Literal["BASE", "FIXED", "MULTI"] = Field("BASE")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    posting_policy: Literal["MANUAL_ALLOWED", "SOURCE_ONLY"] = Field("MANUAL_ALLOWED")
    description: str | None = Field(None, min_length=1, max_length=500)
    inventory_affected: bool = Field(False, strict=True)
    rounding_method: Literal["NONE", "NORMAL", "UP", "DOWN"] = Field("NONE")
    rounding_limit: DecimalInput | None = Field(None, gt=0, max_digits=19, decimal_places=4)
    sort_order: int = Field(0, strict=True, ge=0, le=1000000)


class AccountUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    group_id: uuid.UUID | None = Field(None)
    kind: (
        Literal["GENERAL", "CASH", "BANK", "PARTY", "TAX", "INVENTORY_CONTROL", "ASSET_CONTROL"]
        | None
    ) = Field(None)
    party_id: uuid.UUID | None = Field(None)
    party_role: Literal["CUSTOMER", "SUPPLIER", "OTHER"] | None = Field(None)
    currency_mode: Literal["BASE", "FIXED", "MULTI"] | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    posting_policy: Literal["MANUAL_ALLOWED", "SOURCE_ONLY"] | None = Field(None)
    description: str | None = Field(None, min_length=1, max_length=500)
    inventory_affected: bool | None = Field(None, strict=True)
    rounding_method: Literal["NONE", "NORMAL", "UP", "DOWN"] | None = Field(None)
    rounding_limit: DecimalInput | None = Field(None, gt=0, max_digits=19, decimal_places=4)
    sort_order: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    group_id: uuid.UUID | None = Field(None)
    kind: (
        Literal["GENERAL", "CASH", "BANK", "PARTY", "TAX", "INVENTORY_CONTROL", "ASSET_CONTROL"]
        | None
    ) = Field(None)
    party_id: uuid.UUID | None = Field(None)
    party_role: Literal["CUSTOMER", "SUPPLIER", "OTHER"] | None = Field(None)
    currency_mode: Literal["BASE", "FIXED", "MULTI"] | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    posting_policy: Literal["MANUAL_ALLOWED", "SOURCE_ONLY"] | None = Field(None)
    description: str | None = Field(None, min_length=1, max_length=500)
    system_key: str | None = Field(None, min_length=1, max_length=60)
    used_at: dt.datetime | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    inventory_affected: bool | None = Field(None, strict=True)
    rounding_method: Literal["NONE", "NORMAL", "UP", "DOWN"] | None = Field(None)
    rounding_limit: DecimalInput | None = Field(None, gt=0, max_digits=19, decimal_places=4)
    sort_order: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountAliasCreate(Input):
    account_id: uuid.UUID = Field(...)
    alias: str = Field(..., min_length=1, max_length=160)


class AccountGroupAliasCreate(Input):
    group_id: uuid.UUID = Field(...)
    alias: str = Field(..., min_length=1, max_length=160)


class AccountAliasUpdate(ExpectedVersion):
    account_id: uuid.UUID | None = Field(None)
    alias: str | None = Field(None, min_length=1, max_length=160)


class AccountGroupAliasUpdate(ExpectedVersion):
    group_id: uuid.UUID | None = Field(None)
    alias: str | None = Field(None, min_length=1, max_length=160)


class AccountAliasDetail(Detail):
    account_id: uuid.UUID | None = Field(None)
    alias: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class AccountGroupAliasDetail(Detail):
    group_id: uuid.UUID | None = Field(None)
    alias: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class AccountExternalKeyCreate(Input):
    account_id: uuid.UUID = Field(...)
    source_namespace: str = Field(..., min_length=1, max_length=80)
    external_key: str = Field(..., min_length=1, max_length=160)


class AccountExternalKeyUpdate(ExpectedVersion):
    account_id: uuid.UUID | None = Field(None)
    source_namespace: str | None = Field(None, min_length=1, max_length=80)
    external_key: str | None = Field(None, min_length=1, max_length=160)


class AccountExternalKeyDetail(Detail):
    account_id: uuid.UUID | None = Field(None)
    source_namespace: str | None = Field(None, min_length=1, max_length=80)
    external_key: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyAddressInput(Input):
    label: str = Field(..., min_length=1, max_length=100)
    mailing_name: str = Field(..., min_length=1, max_length=200)
    line1: str = Field(..., min_length=1, max_length=200)
    line2: str | None = Field(None, min_length=1, max_length=200)
    locality: str | None = Field(None, min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    state_code: str | None = Field(None, min_length=1, max_length=20)
    country_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    postal_code: str | None = Field(None, min_length=1, max_length=20)
    delivery_instructions: str | None = Field(None, min_length=1, max_length=500)


class PartyAddressCreate(PartyAddressInput):
    party_id: uuid.UUID = Field(...)


class PartyAddressUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    mailing_name: str | None = Field(None, min_length=1, max_length=200)
    line1: str | None = Field(None, min_length=1, max_length=200)
    line2: str | None = Field(None, min_length=1, max_length=200)
    locality: str | None = Field(None, min_length=1, max_length=100)
    city: str | None = Field(None, min_length=1, max_length=100)
    state_code: str | None = Field(None, min_length=1, max_length=20)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    postal_code: str | None = Field(None, min_length=1, max_length=20)
    delivery_instructions: str | None = Field(None, min_length=1, max_length=500)


class PartyAddressDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    mailing_name: str | None = Field(None, min_length=1, max_length=200)
    line1: str | None = Field(None, min_length=1, max_length=200)
    line2: str | None = Field(None, min_length=1, max_length=200)
    locality: str | None = Field(None, min_length=1, max_length=100)
    city: str | None = Field(None, min_length=1, max_length=100)
    state_code: str | None = Field(None, min_length=1, max_length=20)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    postal_code: str | None = Field(None, min_length=1, max_length=20)
    delivery_instructions: str | None = Field(None, min_length=1, max_length=500)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


PostingPurpose = Literal[
    "SALES_REVENUE",
    "SERVICE_REVENUE",
    "SALES_RETURN",
    "PURCHASE_EXPENSE",
    "OUTPUT_CGST",
    "OUTPUT_SGST",
    "OUTPUT_UTGST",
    "OUTPUT_IGST",
    "OUTPUT_CESS",
    "INPUT_CGST",
    "INPUT_SGST",
    "INPUT_UTGST",
    "INPUT_IGST",
    "INPUT_CESS",
    "PENDING_CGST",
    "PENDING_SGST",
    "PENDING_UTGST",
    "PENDING_IGST",
    "PENDING_CESS",
    "RCM_CGST",
    "RCM_SGST",
    "RCM_UTGST",
    "RCM_IGST",
    "RCM_CESS",
    "TDS_PAYABLE",
    "TCS_PAYABLE",
    "TDS_RECEIVABLE",
    "TCS_RECEIVABLE",
    "CASH_RECEIPT",
    "BANK_RECEIPT",
    "INVENTORY_VALUE",
    "COST_OF_GOODS",
    "ROUNDING_GAIN",
    "ROUNDING_LOSS",
]
PartyRegistrationType = Literal[
    "REGULAR",
    "COMPOSITION",
    "UNREGISTERED",
    "SEZ_UNIT",
    "SEZ_DEVELOPER",
    "UIN",
    "OVERSEAS",
    "CASUAL",
    "NRTP",
    "OTHER",
]


class PartyTaxRegistrationInput(Input):
    scheme: Literal["GST_IN", "VAT", "OTHER"] = Field(...)
    # Absent only for UNREGISTERED (the row records the buyer's state) and OVERSEAS.
    registration_number: str | None = Field(None, min_length=1, max_length=80)
    registration_type: PartyRegistrationType = Field("REGULAR")
    country_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(None, min_length=1, max_length=20)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyTaxRegistrationCreate(PartyTaxRegistrationInput):
    party_id: uuid.UUID = Field(...)


class PartyTaxRegistrationUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
    registration_number: str | None = Field(None, min_length=1, max_length=80)
    registration_type: PartyRegistrationType | None = Field(None)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(None, min_length=1, max_length=20)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyTaxRegistrationDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
    registration_number: str | None = Field(None, min_length=1, max_length=80)
    registration_type: PartyRegistrationType | None = Field(None)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    state_code: str | None = Field(None, min_length=1, max_length=20)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyDrugLicenceCreate(Input):
    party_id: uuid.UUID
    address_id: uuid.UUID
    licence_form: Literal["20", "20B", "21", "21B"]
    licence_number: str = Field(min_length=1, max_length=80)
    valid_from: dt.date
    valid_to: dt.date | None = None
    source_reference: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("drug licence validity is reversed")
        return self


class PartyDrugLicenceUpdate(ExpectedVersion):
    valid_to: dt.date | None = None
    closure_reason: str | None = Field(default=None, min_length=1, max_length=500)


class PartyDrugLicenceDetail(Detail):
    party_id: uuid.UUID | None = None
    address_id: uuid.UUID | None = None
    licence_form: Literal["20", "20B", "21", "21B"] | None = None
    licence_number: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    source_reference: str | None = None
    source_sha256: str | None = None
    reviewed_at: dt.datetime | None = None
    reviewed_by: uuid.UUID | None = None
    closure_reason: str | None = None


class PartyAddressUseCreate(Input):
    party_id: uuid.UUID = Field(...)
    address_id: uuid.UUID = Field(...)
    purpose: Literal[
        "REGISTERED", "BILLING", "SHIPPING", "CORRESPONDENCE", "DISPATCH", "REMITTANCE"
    ] = Field(...)
    registration_id: uuid.UUID | None = Field(None)
    is_default: bool = Field(False)


class PartyAddressUseUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    purpose: (
        Literal["REGISTERED", "BILLING", "SHIPPING", "CORRESPONDENCE", "DISPATCH", "REMITTANCE"]
        | None
    ) = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    is_default: bool | None = Field(None)


class PartyAddressUseDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    purpose: (
        Literal["REGISTERED", "BILLING", "SHIPPING", "CORRESPONDENCE", "DISPATCH", "REMITTANCE"]
        | None
    ) = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    is_default: bool | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyContactInput(Input):
    name: str = Field(..., min_length=1, max_length=160)
    designation: str | None = Field(None, min_length=1, max_length=100)
    department: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=1, max_length=254)
    phone: str | None = Field(None, min_length=1, max_length=40)
    mobile: str | None = Field(None, min_length=1, max_length=40)
    language: str | None = Field(None, min_length=1, max_length=20)


class PartyContactCreate(PartyContactInput):
    party_id: uuid.UUID = Field(...)


class PartyContactUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    name: str | None = Field(None, min_length=1, max_length=160)
    designation: str | None = Field(None, min_length=1, max_length=100)
    department: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=1, max_length=254)
    phone: str | None = Field(None, min_length=1, max_length=40)
    mobile: str | None = Field(None, min_length=1, max_length=40)
    language: str | None = Field(None, min_length=1, max_length=20)


class PartyContactDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    name: str | None = Field(None, min_length=1, max_length=160)
    designation: str | None = Field(None, min_length=1, max_length=100)
    department: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, min_length=1, max_length=254)
    phone: str | None = Field(None, min_length=1, max_length=40)
    mobile: str | None = Field(None, min_length=1, max_length=40)
    language: str | None = Field(None, min_length=1, max_length=20)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyContactUseCreate(Input):
    party_id: uuid.UUID = Field(...)
    contact_id: uuid.UUID = Field(...)
    purpose: Literal["GENERAL", "INVOICING", "PAYMENTS", "DELIVERY"] = Field(...)
    is_default: bool = Field(False)


class PartyContactUseUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    contact_id: uuid.UUID | None = Field(None)
    purpose: Literal["GENERAL", "INVOICING", "PAYMENTS", "DELIVERY"] | None = Field(None)
    is_default: bool | None = Field(None)


class PartyContactUseDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    contact_id: uuid.UUID | None = Field(None)
    purpose: Literal["GENERAL", "INVOICING", "PAYMENTS", "DELIVERY"] | None = Field(None)
    is_default: bool | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyIdentifierCreate(Input):
    party_id: uuid.UUID = Field(...)
    scheme: Literal["PAN", "TAN", "CIN", "EIN", "UDYAM", "BUSINESS_REGISTRATION"] = Field(...)
    value: str = Field(..., min_length=1, max_length=80)
    country_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    verification_reference: str | None = Field(None, min_length=1, max_length=160)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyIdentifierUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["PAN", "TAN", "CIN", "EIN", "UDYAM", "BUSINESS_REGISTRATION"] | None = Field(
        None
    )
    value: str | None = Field(None, min_length=1, max_length=80)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    verification_reference: str | None = Field(None, min_length=1, max_length=160)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyIdentifierDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["PAN", "TAN", "CIN", "EIN", "UDYAM", "BUSINESS_REGISTRATION"] | None = Field(
        None
    )
    value: str | None = Field(None, min_length=1, max_length=80)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    verification_reference: str | None = Field(None, min_length=1, max_length=160)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyRegistrationAddressCreate(Input):
    party_id: uuid.UUID = Field(...)
    registration_id: uuid.UUID = Field(...)
    address_id: uuid.UUID = Field(...)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyRegistrationAddressUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyRegistrationAddressDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyBankAccountCreate(Input):
    party_id: uuid.UUID = Field(...)
    label: str = Field(..., min_length=1, max_length=100)
    beneficiary_name: str = Field(..., min_length=1, max_length=200)
    bank_name: str = Field(..., min_length=1, max_length=160)
    country_code: str = Field(..., pattern=r"^[A-Z]{2}$")
    currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    routing_code: str | None = Field(None, min_length=1, max_length=40)
    account_number: str = Field(..., min_length=4, max_length=64)
    verification_reference: str | None = Field(None, min_length=1, max_length=160)


class PartyBankAccountUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    beneficiary_name: str | None = Field(None, min_length=1, max_length=200)
    bank_name: str | None = Field(None, min_length=1, max_length=160)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    routing_code: str | None = Field(None, min_length=1, max_length=40)
    account_number: str | None = Field(None, min_length=4, max_length=64)
    verification_reference: str | None = Field(None, min_length=1, max_length=160)


class PartyBankAccountDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    beneficiary_name: str | None = Field(None, min_length=1, max_length=200)
    bank_name: str | None = Field(None, min_length=1, max_length=160)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    routing_code: str | None = Field(None, min_length=1, max_length=40)
    verification_reference: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    account_number_last4: str | None = Field(None, min_length=1, max_length=4)


class PartyCommercialTypeCreate(Input):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    role: Literal["CUSTOMER", "SUPPLIER"] = Field(...)


class PartyCommercialTypeUpdate(ExpectedVersion):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)


class PartyCommercialTypeDetail(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyCommercialTypeMembershipCreate(Input):
    party_id: uuid.UUID = Field(...)
    commercial_type_id: uuid.UUID = Field(...)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyCommercialTypeMembershipUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    commercial_type_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyCommercialTypeMembershipDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    commercial_type_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyAccountingPolicyCreate(Input):
    party_id: uuid.UUID = Field(...)
    role: Literal["CUSTOMER", "SUPPLIER"] = Field(...)
    payment_term_id: uuid.UUID = Field(...)
    bill_wise: bool = Field(True)
    settlement_currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    transaction_hold: bool = Field(False)
    payment_hold: bool = Field(False)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyAccountingPolicyUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    payment_term_id: uuid.UUID | None = Field(None)
    bill_wise: bool | None = Field(None)
    settlement_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    transaction_hold: bool | None = Field(None)
    payment_hold: bool | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyAccountingPolicyDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    payment_term_id: uuid.UUID | None = Field(None)
    bill_wise: bool | None = Field(None)
    settlement_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    transaction_hold: bool | None = Field(None)
    payment_hold: bool | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyCreditPolicyCreate(Input):
    party_id: uuid.UUID = Field(...)
    role: Literal["CUSTOMER", "SUPPLIER"] = Field("CUSTOMER")
    limit_mode: Literal["INHERIT", "UNLIMITED", "LIMITED"] = Field("LIMITED")
    limit_amount: DecimalInput | None = Field(None, ge=0, max_digits=19, decimal_places=4)
    currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    enforcement: Literal["WARN", "BLOCK", "OVERRIDE"] = Field("BLOCK")
    overdue_days: int = Field(0, strict=True, ge=0, le=1000000)
    overdue_tolerance: DecimalInput = Field(Decimal("0"), ge=0, max_digits=19, decimal_places=4)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyCreditPolicyUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    limit_mode: Literal["INHERIT", "UNLIMITED", "LIMITED"] | None = Field(None)
    limit_amount: DecimalInput | None = Field(None, ge=0, max_digits=19, decimal_places=4)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    enforcement: Literal["WARN", "BLOCK", "OVERRIDE"] | None = Field(None)
    overdue_days: int | None = Field(None, strict=True, ge=0, le=1000000)
    overdue_tolerance: DecimalInput | None = Field(None, ge=0, max_digits=19, decimal_places=4)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyCreditPolicyDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    limit_mode: Literal["INHERIT", "UNLIMITED", "LIMITED"] | None = Field(None)
    limit_amount: DecimalInput | None = Field(None, ge=0, max_digits=19, decimal_places=4)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    enforcement: Literal["WARN", "BLOCK", "OVERRIDE"] | None = Field(None)
    overdue_days: int | None = Field(None, strict=True, ge=0, le=1000000)
    overdue_tolerance: DecimalInput | None = Field(None, ge=0, max_digits=19, decimal_places=4)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class AccountTaxProfileCreate(Input):
    account_id: uuid.UUID = Field(...)
    company_registration_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] = Field(...)
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS", "VAT", "OTHER"] = Field(...)
    purpose: Literal[
        "INPUT_RECOVERABLE",
        "INPUT_PENDING",
        "OUTPUT_PAYABLE",
        "RCM_PAYABLE",
        "DEPOSIT",
        "ADJUSTMENT",
    ] = Field(...)
    duty_type: Literal["GST", "VAT", "TDS", "TCS", "CESS", "EXCISE", "OTHER"] = Field("OTHER")


class AccountTaxProfileUpdate(ExpectedVersion):
    account_id: uuid.UUID | None = Field(None)
    company_registration_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS", "VAT", "OTHER"] | None = Field(None)
    purpose: (
        Literal[
            "INPUT_RECOVERABLE",
            "INPUT_PENDING",
            "OUTPUT_PAYABLE",
            "RCM_PAYABLE",
            "DEPOSIT",
            "ADJUSTMENT",
        ]
        | None
    ) = Field(None)
    duty_type: Literal["GST", "VAT", "TDS", "TCS", "CESS", "EXCISE", "OTHER"] | None = Field(None)


class AccountTaxProfileDetail(Detail):
    account_id: uuid.UUID | None = Field(None)
    company_registration_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
    component: Literal["CGST", "SGST", "UTGST", "IGST", "CESS", "VAT", "OTHER"] | None = Field(None)
    purpose: (
        Literal[
            "INPUT_RECOVERABLE",
            "INPUT_PENDING",
            "OUTPUT_PAYABLE",
            "RCM_PAYABLE",
            "DEPOSIT",
            "ADJUSTMENT",
        ]
        | None
    ) = Field(None)
    duty_type: Literal["GST", "VAT", "TDS", "TCS", "CESS", "EXCISE", "OTHER"] | None = Field(None)


class AccountBankProfileCreate(Input):
    account_id: uuid.UUID = Field(...)
    company_bank_id: uuid.UUID = Field(...)
    reconciliation_start_date: dt.date | None = Field(None)


class AccountBankProfileUpdate(ExpectedVersion):
    account_id: uuid.UUID | None = Field(None)
    company_bank_id: uuid.UUID | None = Field(None)
    reconciliation_start_date: dt.date | None = Field(None)


class AccountBankProfileDetail(Detail):
    account_id: uuid.UUID | None = Field(None)
    company_bank_id: uuid.UUID | None = Field(None)
    reconciliation_start_date: dt.date | None = Field(None)


class AccountTemplateInstallationCreate(Input):
    template_key: str = Field(..., min_length=1, max_length=60)
    template_version: str = Field(..., min_length=1, max_length=30)
    content_hash: str = Field(..., min_length=1, max_length=64)


class AccountTemplateInstallationUpdate(ExpectedVersion):
    template_key: str | None = Field(None, min_length=1, max_length=60)
    template_version: str | None = Field(None, min_length=1, max_length=30)
    content_hash: str | None = Field(None, min_length=1, max_length=64)


class AccountTemplateInstallationDetail(Detail):
    template_key: str | None = Field(None, min_length=1, max_length=60)
    template_version: str | None = Field(None, min_length=1, max_length=30)
    content_hash: str | None = Field(None, min_length=1, max_length=64)


class AccountTemplateBindingCreate(Input):
    installation_id: uuid.UUID = Field(...)
    object_type: Literal["HEAD", "GROUP", "ACCOUNT"] = Field(...)
    object_id: uuid.UUID = Field(...)


class AccountTemplateBindingUpdate(ExpectedVersion):
    installation_id: uuid.UUID | None = Field(None)
    object_type: Literal["HEAD", "GROUP", "ACCOUNT"] | None = Field(None)
    object_id: uuid.UUID | None = Field(None)


class AccountTemplateBindingDetail(Detail):
    installation_id: uuid.UUID | None = Field(None)
    object_type: Literal["HEAD", "GROUP", "ACCOUNT"] | None = Field(None)
    object_id: uuid.UUID | None = Field(None)
    system_key: str | None = Field(None, min_length=1, max_length=60)


class AccountPostingMappingCreate(Input):
    purpose: PostingPurpose = Field(...)
    account_id: uuid.UUID = Field(...)
    company_registration_id: uuid.UUID | None = Field(None)
    currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class AccountPostingMappingUpdate(ExpectedVersion):
    purpose: PostingPurpose | None = Field(None)
    account_id: uuid.UUID | None = Field(None)
    company_registration_id: uuid.UUID | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class AccountPostingMappingDetail(Detail):
    purpose: PostingPurpose | None = Field(None)
    account_id: uuid.UUID | None = Field(None)
    company_registration_id: uuid.UUID | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


DeducteeType = Literal[
    "INDIVIDUAL",
    "HUF",
    "COMPANY",
    "FIRM",
    "AOP_BOI",
    "LOCAL_AUTHORITY",
    "ARTIFICIAL_JURIDICAL_PERSON",
    "GOVERNMENT",
    "COOPERATIVE",
    "TRUST",
    "NON_RESIDENT_COMPANY",
    "NON_RESIDENT_OTHER",
    "OTHER",
]
WithholdingKind = Literal["TDS", "TCS"]
ThresholdBasis = Literal["TRANSACTION", "AGGREGATE", "EXCESS"]
PanStatus = Literal["VERIFIED", "NOT_AVAILABLE", "INOPERATIVE"]
SECTION_CODE = r"^[A-Z0-9][A-Z0-9()./ -]{0,39}$"
CERTIFICATE_REFERENCE = r"^[A-Za-z0-9][A-Za-z0-9/-]{0,79}$"
SHA256 = r"^[0-9a-f]{64}$"


def official_source(value: str | None) -> str | None:
    """Statutory evidence must be an official Indian government HTTPS document."""
    if value is None:
        return value
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError as exc:
        raise ValueError("source must be an official government HTTPS document") from exc
    if (
        url.scheme != "https"
        or not url.hostname
        or not url.hostname.endswith((".gov.in", ".nic.in"))
        or url.username
        or url.password
        or port not in {None, 443}
    ):
        raise ValueError("source must be an official government HTTPS document")
    return value


class Evidenced(Input):
    @field_validator("source_url", check_fields=False)
    @classmethod
    def official(cls, value: str | None) -> str | None:
        return official_source(value)


class EvidencedVersion(ExpectedVersion):
    @field_validator("source_url", check_fields=False)
    @classmethod
    def official(cls, value: str | None) -> str | None:
        return official_source(value)


class WithholdingSectionCreate(Input):
    code: str = Field(..., pattern=SECTION_CODE)
    kind: WithholdingKind = Field(...)
    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = Field(None, min_length=1, max_length=500)


class WithholdingSectionUpdate(ExpectedVersion):
    code: str | None = Field(None, pattern=SECTION_CODE)
    kind: WithholdingKind | None = Field(None)
    name: str | None = Field(None, min_length=1, max_length=160)
    description: str | None = Field(None, min_length=1, max_length=500)


class WithholdingSectionDetail(Detail):
    code: str | None = Field(None, max_length=40)
    kind: WithholdingKind | None = Field(None)
    name: str | None = Field(None, max_length=160)
    description: str | None = Field(None, max_length=500)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class WithholdingRateCreate(Evidenced):
    section_id: uuid.UUID = Field(...)
    deductee_type: DeducteeType = Field(...)
    rate_percent: DecimalInput = Field(..., ge=0, le=100, max_digits=19, decimal_places=4)
    no_pan_rate_percent: DecimalInput = Field(..., ge=0, le=100, max_digits=19, decimal_places=4)
    single_transaction_threshold: DecimalInput | None = Field(
        None, gt=0, max_digits=19, decimal_places=4
    )
    aggregate_annual_threshold: DecimalInput | None = Field(
        None, gt=0, max_digits=19, decimal_places=4
    )
    threshold_currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    threshold_basis: ThresholdBasis = Field("TRANSACTION")
    source_reference: str = Field(..., min_length=1, max_length=500)
    source_url: str = Field(..., min_length=1, max_length=1000)
    source_sha256: str = Field(..., pattern=SHA256)
    supersedes_id: uuid.UUID | None = Field(None)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class WithholdingRateUpdate(EvidencedVersion):
    section_id: uuid.UUID | None = Field(None)
    deductee_type: DeducteeType | None = Field(None)
    rate_percent: DecimalInput | None = Field(None, ge=0, le=100, max_digits=19, decimal_places=4)
    no_pan_rate_percent: DecimalInput | None = Field(
        None, ge=0, le=100, max_digits=19, decimal_places=4
    )
    single_transaction_threshold: DecimalInput | None = Field(
        None, gt=0, max_digits=19, decimal_places=4
    )
    aggregate_annual_threshold: DecimalInput | None = Field(
        None, gt=0, max_digits=19, decimal_places=4
    )
    threshold_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    threshold_basis: ThresholdBasis | None = Field(None)
    source_reference: str | None = Field(None, min_length=1, max_length=500)
    source_url: str | None = Field(None, min_length=1, max_length=1000)
    source_sha256: str | None = Field(None, pattern=SHA256)
    supersedes_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class WithholdingRateDetail(Detail):
    section_id: uuid.UUID | None = Field(None)
    deductee_type: DeducteeType | None = Field(None)
    rate_percent: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    no_pan_rate_percent: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    single_transaction_threshold: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    aggregate_annual_threshold: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    threshold_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    threshold_basis: ThresholdBasis | None = Field(None)
    source_reference: str | None = Field(None, max_length=500)
    source_url: str | None = Field(None, max_length=1000)
    source_sha256: str | None = Field(None, max_length=64)
    supersedes_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyWithholdingProfileCreate(Input):
    party_id: uuid.UUID = Field(...)
    kind: WithholdingKind = Field(...)
    deductible: bool = Field(True, strict=True)
    deductee_type: DeducteeType = Field(...)
    pan_status: PanStatus = Field(...)
    pan_identifier_id: uuid.UUID | None = Field(None)
    default_section_id: uuid.UUID | None = Field(None)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class PartyWithholdingProfileUpdate(ExpectedVersion):
    party_id: uuid.UUID | None = Field(None)
    kind: WithholdingKind | None = Field(None)
    deductible: bool | None = Field(None, strict=True)
    deductee_type: DeducteeType | None = Field(None)
    pan_status: PanStatus | None = Field(None)
    pan_identifier_id: uuid.UUID | None = Field(None)
    default_section_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyWithholdingProfileDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    kind: WithholdingKind | None = Field(None)
    deductible: bool | None = Field(None, strict=True)
    deductee_type: DeducteeType | None = Field(None)
    pan_status: PanStatus | None = Field(None)
    pan_identifier_id: uuid.UUID | None = Field(None)
    default_section_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class WithholdingCertificateCreate(Evidenced):
    party_id: uuid.UUID = Field(...)
    section_id: uuid.UUID = Field(...)
    certificate_reference: str = Field(..., pattern=CERTIFICATE_REFERENCE)
    rate_percent: DecimalInput = Field(..., ge=0, le=100, max_digits=19, decimal_places=4)
    amount_limit: DecimalInput | None = Field(None, gt=0, max_digits=19, decimal_places=4)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    source_reference: str = Field(..., min_length=1, max_length=500)
    source_url: str = Field(..., min_length=1, max_length=1000)
    source_sha256: str = Field(..., pattern=SHA256)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class WithholdingCertificateUpdate(EvidencedVersion):
    party_id: uuid.UUID | None = Field(None)
    section_id: uuid.UUID | None = Field(None)
    certificate_reference: str | None = Field(None, pattern=CERTIFICATE_REFERENCE)
    rate_percent: DecimalInput | None = Field(None, ge=0, le=100, max_digits=19, decimal_places=4)
    amount_limit: DecimalInput | None = Field(None, gt=0, max_digits=19, decimal_places=4)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    source_reference: str | None = Field(None, min_length=1, max_length=500)
    source_url: str | None = Field(None, min_length=1, max_length=1000)
    source_sha256: str | None = Field(None, pattern=SHA256)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class WithholdingCertificateDetail(Detail):
    party_id: uuid.UUID | None = Field(None)
    section_id: uuid.UUID | None = Field(None)
    certificate_reference: str | None = Field(None, max_length=80)
    rate_percent: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    amount_limit: DecimalInput | None = Field(None, max_digits=19, decimal_places=4)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    source_reference: str | None = Field(None, max_length=500)
    source_url: str | None = Field(None, max_length=1000)
    source_sha256: str | None = Field(None, max_length=64)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


TaxDirection = Literal["SALE", "PURCHASE"]
SupplyKind = Literal["GOODS", "SERVICE"]
CodeSystem = Literal["SAC", "HSN"]
TaxTreatment = Literal["TAXABLE", "NIL_RATED", "EXEMPT", "NON_GST"]
ItcEligibility = Literal["ELIGIBLE", "INELIGIBLE", "BLOCKED"]
AssessableInclusion = Literal["NONE", "GOODS", "SERVICES", "BOTH"]
ApportionBy = Literal["VALUE", "QUANTITY"]
TaxCode = Annotated[str, Field(pattern=r"^[0-9]{4,8}$")]


class AccountTaxDefaultCreate(Input):
    account_id: uuid.UUID = Field(...)
    direction: TaxDirection = Field(...)
    supply_kind: SupplyKind = Field(...)
    code_system: CodeSystem = Field(...)
    code: TaxCode = Field(...)
    rule_id: uuid.UUID | None = Field(None)
    treatment: TaxTreatment = Field(...)
    itc_eligibility: ItcEligibility | None = Field(None)
    rcm_applicable: bool = Field(False, strict=True)
    assessable_inclusion: AssessableInclusion = Field("NONE")
    apportion_by: ApportionBy | None = Field(None)
    valid_from: dt.date = Field(...)
    valid_to: dt.date | None = Field(None)


class AccountTaxDefaultUpdate(ExpectedVersion):
    account_id: uuid.UUID | None = Field(None)
    direction: TaxDirection | None = Field(None)
    supply_kind: SupplyKind | None = Field(None)
    code_system: CodeSystem | None = Field(None)
    code: TaxCode | None = Field(None)
    rule_id: uuid.UUID | None = Field(None)
    treatment: TaxTreatment | None = Field(None)
    itc_eligibility: ItcEligibility | None = Field(None)
    rcm_applicable: bool | None = Field(None, strict=True)
    assessable_inclusion: AssessableInclusion | None = Field(None)
    apportion_by: ApportionBy | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class AccountTaxDefaultDetail(Detail):
    account_id: uuid.UUID | None = Field(None)
    direction: TaxDirection | None = Field(None)
    supply_kind: SupplyKind | None = Field(None)
    code_system: CodeSystem | None = Field(None)
    code: TaxCode | None = Field(None)
    rule_id: uuid.UUID | None = Field(None)
    treatment: TaxTreatment | None = Field(None)
    itc_eligibility: ItcEligibility | None = Field(None)
    rcm_applicable: bool | None = Field(None)
    assessable_inclusion: AssessableInclusion | None = Field(None)
    apportion_by: ApportionBy | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)
