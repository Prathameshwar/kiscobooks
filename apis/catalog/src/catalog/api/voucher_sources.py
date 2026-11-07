"""Signed, scoped owner facts for Vouchers; never a cross-service database read."""

import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import (
    authenticate_snapshot,
    require_snapshot_scope,
    response_headers,
)
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
OWNER = "catalog"


# Service authentication: explicit Vouchers credential plus company grant.
@router.get(
    "/internal/v1/voucher-sources/{tenant_id}/{company_id}/{entity}", include_in_schema=False
)
async def voucher_sources(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    entity: str,
    request: Request,
    after: uuid.UUID | None = None,
    limit: int = Query(default=128, ge=1, le=128),
) -> Response:
    credential, framed, key_id = authenticate_snapshot(
        request.app.state.settings.voucher_snapshot_credentials,
        owner=OWNER,
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        body=await request.body(),
    )
    if set(request.query_params) - {"after", "limit"} or len(request.query_params) != len(
        request.query_params.multi_items()
    ):
        raise ValidationFailedError("unsupported snapshot query")
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            enrolled = False
            if credential.allow_enrolled_companies:
                from catalog.models.projections import CompanyProjection
                from catalog.tasks.projections import require_identity_context

                await require_identity_context(db, company_id)
                enrolled = (
                    await db.scalar(
                        select(CompanyProjection.id).where(
                            CompanyProjection.company_id == company_id,
                            CompanyProjection.source_id == company_id,
                            CompanyProjection.status == "active",
                        )
                    )
                    is not None
                )
            require_snapshot_scope(
                credential, tenant_id=tenant_id, company_id=company_id, enrolled=enrolled
            )
            bundle, next_after = await facts(db, tenant_id, company_id, entity, after, limit)
    body = canonical_json({"bundle": bundle, "next_after": str(next_after) if next_after else None})
    return Response(
        body,
        media_type="application/json",
        headers=response_headers(
            credential, owner=OWNER, key_id=key_id, request_bytes=framed, body=body
        ),
    )


async def facts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    entity: str,
    after: uuid.UUID | None,
    limit: int,
    item_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], uuid.UUID | None]:
    from catalog.models.commercial import ProductTypeRevision
    from catalog.models.products import Item, ProductFamily
    from catalog.models.regulatory import ItemRegulatoryClassification
    from catalog.models.tax import ItemInventoryProfile
    from catalog.models.units import UnitOfMeasure

    if entity == "item_unit_revision":
        from catalog.tasks.voucher_unit_sources import unit_revision_facts

        masters, next_after = await unit_revision_facts(db, company_id, after, limit, item_id)
        return {
            "message_id": str(uuid7()),
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "definitions": [],
            "masters": masters,
        }, next_after
    if entity not in {"item", "item_transaction_policy", "unit", "item_regulatory_classification"}:
        raise ValidationFailedError("unsupported Catalog source entity")
    model: Any = {
        "item": Item,
        "item_transaction_policy": Item,
        "unit": UnitOfMeasure,
        "item_regulatory_classification": ItemRegulatoryClassification,
    }[entity]
    statement = select(model).where(model.company_id == company_id)
    if unit_id is not None:
        if entity != "unit" or item_id is not None:
            raise ValidationFailedError("unit source selection requires only a unit entity")
        statement = statement.where(model.id == unit_id)
    if item_id is not None:
        if entity in {"item", "item_transaction_policy"}:
            statement = statement.where(model.id == item_id)
        elif entity == "item_regulatory_classification":
            statement = statement.where(model.item_id == item_id)
        else:
            raise ValidationFailedError("item source selection is unavailable for this entity")
    if after:
        statement = statement.where(model.id > after)
    rows = list(await db.scalars(statement.order_by(model.id).limit(limit + 1)))
    selected = rows[:limit]
    families = {}
    types = {}
    profiles = set()
    if entity == "item_transaction_policy" and selected:
        families = {
            row.id: row
            for row in await db.scalars(
                select(ProductFamily).where(
                    ProductFamily.company_id == company_id,
                    ProductFamily.id.in_([item.family_id for item in selected]),
                )
            )
        }
        types = {
            row.id: row
            for row in await db.scalars(
                select(ProductTypeRevision).where(
                    ProductTypeRevision.company_id == company_id,
                    ProductTypeRevision.id.in_(
                        [family.product_type_revision_id for family in families.values()]
                    ),
                )
            )
        }
        profiles = set(
            await db.scalars(
                select(ItemInventoryProfile.item_id).where(
                    ItemInventoryProfile.company_id == company_id,
                    ItemInventoryProfile.item_id.in_([item.id for item in selected]),
                )
            )
        )
        if len(families) != len({item.family_id for item in selected}) or len(types) != len(
            {family.product_type_revision_id for family in families.values()}
        ):
            raise ValidationFailedError("item transaction source is incomplete")
    bundle = {
        "message_id": str(uuid7()),
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "definitions": [],
        "masters": [
            {
                "entity_type": entity,
                "source_id": str(row.id),
                "source_version": (
                    (row.row_version << 32) + families[row.family_id].row_version
                    if entity == "item_transaction_policy"
                    else row.row_version
                ),
                "status": "ACTIVE"
                if (
                    row.status == "ACTIVE" and families[row.family_id].status == "ACTIVE"
                    if entity == "item_transaction_policy"
                    else row.status == "ACTIVE"
                    if entity == "item"
                    else row.is_active
                    if entity == "unit"
                    else True
                )
                else "RETIRED",
                "facts": (
                    {
                        "item_id": str(row.item_id),
                        "valid_from": row.valid_from.isoformat(),
                        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                        "product_kind": row.product_kind,
                        "licence_class": row.licence_class,
                        "prescription_schedule": row.prescription_schedule,
                        "food_category_code": row.food_category_code,
                        "source_sha256": row.source_sha256,
                        "reviewed_by": str(row.reviewed_by),
                        "reviewed_at": row.reviewed_at.isoformat(),
                    }
                    if entity == "item_regulatory_classification"
                    else {
                        "kind": families[row.family_id].kind,
                        "item_version": row.row_version,
                        "inventory_mode": (
                            "STOCK"
                            if row.id in profiles
                            else "NON_STOCK"
                            if families[row.family_id].kind == "SERVICE"
                            or "NON_STOCK"
                            in types[
                                families[row.family_id].product_type_revision_id
                            ].inventory_modes
                            else "UNAVAILABLE"
                        ),
                        "sellable": row.sellable,
                        "purchasable": row.purchasable,
                    }
                    if entity == "item_transaction_policy"
                    else {"base_unit_id": str(row.base_unit_id)}
                    if entity == "item"
                    else {
                        "dimension": row.dimension,
                        "decimal_places": row.decimal_places,
                        "quantity_increment": str(row.quantity_increment),
                    }
                    if entity == "unit"
                    else {}
                ),
            }
            for row in selected
        ],
    }
    return bundle, selected[-1].id if len(rows) > limit else None
