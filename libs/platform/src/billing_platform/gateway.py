"""Framework-independent verifier for the existing gateway-signed actor contract.

The gateway resolves grants server-side. This is not a client JWT parser or a new
authentication scheme. Domain/service adapters retain their own policy decisions.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from billing_platform.authz import Grant, Scope, ScopePath, assert_permitted
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.statutory import covers


class _GrantContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[Annotated[str, Field(strict=True, min_length=1, max_length=200)]] = Field(
        max_length=512
    )
    scope_type: str
    scope_id: uuid.UUID | None = None
    valid_from: dt.date
    valid_to: dt.date | None = None
    is_active: StrictBool = True


class ReadPolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    entity_type: str = Field(pattern=r"^(accounting|catalog|vouchers)\.[a-z_]+$", max_length=80)
    field_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    effect: Literal["allow", "deny"]
    scope_type: Literal["tenant", "company", "department"]
    scope_id: uuid.UUID = SCOPE_ALL
    conditional: StrictBool = False
    subject_scope_type: Literal["tenant", "company", "department"] | None = None
    subject_scope_id: uuid.UUID | None = None


class AuditReadScope(BaseModel):
    """The company whose step-up state Identity verified for this Audit request."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    company_id: uuid.UUID | None = None


class NotificationAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(pattern=r"^/v1/platform/", max_length=1000)
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


class _ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issued_at: StrictInt
    notification_authority: NotificationAuthority | None = None
    audit_scope: AuditReadScope | None = None
    field_policies: list[ReadPolicyContext] | None = Field(default=None, max_length=512)
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    grants: list[_GrantContext] = Field(default_factory=list, max_length=256)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=256)
    user_type: str | None = Field(default=None, max_length=40)
    actor_user_id: uuid.UUID | None = None
    impersonation_id: uuid.UUID | None = None
    impersonation_expires_at: StrictInt | None = None


@dataclass(frozen=True, slots=True)
class Actor:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    grants: tuple[Grant, ...] = ()
    group_ids: frozenset[uuid.UUID] = frozenset()
    real_user_id: uuid.UUID | None = None
    impersonation_id: uuid.UUID | None = None
    impersonation_expires_at: int | None = None

    field_policies: tuple[ReadPolicyContext, ...] | None = None
    audit_scope: AuditReadScope | None = None
    user_type: str | None = None
    notification_authority: NotificationAuthority | None = None

    def require_audit_scope(self, company_id: uuid.UUID | None) -> None:
        if self.audit_scope is not None and self.audit_scope.company_id is not None:
            if self.audit_scope.company_id != company_id:
                raise PermissionDeniedError("audit company differs from the authenticated scope")

    @property
    def permissions(self) -> frozenset[str]:
        today = utcnow().date()
        return frozenset(
            permission
            for grant in self.grants
            if grant.is_active and covers(grant.valid_from, grant.valid_to, today)
            for permission in grant.permissions
        )

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionDeniedError(f"this action requires {permission}")

    def require_scope(
        self, permission: str, *, target: ScopePath, on_date: dt.date | None = None
    ) -> None:
        assert_permitted(self.grants, permission, target=target, on_date=on_date or utcnow().date())

    def allows_scope(self, permission: str, *, target: ScopePath) -> bool:
        try:
            self.require_scope(permission, target=target)
        except PermissionDeniedError:
            return False
        return True


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate context key")
        result[key] = value
    return result


def _verified_actor_values(token: str, signature: str, secret: bytes) -> _ActorContext:
    if not 1 <= len(token) <= 32_768 or len(signature) != 64:
        raise ValueError("actor proof bounds")
    body = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("actor proof signature")
    return _ActorContext.model_validate(json.loads(body, object_pairs_hook=_unique_object))


@dataclass(frozen=True, slots=True)
class RetainedActorSubject:
    """Historical signature subject, deliberately without permission methods."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    issued_at: int


def verify_retained_actor_subject(
    token: str, signature: str, secret: bytes
) -> RetainedActorSubject:
    """Verify cancellation evidence only. This can never authorize a new reserve/write."""
    try:
        values = _verified_actor_values(token, signature, secret)
        if (
            values.tenant_id == SCOPE_ALL
            or values.user_id == SCOPE_ALL
            or values.impersonation_id is not None
            or values.actor_user_id is not None
            or values.issued_at > int(time.time()) + 60
        ):
            raise ValueError("invalid retained actor subject")
        return RetainedActorSubject(values.tenant_id, values.user_id, values.issued_at)
    except (ValueError, TypeError, RecursionError, ValidationError, ValidationFailedError) as exc:
        raise AuthenticationRequiredError("invalid retained actor proof") from exc


def decode_actor_context(token: str, signature: str, secret: bytes) -> Actor:
    """Verify before parsing; every malformed/expired context returns the same 401."""
    try:
        values = _verified_actor_values(token, signature, secret)
        if abs(int(time.time()) - values.issued_at) > 60:
            raise ValueError
        if values.tenant_id == SCOPE_ALL or values.user_id == SCOPE_ALL:
            raise ValueError
        support = values.impersonation_id is not None
        if support:
            if (
                values.actor_user_id is None
                or values.actor_user_id in {SCOPE_ALL, values.user_id}
                or values.impersonation_expires_at is None
                or values.impersonation_expires_at <= int(time.time())
            ):
                raise ValueError("invalid support context")
        elif values.actor_user_id is not None or values.impersonation_expires_at is not None:
            raise ValueError("incomplete support context")
        if values.field_policies is not None:
            for policy in values.field_policies:
                Scope(policy.scope_type, policy.scope_id)
                if policy.subject_scope_type is not None:
                    Scope(policy.subject_scope_type, policy.subject_scope_id or SCOPE_ALL)
                elif policy.subject_scope_id is not None:
                    raise ValueError("incomplete policy subject scope")
        grants: list[Grant] = []
        for raw in values.grants:
            if raw.valid_to is not None and raw.valid_to < raw.valid_from:
                raise ValueError
            grants.append(
                Grant(
                    permissions=frozenset(
                        p
                        for p in raw.permissions
                        if not support or (p.endswith(".read") and not p.startswith("platform."))
                    ),
                    scope=Scope(raw.scope_type, raw.scope_id or SCOPE_ALL),
                    valid_from=raw.valid_from,
                    valid_to=raw.valid_to,
                    is_active=raw.is_active,
                )
            )
        return Actor(
            values.tenant_id,
            values.user_id,
            tuple(grants),
            frozenset(values.group_ids),
            values.actor_user_id,
            values.impersonation_id,
            values.impersonation_expires_at,
            tuple(values.field_policies) if values.field_policies is not None else None,
            values.audit_scope,
            values.user_type,
            values.notification_authority,
        )
    except (ValueError, TypeError, RecursionError, ValidationError, ValidationFailedError) as exc:
        raise AuthenticationRequiredError("invalid or expired actor context") from exc
