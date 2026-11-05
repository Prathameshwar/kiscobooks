"""Renderer-only scoped resolution. No actor grants are minted or widened."""

import asyncio
import base64
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from design.domain import asset_storage as storage
from design.models.template import InvoiceTemplate, InvoiceTemplateAsset, InvoiceTemplateVersion
from design.schemas.assignments import ResolveTemplateRequest
from design.schemas.printing import (
    PRINT_IMAGE_MAX_BYTES,
    PRINT_IMAGES_MAX_BYTES,
    PrintAsset,
    PrintLayout,
    PrintResolve,
)
from design.tasks.resolution import _candidates, _publishable, matches

router = APIRouter()
OPERATION = "design.print.resolve"


def custom(
    template: InvoiceTemplate,
    version: InvoiceTemplateVersion,
    rule_id: uuid.UUID | None,
    *,
    preview: bool = False,
) -> PrintLayout:
    return PrintLayout(
        source="CUSTOM",
        name=template.name,
        version=str(version.version_number),
        template_id=template.id,
        version_id=version.id,
        assignment_rule_id=rule_id,
        layout_digest=version.layout_digest,
        layout_definition=version.layout_definition,
        paper_size=template.paper_size,
        page_orientation=template.page_orientation,
        page_width_mm=str(template.page_width_mm) if template.page_width_mm else None,
        page_height_mm=str(template.page_height_mm) if template.page_height_mm else None,
        preview=preview,
    )


async def previewed(
    db: AsyncSession, body: PrintResolve
) -> tuple[InvoiceTemplate, InvoiceTemplateVersion]:
    """The one saved version a preview asked for, if this company may print with it.

    Visible to the company (its own or the tenant's), not archived, designed for Purchase or
    for any kind, and the version is that template's own. Publication is not required: a
    preview is how a version is checked before it is published.
    """
    assert body.preview is not None
    template = await db.scalar(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == body.preview.template_id,
            InvoiceTemplate.company_id.in_([body.company_id, SCOPE_ALL]),
            InvoiceTemplate.status != "ARCHIVED",
        )
    )
    if template is None or template.voucher_kind not in (None, body.voucher_kind):
        raise NotFoundError("template not found")
    version = await db.scalar(
        select(InvoiceTemplateVersion).where(
            InvoiceTemplateVersion.id == body.preview.version_id,
            InvoiceTemplateVersion.template_id == template.id,
        )
    )
    if version is None:
        raise NotFoundError("template version not found")
    return template, version


def referenced(layout: dict[str, Any] | None) -> list[uuid.UUID]:
    """The assets a layout names, in first-use order, each once."""
    found: dict[uuid.UUID, None] = {}
    for section in (layout or {}).get("sections") or []:
        for element in section.get("elements") or []:
            if element.get("asset_id"):
                found[uuid.UUID(str(element["asset_id"]))] = None
    return list(found)


async def printable_assets(
    db: AsyncSession, root: Path | None, company_id: uuid.UUID, layout: dict[str, Any] | None
) -> list[PrintAsset]:
    """Each named image with its verified bytes, or the reason it cannot print.

    Only this company's or the tenant's own assets are read, by the service-derived key and
    the digest measured at upload; nothing in the layout chooses a path.
    """
    wanted = referenced(layout)
    if not wanted:
        return []
    rows = {
        row.id: row
        for row in await db.scalars(
            select(InvoiceTemplateAsset).where(
                InvoiceTemplateAsset.id.in_(wanted),
                InvoiceTemplateAsset.company_id.in_([company_id, SCOPE_ALL]),
            )
        )
    }
    result: list[PrintAsset] = []
    spent = 0
    for identity in wanted:
        row = rows.get(identity)
        if row is None or not row.content_digest or row.mime_type not in storage.PRINTABLE:
            result.append(PrintAsset(asset_id=identity, status="MISSING"))
            continue
        facts: dict[str, Any] = {"mime_type": row.mime_type, "size_bytes": row.file_size_bytes}
        if not row.is_active:
            result.append(PrintAsset(asset_id=identity, status="WITHDRAWN", **facts))
            continue
        if row.file_size_bytes > PRINT_IMAGE_MAX_BYTES:
            result.append(PrintAsset(asset_id=identity, status="TOO_LARGE", **facts))
            continue
        if spent + row.file_size_bytes > PRINT_IMAGES_MAX_BYTES:
            result.append(PrintAsset(asset_id=identity, status="OVER_BUDGET", **facts))
            continue
        try:
            data = await asyncio.to_thread(
                storage.read, root, row.storage_path, row.content_digest, row.file_size_bytes
            )
        except (ConflictError, ValidationFailedError):
            # Storage unconfigured, unreadable, or bytes that no longer match their digest.
            result.append(PrintAsset(asset_id=identity, status="UNAVAILABLE", **facts))
            continue
        spent += len(data)
        result.append(
            PrintAsset(
                asset_id=identity,
                status="READY",
                sha256=row.content_digest,
                content_base64=base64.b64encode(data).decode("ascii"),
                **facts,
            )
        )
    return result


@router.post("/internal/v1/print-layout", response_model=PrintLayout)
async def resolve_print_layout(body: PrintResolve, request: Request) -> Response:
    # This internal route requires a service HMAC and an explicit tenant/company
    # allowlist instead of an interactive design permission.
    source = request.app.state.settings.print_source
    if source is None:
        raise AuthenticationRequiredError("print layout transport is not configured")
    if request.url.query:
        raise PermissionDeniedError("print layout query is not supported")
    secret = source.secret.get_secret_value().encode()
    raw = await request.body()
    framed = service_request_bytes(method="POST", path=request.url.path, query="", body=raw)
    verify_service_body(
        {"current": ServiceKey("vouchers", "design", frozenset({OPERATION}), secret)},
        key_id=request.headers.get("x-source-key-id", ""),
        issuer="vouchers",
        audience="design",
        operation=OPERATION,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
        maximum_age=30,
    )
    if not any(
        scope.tenant_id == body.tenant_id and scope.company_id == body.company_id
        for scope in source.scopes
    ):
        raise PermissionDeniedError("print company is outside the renderer scope")
    if not request.app.state.write_limiter.allow(
        f"print:{body.tenant_id}:{body.company_id}", limit=240
    ):
        raise PermissionDeniedError("print layout rate limit exceeded")
    result = PrintLayout(
        source="BUILTIN",
        name="Standard Purchase · A4",
        version="purchase-a4@3",
        layout_digest=hashlib.sha256(b"purchase-a4@3").hexdigest(),
    )
    criteria = ResolveTemplateRequest(
        voucher_kind=body.voucher_kind,
        voucher_type_id=body.voucher_type_id,
        currency_code=body.currency_code,
    )
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory() as db:
            if body.preview is not None:
                # Vouchers has already required the person's design read permission; this
                # boundary only proves the version is one this company may print with.
                result = custom(*await previewed(db, body), None, preview=True)
            else:
                for rule in await _candidates(
                    db, company_id=body.company_id, voucher_kind=body.voucher_kind
                ):
                    if not matches(rule, criteria):
                        continue
                    chosen = await _publishable(
                        db,
                        template_id=rule.template_id,
                        company_id=body.company_id,
                        version_id=rule.specific_version_id,
                        voucher_kind=body.voucher_kind,
                    )
                    if chosen is None:
                        continue
                    result = custom(*chosen, rule.id)
                    break
            if result.source == "CUSTOM":
                assets = await printable_assets(
                    db,
                    request.app.state.settings.asset_storage_root,
                    body.company_id,
                    result.layout_definition,
                )
                result = result.model_copy(update={"assets": assets})
    # Canvas coordinates are validated display floats, never monetary values.
    payload = json.dumps(
        result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    # The platform's signed service framing bounds a body at 1 MiB.
    if len(payload) > 1_048_576:
        raise ConflictError("print layout and its images exceed the supported size")
    stamp = int(time.time())
    key = ServiceKey("design", "vouchers", frozenset({OPERATION}), secret)
    return Response(
        payload,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Source-Key-Id": "current",
            "X-Source-Issued-At": str(stamp),
            "X-Source-Signature": sign_service_body(
                key,
                key_id="current",
                operation=OPERATION,
                timestamp=stamp,
                body=service_response_bytes(request_bytes=framed, response_body=payload),
            ),
        },
    )
