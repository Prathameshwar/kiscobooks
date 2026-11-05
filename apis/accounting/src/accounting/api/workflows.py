"""Import preview/application, protected exports and retained master history."""

import uuid
from typing import Annotated

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import NotFoundError
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import (
    ERROR_RESPONSES,
    Idempotency,
    no_query,
    response,
    session,
    unique_query,
)
from accounting.events.evidence import access_event
from accounting.financial_resources import FINANCIAL_BY_PATH
from accounting.models.workflows import MasterRevision
from accounting.resources import BY_PATH
from accounting.schemas.query import HistoryQuery, MasterQuery
from accounting.schemas.workflows import (
    HistoryItem,
    ImportApply,
    ImportPreview,
    ImportRequest,
    ImportResult,
)
from accounting.tasks import imports
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.reads import listing

router = APIRouter(prefix="/v1/companies/{company_id}", responses=ERROR_RESPONSES)


@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(
    company_id: uuid.UUID, body: ImportRequest, request: Request, current: Access = Depends(access)
) -> ImportPreview:
    no_query(request)
    return await imports.preview(
        request.app.state.session_factory, current, body, request.app.state.settings
    )


@router.post("/imports/apply", response_model=ImportResult)
async def apply_import(
    company_id: uuid.UUID,
    body: ImportApply,
    request: Request,
    idempotency_key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await imports.apply(
            request.app.state.session_factory,
            current,
            body,
            request.app.state.settings,
            idempotency_key,
        ),
    )


async def export_records(
    company_id: uuid.UUID,
    resource: str,
    request: Request,
    query: Annotated[MasterQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> JSONResponse:
    current.actor.require_scope("accounting.export.read", target=ScopePath(company_id=company_id))
    spec = (BY_PATH | FINANCIAL_BY_PATH).get(resource)
    if spec is None:
        raise NotFoundError("export resource not found")
    result = await listing(
        db,
        current,
        spec,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        spec.detail,
    )
    access_event(db, current, spec, "export", count=len(result.items))
    return JSONResponse(
        result.model_dump(mode="json", exclude_unset=True), headers={"Cache-Control": "no-store"}
    )


@router.get(
    "/history/{resource}/{object_id}",
    response_model=Page[HistoryItem],
    dependencies=[Depends(unique_query)],
)
async def history(
    company_id: uuid.UUID,
    resource: str,
    object_id: uuid.UUID,
    request: Request,
    query: Annotated[HistoryQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[HistoryItem]:
    current.actor.require_scope("accounting.history.read", target=ScopePath(company_id=company_id))
    spec = (BY_PATH | FINANCIAL_BY_PATH).get(resource)
    if spec is None:
        raise NotFoundError("history resource not found")
    authorize(current, spec, "read")
    await company_object(db, spec.model, object_id, company_id=company_id)
    # Revisions do not contain historical field values. Conservatively omit names
    # covered by any applicable read deny, including conditional ones.
    allowed = readable(current, spec)
    model = MasterRevision
    fields = frozenset(HistoryItem.model_fields)
    statement = select(*(getattr(model, key).label(key) for key in fields)).where(
        model.company_id == company_id, model.entity_type == spec.name, model.object_id == object_id
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=fields,
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"history:{current.actor.tenant_id}:{company_id}:{resource}:{object_id}:{query.limit}:{query.sort}:{authority_fingerprint(current)}",
    )
    return await fetch_page(
        db,
        statement,
        query=ListQuery.model_validate(query.model_dump()),
        terms=terms,
        codec=codec,
        project=lambda row: HistoryItem.model_validate(
            dict(row)
            | {
                "created_at": row["created_at"].isoformat(),
                "changed_fields": [key for key in row["changed_fields"] if key in allowed],
            }
        ),
    )
