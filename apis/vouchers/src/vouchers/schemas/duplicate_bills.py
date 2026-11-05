"""Lean, typed duplicate supplier-bill lookup."""

import datetime as dt
import uuid
from typing import Self

from pydantic import Field, model_validator

from vouchers.schemas.configuration import Contract


class DuplicateBillQuery(Contract):
    """The supplier party, the payable ledger the bill posts to, or both (a match on either)."""

    party_id: uuid.UUID | None = None
    party_account_id: uuid.UUID | None = None
    bill_reference: str = Field(min_length=1, max_length=120)
    document_date: dt.date
    exclude_voucher_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def has_a_reference(self) -> Self:
        if self.party_id is None and self.party_account_id is None:
            raise ValueError("party_id or party_account_id is required")
        if not self.bill_reference.strip():
            raise ValueError("bill_reference must not be blank")
        return self


class DuplicateBill(Contract):
    id: uuid.UUID
    status: str
    document_date: dt.date
    bill_reference: str
    revision_number: int


class DuplicateBillList(Contract):
    """At most five rows, most recent first. Not a growing list, so no cursor.

    ``truncated`` is true when the candidate walk hit its hard ceiling before reading every bill
    of the supplier or ledger in the fiscal year: an older duplicate may exist that was not seen.
    """

    items: list[DuplicateBill] = Field(max_length=5)
    truncated: bool = False
