"""Short-lived, request-bound permission proofs for company-scoped durable work.

Identity resolves native grants; consumers verify the independently signed response
outside their business transaction. This protocol never grants authority from a
role name, user type, stored job grants or an unsigned client assertion.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from billing_platform.permissions import PERMISSIONS

CONTRACT = "identity.company_actor_authorization.v1"
REQUEST_OPERATION = "catalog.actor.authorize"
RESPONSE_OPERATION = "catalog.actor.authorization.response"
MAX_LEASE_SECONDS = 30


class ActorAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: uuid.UUID
    user_id: uuid.UUID
    permissions: frozenset[str] = Field(min_length=1, max_length=32)

    @field_validator("request_id", "user_id")
    @classmethod
    def real_identity(cls, value: uuid.UUID) -> uuid.UUID:
        if value.int == 0:
            raise ValueError("authorization requires real identities")
        return value

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: frozenset[str]) -> frozenset[str]:
        if not value <= PERMISSIONS:
            raise ValueError("unknown requested permission")
        return value

    @field_serializer("permissions")
    def sorted_permissions(self, value: frozenset[str]) -> list[str]:
        return sorted(value)


class ActorAuthorizationProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract: str = CONTRACT
    request_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    source_version: int = Field(strict=True, ge=1, lt=2**63)
    generated_at: dt.datetime
    expires_at: dt.datetime
    permissions: frozenset[str] = Field(max_length=32)

    @field_validator("request_id", "tenant_id", "company_id", "user_id")
    @classmethod
    def real_identity(cls, value: uuid.UUID) -> uuid.UUID:
        return ActorAuthorizationRequest.real_identity(value)

    @field_validator("generated_at", "expires_at", mode="before")
    @classmethod
    def aware_timestamp(cls, value: Any) -> dt.datetime:
        if isinstance(value, str):
            value = dt.datetime.fromisoformat(value)
        if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization timestamps require timezone")
        try:
            return value.astimezone(dt.UTC)
        except OverflowError as exc:
            raise ValueError("authorization timestamp is outside its range") from exc

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: frozenset[str]) -> frozenset[str]:
        return ActorAuthorizationRequest.known_permissions(value)

    @field_serializer("permissions")
    def sorted_permissions(self, value: frozenset[str]) -> list[str]:
        return sorted(value)

    @model_validator(mode="after")
    def bounded_contract(self) -> ActorAuthorizationProof:
        if self.contract != CONTRACT or not dt.timedelta(
            0
        ) < self.expires_at - self.generated_at <= dt.timedelta(seconds=MAX_LEASE_SECONDS):
            raise ValueError("invalid authorization contract or lease")
        if self.generated_at.date() == dt.date.max:
            raise ValueError("authorization timestamp is outside its range")
        # Role grant dates resolve in UTC, consistently with the shared gateway.
        # A proof must not carry a scheduled grant across the next date boundary.
        boundary = dt.datetime.combine(
            self.generated_at.date() + dt.timedelta(days=1), dt.time(), dt.UTC
        )
        if self.expires_at > boundary:
            raise ValueError("authorization lease crosses its grant date")
        return self
