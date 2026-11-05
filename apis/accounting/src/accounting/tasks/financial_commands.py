"""Local transaction boundary shared by Accounting financial command workflows."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.company_context import FinancialContext
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.models.fiscal import FinancialSetup
from accounting.models.ledger import Journal
from accounting.models.masters import Record
from accounting.resources import Resource
from accounting.tasks.access import authorize, writable
from accounting.tasks.commands import protected, require_metadata, setup_lock


async def mark_first_posted(
    db: AsyncSession, access: Access, setup: FinancialSetup, posted_at: dt.datetime
) -> None:
    """GL and zero-GL physical effects ratchet the same native company settings."""
    if setup.first_posted_at is None:
        from accounting.financial_resources import FINANCIAL_BY_NAME
        from accounting.tasks.commands import audit, values_of

        spec = FINANCIAL_BY_NAME["financial_setup"]
        before = values_of(setup, spec)
        changed = writable(access, spec, before, before | {"first_posted_at": posted_at})
        setup.first_posted_at = posted_at
        setup.row_version += 1
        setup.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, setup, "update", changed)


@dataclass(frozen=True)
class FinancialEffect:
    row: Record
    permission: str | None = None


def require_any(access: Access, permissions: tuple[str, ...]) -> None:
    """Authorize a command that more than one key may grant.

    The only case is a command whose authority was later **narrowed**: a new, smaller key
    is introduced for it, and the broader key that already authorized it keeps working so
    an existing grant does not stop working on deploy. The refusal names the narrow key,
    because that is the one to grant.
    """
    target = ScopePath(company_id=access.context.company_id)
    if any(access.actor.allows_scope(key, target=target) for key in permissions):
        return
    access.actor.require_scope(permissions[0], target=target)


def financial_context(access: Access) -> FinancialContext:
    access.context.assert_current(access.actor, access.context.company_id)
    if access.actor.impersonation_id is not None:
        raise PermissionDeniedError("support sessions are read only")
    facts = access.context.finance
    if facts is None:
        raise ConflictError("authoritative financial company context is required")
    if not facts.company_active:
        raise ConflictError("company is not active")
    return facts


async def financial_command(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    spec: Resource,
    action: str,
    body: BaseModel,
    key: str,
    mutate: Callable[[AsyncSession], Awaitable[FinancialEffect]],
    *,
    #: A tuple means any one of them authorizes the command (see ``require_any``).
    permission: str | tuple[str, ...] | None,
    object_id: uuid.UUID | None = None,
    status: int = 200,
    timeout_seconds: int = 10,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        financial_context(access)
        authorize(access, spec, "read")
        if permission is not None:
            require_any(access, (permission,) if isinstance(permission, str) else permission)
        if receipt is not None and receipt.get("permission") is not None:
            access.actor.require_scope(
                receipt["permission"], target=ScopePath(company_id=access.context.company_id)
            )
        await require_metadata(db, access)
        target = uuid.UUID(receipt["id"]) if receipt is not None else object_id
        if target is not None:
            row = await company_object(db, spec.model, target, company_id=access.context.company_id)
            protected(row, spec, access)
            if isinstance(row, Journal) and isinstance(permission, str):
                original = row
                reversing = action == "reversal" or row.kind == "REVERSAL"
                if row.reversal_of_id is not None:
                    original = await company_object(
                        db, Journal, row.reversal_of_id, company_id=row.company_id
                    )
                extra_permission = (
                    "accounting.finance.manage"
                    if original.kind == "OPENING"
                    else "accounting.charges.approve"
                    if original.kind == "CHARGE" and reversing
                    else "accounting.charges.manage"
                    if original.kind == "CHARGE"
                    else None
                )
                if extra_permission is not None:
                    access.actor.require_scope(
                        extra_permission, target=ScopePath(company_id=row.company_id)
                    )

    async def change(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        if object_id is None:
            # Import/source inputs may live only inside immutable JSON, but still have
            # their own native field policies. Enforce them before producing effects.
            values = {
                name: value
                for name, value in body.model_dump().items()
                if name in spec.create.model_fields
            }
            writable(access, spec, {}, values)
        effect = await mutate(db)
        await db.flush()
        return CommandReceipt(status, {"id": str(effect.row.id), "permission": effect.permission})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, spec.model, uuid.UUID(receipt["id"]), company_id=access.context.company_id
        )
        return protected(row, spec, access)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            access.actor.tenant_id,
            access.context.company_id,
            access.actor.user_id,
            f"accounting.{spec.name}.{action}",
            key,
            {"body": body.model_dump(mode="json"), "id": str(object_id) if object_id else None},
        ),
        authorize=check,
        mutate=change,
        render=render,
        timeout_seconds=timeout_seconds,
    )
