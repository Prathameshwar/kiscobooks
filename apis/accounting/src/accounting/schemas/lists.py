"""Lean native list projections, intentionally distinct from detail schemas."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from accounting.schemas.masters import (
    CodeSystem,
    Detail,
    PostingPurpose,
    SupplyKind,
    TaxCode,
    TaxDirection,
    TaxTreatment,
)


class AccountHeadListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)


class AccountingSetupListItem(Detail):
    base_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    generation: int | None = Field(None, strict=True, ge=0, le=1000000)
    template_version: str | None = Field(None, min_length=1, max_length=30)


class AccountGroupListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    head_id: uuid.UUID | None = Field(None)
    parent_id: uuid.UUID | None = Field(None)
    system_key: str | None = Field(None, min_length=1, max_length=60)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    is_primary: bool | None = Field(None)
    is_reserved: bool | None = Field(None)
    sort_order: int | None = Field(None, ge=0, le=1000000)


class AccountGroupClosureListItem(Detail):
    pass


class PartyListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    party_type: Literal["ORGANISATION", "PERSON"] | None = Field(None)
    roles: list[Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"]] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyRoleListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PaymentTermListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PaymentTermLineListItem(Detail):
    payment_term_id: uuid.UUID | None = Field(None)
    sequence: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    group_id: uuid.UUID | None = Field(None)
    kind: (
        Literal["GENERAL", "CASH", "BANK", "PARTY", "TAX", "INVENTORY_CONTROL", "ASSET_CONTROL"]
        | None
    ) = Field(None)
    party_id: uuid.UUID | None = Field(None)
    party_role: Literal["CUSTOMER", "SUPPLIER", "OTHER"] | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    currency_mode: Literal["BASE", "FIXED", "MULTI"] | None = Field(None)
    system_key: str | None = Field(None, min_length=1, max_length=60)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    sort_order: int | None = Field(None, strict=True, ge=0, le=1000000)


class AccountAliasListItem(Detail):
    account_id: uuid.UUID | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class AccountGroupAliasListItem(Detail):
    group_id: uuid.UUID | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    alias: str | None = Field(None, min_length=1, max_length=160)


class AccountExternalKeyListItem(Detail):
    account_id: uuid.UUID | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyAddressListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyTaxRegistrationListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyDrugLicenceListItem(Detail):
    party_id: uuid.UUID | None = None
    address_id: uuid.UUID | None = None
    licence_form: Literal["20", "20B", "21", "21B"] | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class PartyAddressUseListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    purpose: (
        Literal["REGISTERED", "BILLING", "SHIPPING", "CORRESPONDENCE", "DISPATCH", "REMITTANCE"]
        | None
    ) = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    is_default: bool | None = Field(None)


class PartyContactListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    name: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyContactUseListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    contact_id: uuid.UUID | None = Field(None)
    purpose: Literal["GENERAL", "INVOICING", "PAYMENTS", "DELIVERY"] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyIdentifierListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    scheme: Literal["PAN", "TAN", "CIN", "EIN", "UDYAM", "BUSINESS_REGISTRATION"] | None = Field(
        None
    )
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyRegistrationAddressListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    address_id: uuid.UUID | None = Field(None)
    registration_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyBankAccountListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    label: str | None = Field(None, min_length=1, max_length=100)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)
    account_number_last4: str | None = Field(None, min_length=1, max_length=4)


class PartyCommercialTypeListItem(Detail):
    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class PartyCommercialTypeMembershipListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    commercial_type_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyAccountingPolicyListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    payment_term_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyCreditPolicyListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    role: Literal["CUSTOMER", "SUPPLIER"] | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class AccountTaxProfileListItem(Detail):
    account_id: uuid.UUID | None = Field(None)
    scheme: Literal["GST_IN", "VAT", "OTHER"] | None = Field(None)
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


class AccountBankProfileListItem(Detail):
    account_id: uuid.UUID | None = Field(None)


class AccountTemplateInstallationListItem(Detail):
    template_key: str | None = Field(None, min_length=1, max_length=60)
    template_version: str | None = Field(None, min_length=1, max_length=30)


class AccountTemplateBindingListItem(Detail):
    object_type: Literal["HEAD", "GROUP", "ACCOUNT"] | None = Field(None)
    system_key: str | None = Field(None, min_length=1, max_length=60)


class AccountPostingMappingListItem(Detail):
    purpose: PostingPurpose | None = Field(None)
    account_id: uuid.UUID | None = Field(None)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class WithholdingSectionListItem(Detail):
    code: str | None = Field(None, max_length=40)
    kind: Literal["TDS", "TCS"] | None = Field(None)
    name: str | None = Field(None, max_length=160)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] | None = Field(None)


class WithholdingRateListItem(Detail):
    section_id: uuid.UUID | None = Field(None)
    deductee_type: str | None = Field(None, max_length=40)
    threshold_basis: Literal["TRANSACTION", "AGGREGATE", "EXCESS"] | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class PartyWithholdingProfileListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    kind: Literal["TDS", "TCS"] | None = Field(None)
    deductee_type: str | None = Field(None, max_length=40)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class WithholdingCertificateListItem(Detail):
    party_id: uuid.UUID | None = Field(None)
    section_id: uuid.UUID | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)


class AccountTaxDefaultListItem(Detail):
    account_id: uuid.UUID | None = Field(None)
    direction: TaxDirection | None = Field(None)
    supply_kind: SupplyKind | None = Field(None)
    code_system: CodeSystem | None = Field(None)
    code: TaxCode | None = Field(None)
    treatment: TaxTreatment | None = Field(None)
    valid_from: dt.date | None = Field(None)
    valid_to: dt.date | None = Field(None)
