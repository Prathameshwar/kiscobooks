"""Editable installation metadata; bootstrap authority is deliberately absent."""

from pydantic import Field, field_validator

from identity.schemas.base import StrictModel
from identity.schemas.setup import SetupRequest


class PlatformDetails(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    public_url: str = Field(min_length=1, max_length=2048)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("enter a valid platform name")
        return value

    @field_validator("public_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        return SetupRequest.validate_url(value)
