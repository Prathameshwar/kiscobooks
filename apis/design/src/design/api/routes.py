"""Company-scoped Invoice Designer routes.

Every route declares the permission it requires and the object that permission is checked
against (``api/authorization.py``), reads and writes alike — the gateway authenticates,
endpoints authorize. Handlers stay thin: validate, authorize, call the domain, emit the
audit event on the same session, return the schema (CLAUDE.md §4).

Lists are keyset-paginated and return lean item schemas; a layout tree or a component's
contents is a detail read (docs/api-conventions.md).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from urllib.parse import quote

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from design.api import authorization as authz
from design.api.auth import Access, access
from design.api.common import ERRORS, Cursor, Limit, session, unique_query
from design.api.paging import Pager
from design.domain import asset_storage as storage
from design.events.evidence import audit_change
from design.models.template import (
    InvoiceRenderSnapshot,
    InvoiceTemplate,
    InvoiceTemplateAsset,
    InvoiceTemplateAssignment,
    InvoiceTemplateComponent,
    InvoiceTemplateVersion,
)
from design.schemas.assets import (
    MAXIMUM_IMAGE_BYTES,
    AssetDetail,
    AssetItem,
    AssetUpload,
    ComponentCreate,
    ComponentDetail,
    ComponentItem,
    ComponentUpdate,
)
from design.schemas.assignments import (
    AssignmentCreate,
    AssignmentItem,
    AssignmentUpdate,
    ResolveTemplateRequest,
    ResolveTemplateResponse,
)
from design.schemas.page import Page
from design.schemas.snapshots import SnapshotDetail, SnapshotItem, SnapshotRecordRequest
from design.schemas.templates import (
    TemplateCreate,
    TemplateCreated,
    TemplateDetail,
    TemplateItem,
    TemplateUpdate,
)
from design.schemas.versions import VersionCreate, VersionDetail, VersionItem
from design.tasks import (
    archive_template,
    assert_layout_fits,
    assert_layout_references,
    create_assignment,
    create_component,
    create_template,
    create_version,
    deactivate_asset,
    fingerprint,
    get_asset,
    get_assignment,
    get_component,
    get_template,
    get_version,
    list_assets,
    list_assignments,
    list_components,
    list_snapshots,
    list_templates,
    list_versions,
    publish_version,
    record_snapshot,
    resolve_template,
    storage_path,
    update_assignment,
    update_component,
    update_template,
    upload_asset,
)
from design.tasks.listing import DEFAULT_LIMIT

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses=ERRORS,
    dependencies=[Depends(unique_query)],
)


# =============================================================================
# 1. Templates
# =============================================================================


@router.post("/templates", response_model=TemplateCreated, status_code=201)
async def create_new_template(
    company_id: uuid.UUID,
    input_data: TemplateCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Create a draft template, optionally with the first version of its canvas."""
    scope = authz.company_scope(company_id)
    # The row's owner, which is both what authorizes the write and what its references
    # are checked against: a shared layout may name only shared assets (§6.2).
    owner = SCOPE_ALL if input_data.is_tenant_wide else scope
    if input_data.is_tenant_wide:
        authz.require_tenant(current.actor, authz.TEMPLATE_MANAGE)
    else:
        authz.require(current.actor, authz.TEMPLATE_MANAGE, scope)
    if input_data.initial_canvas is not None:
        await assert_layout_references(db, layout=input_data.initial_canvas, company_id=owner)

    template, version = await create_template(
        db,
        tenant_id=current.actor.tenant_id,
        company_id=scope,
        input_data=input_data,
        user_id=current.actor.user_id,
    )
    if input_data.initial_canvas is not None:
        # After creation, because the check reads the row's paper size — which this request
        # is what decides. A failure rolls the whole transaction back, so no half-made
        # template with an unprintable first version survives it.
        assert_layout_fits(template, input_data.initial_canvas)
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template",
        template.id,
        "create",
        after={
            "code": template.code,
            "name": template.name,
            "status": template.status,
            "paper_size": template.paper_size,
            "page_orientation": template.page_orientation,
            "is_system": template.is_system,
            "voucher_kind": template.voucher_kind,
            "line_profile": template.line_profile,
        },
    )
    if version is not None:
        audit_change(
            db,
            current.actor,
            template.company_id,
            "invoice_template_version",
            version.id,
            "create",
            after={
                "template_id": template.id,
                "version_number": version.version_number,
                "layout_digest": version.layout_digest,
                "schema_version": version.schema_version,
            },
        )
    created = TemplateCreated.model_validate(template)
    return created.model_copy(
        update={"initial_version_id": None if version is None else version.id}
    )


@router.get("/templates", response_model=Page[TemplateItem])
async def list_company_templates(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    status: str | None = Query(default=None, pattern=r"^(DRAFT|PUBLISHED)$"),
    voucher_kind: str | None = Query(
        default=None, max_length=50, pattern=r"^[A-Z][A-Z0-9_]{0,49}$"
    ),
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """Templates this company may use: its own, and the tenant's shared designs."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    pages = Pager.of(
        request,
        resource="design.template",
        actor=current.actor,
        company_id=scope,
        query={"status": status, "voucher_kind": voucher_kind, "limit": limit},
    )
    rows = await list_templates(
        db,
        company_id=scope,
        limit=limit,
        status=status,
        voucher_kind=voucher_kind,
        keyset=pages.keyset(cursor, InvoiceTemplate.created_at, InvoiceTemplate.id),
    )
    return pages.page(rows, limit=limit, item=TemplateItem)


@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template_detail(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """One template, including its page geometry."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(db, template_id=template_id, company_id=scope)
    return TemplateDetail.model_validate(template)


@router.put("/templates/{template_id}", response_model=TemplateDetail)
async def update_template_metadata(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    input_data: TemplateUpdate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Change a template's name or page setup. Status is not writable here."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(db, template_id=template_id, company_id=scope)
    authz.require_owner(current.actor, authz.TEMPLATE_MANAGE, template.company_id)
    before, afterwards = await update_template(
        db, template=template, input_data=input_data, user_id=current.actor.user_id
    )
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template",
        template.id,
        "update",
        before=before,
        after=afterwards,
    )
    return TemplateDetail.model_validate(template)


@router.delete("/templates/{template_id}", status_code=204, response_class=Response)
async def archive_company_template(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    """Retire a template. The row stays — printed documents point at it."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(db, template_id=template_id, company_id=scope)
    authz.require_owner(current.actor, authz.TEMPLATE_MANAGE, template.company_id)
    previous_status = template.status
    deactivated = await archive_template(db, template=template, user_id=current.actor.user_id)
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template",
        template.id,
        "archive",
        before={"status": previous_status},
        after={"status": template.status},
    )
    for rule in deactivated:
        audit_change(
            db,
            current.actor,
            rule.company_id,
            "invoice_template_assignment",
            rule.id,
            "deactivate",
            before={"is_active": True},
            after={"is_active": False},
        )
    return Response(status_code=204)


# =============================================================================
# 2. Versions
# =============================================================================


@router.post("/templates/{template_id}/versions", response_model=VersionDetail, status_code=201)
async def save_new_version(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    input_data: VersionCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Append a canvas revision. Saving does not publish it."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(db, template_id=template_id, company_id=scope)
    authz.require_owner(current.actor, authz.TEMPLATE_MANAGE, template.company_id)
    await assert_layout_references(
        db, layout=input_data.layout_definition, company_id=template.company_id
    )
    # Needs the row, not the tree: 1.1.0 took paper size out of the canvas, so the only place
    # that knows how big this sheet is, is the template being saved against.
    assert_layout_fits(template, input_data.layout_definition)
    version = await create_version(
        db,
        tenant_id=current.actor.tenant_id,
        template=template,
        input_data=input_data,
        user_id=current.actor.user_id,
    )
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template_version",
        version.id,
        "create",
        after={
            "template_id": template.id,
            "version_number": version.version_number,
            "layout_digest": version.layout_digest,
            "change_summary": version.change_summary,
        },
    )
    return VersionDetail.model_validate(version)


@router.get("/templates/{template_id}/versions", response_model=Page[VersionItem])
async def get_all_template_versions(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """The template's revision history, without a layout tree per row."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    await get_template(db, template_id=template_id, company_id=scope, include_archived=True)
    pages = Pager.of(
        request,
        resource="design.template_version",
        actor=current.actor,
        company_id=scope,
        query={"template_id": str(template_id), "limit": limit},
    )
    rows = await list_versions(
        db,
        template_id=template_id,
        limit=limit,
        keyset=pages.keyset(cursor, InvoiceTemplateVersion.created_at, InvoiceTemplateVersion.id),
    )
    return pages.page(rows, limit=limit, item=VersionItem)


@router.get("/templates/{template_id}/versions/{version_id}", response_model=VersionDetail)
async def get_specific_version(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """One version of **this** template — a version id alone is never enough."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(
        db, template_id=template_id, company_id=scope, include_archived=True
    )
    version = await get_version(db, version_id=version_id, template_id=template.id)
    return VersionDetail.model_validate(version)


@router.post(
    "/templates/{template_id}/versions/{version_id}/publish", response_model=TemplateDetail
)
async def publish_template_version(
    company_id: uuid.UUID,
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Make this version the layout every future document of this design prints on."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    template = await get_template(db, template_id=template_id, company_id=scope)
    authz.require_owner(current.actor, authz.TEMPLATE_PUBLISH, template.company_id)
    version = await get_version(db, version_id=version_id, template_id=template.id)
    previous_status = template.status
    previous, live = await publish_version(
        db, template=template, version=version, user_id=current.actor.user_id
    )
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template_version",
        version.id,
        "publish",
        after={
            "template_id": template.id,
            "version_number": version.version_number,
            "published_at": version.published_at,
        },
    )
    audit_change(
        db,
        current.actor,
        template.company_id,
        "invoice_template",
        template.id,
        "publish",
        before={"status": previous_status, "current_version_id": previous},
        after={"status": template.status, "current_version_id": live},
    )
    return TemplateDetail.model_validate(template)


# =============================================================================
# 3. Assignments and resolution
# =============================================================================


@router.post("/assignments", response_model=AssignmentItem, status_code=201)
async def create_template_assignment(
    company_id: uuid.UUID,
    input_data: AssignmentCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Route a voucher kind to a template. The template must be this company's."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSIGNMENT_MANAGE, scope)
    assignment = await create_assignment(
        db,
        tenant_id=current.actor.tenant_id,
        company_id=scope,
        input_data=input_data,
        user_id=current.actor.user_id,
    )
    audit_change(
        db,
        current.actor,
        scope,
        "invoice_template_assignment",
        assignment.id,
        "create",
        after={
            "voucher_kind": assignment.voucher_kind,
            "template_id": assignment.template_id,
            "specific_version_id": assignment.specific_version_id,
            "priority": assignment.priority,
            "voucher_type_id": assignment.voucher_type_id,
            "branch_id": assignment.branch_id,
            "currency_code": assignment.currency_code,
            "customer_tax_category": assignment.customer_tax_category,
            "is_active": assignment.is_active,
        },
    )
    return AssignmentItem.model_validate(assignment)


@router.get("/assignments", response_model=Page[AssignmentItem])
async def get_template_assignments(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    voucher_kind: str | None = Query(
        default=None, max_length=50, pattern=r"^[A-Z][A-Z0-9_]{0,49}$"
    ),
    template_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """The routing rules in force, newest first; with ``template_id``, where one design is used."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSIGNMENT_READ, scope)
    pages = Pager.of(
        request,
        resource="design.template_assignment",
        actor=current.actor,
        company_id=scope,
        query={
            "voucher_kind": voucher_kind,
            "template_id": str(template_id) if template_id else None,
            "inactive": include_inactive,
            "limit": limit,
        },
    )
    rows = await list_assignments(
        db,
        company_id=scope,
        limit=limit,
        voucher_kind=voucher_kind,
        template_id=template_id,
        include_inactive=include_inactive,
        keyset=pages.keyset(
            cursor, InvoiceTemplateAssignment.created_at, InvoiceTemplateAssignment.id
        ),
    )
    return pages.page(rows, limit=limit, item=AssignmentItem)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentItem)
async def change_template_assignment(
    company_id: uuid.UUID,
    assignment_id: uuid.UUID,
    input_data: AssignmentUpdate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Re-prioritize or deactivate a rule. Its criteria are immutable."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSIGNMENT_READ, scope)
    assignment = await get_assignment(db, assignment_id=assignment_id, company_id=scope)
    authz.require_owner(current.actor, authz.ASSIGNMENT_MANAGE, assignment.company_id)
    before, afterwards = await update_assignment(
        db, assignment=assignment, input_data=input_data, user_id=current.actor.user_id
    )
    action = "deactivate" if afterwards.get("is_active") is False else "update"
    audit_change(
        db,
        current.actor,
        assignment.company_id,
        "invoice_template_assignment",
        assignment.id,
        action,
        before=before,
        after=afterwards,
    )
    return AssignmentItem.model_validate(assignment)


@router.post("/resolve", response_model=ResolveTemplateResponse)
async def resolve_voucher_template(
    company_id: uuid.UUID,
    input_data: ResolveTemplateRequest,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Which layout this document prints on, and which rule decided it."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.TEMPLATE_READ, scope)
    return await resolve_template(db, company_id=scope, request=input_data)


# =============================================================================
# 4. Assets
# =============================================================================


def asset_download_codec(request: Request, current: Access, asset_id: uuid.UUID) -> CursorCodec:
    """Scoped to one asset and one actor: a token minted for a logo cannot read a
    signature, and one actor's copied link is dead on arrival for another's session."""
    actor_key = fingerprint(current.actor.tenant_id, current.actor.user_id)
    return CursorCodec(
        request.app.state.settings.cursor_signing_secret.get_secret_value().encode(),
        context=f"design-asset:{asset_id}:{actor_key}",
        ttl_seconds=120,
    )


def with_download_token(
    asset: InvoiceTemplateAsset, request: Request, current: Access
) -> AssetDetail:
    """A fresh signed download alongside the metadata — minted on every read, held nowhere
    (CLAUDE.md §5.14). Absent for an inactive asset: it can be seen in history, not fetched."""
    detail = AssetDetail.model_validate(asset)
    if not asset.is_active or asset.storage_backend != "PRIVATE_DISK":
        return detail
    codec = asset_download_codec(request, current, asset.id)
    token = codec.encode({"digest": asset.content_digest})
    return detail.model_copy(update={"download_token": token})


@router.post("/assets", response_model=AssetDetail, status_code=201)
async def upload_new_asset(
    company_id: uuid.UUID,
    input_data: AssetUpload,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Upload a brand asset's bytes to this service's own private disk.

    The storage path is derived, never supplied; size, digest and (for PNG) pixel
    dimensions are measured from the decoded bytes, never taken from the request
    (designer plan P4/D3, 2026-11-03 — docs/invoice-design.md §9.2).
    """
    scope = authz.company_scope(company_id)
    if input_data.is_tenant_wide:
        authz.require_tenant(current.actor, authz.ASSET_MANAGE)
    else:
        authz.require(current.actor, authz.ASSET_MANAGE, scope)
    settings = request.app.state.settings
    owner = SCOPE_ALL if input_data.is_tenant_wide else scope
    data, digest = await asyncio.to_thread(
        storage.decode,
        input_data.content_base64,
        input_data.mime_type,
        max_bytes=MAXIMUM_IMAGE_BYTES,
    )
    asset_id = uuid7()
    key = storage_path(
        prefix=settings.object_storage_prefix,
        tenant_id=current.actor.tenant_id,
        company_id=owner,
        asset_id=asset_id,
        mime_type=input_data.mime_type,
    )
    # Written before any row exists: a failed write never leaves a database record
    # pointing at bytes that are not there.
    await asyncio.to_thread(storage.store, settings.asset_storage_root, key, data, digest)
    dimensions = storage.png_dimensions(data, input_data.mime_type)
    asset = await upload_asset(
        db,
        tenant_id=current.actor.tenant_id,
        owner_company_id=owner,
        asset_id=asset_id,
        data=data,
        digest=digest,
        width_px=dimensions[0] if dimensions else None,
        height_px=dimensions[1] if dimensions else None,
        input_data=input_data,
        backend="PRIVATE_DISK",
        key=key,
        user_id=current.actor.user_id,
    )
    audit_change(
        db,
        current.actor,
        asset.company_id,
        "invoice_template_asset",
        asset.id,
        "create",
        after={
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "file_name": asset.file_name,
            "mime_type": asset.mime_type,
            "file_size_bytes": asset.file_size_bytes,
            "storage_backend": asset.storage_backend,
            "storage_path": asset.storage_path,
            "content_digest": asset.content_digest,
            "is_active": asset.is_active,
        },
    )
    return with_download_token(asset, request, current)


@router.get("/assets", response_model=Page[AssetItem])
async def get_company_assets(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    asset_type: str | None = Query(default=None, max_length=32, pattern=r"^[A-Z][A-Z_]{0,31}$"),
    include_inactive: bool = False,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """Assets this company may place on a layout."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSET_READ, scope)
    pages = Pager.of(
        request,
        resource="design.template_asset",
        actor=current.actor,
        company_id=scope,
        query={"asset_type": asset_type, "inactive": include_inactive, "limit": limit},
    )
    rows = await list_assets(
        db,
        company_id=scope,
        limit=limit,
        asset_type=asset_type,
        include_inactive=include_inactive,
        keyset=pages.keyset(cursor, InvoiceTemplateAsset.created_at, InvoiceTemplateAsset.id),
    )
    # The list projection (`AssetItem`) carries no `content_digest` to bind a token to, so
    # the thumbnail picker reads the full `AssetDetail` per chosen asset instead; this page
    # answers "which assets exist", not "show me every one of them".
    return pages.page(rows, limit=limit, item=AssetItem)


@router.get("/assets/{asset_id}", response_model=AssetDetail)
async def get_asset_detail(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """One asset, including where this service stored it, and a fresh download token."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSET_READ, scope)
    asset = await get_asset(db, asset_id=asset_id, company_id=scope)
    return with_download_token(asset, request, current)


@router.get("/assets/{asset_id}/download", response_class=Response)
async def download_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    token: str,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    """The asset's bytes, only against a signed, expiring, actor-bound token.

    Current authorization is re-checked here, same as every other read — a token is
    never itself the authority, only a bounded convenience once authority is confirmed
    (CLAUDE.md §5.14).
    """
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSET_READ, scope)
    asset = await get_asset(db, asset_id=asset_id, company_id=scope)
    if not asset.is_active:
        raise ValidationFailedError("this asset is no longer available for download")
    receipt = asset_download_codec(request, current, asset.id).decode(token)
    if receipt.get("digest") != asset.content_digest:
        raise ValidationFailedError("asset download authority changed")
    settings = request.app.state.settings
    data = await asyncio.to_thread(
        storage.read,
        settings.asset_storage_root,
        asset.storage_path,
        asset.content_digest or "",
        asset.file_size_bytes,
    )
    # Staged on this request's one transaction, same as every other write here
    # (`api/common.py::session`); it commits as the route returns, before the response
    # reaches the client, so the access audit is never lost even though the bytes
    # themselves are read straight from disk and never touch the database.
    audit_change(
        db,
        current.actor,
        asset.company_id,
        "invoice_template_asset",
        asset.id,
        "download",
        after={"content_digest": asset.content_digest, "file_size_bytes": asset.file_size_bytes},
    )
    return Response(
        data,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(asset.file_name, safe='')}",
        },
    )


@router.delete("/assets/{asset_id}", status_code=204, response_class=Response)
async def deactivate_company_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Response:
    """Withdraw an asset from new layouts. Published layouts keep rendering it."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.ASSET_READ, scope)
    asset = await get_asset(db, asset_id=asset_id, company_id=scope)
    authz.require_owner(current.actor, authz.ASSET_MANAGE, asset.company_id)
    await deactivate_asset(db, asset=asset, user_id=current.actor.user_id)
    audit_change(
        db,
        current.actor,
        asset.company_id,
        "invoice_template_asset",
        asset.id,
        "deactivate",
        before={"is_active": True},
        after={"is_active": False},
    )
    return Response(status_code=204)


# =============================================================================
# 5. Components
# =============================================================================


@router.post("/components", response_model=ComponentDetail, status_code=201)
async def create_new_component(
    company_id: uuid.UUID,
    input_data: ComponentCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Create a reusable block a layout can compose."""
    scope = authz.company_scope(company_id)
    if input_data.is_tenant_wide:
        authz.require_tenant(current.actor, authz.COMPONENT_MANAGE)
    else:
        authz.require(current.actor, authz.COMPONENT_MANAGE, scope)
    component = await create_component(
        db,
        tenant_id=current.actor.tenant_id,
        company_id=scope,
        input_data=input_data,
        user_id=current.actor.user_id,
    )
    audit_change(
        db,
        current.actor,
        component.company_id,
        "invoice_template_component",
        component.id,
        "create",
        after={
            "code": component.code,
            "name": component.name,
            "component_category": component.component_category,
            "is_active": component.is_active,
            "content_definition": None,
        },
    )
    return ComponentDetail.model_validate(component)


@router.get("/components", response_model=Page[ComponentItem])
async def get_company_components(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    category: str | None = Query(default=None, max_length=32, pattern=r"^[A-Z][A-Z_]{0,31}$"),
    include_inactive: bool = False,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """Reusable blocks visible to this company, without their contents."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.COMPONENT_READ, scope)
    pages = Pager.of(
        request,
        resource="design.template_component",
        actor=current.actor,
        company_id=scope,
        query={"category": category, "inactive": include_inactive, "limit": limit},
    )
    rows = await list_components(
        db,
        company_id=scope,
        limit=limit,
        category=category,
        include_inactive=include_inactive,
        keyset=pages.keyset(
            cursor, InvoiceTemplateComponent.created_at, InvoiceTemplateComponent.id
        ),
    )
    return pages.page(rows, limit=limit, item=ComponentItem)


@router.get("/components/{component_id}", response_model=ComponentDetail)
async def get_component_detail(
    company_id: uuid.UUID,
    component_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """One block, with its contents."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.COMPONENT_READ, scope)
    component = await get_component(db, component_id=component_id, company_id=scope)
    return ComponentDetail.model_validate(component)


@router.patch("/components/{component_id}", response_model=ComponentDetail)
async def change_company_component(
    company_id: uuid.UUID,
    component_id: uuid.UUID,
    input_data: ComponentUpdate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Edit or deactivate a block. Shipped blocks are read-only."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.COMPONENT_READ, scope)
    component = await get_component(db, component_id=component_id, company_id=scope)
    authz.require_owner(current.actor, authz.COMPONENT_MANAGE, component.company_id)
    before, afterwards = await update_component(
        db, component=component, input_data=input_data, user_id=current.actor.user_id
    )
    action = "deactivate" if afterwards.get("is_active") is False else "update"
    audit_change(
        db,
        current.actor,
        component.company_id,
        "invoice_template_component",
        component.id,
        action,
        before=before,
        after=afterwards,
        changed=frozenset(input_data.model_dump(exclude_unset=True)),
    )
    return ComponentDetail.model_validate(component)


# =============================================================================
# 6. Render evidence
# =============================================================================


@router.post("/renders", response_model=SnapshotDetail, status_code=201)
async def record_render(
    company_id: uuid.UUID,
    input_data: SnapshotRecordRequest,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Any:
    """Record that a document was printed, and from which template version."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.RENDER_RECORD, scope)
    snapshot = await record_snapshot(
        db,
        tenant_id=current.actor.tenant_id,
        company_id=scope,
        input_data=input_data,
        prefix=request.app.state.settings.object_storage_prefix,
        user_id=current.actor.user_id,
    )
    audit_change(
        db,
        current.actor,
        scope,
        "invoice_render_snapshot",
        snapshot.id,
        "create",
        after={
            "voucher_id": snapshot.voucher_id,
            "voucher_revision_id": snapshot.voucher_revision_id,
            "template_id": snapshot.template_id,
            "template_version_id": snapshot.template_version_id,
            "output_format": snapshot.output_format,
            "render_channel": snapshot.render_channel,
            "checksum_sha256": snapshot.checksum_sha256,
        },
    )
    return SnapshotDetail.model_validate(snapshot)


@router.get("/renders", response_model=Page[SnapshotItem])
async def get_render_history(
    company_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
    voucher_id: uuid.UUID | None = None,
    cursor: Cursor = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Any:
    """What was printed, most recent first — optionally for one document."""
    scope = authz.company_scope(company_id)
    authz.require(current.actor, authz.RENDER_READ, scope)
    pages = Pager.of(
        request,
        resource="design.render_snapshot",
        actor=current.actor,
        company_id=scope,
        query={"voucher_id": str(voucher_id) if voucher_id else None, "limit": limit},
    )
    rows = await list_snapshots(
        db,
        company_id=scope,
        limit=limit,
        voucher_id=voucher_id,
        keyset=pages.keyset(cursor, InvoiceRenderSnapshot.rendered_at, InvoiceRenderSnapshot.id),
    )
    return pages.page(rows, limit=limit, item=SnapshotItem, moment="rendered_at")
