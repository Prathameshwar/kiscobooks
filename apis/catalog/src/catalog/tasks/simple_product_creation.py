"""Durable single-Save coordinator; every business mutation uses its native owner."""

import datetime as dt
import hashlib
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.products import Item
from catalog.models.simple_product_creation import SimpleProductCreation as Creation
from catalog.schemas.simple_product_creation import SimpleCreationInput, SimpleCreationStatus
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.simple_creation_preparation import authority, prepare
from catalog.tasks.simple_creation_steps import (
    OpeningPostingRejectedError,
    after_command,
    batch_preflight,
    next_command,
    opening_preflight,
    serial_entries,
    serial_preflight,
)
from catalog.tasks.simple_creation_transport import CreationOwners, OwnerRejectedError

Factory = async_sessionmaker[AsyncSession]


def creation_request(body: SimpleCreationInput) -> dict[str, Any]:
    # Preserve hashes of commands admitted before these optional inputs existed.
    excluded = {"barcode"} if body.barcode is None else set()
    if not body.sale_prices:
        excluded.add("sale_prices")
    if not body.categories:
        excluded.add("categories")
    if not body.batches:
        excluded.add("batches")
    if not body.serials:
        excluded.add("serials")
    for field in ("manufacturer_id", "manufacturer_site_id", "batch_enabled"):
        if getattr(body, field) is None:
            excluded.add(field)
    result = body.model_dump(mode="json", exclude=excluded)
    for batch in result.get("batches", []):
        if not batch["serials"]:
            batch.pop("serials")
    return result


def status(row: Creation) -> SimpleCreationStatus:
    return SimpleCreationStatus.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "status": row.status,
            "step": row.step,
            "code": row.code,
            "item_id": row.item_id,
            "row_version": row.row_version,
            "opening_posted": bool(row.progress.get("opening_posted")),
            "can_edit": row.step == "CREATE"
            and row.item_id is None
            and not row.progress.get("pending")
            and (row.lease_expires_at is None or row.lease_expires_at <= utcnow()),
        }
    )


def audit(db: AsyncSession, row: Creation, actor: Actor, action: str) -> None:
    entity = "catalog.simple_product_creation"
    event = entity + "." + action
    emit(
        db,
        tenant_id=row.tenant_id,
        aggregate_type=entity,
        aggregate_id=row.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="admin",
            entity_type=entity,
            entity_id=row.id,
            actor_user_id=actor.user_id,
            company_id=row.company_id,
        ),
    )


async def require_code_read(db: AsyncSession, actor: Actor, company: uuid.UUID) -> None:
    fields = await ConfigurationAccess(db, actor, company).context(Item)
    if "sku" not in fields.readable():
        raise PermissionDeniedError("Product code is protected")


async def owned(
    db: AsyncSession, actor: Actor, company: uuid.UUID, identity: uuid.UUID, *, lock: bool = False
) -> Creation:
    actor.require_scope("item.read", target=ScopePath(company_id=company))
    row = await company_object(db, Creation, identity, company_id=company, lock=lock)
    if row.created_by != actor.user_id:
        raise PermissionDeniedError("Only the user who started this creation can resume it")
    await require_code_read(db, actor, company)
    return row


async def read(
    factory: Factory, actor: Actor, company: uuid.UUID, identity: uuid.UUID
) -> SimpleCreationStatus:
    with tenant_scope(actor.tenant_id):
        async with factory() as db:
            return status(await owned(db, actor, company, identity))


async def enqueue(
    db: AsyncSession,
    actor: Actor,
    context: CompanyContext,
    body: SimpleCreationInput,
    key: str,
    opening: dict[str, Any],
) -> SimpleCreationStatus:
    """Reserve a durable command in the caller transaction; never contact an owner."""
    context.assert_current(actor, context.company_id)
    authority(actor, context.company_id, body)
    await require_code_read(db, actor, context.company_id)
    digest = hashlib.sha256(canonical_json(creation_request(body))).hexdigest()
    await company_policy_state(db, actor.tenant_id, context.company_id, lock=True)
    previous = await db.scalar(
        select(Creation).where(
            Creation.company_id == context.company_id, Creation.command_key == key
        )
    )
    if previous:
        previous = await owned(db, actor, context.company_id, previous.id)
        if previous.request_hash != digest:
            raise ConflictError("This Save key was already used for different product values")
        return status(previous)
    code = body.code or uuid.uuid4().hex[:10].upper()
    for _ in range(10):
        used = await db.scalar(
            select(Item.id).where(Item.company_id == context.company_id, Item.sku == code).limit(1)
        )
        reserved = await db.scalar(
            select(Creation.id)
            .where(Creation.company_id == context.company_id, Creation.code == code)
            .limit(1)
        )
        if not used and not reserved:
            break
        if body.code:
            raise ConflictError("Product code is already in use")
        code = uuid.uuid4().hex[:10].upper()
    else:
        raise ConflictError("A product code could not be reserved; retry Save")
    native, progress = await prepare(db, actor, context, body, code)
    row = Creation(
        id=uuid7(),
        tenant_id=actor.tenant_id,
        company_id=context.company_id,
        created_by=actor.user_id,
        updated_by=actor.user_id,
        command_key=key,
        request_hash=digest,
        code=code,
        request=creation_request(body),
        progress=progress | opening | {"create": native.model_dump(mode="json", exclude_none=True)},
        status="RUNNING",
        step="CREATE",
        row_version=1,
    )
    db.add(row)
    await db.flush()
    audit(db, row, actor, "create")
    return status(row)


async def start(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    body: SimpleCreationInput,
    key: str,
    owners: CreationOwners,
) -> SimpleCreationStatus:
    context.assert_current(actor, context.company_id)
    authority(actor, context.company_id, body)
    digest = hashlib.sha256(canonical_json(creation_request(body))).hexdigest()
    with tenant_scope(actor.tenant_id):
        async with factory() as db:
            await require_code_read(db, actor, context.company_id)
            previous = await db.scalar(
                select(Creation).where(
                    Creation.company_id == context.company_id, Creation.command_key == key
                )
            )
            if previous:
                previous = await owned(db, actor, context.company_id, previous.id)
                if previous.request_hash != digest:
                    raise ConflictError(
                        "This Save key was already used for different product values"
                    )
                return status(previous)
        opening: dict[str, Any] = {}
        await batch_preflight(owners, context.company_id, body)
        await serial_preflight(owners, context.company_id, body)
        if body.has_opening:
            if context.finance is None:
                raise ConflictError("Company financial setup is unavailable")
            opening = await opening_preflight(
                owners, context.company_id, context.finance.books_begin_date.isoformat()
            )
        async with factory() as db, db.begin():
            return await enqueue(db, actor, context, body, key, opening)


async def revise(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    identity: uuid.UUID,
    body: SimpleCreationInput,
    expected_version: int,
    key: str,
    owners: CreationOwners,
) -> SimpleCreationStatus:
    """Correct definitively rejected input only before any native product exists."""
    context.assert_current(actor, context.company_id)
    authority(actor, context.company_id, body)
    revision_hash = hashlib.sha256(
        canonical_json(
            {
                "expected_version": expected_version,
                "product": creation_request(body),
            }
        )
    ).hexdigest()

    def replay(row: Creation) -> bool:
        if row.progress.get("revision_key") != key:
            return False
        if row.progress.get("revision_hash") != revision_hash:
            raise ConflictError("This correction key was already used for different values")
        return True

    with tenant_scope(actor.tenant_id):
        async with factory() as db:
            current = await owned(db, actor, context.company_id, identity)
            if replay(current):
                return status(current)
            if not status(current).can_edit or current.row_version != expected_version:
                raise ConflictError("Product creation has progressed; retry its saved values")
        opening: dict[str, Any] = {}
        await batch_preflight(owners, context.company_id, body)
        await serial_preflight(owners, context.company_id, body)
        if body.has_opening:
            if context.finance is None:
                raise ConflictError("Company financial setup is unavailable")
            opening = await opening_preflight(
                owners, context.company_id, context.finance.books_begin_date.isoformat()
            )
        async with factory() as db, db.begin():
            await company_policy_state(db, actor.tenant_id, context.company_id, lock=True)
            row = await owned(db, actor, context.company_id, identity, lock=True)
            if replay(row):
                return status(row)
            if not status(row).can_edit or row.row_version != expected_version:
                raise ConflictError("Product creation has progressed; retry its saved values")
            code = body.code or row.code
            if code != row.code:
                used = await db.scalar(
                    select(Item.id)
                    .where(
                        Item.company_id == context.company_id,
                        Item.sku == code,
                    )
                    .limit(1)
                )
                reserved = await db.scalar(
                    select(Creation.id)
                    .where(
                        Creation.company_id == context.company_id,
                        Creation.code == code,
                        Creation.id != identity,
                    )
                    .limit(1)
                )
                if used or reserved:
                    raise ConflictError("Product code is already in use")
            native, progress = await prepare(db, actor, context, body, code)
            row.code = code
            row.request = creation_request(body)
            row.request_hash = hashlib.sha256(canonical_json(row.request)).hexdigest()
            row.progress = (
                progress
                | opening
                | {
                    "create": native.model_dump(mode="json", exclude_none=True),
                    "attempt": row.progress.get("attempt", 0) + 1,
                    "revision_key": key,
                    "revision_hash": revision_hash,
                }
            )
            row.row_version += 1
            row.updated_by = actor.user_id
            audit(db, row, actor, "revise")
            return status(row)


async def advance(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    identity: uuid.UUID,
    owners: CreationOwners,
) -> SimpleCreationStatus:
    company = context.company_id
    context.assert_current(actor, company)
    token = uuid7()
    with tenant_scope(actor.tenant_id):
        async with factory() as db, db.begin():
            row = await owned(db, actor, company, identity, lock=True)
            body = SimpleCreationInput.model_validate(row.request)
            authority(actor, company, body)
            if row.status == "COMPLETE" or (
                row.lease_expires_at and row.lease_expires_at > utcnow()
            ):
                return status(row)
            row.lease_token, row.lease_expires_at = token, utcnow() + dt.timedelta(seconds=90)
            progress, step, item_id = dict(row.progress), row.step, row.item_id
        try:
            pending = progress.get("pending")
            if pending is None:
                if step == "CREATE":
                    async with factory() as db:
                        native, refreshed = await prepare(
                            db, actor, context, body, progress["create"]["code"]
                        )
                        progress["create"] = native.model_dump(mode="json", exclude_none=True)
                        progress.update(refreshed)
                pending = await next_command(
                    owners, company, identity, step, body, progress, item_id
                )
                if pending is not None:
                    key_parts: tuple[Any, ...] = (
                        identity,
                        step,
                        progress.get("published", 0),
                        progress.get("attempt", 0),
                    )
                    if step in {"BATCH", "BATCH_PRICES"}:
                        key_parts += (progress.get("batch_index", 0),)
                    if step == "SERIAL":
                        key_parts += (progress.get("serial_index", 0),)
                    pending["key"] = hashlib.sha256(
                        ":".join(map(str, key_parts)).encode()
                    ).hexdigest()
                    async with factory() as db, db.begin():
                        row = await owned(db, actor, company, identity, lock=True)
                        if row.lease_token != token:
                            return status(row)
                        progress["pending"] = pending
                        row.progress = dict(progress)
            result = (
                await owners.call(
                    pending["service"], "POST", pending["path"], pending["body"], pending["key"]
                )
                if pending
                else None
            )
            async with factory() as db, db.begin():
                row = await owned(db, actor, company, identity, lock=True)
                if row.lease_token != token:
                    return status(row)
                if pending and result is not None:
                    next_step, new_item = after_command(step, body, progress, pending, result)
                    row.step, row.item_id = next_step, new_item or item_id
                    progress.pop("pending", None)
                elif step == "PUBLISH":
                    row.step = "ACTIVATE"
                row.progress, row.lease_token, row.lease_expires_at = progress, None, None
                row.row_version += 1
                if row.step == "COMPLETE":
                    row.status = "COMPLETE"
                    audit(db, row, actor, "complete")
                return status(row)
        except Exception as error:
            if isinstance(error, OwnerRejectedError) and step == "SERIAL":
                batch_index, index, _ = serial_entries(body)[progress.get("serial_index", 0)]
                prefix = (
                    "" if batch_index is None else f"batches.{batch_index}."
                ) + f"serials.{index}."
                error.extra["fields"] = {
                    prefix + key: message
                    for key, message in (
                        error.extra.get("fields") or {"identifiers": error.message}
                    ).items()
                }
            if isinstance(error, OwnerRejectedError) and step in {"BATCH", "BATCH_PRICES"}:
                prefix = "batches." + str(progress.get("batch_index", 0)) + "."
                error.extra["fields"] = {
                    prefix + key: value
                    for key, value in (error.extra.get("fields") or {"code": error.message}).items()
                }
            async with factory() as db, db.begin():
                row = await owned(db, actor, company, identity, lock=True)
                if row.lease_token == token:
                    posting_rejected = isinstance(error, OpeningPostingRejectedError)
                    if posting_rejected or (
                        isinstance(error, OwnerRejectedError) and error.definite
                    ):
                        progress = dict(row.progress)
                        progress.pop("pending", None)
                        if posting_rejected:
                            # Only a terminal owner receipt permits a fresh posting attempt.
                            # Keep the same voucher and opening control; uncertain work waits.
                            row.step = "POST"
                            progress.pop("operation_id", None)
                        progress["attempt"] = progress.get("attempt", 0) + 1
                        row.progress = progress
                        row.row_version += 1
                    row.lease_token, row.lease_expires_at = None, None
            raise
