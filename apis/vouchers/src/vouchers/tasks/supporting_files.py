"""Live document authority and registered evidence, independent of byte transport."""

import uuid
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.models.supporting_files import PurchaseSupportingFile
from vouchers.schemas.documents import AttachmentInput
from vouchers.tasks.access import authorize, denied, writable
from vouchers.tasks.common import get
from vouchers.tasks.documents import content, guard_execution, revision_for


async def authority(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    *,
    editing: bool = False,
    revision_id: uuid.UUID | None = None,
) -> tuple[m.Voucher, m.VoucherRevision, dict[str, Any]]:
    authorize(current, "read")
    if editing:
        authorize(current, "edit")
    voucher = await get(db, current, m.Voucher, voucher_id, lock=editing)
    revision = (
        await get(db, current, m.VoucherRevision, revision_id)
        if revision_id
        else await revision_for(db, current, voucher)
    )
    if revision.voucher_id != voucher.id:
        raise ValidationFailedError("revision belongs to another voucher")
    kind = await get(db, current, m.VoucherType, voucher.type_id)
    if kind.kind != "PURCHASE":
        raise ValidationFailedError("supporting-file storage is available for Purchase only")
    raw = await content(db, current, revision)
    if denied(current, "vouchers.voucher", {"attachments"}, "read", raw):
        raise PermissionDeniedError("supporting files are not readable")
    if editing:
        await guard_execution(db, current, voucher.id)
        if voucher.status not in {"DRAFT", "REJECTED", "SUBMITTED", "APPROVED"}:
            raise ConflictError("this Purchase can no longer accept supporting files")
        writable(
            current,
            "vouchers.voucher",
            raw,
            raw | {"attachments": [*raw["attachments"], {"upload": True}]},
        )
    return voucher, revision, raw


def detail(row: PurchaseSupportingFile, *, token: str | None = None) -> dict[str, Any]:
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "company_id",
            "voucher_id",
            "object_key",
            "content_hash",
            "media_type",
            "size_bytes",
            "filename",
        )
    } | {"download_token": token}


async def validate_references(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    attachments: tuple[AttachmentInput, ...],
    previous: list[dict[str, Any]],
) -> None:
    # Existing foundation metadata remains visible, but is never downloadable through
    # this adapter. New/changed references require a registered upload for this bill.
    for item in attachments:
        value = item.model_dump(mode="json")
        if value in previous:
            continue
        row = await db.scalar(
            select(PurchaseSupportingFile).where(
                PurchaseSupportingFile.company_id == current.context.company_id,
                PurchaseSupportingFile.voucher_id == voucher_id,
                PurchaseSupportingFile.object_key == item.object_key,
            )
        )
        if row is None or any(
            getattr(row, key) != getattr(item, key)
            for key in ("content_hash", "media_type", "size_bytes")
        ):
            raise ValidationFailedError(
                "supporting file must match a verified upload for this Purchase"
            )


async def linked(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    file_id: uuid.UUID,
    revision_id: uuid.UUID | None,
) -> tuple[PurchaseSupportingFile, m.VoucherRevision]:
    _, revision, raw = await authority(db, current, voucher_id, revision_id=revision_id)
    row = await get(db, current, PurchaseSupportingFile, file_id)
    if row.voucher_id != voucher_id or not any(
        all(
            item.get(key) == getattr(row, key)
            for key in ("object_key", "content_hash", "media_type", "size_bytes")
        )
        for item in raw["attachments"]
    ):
        raise PermissionDeniedError("supporting file is not linked to this Purchase revision")
    return row, revision
