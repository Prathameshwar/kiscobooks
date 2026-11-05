"""Signed, bounded installation-level source discovery contract."""

from billing_platform.service_auth import CompanyServiceScope
from pydantic import BaseModel, ConfigDict, Field


class EnrollmentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: int = Field(default=100, strict=True, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)


class EnrollmentPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scopes: tuple[CompanyServiceScope, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=4096)
