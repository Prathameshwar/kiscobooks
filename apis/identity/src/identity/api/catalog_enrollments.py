"""Discovery requires an explicit installation-level service capability."""

from billing_platform.db import unfiltered
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError

from identity.api.catalog_sources import (
    SOURCE_HEADERS,
    VerifiedSourceRequest,
    authenticate_source_request,
    signed_response,
)
from identity.schemas.catalog_enrollment import EnrollmentPage, EnrollmentQuery
from identity.services.catalog_enrollment import discover_enrollments

router = APIRouter(
    prefix="/internal/v1/catalog-enrollments",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 422)},
)


async def discovery_scope(request: Request) -> VerifiedSourceRequest:
    return await authenticate_source_request(request, operation="catalog.enrollment.read")


@router.post(
    "",
    response_model=EnrollmentPage,
    operation_id="list_catalog_enrollments",
    openapi_extra={
        **SOURCE_HEADERS,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": EnrollmentQuery.model_json_schema()}},
        },
    },
)
async def list_enrollments(
    request: Request, scope: VerifiedSourceRequest = Depends(discovery_scope)
) -> Response:
    try:
        query = EnrollmentQuery.model_validate_json(request.state.source_raw_body)
    except ValidationError as exc:
        raise ValidationFailedError("invalid enrollment discovery request") from exc
    # Deliberate installation-wide read: the signed Catalog credential explicitly
    # grants discovery. Return only active enrolled scope IDs, never user/company data.
    # The service records this cross-tenant read in the same transaction.
    with unfiltered():
        async with request.app.state.session_factory() as db, db.begin():
            page = await discover_enrollments(
                db, request.app.state.settings, key_id=scope.key_id, query=query
            )
    return signed_response(
        request, scope, page.model_dump(mode="json"), operation="catalog.enrollment.response"
    )
