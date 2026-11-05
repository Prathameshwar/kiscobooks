"""Stock source selectors read immutable report facts under complete authority."""

import uuid
from typing import Annotated, Literal

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from fastapi import Depends, Query, Request
from reporting_contract.inventory import Coverage
from sqlalchemy import select

from reports.api.auth import Access, access
from reports.api.framework import resolve, router
from reports.api.routes import codec
from reports.models.core import ReportGeneration
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import SourceView
from reports.schemas.stock_summary import StockReference, StockReferencePage
from reports.tasks.common import get


@router.get("/report-generations/{identity}/inventory", response_model=StockReferencePage)
async def stock_source(
    company_id: uuid.UUID,
    identity: uuid.UUID,
    request: Request,
    current: Annotated[Access, Depends(access)],
    kind: Literal["ITEM", "LOCATION", "GROUP", "LOT"] = "ITEM",
    q: Annotated[str, Query(max_length=120)] = "",
    object_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> StockReferencePage:
    resolve(current, "STOCK_SUMMARY")
    if set(request.query_params) - {"kind", "q", "object_id", "item_id", "cursor", "limit"} or len(
        request.query_params
    ) != len(request.query_params.multi_items()):
        raise ValidationFailedError("unsupported stock reference query")
    if item_id is not None and kind != "LOT":
        raise ValidationFailedError("an item scope applies only to batch choices")
    signer = codec(
        request, current, f"inventory:{identity}:{kind}:{q.strip()}:{object_id}:{item_id}:{limit}"
    )
    try:
        after = uuid.UUID(signer.decode(cursor)["id"]) if cursor else None
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationFailedError("invalid stock reference cursor") from exc
    with tenant_scope(current.actor.tenant_id):
        async with request.app.state.session_factory() as db:
            generation = await get(db, company_id, ReportGeneration, identity)
            cut = await db.scalar(
                select(ReportSourceCut).where(
                    ReportSourceCut.company_id == company_id,
                    ReportSourceCut.generation_id == identity,
                )
            )
            if generation.status != "READY" or cut is None or cut.verification is None:
                raise ConflictError("Stock Summary requires a verified source snapshot")
            view = SourceView(company_id, cut.epoch_id, cut.sequence)
            coverage_rows = list(
                await db.scalars(
                    view.rows("inventory_report_record")
                    .where(ReportFactVersion.inventory_kind == "COVERAGE")
                    .limit(2)
                )
            )
            if len(coverage_rows) != 1 or coverage_rows[0].data is None:
                raise ConflictError(
                    "a complete inventory snapshot is unavailable; refresh stock data"
                )
            coverage = Coverage.model_validate(coverage_rows[0].data["payload"])
            if not coverage.native_stock_current:
                raise ConflictError("native stock changed; prepare a fresh inventory snapshot")
            key = {
                "ITEM": "item_id",
                "LOCATION": "location_id",
                "GROUP": "group_id",
                "LOT": "lot_id",
            }[kind]
            payload = ReportFactVersion.data["payload"]
            object_key = payload[key].as_string()
            code_key = payload["lot_code" if kind == "LOT" else "code"].as_string()
            name_key = code_key if kind == "LOT" else payload["name"].as_string()
            query = (
                view.rows("inventory_report_record")
                .with_only_columns(object_key, code_key, name_key)
                .where(
                    ReportFactVersion.inventory_kind == ("POSITION" if kind == "LOT" else kind),
                    object_key.is_not(None),
                )
                .distinct()
            )
            if after:
                query = query.where(object_key > str(after))
            if item_id:
                query = query.where(payload["item_id"].as_string() == str(item_id))
            if object_id:
                query = query.where(object_key == str(object_id))
            if q.strip():
                escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                query = query.where(
                    code_key.ilike("%" + escaped + "%", escape="\\")
                    | name_key.ilike("%" + escaped + "%", escape="\\")
                )
            found = list((await db.execute(query.order_by(object_key).limit(limit + 1))).all())
            choices = []
            for row in found[:limit]:
                if row[1] is None or row[2] is None:
                    raise ConflictError("stock master source is unavailable")
                choices.append(StockReference(id=row[0], code=row[1], name=row[2]))
    return StockReferencePage(
        generation_id=identity,
        coverage=coverage,
        items=choices,
        next_cursor=signer.encode({"id": str(choices[-1].id)}) if len(found) > limit else None,
    )
