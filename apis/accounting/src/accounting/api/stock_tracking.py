"""Batch/serial registration and controlled metadata; no stock-posting endpoints."""

import asyncio
import datetime as dt
import uuid
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ErrorEnvelope
from billing_platform.idempotency import has_retained_command
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import Idempotency, no_query, response, session, unique_query
from accounting.models.stock_tracking import StockTrackingEvent
from accounting.schemas import stock_tracking as s
from accounting.schemas.query import FieldDescription, FieldSet
from accounting.stock_resources import BATCH, SERIAL, STOCK_POSITION, STOCK_SAFE_FIELDS
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.reads import field_set
from accounting.tasks.stock_tracking import command, command_identity, detail, listing
from accounting.tasks.stock_tracking_source import TrackingSourceUnavailableError, tracking_source

router = APIRouter(
    prefix="/v1/companies/{company_id}/stock-tracking",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)
ResourceKind = Literal["batches", "serials"]
Lifecycle = Literal["hold", "release", "retire", "reactivate"]


@router.post("/serials/check-identifiers", response_model=s.SerialIdentityCheckResult)
async def serial_identity_check(
    company_id: uuid.UUID,
    body: s.SerialIdentityCheck,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> s.SerialIdentityCheckResult:
    from accounting.tasks.serial_input_check import check_identifiers

    no_query(request)
    await check_identifiers(db, current, body)
    return s.SerialIdentityCheckResult()


async def source(
    request: Request, current: Access, item: uuid.UUID, *, include_identifiers: bool = True
) -> s.TrackingSource:
    if current.context.finance is None:
        raise TrackingSourceUnavailableError("verified company date settings are required")
    day = dt.datetime.now(ZoneInfo(current.context.finance.timezone)).date()
    try:
        async with asyncio.timeout(10):
            return await tracking_source(
                request.app.state.settings,
                current,
                item,
                day,
                request.headers.get("authorization"),
                request.headers.get("x-company-step-up"),
                include_identifiers=include_identifiers,
            )
    except TimeoutError as exc:
        raise TrackingSourceUnavailableError("product tracking verification timed out") from exc


@router.get("/context/{item_id}", response_model=s.TrackingSource)
async def context(
    company_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    resource: Literal["batches", "serials", "stock"] = "serials",
    current: Access = Depends(access),
) -> s.TrackingSource:
    unique_query(request)
    if set(request.query_params) - {"resource"}:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("unsupported tracking context query")
    authorize(
        current,
        STOCK_POSITION if resource == "stock" else BATCH if resource == "batches" else SERIAL,
        "read",
    )
    return await source(request, current, item_id, include_identifiers=resource == "serials")


@router.get(
    "/batches",
    response_model=Page[s.BatchListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def batches(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[s.BatchQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        BATCH,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/serials",
    response_model=Page[s.SerialListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
)
async def serials(
    company_id: uuid.UUID,
    request: Request,
    query: Annotated[s.SerialQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await listing(
        db,
        current,
        SERIAL,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get("/{resource}/field-set", response_model=FieldSet)
async def fields(
    company_id: uuid.UUID,
    resource: ResourceKind,
    request: Request,
    current: Access = Depends(access),
    action: Literal["prepare", "correct", "hold", "release", "retire", "reactivate"] = "prepare",
) -> FieldSet:
    unique_query(request)
    if set(request.query_params) - {"action"}:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("unsupported field-set query")
    spec = BATCH if resource == "batches" else SERIAL
    if action == "prepare":
        result = field_set(current, spec)
        from accounting.schemas.metadata import resolved_schema

        known = {field.key for field in result.fields}
        definitions = resolved_schema(spec.detail)["properties"]
        allowed = readable(current, spec)
        return result.model_copy(
            update={
                "fields": [
                    *result.fields,
                    *[
                        FieldDescription(
                            key=key,
                            label=key.replace("_", " ").capitalize(),
                            required=False,
                            visible=True,
                            readable=key in allowed,
                            writable=False,
                            definition=value,
                        )
                        for key, value in definitions.items()
                        if key not in known
                    ],
                ]
            }
        )
    authorize(current, spec, "read")
    from billing_platform.field_policy import denied_fields

    from accounting.schemas.metadata import resolved_schema
    from accounting.tasks.access import permission, rules

    form = s.BatchCorrect if action == "correct" and resource == "batches" else s.ExpectedVersion
    definitions = resolved_schema(form)["properties"]
    target = ScopePath(company_id=company_id)
    can_write = current.actor.allows_scope(
        permission(spec, "hold" if action in {"hold", "release"} else "manage"), target=target
    )
    policy = rules(current, spec, None)
    denied = denied_fields(form.model_fields, rules=policy, access="write", target=target)
    hidden = denied_fields(form.model_fields, rules=policy, access="read", target=target)
    return FieldSet(
        resource=spec.path,
        fields=[
            FieldDescription(
                key=key,
                label=key.replace("_", " ").capitalize(),
                required=value.is_required(),
                visible=True,
                readable=key not in hidden,
                writable=can_write and key not in denied,
                definition=definitions[key],
            )
            for key, value in form.model_fields.items()
        ],
    )


@router.get(
    "/{resource}/{object_id}",
    response_model=s.BatchDetail | s.SerialDetail,
    response_model_exclude_unset=True,
)
async def record(
    company_id: uuid.UUID,
    resource: ResourceKind,
    object_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await detail(db, current, BATCH if resource == "batches" else SERIAL, object_id)


@router.post(
    "/batches", response_model=s.BatchDetail, response_model_exclude_unset=True, status_code=201
)
async def prepare_batch(
    company_id: uuid.UUID,
    body: s.BatchPrepare,
    request: Request,
    key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    authorize(current, BATCH, "read")
    authorize(current, BATCH, "manage")
    retained = await has_retained_command(
        request.app.state.session_factory, command_identity(current, BATCH, body, key, "prepare")
    )
    facts = (
        None
        if retained
        else await source(request, current, body.item_id, include_identifiers=False)
    )
    return response(
        request,
        await command(
            request.app.state.session_factory, current, BATCH, body, key, "prepare", source=facts
        ),
    )


@router.post(
    "/serials", response_model=s.SerialDetail, response_model_exclude_unset=True, status_code=201
)
async def prepare_serial(
    company_id: uuid.UUID,
    body: s.SerialPrepare,
    request: Request,
    key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    authorize(current, SERIAL, "read")
    authorize(current, SERIAL, "manage")
    retained = await has_retained_command(
        request.app.state.session_factory, command_identity(current, SERIAL, body, key, "prepare")
    )
    facts = None if retained else await source(request, current, body.item_id)
    return response(
        request,
        await command(
            request.app.state.session_factory, current, SERIAL, body, key, "prepare", source=facts
        ),
    )


@router.patch(
    "/batches/{object_id}", response_model=s.BatchDetail, response_model_exclude_unset=True
)
async def correct_batch(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.BatchCorrect,
    request: Request,
    key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory, current, BATCH, body, key, "correct", object_id
        ),
    )


@router.post(
    "/{resource}/{object_id}/{action}",
    response_model=s.BatchDetail | s.SerialDetail,
    response_model_exclude_unset=True,
)
async def lifecycle(
    company_id: uuid.UUID,
    resource: ResourceKind,
    object_id: uuid.UUID,
    action: Lifecycle,
    body: s.ExpectedVersion,
    request: Request,
    key: Idempotency,
    current: Access = Depends(access),
) -> JSONResponse:
    no_query(request)
    return response(
        request,
        await command(
            request.app.state.session_factory,
            current,
            BATCH if resource == "batches" else SERIAL,
            body,
            key,
            action,
            object_id,
        ),
    )


@router.get(
    "/{resource}/{object_id}/history",
    response_model=Page[s.TrackingEventItem],
    dependencies=[Depends(unique_query)],
)
async def history(
    company_id: uuid.UUID,
    resource: ResourceKind,
    object_id: uuid.UUID,
    request: Request,
    query: Annotated[ListQuery, Query()],
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> Page[s.TrackingEventItem]:
    spec = BATCH if resource == "batches" else SERIAL
    await detail(db, current, spec, object_id)
    # Reason is an authored field and may be protected independently.
    from billing_platform.field_policy import denied_fields

    from accounting.tasks.access import rules

    denied = denied_fields(
        {"reason", "created_by"},
        rules=rules(current, spec, None),
        access="read",
        target=ScopePath(company_id=company_id),
    )

    columns = [StockTrackingEvent.id, StockTrackingEvent.action, StockTrackingEvent.created_at]
    if "reason" not in denied:
        columns.append(StockTrackingEvent.reason)
    if "created_by" not in denied:
        columns.append(StockTrackingEvent.created_by)
    statement = select(*columns).where(
        StockTrackingEvent.company_id == company_id,
        StockTrackingEvent.target_id == object_id,
        StockTrackingEvent.resource == ("BATCH" if resource == "batches" else "SERIAL"),
    )
    if query.q:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("history does not support text search")
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={"id": SortColumn(StockTrackingEvent.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = CursorCodec(
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context=f"stock-history:{current.actor.tenant_id}:{company_id}:{current.actor.user_id}:{resource}:{object_id}:{authority_fingerprint(current)}:{query.model_dump_json(exclude={'cursor'})}",
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=codec,
        project=lambda row: s.TrackingEventItem.model_validate(dict(row)),
    )


@router.get(
    "/{resource}/{object_id}/history/{event_id}",
    response_model=s.TrackingEventDetail,
    response_model_exclude_unset=True,
)
async def history_event(
    company_id: uuid.UUID,
    resource: ResourceKind,
    object_id: uuid.UUID,
    event_id: uuid.UUID,
    request: Request,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> s.TrackingEventDetail:
    no_query(request)
    spec = BATCH if resource == "batches" else SERIAL
    await detail(db, current, spec, object_id)
    event = await company_object(db, StockTrackingEvent, event_id, company_id=company_id)
    if event.target_id != object_id or event.resource != (
        "BATCH" if resource == "batches" else "SERIAL"
    ):
        from billing_platform.errors import NotFoundError

        raise NotFoundError("tracking event is unavailable")
    row = await company_object(db, spec.model, object_id, company_id=company_id)
    from accounting.tasks.stock_tracking import values

    native = values(row, spec)
    before = native | {key: change.get("from") for key, change in event.evidence.items()}
    after = native | {key: change.get("to") for key, change in event.evidence.items()}
    allowed = (
        readable(current, spec, native)
        & readable(current, spec, before)
        & readable(current, spec, after)
    )
    result = s.TrackingEventDetail(
        id=event.id,
        action=event.action,
        created_at=event.created_at,
        changes=[
            s.TrackingChange(
                field=key,
                **(
                    {"before": change.get("from"), "after": change.get("to")}
                    if key in STOCK_SAFE_FIELDS
                    else {}
                ),
            )
            for key, change in event.evidence.items()
            if key in allowed
        ],
    )
    # Reasons and actors use their own field policy, even when the target's identity is readable.
    from billing_platform.field_policy import denied_fields

    from accounting.tasks.access import rules

    denied = denied_fields(
        {"reason", "created_by"},
        rules=rules(current, spec, native),
        access="read",
        target=ScopePath(company_id=company_id),
    )
    if "reason" not in denied:
        result.reason = event.reason
    if "created_by" not in denied:
        result.created_by = event.created_by
    return result
