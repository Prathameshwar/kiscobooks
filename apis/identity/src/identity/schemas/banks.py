from __future__ import annotations

import uuid

from pydantic import Field, SecretStr, model_validator

from identity.schemas.base import StrictModel


class BankMetadata(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    account_name: str = Field(min_length=1, max_length=200)
    bank_name: str = Field(min_length=1, max_length=200)
    branch: str | None = Field(default=None, max_length=200)
    swift: str | None = Field(default=None, pattern=r"^[A-Z0-9]{8}([A-Z0-9]{3})?$")
    ifsc: str | None = Field(default=None, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    is_primary: bool = Field(default=False, strict=True)


class BankWrite(BankMetadata):
    account_number: SecretStr | None = Field(default=None, min_length=4, max_length=60)
    iban: SecretStr | None = Field(default=None, min_length=15, max_length=34)

    @model_validator(mode="after")
    def require_number(self) -> BankWrite:
        if self.account_number is None and self.iban is None:
            raise ValueError("an account number or IBAN is required")
        for value in (self.account_number, self.iban):
            if value is not None and not value.get_secret_value().isascii():
                raise ValueError("account identifiers must contain ASCII characters")
        return self


class BankItem(BankMetadata):
    id: uuid.UUID
    company_id: uuid.UUID
    account_last4: str | None
    iban_last4: str | None
    is_active: bool


class BankReveal(StrictModel):
    account_number: str | None
    iban: str | None
