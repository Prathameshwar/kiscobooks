"""Actor-private wizard snapshots with optimistic versions and source review."""

import hashlib
import json
import uuid

from billing_platform.authz import ScopePath
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.advanced_product_draft import AdvancedProductDraft
from catalog.schemas.advanced_product_creation import (
    AdvancedDraftContent,
    AdvancedDraftDetail,
    AdvancedDraftListItem,
    AdvancedDraftRevision,
    AdvancedDraftSave,
)
from catalog.schemas.field_metadata import FieldSet
from catalog.schemas.product_mode import ProductModeDetail
from catalog.tasks.advanced_product_options import (
    defaults,
    fields,
    guard_content,
    selected_context,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.product_mode import read as read_mode

ENTITY = "catalog.advanced_product_draft"
MAX_DRAFTS = 20


def digest(body: AdvancedDraftSave) -> str:
    encoded = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


async def source(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    content: AdvancedDraftContent,
    field_sets: tuple[FieldSet, FieldSet] | None = None,
) -> tuple[ProductModeDetail, int, FieldSet, FieldSet]:
    current.require_scope("item.create", target=ScopePath(company_id=company))
    mode = await read_mode(db, current, company)
    kind, group, type_revision = selected_context(content)
    resolved, _, _ = await defaults(
        db,
        current,
        company,
        kind=kind,
        group_id=group,
        product_type_revision_id=type_revision,
    )
    family, sku = field_sets or await fields(db, current, company, request)
    return mode, resolved.configuration.source_version, family, sku


async def check_write(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    body: AdvancedDraftSave,
) -> None:
    mode, configuration, family, sku = await source(db, current, company, request, body.content)
    if not mode.product_family_sku_enabled:
        raise ConflictError("This company uses Simple Product creation")
    if (
        body.mode_version != mode.row_version
        or body.policy_generation != mode.policy_generation
        or body.source_version != configuration
        or body.family_field_version != family.source_version
        or body.sku_field_version != sku.source_version
    ):
        raise ConflictError("Product setup changed; refresh options and review the draft")
    guard_content(body.content, family, sku, write=True)


async def owned(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    draft_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AdvancedProductDraft:
    current.require_scope("item.create", target=ScopePath(company_id=company))
    query = select(AdvancedProductDraft).where(
        AdvancedProductDraft.id == draft_id,
        AdvancedProductDraft.company_id == company,
        AdvancedProductDraft.owner_user_id == current.user_id,
    )
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFoundError("Product draft was not found")
    return row


async def needs_review(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    row: AdvancedProductDraft,
    mode: ProductModeDetail,
    content: AdvancedDraftContent,
    field_sets: tuple[FieldSet, FieldSet],
) -> bool:
    if (
        not mode.product_family_sku_enabled
        or row.mode_version != mode.row_version
        or row.policy_generation != mode.policy_generation
    ):
        return True
    try:
        _, source_version, family, sku = await source(
            db, current, company, request, content, field_sets
        )
    except (ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError):
        return True
    return (
        row.source_version != source_version
        or row.family_field_version != family.source_version
        or row.sku_field_version != sku.source_version
    )


async def detail(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    row: AdvancedProductDraft,
    *,
    mode: ProductModeDetail | None = None,
) -> AdvancedDraftDetail:
    verified = mode or await read_mode(db, current, company)
    content = AdvancedDraftContent.model_validate(row.payload)
    family, sku = await fields(db, current, company, request)
    guard_content(content, family, sku, write=False)
    return AdvancedDraftDetail(
        id=row.id,
        company_id=company,
        row_version=row.row_version,
        step=row.step,
        created_at=row.created_at,
        updated_at=row.updated_at,
        mode_version=row.mode_version,
        policy_generation=row.policy_generation,
        source_version=row.source_version,
        family_field_version=row.family_field_version,
        sku_field_version=row.sku_field_version,
        content=content,
        needs_review=await needs_review(
            db, current, company, request, row, verified, content, (family, sku)
        ),
    )


async def create(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    body: AdvancedDraftSave,
    key: str,
) -> tuple[AdvancedDraftDetail, bool]:
    await check_write(db, current, company, request, body)
    existing = await db.scalar(
        select(AdvancedProductDraft).where(
            AdvancedProductDraft.company_id == company,
            AdvancedProductDraft.owner_user_id == current.user_id,
            AdvancedProductDraft.create_key == key,
        )
    )
    hashed = digest(body)
    if existing is not None:
        if existing.create_hash != hashed:
            raise ConflictError("This draft key already belongs to another request")
        return await detail(db, current, company, request, existing), True
    count = await db.scalar(
        select(func.count(AdvancedProductDraft.id)).where(
            AdvancedProductDraft.company_id == company,
            AdvancedProductDraft.owner_user_id == current.user_id,
        )
    )
    if count is not None and count >= MAX_DRAFTS:
        raise ConflictError("Delete an older product draft before saving another")
    row = AdvancedProductDraft(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company,
        owner_user_id=current.user_id,
        created_by=current.user_id,
        updated_by=current.user_id,
        create_key=key,
        create_hash=hashed,
        mode_version=body.mode_version,
        policy_generation=body.policy_generation,
        source_version=body.source_version,
        family_field_version=body.family_field_version,
        sku_field_version=body.sku_field_version,
        step=body.step,
        payload=body.content.model_dump(mode="json"),
        row_version=1,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError as exc:
        concurrent = await db.scalar(
            select(AdvancedProductDraft)
            .where(
                AdvancedProductDraft.company_id == company,
                AdvancedProductDraft.owner_user_id == current.user_id,
                AdvancedProductDraft.create_key == key,
            )
            .with_for_update()
        )
        if concurrent is not None and concurrent.create_hash == hashed:
            return await detail(db, current, company, request, concurrent), True
        raise ConflictError("Product draft could not be created with this key") from exc
    audit_change(db, current, company, ENTITY, row.id, "create", frozenset({"payload", "step"}))
    return await detail(db, current, company, request, row), False


async def replace(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    draft_id: uuid.UUID,
    body: AdvancedDraftRevision,
) -> AdvancedDraftDetail:
    row = await owned(db, current, company, draft_id, lock=True)
    if row.row_version != body.expected_version:
        raise ConflictError("Product draft changed; reload before saving")
    await check_write(db, current, company, request, body)
    row.payload = body.content.model_dump(mode="json")
    row.step = body.step
    row.mode_version = body.mode_version
    row.policy_generation = body.policy_generation
    row.source_version = body.source_version
    row.family_field_version = body.family_field_version
    row.sku_field_version = body.sku_field_version
    row.row_version += 1
    row.updated_by = current.user_id
    await db.flush()
    audit_change(db, current, company, ENTITY, row.id, "update", frozenset({"payload", "step"}))
    return await detail(db, current, company, request, row)


async def read(
    db: AsyncSession, current: Actor, company: uuid.UUID, request: Request, draft_id: uuid.UUID
) -> AdvancedDraftDetail:
    row = await owned(db, current, company, draft_id)
    return await detail(db, current, company, request, row)


async def list_owned(
    db: AsyncSession, current: Actor, company: uuid.UUID, request: Request
) -> list[AdvancedDraftListItem]:
    current.require_scope("item.create", target=ScopePath(company_id=company))
    mode = await read_mode(db, current, company)
    family, sku = await fields(db, current, company, request)
    rows = list(
        await db.scalars(
            select(AdvancedProductDraft)
            .where(
                AdvancedProductDraft.company_id == company,
                AdvancedProductDraft.owner_user_id == current.user_id,
            )
            .order_by(AdvancedProductDraft.updated_at.desc(), AdvancedProductDraft.id.desc())
            .limit(MAX_DRAFTS)
        )
    )
    result = []
    for row in rows:
        content = AdvancedDraftContent.model_validate(row.payload)
        guard_content(content, family, sku, write=False)
        result.append(
            AdvancedDraftListItem(
                id=row.id,
                company_id=company,
                row_version=row.row_version,
                step=row.step,
                updated_at=row.updated_at,
                needs_review=await needs_review(
                    db, current, company, request, row, mode, content, (family, sku)
                ),
            )
        )
    return result


async def delete(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    draft_id: uuid.UUID,
    expected_version: int,
) -> None:
    row = await owned(db, current, company, draft_id, lock=True)
    await read_mode(db, current, company)
    if row.row_version != expected_version:
        raise ConflictError("Product draft changed; reload before deleting")
    audit_change(db, current, company, ENTITY, row.id, "delete", frozenset({"payload"}))
    await db.delete(row)
