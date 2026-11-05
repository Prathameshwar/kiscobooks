"""Atomic idempotent commands with current-authority receipt rendering.

The executor owns one local transaction. Domain effects, audit/outbox rows and
the receipt commit together. Store references in receipts, never cached private
response data: render under current object/field authority on every replay.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import Insert

from billing_platform.command_transaction import participating_session
from billing_platform.db.claims import candidate_statement, insert_candidate
from billing_platform.db.platform_models import IdempotencyKey
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, IdempotencyConflictError, ValidationFailedError
from billing_platform.ids import uuid7


def canonical_json(value: Any, *, maximum_bytes: int = 1048576) -> bytes:
    """Canonical wire JSON, with no floats or implicit Decimal/UUID coercion."""

    def validate(node: Any, depth: int = 0) -> None:
        if depth > 32:
            raise ValueError("JSON nesting exceeds limit")
        if node is None or type(node) in (str, int, bool):
            return
        if isinstance(node, dict) and all(isinstance(key, str) for key in node):
            for child in node.values():
                validate(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                validate(child, depth + 1)
        else:
            raise ValueError("use exact JSON types; decimals must be strings")

    validate(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > maximum_bytes:
        raise ValueError("JSON exceeds size limit")
    return encoded


@dataclass(frozen=True, slots=True)
class CommandIdentity:
    tenant_id: uuid.UUID
    company_id: uuid.UUID | None
    actor_id: uuid.UUID
    operation: str
    key: str
    request: Mapping[str, Any]

    def __post_init__(self) -> None:
        if (
            self.tenant_id.int == 0
            or self.actor_id.int == 0
            or (self.company_id is not None and self.company_id.int == 0)
        ):
            raise ValueError(
                "a command requires a tenant and actor; company must be real when supplied"
            )
        if not re.fullmatch(r"[a-z][a-z0-9_.:/-]{0,199}", self.operation):
            raise ValueError("invalid registered operation")
        if not re.fullmatch(r"[\x21-\x7e]{1,255}", self.key):
            raise ValidationFailedError("invalid idempotency key")
        canonical_json(dict(self.request))

    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "tenant": str(self.tenant_id),
                    "company": str(self.company_id) if self.company_id is not None else None,
                    "actor": str(self.actor_id),
                    "operation": self.operation,
                    "request": dict(self.request),
                }
            )
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    status: int
    references: dict[str, Any]

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 200 <= self.status < 300:
            raise ValueError("only successful command receipts may be retained")
        canonical_json(self.references, maximum_bytes=16384)


@dataclass(frozen=True, slots=True)
class CommandResult[T]:
    status: int
    value: T
    replayed: bool


type Authorize = Callable[[AsyncSession, dict[str, Any] | None], Awaitable[None]]
type Mutate = Callable[[AsyncSession], Awaitable[CommandReceipt]]


async def has_retained_command(
    factory: async_sessionmaker[AsyncSession], identity: CommandIdentity
) -> bool:
    """Presence hint for skipping external preparation, never replay/authority proof.

    Call execute_idempotent afterwards with the full identity and current
    authorization to check digest, expiry, state and object policies. Concurrent
    first requests may still need preparation; keep remote calls outside the
    executor's transaction.
    """
    with tenant_scope(identity.tenant_id):
        async with factory() as db:
            return (
                await db.scalar(
                    select(IdempotencyKey.id)
                    .where(
                        IdempotencyKey.endpoint == identity.operation,
                        IdempotencyKey.key_value
                        == hashlib.sha256(identity.key.encode()).hexdigest(),
                    )
                    .limit(1)
                )
                is not None
            )


async def execute_idempotent[T](
    factory: async_sessionmaker[AsyncSession],
    identity: CommandIdentity,
    *,
    authorize: Authorize,
    mutate: Mutate,
    render: Callable[[AsyncSession, dict[str, Any]], Awaitable[T]],
    retention: dt.timedelta = dt.timedelta(hours=24),
    timeout_seconds: int = 10,
) -> CommandResult[T]:
    """Execute once, or render the retained receipt after fresh authorization.

    Callbacks may perform only local database work. Authorization is mandatory
    before lookup and again for the receipt's objects. A timeout rolls back the
    entire transaction. Expired retained keys are refused, never silently reused.
    The caller must include resource IDs and conditional headers in request.
    """
    if not dt.timedelta(minutes=1) <= retention <= dt.timedelta(days=30):
        raise ValueError("retention must be between one minute and thirty days")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError("invalid command timeout")
    request_hash = identity.digest()

    async def execute(db: AsyncSession) -> CommandResult[T]:
        await authorize(db, None)
        row, created = await _claim(db, identity, request_hash, retention)
        if row.request_hash != request_hash:
            raise IdempotencyConflictError("idempotency key belongs to another request")
        if row.expires_at <= utcnow():
            raise ConflictError("idempotency key has expired; reconcile before retrying")
        if created:
            receipt = await mutate(db)
            row.state = "completed"
            row.response_status = receipt.status
            row.response_body = receipt.references
            row.completed_at = utcnow()
            await db.flush()
        elif row.state != "completed":
            raise ConflictError("request is already in progress; retry later")
        if row.response_body is None or row.response_status is None:
            raise ConflictError("command receipt is unavailable")
        await authorize(db, row.response_body)
        value = await render(db, row.response_body)
        return CommandResult(row.response_status, value, replayed=not created)

    try:
        async with asyncio.timeout(timeout_seconds):
            participant = participating_session(
                factory, identity.tenant_id, identity.company_id, identity.actor_id
            )
            if participant is not None:
                async with participant.begin_nested():
                    return await execute(participant)
            with tenant_scope(identity.tenant_id):
                async with factory() as db, db.begin():
                    return await execute(db)
    except TimeoutError as exc:
        raise ConflictError("request is busy; retry with the same idempotency key") from exc
    except OperationalError as exc:
        # MySQL deadlock, lock timeout and NOWAIT; SQLite contention in tests.
        code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
        if code in (1205, 1213, 3572) or code == "database is locked":
            raise ConflictError("request is busy; retry with the same idempotency key") from exc
        raise


async def _claim(
    db: AsyncSession,
    identity: CommandIdentity,
    request_hash: str,
    retention: dt.timedelta,
) -> tuple[IdempotencyKey, bool]:
    candidate_id, now = uuid7(), utcnow()
    # Hash the opaque key: MySQL's case-insensitive service collation must not
    # collapse distinct client tokens, and raw client tokens need not be stored.
    stored_key = hashlib.sha256(identity.key.encode()).hexdigest()
    values = {
        "id": candidate_id,
        "tenant_id": identity.tenant_id,
        "endpoint": identity.operation,
        "key_value": stored_key,
        "request_hash": request_hash,
        "state": "in_progress",
        "locked_at": now,
        "expires_at": now + retention,
        "attempt_count": 1,
    }
    await insert_candidate(db, IdempotencyKey, values)
    row = await db.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.endpoint == identity.operation,
            IdempotencyKey.key_value == stored_key,
        )
        .with_for_update()
    )
    if row is None:
        raise ConflictError("command claim is unavailable")
    return row, row.id == candidate_id


def claim_statement(dialect: str, values: Mapping[str, Any]) -> Insert:
    """Compile the unique-key claim without modifying an existing receipt."""
    return candidate_statement(dialect, IdempotencyKey, values)
