"""First-run contracts contain no database, OIDC or email credentials."""

from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from identity.schemas.base import StrictModel


class SetupStatus(StrictModel):
    available: bool
    completed: bool


class SetupChoice(StrictModel):
    code: str
    name: str


class SetupCheck(StrictModel):
    name: str
    status: Literal["ready", "failed", "optional"]
    message: str


class SetupChecks(StrictModel):
    ready: bool
    checks: list[SetupCheck]
    countries: list[SetupChoice]
    currencies: list[SetupChoice]
    languages: list[SetupChoice]
    timezones: list[SetupChoice]


class SetupAdministrator(StrictModel):
    email: str


class SetupRequest(StrictModel):
    platform_name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    public_url: str = Field(min_length=1, max_length=2048)
    workspace_name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    workspace_slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
    administrator_name: str = Field(min_length=1, max_length=100, pattern=r"\S")
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    timezone: str = Field(min_length=1, max_length=64)
    locale: str = Field(default="en", pattern=r"^[a-z]{2}$")

    @field_validator("platform_name", "workspace_name", "administrator_name", "timezone")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("public_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        # Accessing port rejects nonnumeric and out-of-range ports before persisting an origin.
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or port == 0
            or any(character.isspace() or ord(character) < 32 for character in value)
            or (
                parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError("use an HTTPS application origin, or HTTP on localhost")
        return value.rstrip("/")


class SetupResult(StrictModel):
    completed: bool = True
    tenant_id: uuid.UUID
    administrator_id: uuid.UUID
    platform_name: str
