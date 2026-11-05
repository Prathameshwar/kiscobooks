import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.domain.readiness import CAPABILITIES, SOURCE_REQUIREMENTS
from catalog.models.projections import CompanyProjection, ProjectionCheckpoint
from catalog.schemas.identity_source import CONTRACT
from catalog.schemas.readiness import CapabilityStatus, CatalogReadiness, SourceStatus

router = APIRouter(
    prefix="/v1",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 422, 500)},
)


@router.get(
    "/companies/{company_id}/catalog-readiness",
    response_model=CatalogReadiness,
    operation_id="get_catalog_readiness",
    description=(
        "Implementation and verified source readiness; missing dependencies remain explicit."
    ),
)
async def catalog_readiness(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CatalogReadiness:
    current.require("item.read")
    current.require_scope("item.read", target=ScopePath(company_id=company_id))
    if request.query_params:
        raise ValidationFailedError("this endpoint accepts no query parameters")
    checkpoint = await db.scalar(
        select(ProjectionCheckpoint)
        .where(
            ProjectionCheckpoint.company_id == company_id,
            ProjectionCheckpoint.source_key == CONTRACT,
        )
        .with_for_update(read=True)
    )
    verified = bool(
        checkpoint is not None
        and checkpoint.status == "ready"
        and checkpoint.expires_at is not None
        and checkpoint.expires_at > utcnow()
    )
    if verified:
        verified = (
            await db.scalar(
                select(CompanyProjection.id).where(
                    CompanyProjection.company_id == company_id,
                    CompanyProjection.source_id == company_id,
                )
            )
            is not None
        )
    sources = [SourceStatus.model_validate(source) for source in SOURCE_REQUIREMENTS]
    for source in sources:
        if source.owner == "identity":
            source.status = (
                "ready" if verified else "stale" if checkpoint is not None else "unavailable"
            )
    return CatalogReadiness(
        company_id=company_id,
        company_verified=verified,
        sources=sources,
        capabilities=[CapabilityStatus.model_validate(capability) for capability in CAPABILITIES],
    )
