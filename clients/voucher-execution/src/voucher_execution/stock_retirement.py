"""Native coordinated retirement evidence; it never authorizes stock posting."""

import datetime as dt
import hashlib
import uuid
from typing import Literal, Self

from billing_platform.idempotency import canonical_json
from billing_platform.gateway import Actor, decode_actor_context
from billing_platform.errors import AuthenticationRequiredError
from pydantic import Field, model_validator

from voucher_execution.contracts import Contract


class ActorProof(Contract):
    context: str = Field(min_length=1, max_length=65536, repr=False)
    signature: str = Field(min_length=1, max_length=256, repr=False)

    def verified_actor(
        self, secret: bytes, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> Actor:
        actor = decode_actor_context(self.context, self.signature, secret)
        if (actor.tenant_id, actor.user_id) != (
            tenant_id,
            actor_user_id,
        ) or actor.impersonation_id:
            raise AuthenticationRequiredError(
                "owner control requires its original delegated subject"
            )
        return actor


class RetirementRequest(Contract):
    check_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID | None = None
    expected_version: int = Field(strict=True, ge=1)
    command_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    authority: ActorProof = Field(repr=False)

    @model_validator(mode="after")
    def real_scope(self) -> Self:
        if any(
            isinstance(value, uuid.UUID) and not value.int
            for value in self.model_dump(exclude={"authority"}).values()
        ):
            raise ValueError("retirement needs real scoped references")
        return self

    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json(
                self.model_dump(mode="json", exclude={"authority"}),
            )
        ).hexdigest()

    def verified_actor(self, secret: bytes) -> Actor:
        return self.authority.verified_actor(
            secret, tenant_id=self.tenant_id, actor_user_id=self.actor_user_id
        )


class RetirementEvidence(Contract):
    owner: Literal["accounting", "vouchers"]
    check_id: uuid.UUID
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    issued_at: dt.datetime
    expires_at: dt.datetime
    fence_id: uuid.UUID | None = None
    result: Literal["CLEARED", "BLOCKED", "UNAVAILABLE"]
    reason: (
        Literal[
            "STOCK_ON_HAND", "OPEN_TRANSFER", "PENDING_DOCUMENT", "SOURCE_UNAVAILABLE"
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def closed_result(self) -> Self:
        if (
            self.issued_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not (
                dt.timedelta(0)
                < self.expires_at - self.issued_at
                <= dt.timedelta(seconds=60)
            )
        ):
            raise ValueError("retirement evidence requires a bounded aware lifetime")
        if (self.result == "CLEARED") != (self.reason is None):
            raise ValueError("retirement result needs its exact reason")
        if (
            self.owner == "vouchers"
            and self.result == "CLEARED"
            and self.fence_id is None
        ):
            raise ValueError("Vouchers clearance requires a retained write fence")
        return self


class RetirementRelease(Contract):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    check_id: uuid.UUID
    fence_id: uuid.UUID
