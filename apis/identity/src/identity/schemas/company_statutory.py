"""Schemas for a company's tax registrations, statutory IDs, licences and addresses.

The statutory-ID schemas are where the AADHAAR/SSN-class rule lives on the wire: the
create body accepts the full ``value`` (validated against the jurisdiction pattern),
but the response and stored row keep only ``value_last4`` for a restricted kind — the
full number is discarded and never echoed (docs/company.md §4.3, CLAUDE.md §5.10).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, field_validator

from identity.models import ADDRESS_TYPES
from identity.schemas.base import StrictModel

# --- tax registration ---------------------------------------------------------


class InitialTaxRegistration(StrictModel):
    """One optional registration for the new company's selected jurisdiction."""

    regime: str = Field(min_length=1, max_length=40)
    number: str = Field(min_length=1, max_length=40)
    valid_from: dt.date


class TaxRegistrationCreate(StrictModel):
    tax_system: str = Field(min_length=1, max_length=20)
    regime: str = Field(min_length=1, max_length=40)
    number: str = Field(min_length=1, max_length=40)
    jurisdiction_code: str = Field(min_length=1, max_length=8)
    legal_name_on_registration: str | None = Field(default=None, max_length=255)
    registered_address_id: uuid.UUID | None = None
    is_primary: bool = False
    valid_from: dt.date
    valid_to: dt.date | None = None


class TaxRegistrationUpdate(StrictModel):
    """An amendment. ``regime``, ``number``, ``jurisdiction_code`` and ``valid_from``
    are accepted only unchanged — echoing the row back is not an edit — and any real
    change is a 422 ``immutable_field`` for every actor (docs/company.md §4.2). A
    regime change is "set ``valid_to`` here, then add a new registration"."""

    nonnullable = frozenset({"regime", "number", "jurisdiction_code", "valid_from", "is_primary"})

    regime: str | None = Field(default=None, min_length=1, max_length=40)
    number: str | None = Field(default=None, min_length=1, max_length=40)
    jurisdiction_code: str | None = Field(default=None, min_length=1, max_length=8)
    legal_name_on_registration: str | None = Field(default=None, max_length=255)
    registered_address_id: uuid.UUID | None = None
    is_primary: bool | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None


class TaxRegistrationItem(StrictModel):
    id: uuid.UUID
    tax_system: str
    regime: str
    #: Read-only; derived from ``regime`` (``billing_platform.tax.REGISTRATION_CLASSES``).
    registration_class: str
    number: str
    jurisdiction_code: str
    legal_name_on_registration: str | None
    registered_address_id: uuid.UUID | None
    is_primary: bool
    valid_from: dt.date
    valid_to: dt.date | None


# --- statutory id -------------------------------------------------------------


class StatutoryIdCreate(StrictModel):
    kind: str = Field(min_length=1, max_length=40)
    #: The full submitted identifier. For a restricted kind (AADHAAR/SSN) only the last
    #: four survive — the rest is discarded before anything is stored, logged or
    #: returned. For a business identifier (PAN/CIN/…) it is stored in full.
    value: str = Field(min_length=1, max_length=100)
    holder_name: str | None = Field(default=None, max_length=200)
    issued_on: dt.date | None = None
    valid_to: dt.date | None = None
    verification_reference: str | None = Field(default=None, max_length=100)


class StatutoryIdItem(StrictModel):
    id: uuid.UUID
    kind: str
    #: ``null`` for a restricted identifier — by design, not omission.
    value: str | None
    value_last4: str
    holder_name: str | None
    issued_on: dt.date | None
    valid_to: dt.date | None
    verification_reference: str | None
    is_active: bool


# --- licence ------------------------------------------------------------------


class LicenceCreate(StrictModel):
    kind: str = Field(min_length=1, max_length=40)
    number: str = Field(min_length=1, max_length=60)
    issuing_authority: str | None = Field(default=None, max_length=150)
    premises_address_id: uuid.UUID | None = None
    issued_on: dt.date | None = None
    renewal_reminder_days: int | None = Field(default=None, ge=0, le=365)
    document_url: str | None = Field(default=None, max_length=500)
    is_primary: bool = False
    valid_from: dt.date
    valid_to: dt.date | None = None


class LicenceItem(StrictModel):
    id: uuid.UUID
    kind: str
    number: str
    issuing_authority: str | None
    premises_address_id: uuid.UUID | None
    issued_on: dt.date | None
    renewal_reminder_days: int | None
    document_url: str | None
    is_primary: bool
    valid_from: dt.date
    valid_to: dt.date | None


# --- address ------------------------------------------------------------------


class AddressCreate(StrictModel):
    type: str
    label: str | None = Field(default=None, max_length=60)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state_code: str = Field(min_length=1, max_length=6)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(min_length=2, max_length=2)
    is_primary: bool = False

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in ADDRESS_TYPES:
            raise ValueError(f"type must be one of {', '.join(sorted(ADDRESS_TYPES))}")
        return v


class AddressItem(StrictModel):
    id: uuid.UUID
    type: str
    label: str | None
    line1: str
    line2: str | None
    city: str
    state_code: str
    postal_code: str
    country_code: str
    is_primary: bool
    is_active: bool
