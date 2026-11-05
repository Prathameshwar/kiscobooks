"""Current-authority Catalog pricing administration; no transaction posting."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from billing_platform.money import MoneyError
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.models import pricing as models
from catalog.schemas import pricing as schemas
from catalog.schemas import pricing_reads as reads
from catalog.schemas.batch_pricing import BatchPricingInput
from catalog.tasks import pricing_foundation as foundation
from catalog.tasks import pricing_publication as publication
from catalog.tasks import pricing_reads as browse
from catalog.tasks import pricing_references as references
from catalog.tasks.pricing_commands import Handler, command
from catalog.tasks.pricing_resolution import resolve


async def exact_pricing_errors() -> AsyncIterator[None]:
    try:
        yield
    except MoneyError as exc:
        raise ValidationFailedError(
            "price or quantity does not fit its exact numeric rules"
        ) from exc


async def verified_batch(
    request: Request, current: Actor, company: uuid.UUID, item: uuid.UUID, lot: uuid.UUID
) -> dict[str, Any]:
    from billing_platform.authz import ScopePath
    from billing_platform.errors import PermissionDeniedError

    from catalog.tasks.simple_creation_transport import CreationOwners

    current.require_scope("price_plan.read", target=ScopePath(company_id=company))
    result = await CreationOwners(
        request.app, request.headers, request.app.state.settings.simple_creation_origins
    ).call("accounting", "GET", f"/v1/companies/{company}/stock-tracking/batches/{lot}")
    if (
        result.get("id"),
        result.get("company_id"),
        result.get("item_id"),
        result.get("status"),
        result.get("is_held"),
    ) != (str(lot), str(company), str(item), "ACTIVE", False):
        raise PermissionDeniedError("An active batch of this company and product is required")
    return result


router = APIRouter(
    prefix="/v1/companies/{company_id}",
    dependencies=[Depends(exact_pricing_errors)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    body: Any,
    key: str,
    model: type[models.PricingRow],
    handler: Handler,
    object_id: uuid.UUID | None = None,
    action: str = "create",
) -> JSONResponse:
    no_query(request)
    bucket = current.tenant_id.hex + company.hex + current.user_id.hex
    if not request.app.state.pricing_limiter.allow(bucket, limit=120):
        raise HTTPException(status_code=429, detail="pricing write rate exceeded")
    result = await command(
        request.app.state.session_factory,
        current,
        company,
        model,
        body,
        key,
        handler,
        object_id=object_id,
        action=action,
        timeout_seconds=60 if isinstance(body, BatchPricingInput) else None,
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )


@router.get(
    "/price-levels",
    response_model=Page[reads.PriceLevelListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_price_level",
)
async def list_price_level(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.PriceLevel,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-levels/{object_id}",
    response_model=reads.PriceLevelDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_price_level",
)
async def get_price_level(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.PriceLevel, object_id)


@router.get(
    "/price-plans",
    response_model=Page[reads.PricePlanListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_price_plan",
)
async def list_price_plan(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.PricePlan,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-plans/{object_id}",
    response_model=reads.PricePlanDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_price_plan",
)
async def get_price_plan(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.PricePlan, object_id)


@router.get(
    "/company-pricing-policies",
    response_model=Page[reads.CompanyPricingPolicyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_company_pricing_policy",
)
async def list_company_pricing_policy(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.CompanyPricingPolicy,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/company-pricing-policies/{object_id}",
    response_model=reads.CompanyPricingPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_company_pricing_policy",
)
async def get_company_pricing_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.CompanyPricingPolicy, object_id)


@router.get(
    "/price-scopes",
    response_model=Page[reads.ItemPriceScopeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_scope",
)
async def list_item_price_scope(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceScope,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-scopes/{object_id}",
    response_model=reads.ItemPriceScopeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_scope",
)
async def get_item_price_scope(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceScope, object_id)


@router.get(
    "/price-numeric-revisions",
    response_model=Page[reads.ItemPriceNumericRevisionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_numeric_revision",
)
async def list_item_price_numeric_revision(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceNumericRevision,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-numeric-revisions/{object_id}",
    response_model=reads.ItemPriceNumericRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_numeric_revision",
)
async def get_item_price_numeric_revision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceNumericRevision, object_id)


@router.get(
    "/price-series",
    response_model=Page[reads.ItemPriceSeriesListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_series",
)
async def list_item_price_series(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceSeries,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-series/{object_id}",
    response_model=reads.ItemPriceSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_series",
)
async def get_item_price_series(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceSeries, object_id)


@router.get(
    "/price-drafts",
    response_model=Page[reads.ItemPriceDraftListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_draft",
)
async def list_item_price_draft(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceDraft,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-drafts/{object_id}",
    response_model=reads.ItemPriceDraftDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_draft",
)
async def get_item_price_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceDraft, object_id)


@router.get(
    "/prices",
    response_model=Page[reads.ItemPriceListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price",
)
async def list_item_price(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPrice,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/prices/{object_id}",
    response_model=reads.ItemPriceDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price",
)
async def get_item_price(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPrice, object_id)


@router.get(
    "/price-tiers",
    response_model=Page[reads.ItemPriceTierListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_tier",
)
async def list_item_price_tier(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceTier,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-tiers/{object_id}",
    response_model=reads.ItemPriceTierDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_tier",
)
async def get_item_price_tier(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceTier, object_id)


@router.get(
    "/purchase-price-terms",
    response_model=Page[reads.PurchasePriceTermListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_purchase_price_term",
)
async def list_purchase_price_term(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.PurchasePriceTerm,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/purchase-price-terms/{object_id}",
    response_model=reads.PurchasePriceTermDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_purchase_price_term",
)
async def get_purchase_price_term(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.PurchasePriceTerm, object_id)


@router.get(
    "/reference-costs",
    response_model=Page[reads.ItemReferenceCostListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_reference_cost",
)
async def list_item_reference_cost(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemReferenceCost,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/reference-costs/{object_id}",
    response_model=reads.ItemReferenceCostDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_reference_cost",
)
async def get_item_reference_cost(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemReferenceCost, object_id)


@router.get(
    "/product-mrps",
    response_model=Page[reads.ItemMrpListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_mrp",
)
async def list_item_mrp(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemMrp,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-mrps/{object_id}",
    response_model=reads.ItemMrpDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_mrp",
)
async def get_item_mrp(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemMrp, object_id)


@router.get(
    "/price-formulas",
    response_model=Page[reads.ItemPriceFormulaListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_price_formula",
)
async def list_item_price_formula(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemPriceFormula,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/price-formulas/{object_id}",
    response_model=reads.ItemPriceFormulaDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_price_formula",
)
async def get_item_price_formula(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemPriceFormula, object_id)


@router.get(
    "/commercial-policy-scopes",
    response_model=Page[reads.CommercialPolicyScopeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_commercial_policy_scope",
)
async def list_commercial_policy_scope(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.CommercialPolicyScope,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/commercial-policy-scopes/{object_id}",
    response_model=reads.CommercialPolicyScopeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_commercial_policy_scope",
)
async def get_commercial_policy_scope(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.CommercialPolicyScope, object_id)


@router.get(
    "/commercial-guard-rules",
    response_model=Page[reads.CommercialGuardRuleListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_commercial_guard_rule",
)
async def list_commercial_guard_rule(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.CommercialGuardRule,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/commercial-guard-rules/{object_id}",
    response_model=reads.CommercialGuardRuleDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_commercial_guard_rule",
)
async def get_commercial_guard_rule(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.CommercialGuardRule, object_id)


@router.get(
    "/discount-ceilings",
    response_model=Page[reads.DiscountCeilingListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_discount_ceiling",
)
async def list_discount_ceiling(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.DiscountCeiling,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/discount-ceilings/{object_id}",
    response_model=reads.DiscountCeilingDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_discount_ceiling",
)
async def get_discount_ceiling(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.DiscountCeiling, object_id)


@router.get(
    "/item-commercial-policies",
    response_model=Page[reads.ItemCommercialPolicyListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_item_commercial_policy",
)
async def list_item_commercial_policy(
    company_id: uuid.UUID,
    query: Annotated[schemas.PricingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        models.ItemCommercialPolicy,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-commercial-policies/{object_id}",
    response_model=reads.ItemCommercialPolicyDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_item_commercial_policy",
)
async def get_item_commercial_policy(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, models.ItemCommercialPolicy, object_id)


@router.post(
    "/pricing/bootstrap",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="bootstrap_catalog_pricing",
)
async def bootstrap(
    company_id: uuid.UUID,
    body: schemas.BootstrapInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, idempotency_key, models.PriceLevel, foundation.bootstrap
    )


@router.post(
    "/price-levels",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_level_catalog_pricing",
)
async def create_level(
    company_id: uuid.UUID,
    body: schemas.LevelCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.PriceLevel,
        foundation.create_level,
    )


@router.post(
    "/price-plans",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_plan_catalog_pricing",
)
async def create_plan(
    company_id: uuid.UUID,
    body: schemas.PlanCreate,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.PricePlan,
        foundation.create_plan,
    )


@router.post(
    "/company-pricing-policies",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_policy_catalog_pricing",
)
async def create_policy(
    company_id: uuid.UUID,
    body: schemas.PolicyInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.CompanyPricingPolicy,
        foundation.create_policy,
    )


@router.post(
    "/price-scopes",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_scope_catalog_pricing",
)
async def create_scope(
    company_id: uuid.UUID,
    body: schemas.ScopeInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceScope,
        foundation.create_scope,
    )


@router.post(
    "/price-numeric-revisions",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_numeric_catalog_pricing",
)
async def create_numeric(
    company_id: uuid.UUID,
    body: schemas.NumericInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceNumericRevision,
        foundation.create_numeric,
    )


@router.post(
    "/price-series",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_series_catalog_pricing",
)
async def create_series(
    company_id: uuid.UUID,
    body: schemas.SeriesInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceSeries,
        foundation.create_series,
    )


@router.patch(
    "/price-levels/{object_id}",
    response_model=schemas.CommandOutput,
    operation_id="update_catalog_price_level",
)
async def update_level(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schemas.LevelPatch,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.PriceLevel,
        foundation.update_level,
        object_id,
        "update",
    )


@router.post(
    "/price-drafts",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_price_draft_catalog_pricing",
)
async def create_price_draft(
    company_id: uuid.UUID,
    body: schemas.DraftInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceDraft,
        publication.save_draft,
    )


@router.post(
    "/reference-costs",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_reference_cost_catalog_pricing",
)
async def create_reference_cost(
    company_id: uuid.UUID,
    body: schemas.CostInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemReferenceCost,
        references.create_cost,
    )


@router.post(
    "/product-mrps",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_product_mrp_catalog_pricing",
)
async def create_product_mrp(
    company_id: uuid.UUID,
    body: schemas.MrpInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, idempotency_key, models.ItemMrp, references.create_mrp
    )


@router.post(
    "/commercial-guard-rules",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_commercial_guard_catalog_pricing",
)
async def create_commercial_guard(
    company_id: uuid.UUID,
    body: schemas.GuardInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.CommercialGuardRule,
        references.create_guard,
    )


@router.post(
    "/commercial-policy-scopes",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_commercial_scope_catalog_pricing",
)
async def create_commercial_scope(
    company_id: uuid.UUID,
    body: schemas.CommercialScopeInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.CommercialPolicyScope,
        references.create_commercial_scope,
    )


@router.post(
    "/discount-ceilings",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_discount_ceiling_catalog_pricing",
)
async def create_discount_ceiling(
    company_id: uuid.UUID,
    body: schemas.DiscountInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.DiscountCeiling,
        references.create_discount,
    )


@router.post(
    "/item-commercial-policies",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="create_item_commercial_catalog_pricing",
)
async def create_item_commercial(
    company_id: uuid.UUID,
    body: schemas.CommercialInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemCommercialPolicy,
        references.create_commercial,
    )


@router.put(
    "/price-drafts/{object_id}",
    response_model=schemas.CommandOutput,
    operation_id="replace_catalog_price_draft",
)
async def replace_price_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schemas.DraftReplace,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceDraft,
        publication.save_draft,
        object_id,
        "update",
    )


@router.get(
    "/price-drafts/{object_id}/preview",
    response_model=schemas.DraftPreview,
    operation_id="preview_catalog_price_draft",
)
async def preview_price_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> schemas.DraftPreview:
    no_query(request)
    return await publication.preview(db, current, company_id, object_id)


@router.post(
    "/price-drafts/{object_id}/publish",
    response_model=schemas.CommandOutput,
    status_code=201,
    operation_id="publish_catalog_price_draft",
)
async def publish_price_draft(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schemas.PublishInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.ItemPriceDraft,
        publication.publish,
        object_id,
        "publish",
    )


@router.post(
    "/prices/resolve", response_model=schemas.PriceResolution, operation_id="resolve_catalog_price"
)
async def resolve_price(
    company_id: uuid.UUID,
    body: schemas.ResolveInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> schemas.PriceResolution:
    no_query(request)
    if body.lot_id is not None:
        await verified_batch(request, current, company_id, body.item_id, body.lot_id)
    return await resolve(db, current, company_id, body)


@router.post(
    "/prices/coverage",
    response_model=schemas.PriceResolution,
    operation_id="coverage_catalog_price",
)
async def price_coverage(
    company_id: uuid.UUID,
    body: schemas.ResolveInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> schemas.PriceResolution:
    no_query(request)
    if body.lot_id is not None:
        await verified_batch(request, current, company_id, body.item_id, body.lot_id)
    return await resolve(db, current, company_id, body, coverage=True)


@router.post(
    "/batch-prices",
    response_model=schemas.CommandOutput,
    operation_id="create_initial_batch_prices",
)
async def create_initial_batch_prices(
    company_id: uuid.UUID,
    body: BatchPricingInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    from billing_platform.authz import ScopePath

    from catalog.tasks.batch_pricing import publish_initial

    no_query(request)
    current.require_scope("price_plan.manage", target=ScopePath(company_id=company_id))
    current.require_scope("price_plan.publish", target=ScopePath(company_id=company_id))
    verified = await verified_batch(request, current, company_id, body.item_id, body.lot_id)

    async def publish_batch(
        work: Any, value: BatchPricingInput, object_id: uuid.UUID | None
    ) -> models.PricingRow:
        return await publish_initial(work, value, verified)

    return await write(
        request, current, company_id, body, key, models.ItemPriceScope, publish_batch
    )


@router.patch(
    "/price-plans/{object_id}",
    response_model=schemas.CommandOutput,
    operation_id="update_catalog_price_plan",
)
async def update_plan(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: schemas.PlanPatch,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        idempotency_key,
        models.PricePlan,
        foundation.update_plan,
        object_id,
        "update",
    )
