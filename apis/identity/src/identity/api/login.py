"""Authenticated self/session operations and the nginx authorization subrequest."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import posixpath
import re
import time
import uuid
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from billing_platform.authz import (
    ScopePath,
    grant_to_wire,
    resolve_permissions,
)
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, ValidationFailedError
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload, jsonable
from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.field_access import CompanyAccess
from identity.api.listing import cursor_codec, keyset_page
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Company, Department, Tenant, User
from identity.schemas.base import PageMeta
from identity.schemas.login import (
    PreferenceUpdate,
    ReasonRequest,
    SessionCompany,
    SessionCompanyChoice,
    SessionCompanyPage,
    SessionDetail,
    SessionGrant,
    SessionTenant,
)
from identity.schemas.user import UserDetail
from identity.services.session_context import can_open, own_company_ids, resolve_company

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute)


async def own_user(db: AsyncSession, current: Actor) -> User:
    row = await db.get(User, current.user_id)
    if row is None:
        raise NotFoundError("user not found")
    return row


@router.get("/v1/session", response_model=SessionDetail, response_model_exclude_unset=True)
async def current_session(
    request: Request,
    company_id: uuid.UUID | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SessionDetail:
    # Authenticated self-read: no permission is granted by resolving one's own session.
    user = await own_user(db, current)
    tenant = await db.get(Tenant, current.tenant_id)
    assert tenant is not None
    # The four-rule chain, and the reasons for its order, live in one place server-side
    # so every client resolves the same company (identity/services/session_context.py).
    selection = await resolve_company(db, request, current, user, company_id)
    company = None
    if selection.company is not None:
        access = await CompanyAccess.load(db, current)
        company = SessionCompany.model_validate(access.project(selection.company, SessionCompany))
    return SessionDetail(
        user=UserDetail.model_validate(user),
        tenant=SessionTenant.model_validate(tenant),
        company=company,
        selected_source=selection.source,
        selected_company_id=selection.selected_company_id,
        step_up_required=selection.step_up_required,
        permissions=sorted(
            resolve_permissions(
                current.grants,
                target=ScopePath(company_id=company.id if company else None),
                on_date=utcnow().date(),
            )
        ),
        grants=[
            SessionGrant(
                permissions=sorted(g.permissions),
                scope_type=g.scope.scope_type,
                scope_id=None if g.scope.scope_id == SCOPE_ALL else g.scope.scope_id,
                valid_from=g.valid_from,
                valid_to=g.valid_to,
            )
            for g in current.grants
        ],
    )


@router.get("/v1/session/companies", response_model=SessionCompanyPage)
async def list_session_companies(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=100),
    company_id: uuid.UUID | None = Query(None, alias="id"),
) -> SessionCompanyPage | JSONResponse:
    """The companies this actor may work in — an authenticated self-read, no permission.

    Not a second company list. ``GET /v1/companies`` answers "describe the companies I
    may read" and requires ``company.read``; this answers "where may I work", which a
    clerk has to be able to ask about their own access (docs/company-context-ui-todo.md
    D2). Rows come from the actor's own grants, so there is nothing here they could not
    already reach, and the projection carries four fields rather than a company's details.
    """
    user = await own_user(db, current)
    access = await CompanyAccess.load(db, current)
    query_fields = {"code", "visibility"}
    if q:
        query_fields.add("display_name")
    # A field denied for read is denied for search too (CLAUDE.md invariant 15), and a
    # prefix search is a read: set membership across two-character prefixes reconstructs a
    # value the projection correctly strips. `gated_by_read=False` because these rows are
    # chosen by any authority in a company, not by `company.read` — the gate the company
    # list's own check relies on (see `CompanyAccess.assert_query`).
    access.assert_query(query_fields, gated_by_read=False)
    statement = select(Company).where(Company.status == "active", Company.visibility == "listed")
    if company_id is not None:
        statement = statement.where(Company.id == company_id)
    allowed = await own_company_ids(db, current)
    if allowed is not None:
        if not allowed:
            return SessionCompanyPage(items=[], page=PageMeta(next_cursor=None, has_more=False))
        statement = statement.where(Company.id.in_(allowed))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        # Only the two fields this list returns. `legal_name` is searched by the company
        # list, which also returns it; searching a field that is never in the response
        # would make it readable one prefix at a time and nowhere else.
        statement = statement.where(
            or_(
                Company.code.like(f"{escaped}%", escape="\\"),
                Company.display_name.like(f"{escaped}%", escape="\\"),
            )
        )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=Company,
        projection=SessionCompanyChoice,
        extra_columns=access.condition_columns,
        page=PageRequest(limit, cursor),
        sort="code",
        allowed=frozenset({"code"}),
        default="code",
        codec=cursor_codec(request, "session-companies", authority_version=access.fingerprint),
    )
    return JSONResponse(
        {
            # `is_default` is a fact about the *user*, not a company column, so the row is
            # projected from explicit values. Read denies still apply to the two text
            # fields, which is why they may be absent from an item (invariant 15).
            "items": [
                access.project(
                    row,
                    SessionCompanyChoice,
                    values={
                        "id": row.id,
                        "code": row.code,
                        "display_name": row.display_name,
                        "requires_step_up": row.requires_step_up,
                        "is_default": row.id == user.default_company_id,
                    },
                )
                for row in rows
            ],
            "page": PageMeta(next_cursor=next_cursor, has_more=has_more).model_dump(),
        }
    )


@router.patch("/v1/session/preferences", response_model=UserDetail)
async def update_preferences(
    body: PreferenceUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> User:
    # Authenticated self-write over an explicit allowlist: presentation, plus the one
    # navigation preference a person sets for themselves — which company to open.
    row = await own_user(db, current)
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationFailedError("unknown timezone") from exc
    if body.default_company_id is not None and not await can_open(
        db, current, body.default_company_id
    ):
        # Same rule the resolution chain applies, so a stored default is one the chain
        # will actually honour. Deliberately a 422 naming the field and not a 404: this
        # endpoint must not become a way to probe which company ids exist.
        raise ValidationFailedError(
            "unknown company",
            fields={"default_company_id": "must be a company you can open in this tenant"},
        )
    changes = {
        key: {"from": jsonable(getattr(row, key)), "to": jsonable(value)}
        for key, value in body.model_dump(exclude_unset=True).items()
        if getattr(row, key) != value
    }
    for key in changes:
        setattr(row, key, getattr(body, key))
    if "default_company_id" in changes and row.default_department_id is not None:
        # A default department belongs to a company, so it cannot survive its company
        # being replaced — the `user` check constraint says as much, and `org` sets the
        # pair together. Cleared here rather than left pointing into another company.
        department = await db.get(Department, row.default_department_id)
        if department is None or department.company_id != row.default_company_id:
            changes["default_department_id"] = {
                "from": jsonable(row.default_department_id),
                "to": None,
            }
            row.default_department_id = None
    if changes:
        row.updated_by = current.user_id
        emit(
            db,
            tenant_id=current.tenant_id,
            aggregate_type="user",
            aggregate_id=row.id,
            event_type="user.preferences_updated",
            payload=audit_payload(
                action="user.preferences_updated",
                category="admin",
                entity_type="user",
                entity_id=row.id,
                actor_user_id=current.user_id,
                changes=changes,
            ),
        )
    await db.flush()
    return row


@router.post("/v1/session/revoke", status_code=204)
async def revoke_own_sessions(
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    row = await own_user(db, current)
    await _revoke(db, current, row, "self sign-out")
    return Response(status_code=204)


async def _revoke(db: AsyncSession, current: Actor, row: User, reason: str) -> None:
    row.tokens_valid_after_at = utcnow()
    row.updated_by = current.user_id
    emit(
        db,
        tenant_id=current.tenant_id,
        aggregate_type="user",
        aggregate_id=row.id,
        event_type="user.sessions_revoked",
        payload=audit_payload(
            action="user.sessions_revoked",
            category="security",
            entity_type="user",
            entity_id=row.id,
            actor_user_id=current.user_id,
            reason=reason,
        ),
    )
    await db.flush()


@router.post("/v1/users/{user_id}/revoke-sessions", status_code=204)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    body: ReasonRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    current.require_scope("user.update", target=ScopePath())
    row = await db.get(User, user_id)
    if row is None:
        raise NotFoundError("user not found")
    await _revoke(db, current, row, body.reason)
    return Response(status_code=204)


@router.get("/internal/v1/gateway/authorize", include_in_schema=False)
async def gateway_authorize(request: Request, current: Actor = Depends(actor)) -> Response:
    # nginx's internal auth_request target. It authenticates; endpoints still authorize.
    # The gateway passes its original company path on an internal-only subrequest.
    original = request.headers.get("x-original-uri", "")
    try:
        raw_path = (
            urlsplit(original).path
            if original.lower().startswith(("http://", "https://"))
            else original.split("?", 1)[0]
        )
        path = unquote(raw_path, errors="strict")
    except (UnicodeError, ValueError) as exc:
        raise ValidationFailedError("invalid gateway URI") from exc
    if "%" in path:
        raise ValidationFailedError("ambiguous gateway URI encoding")
    # Match nginx's decoded path, including dot/slash normalization (Windows too).
    path = posixpath.normpath("/" + path.replace("\\", "/").lstrip("/"))
    company_headers: dict[str, str] = {}
    gateway_grants = current.grants
    match = re.search(r"/companies/([0-9a-fA-F-]{36})(?:/|$)", path)
    if match:
        from billing_platform.db import tenant_scope

        from identity.services.step_up import require_company

        try:
            selected_company = uuid.UUID(match.group(1))
        except ValueError as exc:
            raise ValidationFailedError("invalid company identifier") from exc
        with tenant_scope(current.tenant_id):
            async with request.app.state.session_factory() as db:
                await require_company(db, request, current, selected_company)
                # A user can administer many companies. Sending every company's
                # role repeats hundreds of keys until the bounded header fails.
                # Retain tenant authority and this company's exact scopes only;
                # do not broaden permissions or enlarge the transport bound.
                department_ids = {
                    g.scope.scope_id for g in current.grants if g.scope.scope_type == "department"
                }
                company_departments = (
                    set(
                        await db.scalars(
                            select(Department.id).where(
                                Department.company_id == selected_company,
                                Department.id.in_(department_ids),
                            )
                        )
                    )
                    if department_ids
                    else set()
                )
                gateway_grants = tuple(
                    g
                    for g in current.grants
                    if (
                        g.scope.scope_type == "tenant"
                        or (
                            g.scope.scope_type == "company" and g.scope.scope_id == selected_company
                        )
                        or (
                            g.scope.scope_type == "department"
                            and g.scope.scope_id in company_departments
                        )
                    )
                )
                simple_creation = path.startswith("/catalog/v1/companies/") and path.split("?", 1)[
                    0
                ].split("/")[5:6] in (
                    ["simple-product-creations"],
                    ["simple-product-imports"],
                    ["import-templates"],
                    ["import-jobs"],
                )
                if simple_creation or path.startswith(("/accounting/", "/vouchers/", "/reports/")):
                    from billing_platform.company_context import sign_company_context

                    from identity.services.accounting_context import company_context

                    facts = await company_context(
                        db,
                        current,
                        selected_company,
                        entity_prefix="vouchers."
                        if simple_creation or path.startswith("/vouchers/")
                        else "reports."
                        if path.startswith("/reports/")
                        else "accounting.",
                    )
                    company_token, company_signature = sign_company_context(
                        facts,
                        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
                    )
                    company_headers = {
                        "X-Company-Context": company_token,
                        "X-Company-Signature": company_signature,
                    }
    notification_fields: dict[str, object] = {}
    if path.startswith("/notification/v1/platform/"):
        from identity.api.platform import fresh_platform_actor, platform_actor

        await platform_actor(request, current)
        original_method = request.headers.get("x-original-method", "GET")
        if original_method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValidationFailedError("invalid gateway method")
        if original_method not in {"GET", "HEAD"}:
            await fresh_platform_actor(request, current)
        notification_fields["user_type"] = "platform_notification_operator"
        notification_fields["notification_authority"] = {
            "path": path.removeprefix("/notification"),
            "method": original_method,
        }
    audit_fields: dict[str, object] = {}
    if path.startswith("/audit/"):
        from billing_platform.db import tenant_scope

        from identity.services.audit_context import historical_read_policies, historical_read_scope

        with tenant_scope(current.tenant_id):
            async with request.app.state.session_factory() as db:
                if path == "/audit/v1/platform-events" or path.startswith(
                    "/audit/v1/platform-events/"
                ):
                    from identity.services.platform_audit import gateway_context

                    audit_fields.update(await gateway_context(db, request, current))
                else:
                    audit_fields["audit_scope"] = await historical_read_scope(db, request, current)
                    audit_fields["field_policies"] = await historical_read_policies(db, current)
    support = (
        {
            "actor_user_id": str(current.real_user_id),
            "impersonation_id": str(current.impersonation_id),
            "impersonation_expires_at": current.impersonation_expires_at,
        }
        if current.impersonation_id
        else {}
    )
    body = json.dumps(
        {
            **support,
            **audit_fields,
            **notification_fields,
            "issued_at": int(time.time()),
            "tenant_id": str(current.tenant_id),
            "user_id": str(current.user_id),
            "group_ids": sorted(str(g) for g in current.group_ids),
            # Same canonical grant shape the permission cache uses (authz.grant_to_wire),
            # so the two never drift. The gateway envelope's other fields stay here.
            "grants": [grant_to_wire(g) for g in gateway_grants],
        },
        separators=(",", ":"),
    ).encode()
    if len(body) > 24_000:
        raise ValidationFailedError("resolved gateway context exceeds the transport bound")
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    return Response(
        status_code=204,
        headers={
            "X-Actor-Context": base64.urlsafe_b64encode(body).decode().rstrip("="),
            "X-Actor-Signature": hmac.new(secret, body, hashlib.sha256).hexdigest(),
            "Cache-Control": "no-store",
            **company_headers,
        },
    )
