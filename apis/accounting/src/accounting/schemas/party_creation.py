"""Bounded initial party setup; related owners are assigned by the server."""

import uuid
from typing import Literal

from pydantic import Field

from accounting.schemas.master_opening import MasterOpeningInput
from accounting.schemas.masters import (
    ExpectedVersion,
    Input,
    PartyAddressInput,
    PartyContactInput,
    PartyCreate,
    PartyTaxRegistrationInput,
)


class PartyLedgerInput(Input):
    """Choices for the party's ledger account; everything left out is decided by the server.

    The ledger is never optional: every party role has exactly one account, created with it.
    The account's kind, party, party role, posting policy and status are never taken from the
    caller: a ledger is a PARTY account of this party, in the account role of its party role.
    """

    code: str | None = Field(None, min_length=1, max_length=40)
    name: str | None = Field(None, min_length=1, max_length=160)
    group_id: uuid.UUID | None = Field(None)
    currency_mode: Literal["BASE", "FIXED", "MULTI"] = Field("BASE")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")


def no_choices() -> PartyLedgerInput:
    """A ledger with every choice left to the server."""
    return PartyLedgerInput.model_validate({})


class PartyCreation(PartyCreate):
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"]
    address: PartyAddressInput | None = None
    contact: PartyContactInput | None = None
    tax_registration: PartyTaxRegistrationInput | None = None
    ledger: PartyLedgerInput = Field(default_factory=no_choices)
    opening: MasterOpeningInput | None = None


class PartyRoleActivation(ExpectedVersion):
    """Activating a role also creates its account, unless the party already holds one for it."""

    ledger: PartyLedgerInput = Field(default_factory=no_choices)


class PartyLedgerRepair(Input):
    """Give every active party role that has no account its account, a bounded batch at a time.

    Roles are taken in identity order; pass the previous result's `next_after` to continue.
    """

    limit: int = Field(100, ge=1, le=200)
    after: uuid.UUID | None = None


class PartyLedgerRepairItem(Input):
    party_id: uuid.UUID
    role: Literal["CUSTOMER", "SUPPLIER", "OTHER", "BROKER"]
    account_id: uuid.UUID | None = None
    reason: str | None = None
    account_ids: list[uuid.UUID] | None = None


class PartyLedgerRepairResult(Input):
    """`created` got an account; `attention` could not be repaired here, or holds several.

    `next_after` is empty once every role has been looked at.
    """

    created: list[PartyLedgerRepairItem]
    attention: list[PartyLedgerRepairItem]
    next_after: uuid.UUID | None = None
