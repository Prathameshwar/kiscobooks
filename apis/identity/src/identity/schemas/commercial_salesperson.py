"""Company salesperson contracts; these identities do not confer permissions."""

import uuid

from pydantic import Field

from identity.schemas.base import Page, StrictModel


class SalespersonCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=160)
    user_id: uuid.UUID | None = None


class SalespersonUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    user_id: uuid.UUID | None = None
    is_active: bool | None = None


class SalespersonItem(StrictModel):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    user_id: uuid.UUID | None
    is_active: bool
    row_version: int


class SalespersonPage(Page[SalespersonItem]):
    pass
