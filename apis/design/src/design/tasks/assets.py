"""Brand assets and reusable components (docs/invoice-design.md §6.3).

The storage path is **derived here**, from the configured prefix, the tenant, the owning
company and the asset's own id. A client-supplied path can name another tenant's object,
and the upload call is the only place that boundary can be drawn, because nothing
downstream knows what the caller was allowed to see. The bytes behind that path are
written and read through ``domain/asset_storage.py`` (plan P4/D3, 2026-11-03) — never
trusting a client-declared size, digest or pixel count, always measuring the bytes
actually received.

Assets and components are deactivated, never deleted: a published layout may reference
one, and removing the row would leave a document that cannot be reprinted
(CLAUDE.md invariant 12).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from sqlalchemy import ColumnElement, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from design.models.template import InvoiceTemplateAsset, InvoiceTemplateComponent
from design.schemas.assets import (
    AssetUpload,
    ComponentCreate,
    ComponentUpdate,
)

#: Extensions the derived path may end in, by media type. The stored name never comes
#: from the client's file name, so a crafted name cannot shape the object key.
_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def storage_path(
    *,
    prefix: str,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    mime_type: str,
) -> str:
    """``<prefix>/assets/<tenant>/<company>/<asset>.<ext>`` — derived, never supplied."""
    extension = _EXTENSIONS.get(mime_type)
    if extension is None:
        raise ValidationFailedError("unsupported asset media type")
    return f"{prefix}/assets/{tenant_id}/{company_id}/{asset_id}.{extension}"


def fingerprint(tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> str:
    """Binds a signed download token to the actor who read it; it is never a credential
    and grants nothing on its own — authorization is re-checked on every download."""
    return hashlib.sha256(f"{tenant_id}:{user_id}".encode()).hexdigest()


async def upload_asset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_company_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: bytes,
    digest: str,
    width_px: int | None,
    height_px: int | None,
    input_data: AssetUpload,
    backend: str,
    key: str,
    user_id: uuid.UUID | None = None,
) -> InvoiceTemplateAsset:
    """Record an asset already written to disk under ``key``, from its real bytes.

    ``data``, ``digest`` and the pixel dimensions are measured by the caller from the
    decoded upload — never the request's own claims, which this function does not see.
    ``owner_company_id`` is the row's owning scope (``SCOPE_ALL`` for tenant-wide),
    already resolved by the caller — the same scope ``key`` was derived and stored
    against, so there is one resolution of "whose asset is this", not two.
    """
    asset = InvoiceTemplateAsset(
        id=asset_id,
        tenant_id=tenant_id,
        company_id=owner_company_id,
        asset_name=input_data.asset_name,
        asset_type=input_data.asset_type,
        file_name=input_data.file_name,
        mime_type=input_data.mime_type,
        file_size_bytes=len(data),
        storage_backend=backend,
        storage_path=key,
        content_digest=digest,
        image_width_px=width_px,
        image_height_px=height_px,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def get_asset(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    company_id: uuid.UUID,
) -> InvoiceTemplateAsset:
    result = await session.execute(
        select(InvoiceTemplateAsset).where(
            InvoiceTemplateAsset.id == asset_id,
            InvoiceTemplateAsset.company_id.in_([company_id, SCOPE_ALL]),
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise NotFoundError("template asset not found")
    return asset


async def list_assets(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    limit: int,
    asset_type: str | None = None,
    include_inactive: bool = False,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceTemplateAsset]:
    conditions: list[Any] = [InvoiceTemplateAsset.company_id.in_([company_id, SCOPE_ALL])]
    if asset_type is not None:
        conditions.append(InvoiceTemplateAsset.asset_type == asset_type)
    if not include_inactive:
        conditions.append(InvoiceTemplateAsset.is_active.is_(True))
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceTemplateAsset)
        .where(*conditions)
        .order_by(desc(InvoiceTemplateAsset.created_at), desc(InvoiceTemplateAsset.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())


async def deactivate_asset(
    session: AsyncSession,
    *,
    asset: InvoiceTemplateAsset,
    user_id: uuid.UUID | None = None,
) -> None:
    """Withdraw an asset from new layouts. Published layouts keep rendering it."""
    if not asset.is_active:
        raise ConflictError("asset is already inactive")
    asset.is_active = False
    asset.updated_by = user_id
    await session.flush()


async def assert_layout_references(
    session: AsyncSession,
    *,
    layout: Any,
    company_id: uuid.UUID,
) -> None:
    """Every asset and component a layout names must be this company's, and active.

    Checked when the layout is **stored**, not when it is rendered: a version is
    immutable and long-lived, so a dangling or cross-company reference inside one would
    be discovered by a renderer at print time, which is the worst possible moment.
    """
    asset_ids = {
        uuid.UUID(element.asset_id)
        for section in layout.sections
        for element in section.elements
        if element.asset_id is not None
    }
    if asset_ids:
        found = await session.execute(
            select(InvoiceTemplateAsset.id).where(
                InvoiceTemplateAsset.id.in_(asset_ids),
                InvoiceTemplateAsset.company_id.in_([company_id, SCOPE_ALL]),
                InvoiceTemplateAsset.is_active.is_(True),
            )
        )
        missing = asset_ids - set(found.scalars().all())
        if missing:
            raise ValidationFailedError(
                "layout references an unknown or inactive asset",
                fields={"asset_id": ", ".join(sorted(str(value) for value in missing))},
            )

    codes = {
        section.component_code for section in layout.sections if section.component_code is not None
    }
    if codes:
        found_codes = await session.execute(
            select(InvoiceTemplateComponent.code).where(
                InvoiceTemplateComponent.code.in_(codes),
                InvoiceTemplateComponent.company_id.in_([company_id, SCOPE_ALL]),
                InvoiceTemplateComponent.is_active.is_(True),
            )
        )
        absent = codes - set(found_codes.scalars().all())
        if absent:
            raise ValidationFailedError(
                "layout references an unknown or inactive component",
                fields={"component_code": ", ".join(sorted(absent))},
            )


async def create_component(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    input_data: ComponentCreate,
    user_id: uuid.UUID | None = None,
) -> InvoiceTemplateComponent:
    component = InvoiceTemplateComponent(
        tenant_id=tenant_id,
        company_id=SCOPE_ALL if input_data.is_tenant_wide else company_id,
        name=input_data.name,
        code=input_data.code,
        component_category=input_data.component_category,
        description=input_data.description,
        content_definition=dict(input_data.content_definition),
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(component)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"component code '{input_data.code}' is already in use") from exc
    return component


async def get_component(
    session: AsyncSession,
    *,
    component_id: uuid.UUID,
    company_id: uuid.UUID,
) -> InvoiceTemplateComponent:
    result = await session.execute(
        select(InvoiceTemplateComponent).where(
            InvoiceTemplateComponent.id == component_id,
            InvoiceTemplateComponent.company_id.in_([company_id, SCOPE_ALL]),
        )
    )
    component = result.scalar_one_or_none()
    if component is None:
        raise NotFoundError("template component not found")
    return component


async def list_components(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    limit: int,
    category: str | None = None,
    include_inactive: bool = False,
    keyset: ColumnElement[bool] | None = None,
) -> list[InvoiceTemplateComponent]:
    conditions: list[Any] = [InvoiceTemplateComponent.company_id.in_([company_id, SCOPE_ALL])]
    if category is not None:
        conditions.append(InvoiceTemplateComponent.component_category == category)
    if not include_inactive:
        conditions.append(InvoiceTemplateComponent.is_active.is_(True))
    if keyset is not None:
        conditions.append(keyset)
    result = await session.execute(
        select(InvoiceTemplateComponent)
        .where(*conditions)
        .order_by(desc(InvoiceTemplateComponent.created_at), desc(InvoiceTemplateComponent.id))
        .limit(limit + 1)
    )
    return list(result.scalars().all())


async def update_component(
    session: AsyncSession,
    *,
    component: InvoiceTemplateComponent,
    input_data: ComponentUpdate,
    user_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Patch a component. A shipped component is read-only, like a shipped template."""
    if component.is_system:
        raise ValidationFailedError("a system component is read-only")
    requested = input_data.model_dump(exclude_unset=True)
    if not requested:
        raise ValidationFailedError("no changes were supplied")
    # The block's contents are deliberately absent from the before/after values: they are
    # free-form text a tenant composes, and the auditable fact is that they changed. The
    # audit writer records any field outside its allowlist as a marker (docs/audit.md §5.2).
    tracked = [field for field in requested if field != "content_definition"]
    before = {field: getattr(component, field) for field in tracked}
    for field, value in requested.items():
        setattr(component, field, dict(value) if field == "content_definition" else value)
    component.updated_by = user_id
    await session.flush()
    return before, {field: getattr(component, field) for field in before}
