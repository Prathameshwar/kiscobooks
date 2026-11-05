"""Shared configuration for authenticated owner connections."""

from typing import Literal

import httpx
from billing_platform.owner_snapshot import SnapshotCredential
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Owner(SnapshotCredential):
    owner: Literal["identity", "catalog", "accounting"]
    origin: str
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")

    @field_validator("origin")
    @classmethod
    def https_origin(cls, value: str) -> str:
        url = httpx.URL(value)
        if (
            (
                url.scheme != "https"
                and not (url.scheme == "http" and url.host in {"127.0.0.1", "::1"})
            )
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError(
                "owner origin requires HTTPS (or a loopback development address), "
                "without credentials or path"
            )
        return value.rstrip("/")


class StockExecutionOwner(BaseModel):
    """Transport credential only; each accepted command carries exact user authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    origin: str
    key_id: Literal["stock.current"] = "stock.current"
    secret: SecretStr = Field(min_length=32)

    @field_validator("origin")
    @classmethod
    def https_origin(cls, value: str) -> str:
        return Owner.https_origin(value)
