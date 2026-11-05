"""Signed report-purpose discovery. Never accepts an actor-supplied company list."""

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
from reporting_contract.enrollment import EnrollmentPage, EnrollmentQuery
from sqlalchemy import select

from identity.models import PlatformInstallation, ReportSourceEnrollment
from identity.services.report_enrollment import eligible

router = APIRouter()


# Explicit signed installation capability replaces user authority for identifier discovery.
@router.post("/internal/v1/report-enrollments", response_model=EnrollmentPage)
async def enrollments(request: Request) -> Response:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise ValidationFailedError("enrollment request exceeds its bound")
    if request.query_params:
        raise ValidationFailedError("unsupported enrollment query")
    credentials = request.app.state.settings.report_enrollment_credentials
    configured = credentials.get(request.headers.get("x-source-key-id", ""))
    if configured is None:
        raise PermissionDeniedError("enrollment discovery is unavailable")
    credential, framed, key_id = authenticate_snapshot(
        credentials,
        owner="identity",
        requester=configured.requester,
        headers=request.headers,
        method="POST",
        path=request.url.path,
        query="",
        body=bytes(raw),
    )
    if not credential.allow_enrolled_companies:
        raise PermissionDeniedError("enrollment discovery is not authorised")
    try:
        query = EnrollmentQuery.model_validate_json(raw)
        if (query.tenant_id is None) != (query.company_id is None):
            raise ValueError("scope must be complete")
    except (ValidationError, ValueError) as exc:
        raise ValidationFailedError("invalid report enrollment request") from exc
    codec = CursorCodec(
        request.app.state.settings.cursor_signing_secret.get_secret_value().encode(),
        context=f"report-enrollments:v1:{key_id}:{query.purpose}:{query.tenant_id}:{query.company_id}:{query.limit}",
    )
    statement = eligible(retained=query.purpose == "retained")
    if query.company_id is not None:
        statement = statement.where(
            ReportSourceEnrollment.tenant_id == query.tenant_id,
            ReportSourceEnrollment.company_id == query.company_id,
        )
    if query.cursor:
        values = codec.decode(query.cursor)
        try:
            if set(values) != {"after"}:
                raise ValueError
            after = uuid.UUID(values["after"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationFailedError("invalid enrollment cursor") from exc
        statement = statement.where(ReportSourceEnrollment.id > after)
    with unfiltered():
        async with request.app.state.session_factory.begin() as db:
            rows = list(
                await db.scalars(
                    statement.order_by(ReportSourceEnrollment.id).limit(query.limit + 1)
                )
            )
            platform = await db.scalar(
                select(PlatformInstallation.tenant_id).where(
                    PlatformInstallation.key == "platform",
                    PlatformInstallation.completed_at.is_not(None),
                )
            )
            if platform is None:
                raise PermissionDeniedError("platform installation is unavailable")
            selected = rows[: query.limit]
            evidence = uuid7()
            emit(
                db,
                tenant_id=platform,
                aggregate_type="report_source_enrollment",
                aggregate_id=evidence,
                event_type="report_source.discovery_read",
                payload=audit_payload(
                    action="report_source.discovery_read",
                    category="security",
                    entity_type="report_source_enrollment",
                    entity_id=evidence,
                    actor_user_id=None,
                    changes={"scope_count": {"to": len(selected)}},
                ),
            )
            page = EnrollmentPage(
                scopes=tuple(
                    CompanyServiceScope(tenant_id=r.tenant_id, company_id=r.company_id)
                    for r in selected
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
            credential,
            owner="identity",
            requester=configured.requester,
            key_id=key_id,
            request_bytes=framed,
            body=body,
        ),
    )
