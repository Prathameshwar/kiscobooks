"""Restartable opening draft import; each effect and checkpoint commit together."""

import asyncio
import datetime as dt
import hashlib
import uuid
from typing import Any, Literal

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, PlatformError
from billing_platform.idempotency import CommandReceipt, canonical_json
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.api.auth import Access
from vouchers.domain.stock_opening_import import decode
from vouchers.models.core import Voucher
from vouchers.models.stock_opening_import import StockOpeningImport, StockOpeningImportClaim
from vouchers.schemas.stock_opening_import import (
    OpeningImportCommit,
    OpeningImportDetail,
    OpeningImportDocument,
    OpeningImportStage,
    OpeningImportVersion,
)
from vouchers.tasks import documents
from vouchers.tasks.access import authorize, denied, fingerprint
from vouchers.tasks.common import audit, command, expected, get, values
from vouchers.tasks.imports import definition_digest
from vouchers.tasks.stock_details import restricted

STEP = 2


def require(current: Access, action: str) -> None:
    for key in {"import.read", "read", action}:
        authorize(current, key)


def visible_source(current: Access, document: OpeningImportDocument) -> None:
    for native in document.vouchers:
        content = native.model_dump(mode="json")
        if restricted(current, content) or denied(
            current, "vouchers.voucher", set(content), "read", content
        ):
            raise PermissionDeniedError("opening import source fields are not readable")


async def detail(db: AsyncSession, current: Access, row: StockOpeningImport) -> dict[str, Any]:
    require(current, "import.read")
    document = OpeningImportDocument.model_validate(row.payload)
    visible_source(current, document)
    effects = []
    for effect in row.effects:
        voucher = await documents.detail(db, current, uuid.UUID(effect["voucher_id"]))
        effects.append(effect | {"voucher_status": voucher["status"]})
    return OpeningImportDetail(
        id=row.id,
        company_id=row.company_id,
        row_version=row.row_version,
        source_key=row.source_key,
        state=row.state,
        input_hash=row.input_hash,
        review_hash=row.review_hash,
        chunk_count=len(document.vouchers),
        validated_chunks=len(row.review),
        created_chunks=len(effects),
        effects=effects,
        errors=row.errors,
        posting_required=len(effects) != len(document.vouchers)
        or any(effect["voucher_status"] != "POSTED" for effect in effects),
    ).model_dump(mode="json")


async def stage(
    factory: async_sessionmaker[AsyncSession], current: Access, body: OpeningImportStage, key: str
) -> Any:
    require(current, "import.manage")
    authorize(current, "create")
    document = await asyncio.to_thread(decode, body)
    visible_source(current, document)
    payload = document.model_dump(mode="json")
    digest = hashlib.sha256(canonical_json(payload, maximum_bytes=2_097_152)).hexdigest()

    async def mutate(db: AsyncSession) -> CommandReceipt:
        authorize(current, "create")
        old = await db.scalar(
            select(StockOpeningImport)
            .where(
                StockOpeningImport.company_id == current.context.company_id,
                or_(
                    StockOpeningImport.source_key == body.source_key,
                    StockOpeningImport.input_hash == digest,
                ),
            )
            .with_for_update()
        )
        if old is not None:
            if old.input_hash != digest:
                raise ConflictError(
                    "opening import source key already identifies different content"
                )
            return CommandReceipt(200, {"id": str(old.id)})
        row = StockOpeningImport(
            **values(current),
            source_key=body.source_key,
            input_hash=digest,
            payload=payload,
            state="STAGED",
            review=[],
            effects=[],
            errors=[],
            expires_at=utcnow() + dt.timedelta(days=7),
        )
        db.add(row)
        await db.flush()
        audit(db, current, "stock_opening_import", row.id, "stage")
        return CommandReceipt(201, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await detail(
            db, current, await get(db, current, StockOpeningImport, uuid.UUID(refs["id"]))
        )

    return await command(factory, current, "import.manage", key, body, mutate, render)


async def advance(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    identity: uuid.UUID,
    action: Literal["validate", "commit", "cancel"],
    body: OpeningImportVersion | OpeningImportCommit,
    key: str,
) -> Any:
    permission = "import.commit" if action == "commit" else "import.manage"
    require(current, permission)
    if action != "cancel":
        authorize(current, "create")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        require(current, permission)
        if action != "cancel":
            authorize(current, "create")
        row = await get(db, current, StockOpeningImport, identity, lock=True)
        expected(row, body.expected_version)
        document = OpeningImportDocument.model_validate(row.payload)
        visible_source(current, document)
        if row.expires_at <= utcnow() or row.state == "CANCELLED":
            raise ConflictError(
                "opening import expired or cancelled; retained effects remain available"
            )
        if action == "cancel":
            if row.state == "DRAFTS_CREATED":
                raise ConflictError(
                    "draft creation finished; use each voucher's normal cancellation workflow"
                )
            row.state = "CANCELLED"
        else:
            authority = hashlib.sha256(
                (fingerprint(current) + await definition_digest(db, current)).encode()
            ).hexdigest()
            if action == "validate":
                if row.state == "DRAFTS_CREATED":
                    raise ConflictError("all drafts are already created")
                if (
                    row.state in {"STAGED", "BLOCKED", "READY"}
                    or row.reviewed_authority != authority
                ):
                    row.review = row.review[: len(row.effects)]
                    row.errors = []
                    row.state = "VALIDATING"
                    row.reviewed_authority = authority
                    row.review_hash = None
                start = len(row.review)
            else:
                if (
                    not isinstance(body, OpeningImportCommit)
                    or row.state not in {"READY", "COMMITTING"}
                    or body.review_hash != row.review_hash
                    or row.reviewed_authority != authority
                ):
                    raise ConflictError(
                        "opening import review changed; validate remaining chunks again"
                    )
                row.state = "COMMITTING"
                start = len(row.effects)
            for index in range(start, min(start + STEP, len(document.vouchers))):
                native = document.vouchers[index]
                saved_info = db.info.get("voucher_revisions_created_in_transaction", set()).copy()
                nested = await db.begin_nested()
                rolled_back = False
                try:
                    db.info["voucher_actor"] = current.actor.user_id
                    assert native.stock is not None
                    source_keys = [
                        line.opening.source_key for line in native.stock.lines if line.opening
                    ]
                    if action == "commit" and await db.scalar(
                        select(StockOpeningImportClaim.id)
                        .join(Voucher, Voucher.id == StockOpeningImportClaim.voucher_id)
                        .where(
                            StockOpeningImportClaim.company_id == current.context.company_id,
                            Voucher.company_id == current.context.company_id,
                            Voucher.status.not_in(("CANCELLED", "REVERSED")),
                            StockOpeningImportClaim.control_id == native.stock.opening_control_id,
                            StockOpeningImportClaim.source_key.in_(source_keys),
                        )
                        .limit(1)
                    ):
                        raise ConflictError(
                            "opening cohort already has an imported draft; resume its original job"
                        )
                    voucher = await documents.write(db, current, native)
                    revision = await documents.revision_for(db, current, voucher)
                    if (
                        revision.configuration_evidence["kind"],
                        revision.configuration_evidence["profile"],
                    ) != ("STOCK_JOURNAL", "OPENING"):
                        raise ConflictError(
                            "import requires the native Stock Journal Opening profile"
                        )
                    review = {"configuration_hash": revision.configuration_hash}
                    effect = {
                        "chunk": index + 1,
                        "voucher_id": str(voucher.id),
                        "revision_id": str(revision.id),
                    }
                    if action == "commit":
                        if review != row.review[index]:
                            raise ConflictError(
                                "voucher configuration changed since opening import review"
                            )
                        for source_key in source_keys:
                            db.add(
                                StockOpeningImportClaim(
                                    **values(current),
                                    control_id=native.stock.opening_control_id,
                                    source_key=source_key,
                                    job_id=row.id,
                                    voucher_id=voucher.id,
                                )
                            )
                        await nested.commit()
                        row.effects = [*row.effects, effect]
                    else:
                        await nested.rollback()
                        rolled_back = True
                        row.review = [*row.review, review]
                except PlatformError as error:
                    if nested.is_active:
                        await nested.rollback()
                    rolled_back = True
                    row.errors = [
                        {"chunk": index + 1, "code": error.code, "message": error.message}
                    ]
                    row.state = "BLOCKED"
                    break
                finally:
                    if action == "validate" or rolled_back:
                        db.info["voucher_revisions_created_in_transaction"] = saved_info
            if row.state != "BLOCKED":
                if action == "validate" and len(row.review) == len(document.vouchers):
                    row.state = "READY"
                    row.review_hash = hashlib.sha256(
                        canonical_json(
                            {"input": row.input_hash, "authority": authority, "chunks": row.review}
                        )
                    ).hexdigest()
                elif action == "commit" and len(row.effects) == len(document.vouchers):
                    row.state = "DRAFTS_CREATED"
        row.row_version += 1
        row.updated_by = current.actor.user_id
        audit(db, current, "stock_opening_import", row.id, action)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return await detail(db, current, await get(db, current, StockOpeningImport, identity))

    return await command(
        factory, current, permission, key, body, mutate, render, object_id=identity
    )
