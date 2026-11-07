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
OWNER = "identity"


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
                from identity.services.catalog_enrollment import is_enrolled

                enrolled = await is_enrolled(db, company_id)
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
) -> tuple[dict[str, Any], uuid.UUID | None]:
    from identity.models import CommercialSalesperson, Company
    from identity.services.customization import contract, definitions

    version = None
    if entity == "company":
        from identity.events.catalog_source import lock_current_generation

        # The same tenant fence used by company/feature writers precedes all source reads.
        version = await db.run_sync(lambda sync: lock_current_generation(sync, tenant_id))
    company = await db.get(Company, company_id)
    if (
        company is None
        or company.status != "active"
        or entity not in {"company", "vouchers.voucher", "vouchers.voucher_item", "salesperson"}
    ):
        raise ValidationFailedError("source company or entity unavailable")
    if entity == "company":
        from identity.models.company_feature import CompanyFeature

        enabled = set(
            await db.scalars(
                select(CompanyFeature.feature_key).where(
                    CompanyFeature.company_id == company_id,
                    CompanyFeature.is_enabled.is_(True),
                )
            )
        )
        return {
            "message_id": str(uuid7()),
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "definitions": [],
            "masters": [
                {
                    "entity_type": "company",
                    "source_id": str(company_id),
                    "source_version": version,
                    "status": "ACTIVE",
                    "facts": {
                        key: key in enabled
                        for key in (
                            "inventory",
                            "bom_definitions",
                            "approval_workflow",
                            "multi_currency",
                        )
                    },
                }
            ],
        }, None
    if entity == "salesperson":
        statement = select(CommercialSalesperson).where(
            CommercialSalesperson.company_id == company_id
        )
        if after is not None:
            statement = statement.where(CommercialSalesperson.id > after)
        salespeople = list(
            await db.scalars(statement.order_by(CommercialSalesperson.id).limit(limit + 1))
        )
        sales_selected = salespeople[:limit]
        return {
            "message_id": str(uuid7()),
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "definitions": [],
            "masters": [
                {
                    "entity_type": "salesperson",
                    "source_id": str(row.id),
                    "source_version": row.row_version,
                    "status": "ACTIVE" if row.is_active else "RETIRED",
                    "facts": {
                        "code": row.code,
                        "name": row.name,
                        "user_id": str(row.user_id) if row.user_id else None,
                    },
                }
                for row in sales_selected
            ],
        }, sales_selected[-1].id if len(salespeople) > limit else None
    rows = sorted(await definitions(db, company_id, entity), key=lambda row: row.id)
    if after:
        rows = [row for row in rows if row.id > after]
    selected = rows[:limit]
    bundle = {
        "message_id": str(uuid7()),
        "tenant_id": str(tenant_id),
        "company_id": str(company_id),
        "definitions": [
            {
                "entity_type": entity,
                "source_version": int(row.updated_at.timestamp() * 1000000),
                "definition": contract(row).model_dump(mode="json"),
                "presentation": {"label": row.label, "help_text": row.help_text},
            }
            for row in selected
        ],
        "masters": [],
    }
    return bundle, selected[-1].id if len(rows) > limit else None
