"""Local transaction boundaries, company fences and atomic reference-only audit."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.db.claims import insert_candidate
from billing_platform.errors import ConflictError
from billing_platform.idempotency import CommandIdentity, CommandReceipt, execute_idempotent
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.tasks.access import authorize


def values(current: Access) -> dict[str, Any]:
    return {
        "id": uuid7(),
        "tenant_id": current.actor.tenant_id,
        "company_id": current.context.company_id,
        "created_by": current.actor.user_id,
        "updated_by": current.actor.user_id,
    }


async def company_lock(db: AsyncSession, current: Access) -> m.VoucherCompanyGuard:
    query = (
        select(m.VoucherCompanyGuard)
        .where(m.VoucherCompanyGuard.company_id == current.context.company_id)
        .with_for_update()
    )
    row = await db.scalar(query)
    if row is None:
        await insert_candidate(
            db, m.VoucherCompanyGuard, values(current) | {"generation": 1, "row_version": 1}
        )
        row = await db.scalar(query)
    if row is None:
        raise ConflictError("voucher company guard unavailable")
    row.generation += 1
    return row


def expected(row: m.Record, version: int) -> None:
    if row.row_version != version:
        raise ConflictError("voucher version changed; reload before retrying")


def audit(
    db: AsyncSession,
    current: Access,
    entity: str,
    object_id: uuid.UUID,
    action: str,
    *,
    reason: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    event = f"vouchers.{entity}.{action}"
    category = (
        "access"
        if (
            (entity in {"import_job", "stock_opening_import"} and action == "report_access")
            or (entity in {"print_job", "supporting_file"} and action == "download")
        )
        else "security"
        if entity == "counter_operator"
        else "money"
        if entity in {"voucher", "operation", "counter_session", "counter_cash_event"}
        else "admin"
    )
    emit(
        db,
        aggregate_type="vouchers." + entity,
        aggregate_id=object_id,
        event_type=event,
        tenant_id=current.actor.tenant_id,
        payload=audit_payload(
            action=event,
            category=category,
            entity_type="vouchers." + entity,
            entity_id=object_id,
            actor_user_id=current.actor.user_id,
            company_id=current.context.company_id,
            reason=reason,
            changes=changes,
        )
        | {"actor_type": "user"},
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    action: str,
    key: str,
    body: BaseModel,
    mutation: Callable[[AsyncSession], Awaitable[CommandReceipt]],
    render: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]],
    *,
    object_id: uuid.UUID | None = None,
    path_ids: tuple[uuid.UUID, ...] = (),
) -> Any:
    authorize(current, action)

    async def auth(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        authorize(current, action)

    async def apply(db: AsyncSession) -> CommandReceipt:
        db.info["voucher_actor"] = current.actor.user_id
        await company_lock(db, current)
        if action in {
            "type.manage",
            "configuration.manage",
            "configuration.publish",
            "field.adopt",
        }:
            pending = await db.scalar(
                select(m.VoucherOperation.id)
                .where(
                    m.VoucherOperation.company_id == current.context.company_id,
                    m.VoucherOperation.purpose.in_(["POST", "REVERSE"]),
                    m.VoucherOperation.status == "PENDING",
                )
                .limit(1)
            )
            if pending is not None:
                raise ConflictError(
                    "reconcile pending execution before changing accepted configuration"
                )
        return await mutation(db)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "vouchers." + action,
            key,
            {
                "object_id": str(object_id) if object_id else None,
                "body": body.model_dump(mode="json"),
                **({"path_ids": [str(value) for value in path_ids]} if path_ids else {}),
            },
        ),
        authorize=auth,
        mutate=apply,
        render=render,
    )


async def get[T: Base](
    db: AsyncSession, current: Access, model: type[T], object_id: uuid.UUID, *, lock: bool = False
) -> T:
    return await company_object(
        db, model, object_id, company_id=current.context.company_id, lock=lock
    )
