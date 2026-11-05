"""Bounded, versioned materialization mechanism shared by reference consumers."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.language import Language
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.errors import ValidationFailedError
from billing_platform.reference.contracts import CatalogData


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    kind: str
    code: str
    version: int = Field(strict=True, ge=1)
    payload: dict[str, Any]


class ChangePage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Change] = Field(max_length=100)
    has_more: bool


async def apply(db: AsyncSession, changes: list[Change], *, service: str) -> uuid.UUID | None:
    models: dict[str, Any] = {
        "country": Country,
        "state": State,
        "currency": Currency,
        "language": Language,
    }
    checkpoint = await db.scalar(
        select(ReferenceSyncState).where(ReferenceSyncState.service == service).with_for_update()
    )
    if checkpoint is None:
        checkpoint = ReferenceSyncState(service=service)
        db.add(checkpoint)
        await db.flush()
    previous = checkpoint.cursor
    for change in changes:
        if previous is not None and change.id <= previous:
            raise ValidationFailedError("reference changes must be ordered after the checkpoint")
        previous = change.id
        if "kind" in change.payload:
            raise ValidationFailedError("reference payload cannot redefine its kind")
        data: CatalogData = TypeAdapter(CatalogData).validate_python(
            {"kind": change.kind, **change.payload}
        )
        if data.code != change.code:
            raise ValidationFailedError("reference change identity mismatch")
        revision = await db.scalar(
            select(ReferenceRevision)
            .where(ReferenceRevision.kind == change.kind, ReferenceRevision.code == change.code)
            .with_for_update()
        )
        if revision is not None and change.version <= revision.version:
            if change.version == revision.version and revision.payload != change.payload:
                raise ValidationFailedError("reference version integrity mismatch")
            continue
        native = await db.get(models[change.kind], change.code)
        if native is None:
            native = models[change.kind](**change.payload)
            db.add(native)
        else:
            for key, value in change.payload.items():
                setattr(native, key, value)
        if revision is None:
            revision = ReferenceRevision(kind=change.kind, code=change.code, is_custom=True)
            db.add(revision)
        revision.name, revision.is_active = data.name, data.is_active
        revision.source, revision.version, revision.change_id = (
            "operator",
            change.version,
            change.id,
        )
        revision.parent_code = change.payload.get(
            "country_code", change.payload.get("default_currency_code")
        )
        revision.payload = change.payload
        await db.flush()
    checkpoint.cursor = previous
    await db.flush()
    return previous
