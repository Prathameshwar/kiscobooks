"""Frozen v2 ledger input contract including scoped journal selection."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_id: uuid.UUID
    code: Literal["ACCOUNT_LEDGER", "DAY_BOOK", "PARTY_LEDGER", "CASH_BOOK", "BANK_BOOK"]
    date_from: dt.date
    date_to: dt.date
    basis: Literal["BASE", "TRANSACTION"] = "BASE"
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    journal_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    role: Literal["CUSTOMER", "SUPPLIER"] | None = None
    comparative_from: dt.date | None = None
    comparative_to: dt.date | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("invalid ledger date range")
        if (self.comparative_from is None) != (self.comparative_to is None):
            raise ValueError("both comparative dates are required")
        if (
            self.comparative_from
            and self.comparative_to
            and self.comparative_from > self.comparative_to
        ):
            raise ValueError("invalid comparative date range")
        if (self.basis == "TRANSACTION") != (self.currency is not None):
            raise ValueError("transaction basis requires a selected currency")
        return self
