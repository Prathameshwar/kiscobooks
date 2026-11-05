"""Mapping draft review/publication; publication always revalidates live references."""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.models.workflows import MappingDraft
from accounting.resources import BY_NAME
from accounting.schemas.masters import AccountPostingMappingCreate
from accounting.schemas.workflows import MappingDraftDetail
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.commands import audit, mutate_master, require_metadata, setup_lock
from accounting.tasks.validation import validate

SPEC = BY_NAME["account_posting_mapping"]


def detail(row: MappingDraft, access: Access) -> MappingDraftDetail:
    authorize(access, SPEC, "read")
    allowed = readable(access, SPEC, row.values)
    return MappingDraftDetail(
        id=row.id,
        row_version=row.row_version,
        values={key: value for key, value in row.values.items() if key in allowed},
        published_mapping_id=row.published_mapping_id,
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    action: str,
    body: BaseModel,
    key: str,
    settings: Settings,
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        authorize(access, SPEC, "manage")
        authorize(access, SPEC, "read")
        await require_metadata(db, access)
        if action == "publish":
            access.actor.require_scope(
                "accounting.mapping.publish", target=ScopePath(company_id=access.context.company_id)
            )
        if object_id is not None:
            await company_object(db, MappingDraft, object_id, company_id=access.context.company_id)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        data = body.model_dump(mode="json")
        if object_id is None:
            values = AccountPostingMappingCreate.model_validate(data["values"]).model_dump(
                mode="json"
            )
            changed = writable(access, SPEC, {}, values)
            row = MappingDraft(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                values=values,
                row_version=1,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
            )
            db.add(row)
        else:
            row = await company_object(
                db, MappingDraft, object_id, company_id=access.context.company_id, lock=True
            )
            if row.row_version != data["expected_version"]:
                raise ConflictError("mapping draft version changed")
            if row.published_mapping_id is not None:
                raise ConflictError("published drafts are immutable")
            changed = set()
            if action == "update":
                values = AccountPostingMappingCreate.model_validate(data["values"]).model_dump(
                    mode="json"
                )
                changed = writable(access, SPEC, row.values, values)
                row.values = values
            if action == "publish":
                mapping = await mutate_master(
                    db,
                    access,
                    SPEC,
                    "create",
                    AccountPostingMappingCreate.model_validate(row.values),
                    settings,
                )
                row.published_mapping_id = mapping.id
                changed.add("published_mapping_id")
            row.row_version += 1
            row.updated_by = access.actor.user_id
        await db.flush()
        # Audit uses the mapping namespace; draft identity remains distinct from posted mapping.
        audit(db, access, SPEC, row, "draft_" + action, changed)
        return CommandReceipt(201 if action == "create" else 200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, MappingDraft, uuid.UUID(receipt["id"]), company_id=access.context.company_id
        )
        return detail(row, access)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            actor_id=access.actor.user_id,
            operation="accounting.mapping_draft." + action,
            key=key,
            request={
                "id": str(object_id) if object_id else None,
                "body": body.model_dump(mode="json"),
            },
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )


async def validate_draft(
    db: AsyncSession, access: Access, object_id: uuid.UUID
) -> MappingDraftDetail:
    authorize(access, SPEC, "read")
    row = await company_object(db, MappingDraft, object_id, company_id=access.context.company_id)
    if not set(row.values) <= readable(access, SPEC, row.values):
        raise PermissionDeniedError("mapping validation requires readable values")
    await validate(
        db, access, SPEC, AccountPostingMappingCreate.model_validate(row.values).model_dump()
    )
    return detail(row, access)
