"""Signed source-company discovery for the explicitly enabled Vouchers installation."""

import uuid

from billing_platform.db import unfiltered
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from billing_platform.owner_snapshot import authenticate_snapshot, response_headers
from billing_platform.pagination import CursorCodec
from billing_platform.service_auth import CompanyServiceScope
from fastapi import APIRouter, Request, Response
from pydantic import ValidationError
from sqlalchemy import select

from identity.models.catalog_enrollment import CatalogSourceEnrollment
from identity.models.platform_installation import PlatformInstallation
from identity.schemas.catalog_enrollment import EnrollmentPage, EnrollmentQuery
from identity.services.catalog_enrollment import active_enrollments

router = APIRouter()


# Internal service authentication, not a user or public enumeration endpoint.
@router.post("/internal/v1/voucher-enrollments", response_model=EnrollmentPage)
async def enrollments(request: Request) -> Response:
    raw = await request.body()
    if len(raw) > 8192 or request.query_params:
        raise ValidationFailedError("unsupported voucher enrollment request")
    credential, framed, key_id = authenticate_snapshot(
        request.app.state.settings.voucher_snapshot_credentials,
        owner="identity",
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query="",
        body=raw,
    )
    if not credential.allow_enrolled_companies:
        raise PermissionDeniedError("voucher enrollment discovery is not authorised")
    try:
        query = EnrollmentQuery.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid voucher enrollment query") from exc
    codec = CursorCodec(
        request.app.state.settings.cursor_signing_secret.get_secret_value().encode(),
        context=f"voucher-enrollments:v1:{key_id}:{query.limit}",
    )
    statement = active_enrollments()
    if query.cursor:
        values = codec.decode(query.cursor)
        try:
            if set(values) != {"after"}:
                raise ValueError
            after = uuid.UUID(values["after"])
            if not after.int:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationFailedError("invalid voucher enrollment cursor") from exc
        statement = statement.where(CatalogSourceEnrollment.id > after)
    # Deliberate installation-wide identifier discovery for this signed service
    # capability. The native company-create enrollment and active tenant/company
    # predicates decide eligibility. Record this cross-tenant read atomically.
    with unfiltered():
        async with request.app.state.session_factory() as db, db.begin():
            rows = list(
                await db.scalars(
                    statement.order_by(CatalogSourceEnrollment.id).limit(query.limit + 1)
                )
            )
            operating_tenant = await db.scalar(
                select(PlatformInstallation.tenant_id).where(
                    PlatformInstallation.key == "platform",
                    PlatformInstallation.completed_at.is_not(None),
                )
            )
            if operating_tenant is None:
                raise PermissionDeniedError("platform installation is unavailable")
            selected = rows[: query.limit]
            evidence_id = uuid7()
            emit(
                db,
                tenant_id=operating_tenant,
                aggregate_type="voucher_source_enrollment",
                aggregate_id=evidence_id,
                event_type="voucher_source.discovery_read",
                payload=audit_payload(
                    action="voucher_source.discovery_read",
                    category="security",
                    entity_type="voucher_source_enrollment",
                    entity_id=evidence_id,
                    actor_user_id=None,
                    changes={"scope_count": {"from": None, "to": len(selected)}},
                ),
            )
            page = EnrollmentPage(
                scopes=tuple(
                    CompanyServiceScope(tenant_id=row.tenant_id, company_id=row.company_id)
                    for row in selected
                ),
                next_cursor=codec.encode({"after": str(selected[-1].id)})
                if len(rows) > query.limit
                else None,
            )
    body = canonical_json(page.model_dump(mode="json"))
    return Response(
        body,
        media_type="application/json",
        headers=response_headers(
            credential, owner="identity", key_id=key_id, request_bytes=framed, body=body
        ),
    )
