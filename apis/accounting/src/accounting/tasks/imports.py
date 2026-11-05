"""Bounded transactional imports. Preview rolls back and apply revalidates everything."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.pagination import CursorCodec
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.models.masters import Record
from accounting.resources import BY_PATH
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.workflows import (
    ImportApply,
    ImportIssue,
    ImportPreview,
    ImportRequest,
    ImportResult,
)
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.commands import mutate_master, require_metadata, setup_lock
from accounting.tasks.party_ledger import activate_role_with_ledger


def codec(access: Access, settings: Settings) -> CursorCodec:
    return CursorCodec(
        settings.actor_signing_secret.get_secret_value().encode(),
        context=f"accounting.import:{access.actor.tenant_id}:{access.context.company_id}:{authority_fingerprint(access)}",
    )


def digest(body: ImportRequest) -> str:
    return hashlib.sha256(
        canonical_json({"items": [row.model_dump(mode="json") for row in body.items]})
    ).hexdigest()


def check(access: Access, body: ImportRequest) -> None:
    access.context.assert_current(access.actor, access.context.company_id)
    access.actor.require_scope(
        "accounting.import.manage", target=ScopePath(company_id=access.context.company_id)
    )
    if len({item.key for item in body.items}) != len(body.items):
        raise ValidationFailedError("import keys must be unique")
    for item in body.items:
        spec = BY_PATH.get(item.resource)
        if spec is None:
            raise ValidationFailedError("unknown import resource")
        authorize(access, spec, "manage")
        authorize(access, spec, "read")
        readable(access, spec)


def resolve(value: Any, records: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        if value[1:] not in records:
            raise ValidationFailedError("import reference must name a preceding record")
        return records[value[1:]]
    return value


async def rows(
    db: AsyncSession, access: Access, body: ImportRequest, settings: Settings, *, collect: bool
) -> tuple[dict[str, str], list[ImportIssue]]:
    records: dict[str, str] = {}
    issues = []
    for item in body.items:
        try:
            async with db.begin_nested():
                spec = BY_PATH[item.resource]
                values = dict(item.values)
                for key in spec.references:
                    if key in values:
                        values[key] = resolve(values[key], records)
                identifier = uuid.UUID(resolve(item.object_id, records)) if item.object_id else None
                schema = (
                    spec.create
                    if item.action == "create"
                    else spec.update
                    if item.action == "update"
                    else ExpectedVersion
                )
                parsed = schema.model_validate(values)
                if spec.name == "party" and item.action == "create":
                    # A party only ever arrives with its role and ledger account.
                    raise ConflictError(
                        "create parties with create-with-details or the ready customer/supplier "
                        "import: a party always arrives with its role and ledger account"
                    )
                row: Record
                if spec.name == "party_role" and item.action == "activate" and identifier:
                    # A role never goes live without its ledger account.
                    row = await activate_role_with_ledger(
                        db,
                        access,
                        settings,
                        role_id=identifier,
                        expected_version=ExpectedVersion.model_validate(values).expected_version,
                    )
                else:
                    row = await mutate_master(
                        db, access, spec, item.action, parsed, settings, identifier
                    )
                await db.flush()
                records[item.key] = str(row.id)
        except (PlatformError, ValidationError, ValueError, IntegrityError) as exc:
            if not collect:
                if isinstance(exc, PlatformError):
                    raise
                raise ValidationFailedError(
                    "import failed validation; no rows were applied"
                ) from exc
            issues.append(
                ImportIssue(
                    key=item.key,
                    code="conflict"
                    if isinstance(exc, ConflictError | IntegrityError)
                    else "invalid_record",
                )
            )
    return records, issues


async def preview(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: ImportRequest,
    settings: Settings,
) -> ImportPreview:
    check(access, body)
    with tenant_scope(access.actor.tenant_id):
        async with factory() as db:
            await db.begin()
            try:
                state = await setup_lock(db, access)
                generation = state.generation - 1
                _, issues = await rows(db, access, body, settings, collect=True)
                token = (
                    None
                    if issues
                    else codec(access, settings).encode(
                        {"generation": generation, "digest": digest(body)}
                    )
                )
                return ImportPreview(valid=not issues, issues=issues, preview_token=token)
            finally:
                await db.rollback()


async def apply(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: ImportApply,
    settings: Settings,
    key: str,
) -> CommandResult[BaseModel]:
    async def authorize_command(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        check(access, body)
        await require_metadata(db, access)
        token = codec(access, settings).decode(body.preview_token)
        if token.get("digest") != digest(body):
            raise ConflictError("import differs from its preview")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        state = await setup_lock(db, access)
        token = codec(access, settings).decode(body.preview_token)
        if token.get("generation") != state.generation - 1:
            raise ConflictError("masters changed after preview; preview again")
        records, _ = await rows(db, access, body, settings, collect=False)
        # Request keys can be fifty characters each. Store only ordered identifiers so a
        # valid 200-row batch remains below the shared receipt size limit.
        return CommandReceipt(200, {"ids": [records[item.key] for item in body.items]})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        if "records" in receipt:  # Receipts committed before compact storage remain replayable.
            return ImportResult.model_validate(receipt)
        return ImportResult(
            records={
                item.key: identifier
                for item, identifier in zip(body.items, receipt["ids"], strict=True)
            }
        )

    return await execute_idempotent(
        factory,
        CommandIdentity(
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            actor_id=access.actor.user_id,
            operation="accounting.import.apply",
            key=key,
            request=body.model_dump(mode="json"),
        ),
        authorize=authorize_command,
        mutate=mutate,
        render=render,
        timeout_seconds=30,
    )
