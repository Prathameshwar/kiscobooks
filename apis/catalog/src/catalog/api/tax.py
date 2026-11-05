"""India GST definitions; transaction tax determination remains with Billing."""

import uuid
from typing import Annotated, Any, Literal

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.pricing import exact_pricing_errors
from catalog.api.units import Idempotency, command_response, no_query, unique_query
from catalog.domain.cbic_directory import lookup_hsn_sac, search_hsn_sac
from catalog.models import tax as m
from catalog.models.pricing import PricingRow
from catalog.schemas import tax as s
from catalog.schemas import tax_governance as g
from catalog.schemas import tax_reads as reads
from catalog.schemas.pricing import CommandOutput
from catalog.schemas.tax_defaults import TaxDefaultsInput, TaxDefaultsResult
from catalog.tasks import tax_commands as tasks
from catalog.tasks import tax_governance as governance
from catalog.tasks import tax_impact_reviews as reviews
from catalog.tasks import tax_reads as browse
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import Handler, PricingWork, business_date, command
from catalog.tasks.tax_defaults import bootstrap_tax_defaults
from catalog.tasks.tax_resolution import resolve

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    dependencies=[Depends(exact_pricing_errors)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@router.post("/tax-defaults/bootstrap", response_model=TaxDefaultsResult)
async def bootstrap_defaults(
    company_id: uuid.UUID,
    body: TaxDefaultsInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    no_query(request)
    limit(request, current, company_id)
    result = await bootstrap_tax_defaults(
        request.app.state.session_factory, current, company_id, idempotency_key
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )


@router.get(
    "/tax-administration",
    response_model=s.TaxAdministrationContext,
    operation_id="get_catalog_tax_administration",
)
async def administration_context(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> s.TaxAdministrationContext:
    """Current publication expectations; authenticated company read with no writes."""
    no_query(request)
    context = await ConfigurationAccess(db, current, company_id).context(m.TaxRule)
    state = await policy_state(db, current, company_id)
    return s.TaxAdministrationContext(
        company_id=company_id,
        country_code=context.company.country_code,
        default_tax_system=context.company.default_tax_system,
        timezone=context.company.timezone,
        business_date=business_date(context.company.timezone),
        policy_generation=state.generation if state is not None else 1,
        source_version=context.source_version,
    )


def limit(request: Request, current: Actor, company: uuid.UUID) -> None:
    bucket = "tax:" + current.tenant_id.hex + company.hex + current.user_id.hex
    if not request.app.state.pricing_limiter.allow(bucket, limit=120):
        raise HTTPException(status_code=429, detail="tax write rate exceeded")


async def preview_limit(
    request: Request, company_id: uuid.UUID, current: Actor = Depends(actor)
) -> None:
    """Previews run the whole publication in a savepoint, so they share the write budget.

    A dependency, so the budget is spent before body validation and garbage still counts.
    """
    limit(request, current, company_id)


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    body: Any,
    key: str,
    model: type[PricingRow],
    handler: Handler,
    *,
    object_id: uuid.UUID | None = None,
    action: str = "create",
) -> JSONResponse:
    no_query(request)
    limit(request, current, company)
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
        models=m.TAX_MODELS,
        work_type=tasks.TaxWork,
        publish_permission="tax_rule.publish",
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Idempotency-Replayed": str(result.replayed).lower(), "Cache-Control": "no-store"},
    )


@router.get(
    "/tax-classifications",
    response_model=Page[reads.TaxClassificationListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxclassification",
)
async def list_taxclassification(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxClassification,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-classifications/{object_id}",
    response_model=reads.TaxClassificationDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxclassification",
)
async def get_taxclassification(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxClassification, object_id)


@router.get(
    "/tax-reference/hsn-sac",
    response_model=reads.HsnSacSearchResponse,
    operation_id="search_catalog_cbic_hsn_sac",
    summary="Search CBIC HSN/SAC Directory",
)
async def get_cbic_hsn_sac(
    company_id: uuid.UUID,
    q: Annotated[str | None, Query(description="Search term in code or description")] = None,
    code_system: Annotated[Literal["HSN", "SAC"] | None, Query(description="HSN or SAC")] = None,
    chapter: Annotated[str | None, Query(description="2-digit chapter filter")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    current: Actor = Depends(actor),
) -> reads.HsnSacSearchResponse:
    results = search_hsn_sac(query=q, code_system=code_system, chapter=chapter, limit=limit)
    items = [
        reads.HsnSacReferenceItem(
            code=e.code,
            code_system=e.code_system,
            description=e.description,
            chapter=e.chapter,
            item_kind=e.item_kind,
            gst_rate_default=None,
        )
        for e in results
    ]
    return reads.HsnSacSearchResponse(items=items, count=len(items))


@router.get(
    "/tax-reference/hsn-sac/{code}",
    response_model=reads.HsnSacReferenceItem,
    operation_id="get_catalog_cbic_hsn_sac",
    summary="Get CBIC HSN/SAC Entry by Code",
)
async def get_cbic_hsn_sac_by_code(
    company_id: uuid.UUID,
    code: str,
    current: Actor = Depends(actor),
) -> reads.HsnSacReferenceItem:
    entry = lookup_hsn_sac(code)
    if entry is None:
        raise HTTPException(status_code=404, detail="HSN/SAC code not found in CBIC directory")
    return reads.HsnSacReferenceItem(
        code=entry.code,
        code_system=entry.code_system,
        description=entry.description,
        chapter=entry.chapter,
        item_kind=entry.item_kind,
        gst_rate_default=None,
    )


@router.get(
    "/tax-categories",
    response_model=Page[reads.TaxCategoryListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxcategory",
)
async def list_taxcategory(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxCategory,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-categories/{object_id}",
    response_model=reads.TaxCategoryDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxcategory",
)
async def get_taxcategory(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxCategory, object_id)


@router.get(
    "/tax-rules",
    response_model=Page[reads.TaxRuleListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxrule",
)
async def list_taxrule(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRule,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-rules/{object_id}",
    response_model=reads.TaxRuleDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxrule",
)
async def get_taxrule(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRule, object_id)


@router.get(
    "/tax-rate-series",
    response_model=Page[reads.TaxRateSeriesListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxrateseries",
)
async def list_taxrateseries(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRateSeries,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-rate-series/{object_id}",
    response_model=reads.TaxRateSeriesDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxrateseries",
)
async def get_taxrateseries(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRateSeries, object_id)


@router.get(
    "/tax-rates",
    response_model=Page[reads.TaxRateListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxrate",
)
async def list_taxrate(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRate,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-rates/{object_id}",
    response_model=reads.TaxRateDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxrate",
)
async def get_taxrate(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRate, object_id)


@router.get(
    "/tax-rate-components",
    response_model=Page[reads.TaxRateComponentListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxratecomponent",
)
async def list_taxratecomponent(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRateComponent,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-rate-components/{object_id}",
    response_model=reads.TaxRateComponentDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxratecomponent",
)
async def get_taxratecomponent(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRateComponent, object_id)


@router.get(
    "/tax-scopes",
    response_model=Page[reads.CatalogTaxScopeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_catalogtaxscope",
)
async def list_catalogtaxscope(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.CatalogTaxScope,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-scopes/{object_id}",
    response_model=reads.CatalogTaxScopeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_catalogtaxscope",
)
async def get_catalogtaxscope(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.CatalogTaxScope, object_id)


@router.get(
    "/tax-bindings",
    response_model=Page[reads.CatalogTaxBindingListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_catalogtaxbinding",
)
async def list_catalogtaxbinding(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.CatalogTaxBinding,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-bindings/{object_id}",
    response_model=reads.CatalogTaxBindingDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_catalogtaxbinding",
)
async def get_catalogtaxbinding(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.CatalogTaxBinding, object_id)


@router.get(
    "/item-activations",
    response_model=Page[reads.ItemActivationListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itemactivation",
)
async def list_itemactivation(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.ItemActivation,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-activations/{object_id}",
    response_model=reads.ItemActivationDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itemactivation",
)
async def get_itemactivation(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.ItemActivation, object_id)


@router.get(
    "/item-activation-sources",
    response_model=Page[reads.ItemActivationSourceListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itemactivationsource",
)
async def list_itemactivationsource(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.ItemActivationSource,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-activation-sources/{object_id}",
    response_model=reads.ItemActivationSourceDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itemactivationsource",
)
async def get_itemactivationsource(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.ItemActivationSource, object_id)


@router.get(
    "/item-inventory-profiles",
    response_model=Page[reads.ItemInventoryProfileListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_iteminventoryprofile",
)
async def list_iteminventoryprofile(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.ItemInventoryProfile,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-inventory-profiles/{object_id}",
    response_model=reads.ItemInventoryProfileDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_iteminventoryprofile",
)
async def get_iteminventoryprofile(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.ItemInventoryProfile, object_id)


@router.post(
    "/tax-classifications",
    response_model=CommandOutput,
    status_code=201,
    operation_id="create_classification_catalog",
)
async def create_classification(
    company_id: uuid.UUID,
    body: s.ClassificationInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxClassification,
        tasks.create_classification,
        action="create",
    )


@router.post(
    "/tax-categories",
    response_model=CommandOutput,
    status_code=201,
    operation_id="create_category_catalog",
)
async def create_category(
    company_id: uuid.UUID,
    body: s.CategoryInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxCategory,
        tasks.create_category,
        action="create",
    )


@router.patch(
    "/tax-categories/{object_id}",
    response_model=CommandOutput,
    status_code=200,
    operation_id="patch_category_catalog",
)
async def patch_category(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.MasterPatch,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxCategory,
        tasks.patch_category,
        action="update",
        object_id=object_id,
    )


@router.post(
    "/tax-rules", response_model=CommandOutput, status_code=201, operation_id="create_rule_catalog"
)
async def create_rule(
    company_id: uuid.UUID,
    body: s.RuleInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, key, m.TaxRule, tasks.create_rule, action="create"
    )


@router.patch(
    "/tax-rules/{object_id}",
    response_model=CommandOutput,
    status_code=200,
    operation_id="patch_rule_catalog",
)
async def patch_rule(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: s.RulePatch,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxRule,
        tasks.patch_rule,
        action="update",
        object_id=object_id,
    )


@router.post(
    "/tax-rate-series",
    response_model=CommandOutput,
    status_code=201,
    operation_id="create_series_catalog",
)
async def create_series(
    company_id: uuid.UUID,
    body: s.SeriesInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxRateSeries,
        tasks.create_series,
        action="create",
    )


@router.post(
    "/tax-rates", response_model=CommandOutput, status_code=201, operation_id="publish_rate_catalog"
)
async def publish_rate(
    company_id: uuid.UUID,
    body: s.RateInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, key, m.TaxRate, tasks.publish_rate, action="publish"
    )


@router.post(
    "/tax-scopes",
    response_model=CommandOutput,
    status_code=201,
    operation_id="create_scope_catalog",
)
async def create_scope(
    company_id: uuid.UUID,
    body: s.ScopeInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.CatalogTaxScope,
        tasks.create_scope,
        action="create",
    )


@router.post(
    "/tax-bindings",
    response_model=CommandOutput,
    status_code=201,
    operation_id="publish_binding_catalog",
)
async def publish_binding(
    company_id: uuid.UUID,
    body: s.BindingInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.CatalogTaxBinding,
        tasks.publish_binding,
        action="publish",
    )


@router.post(
    "/tax-rate-previews",
    response_model=s.RatePreview,
    operation_id="preview_catalog_tax_rate",
    dependencies=[Depends(preview_limit)],
)
async def preview_rate(
    company_id: uuid.UUID,
    body: s.RateInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> s.RatePreview:
    no_query(request)
    return await tasks.preview_rate(ConfigurationAccess(db, current, company_id), body)


@router.post(
    "/tax-configurations/resolve",
    response_model=s.Resolution,
    operation_id="resolve_catalog_tax_configuration",
)
async def resolve_tax(
    company_id: uuid.UUID,
    body: s.ResolveInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> s.Resolution:
    no_query(request)
    return await resolve(ConfigurationAccess(db, current, company_id), body)


# Coordinated publications use the same lock, field policies and idempotent executor.


@router.get(
    "/tax-rule-applicabilities",
    response_model=Page[reads.TaxRuleApplicabilityListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxruleapplicability",
)
async def list_taxruleapplicability(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRuleApplicability,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-rule-applicabilities/{object_id}",
    response_model=reads.TaxRuleApplicabilityDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxruleapplicability",
)
async def get_taxruleapplicability(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRuleApplicability, object_id)


@router.get(
    "/tax-releases",
    response_model=Page[reads.TaxReleaseListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxrelease",
)
async def list_taxrelease(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxRelease,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-releases/{object_id}",
    response_model=reads.TaxReleaseDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxrelease",
)
async def get_taxrelease(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxRelease, object_id)


@router.get(
    "/tax-history-actions",
    response_model=Page[reads.TaxHistoryActionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_taxhistoryaction",
)
async def list_taxhistoryaction(
    company_id: uuid.UUID,
    query: Annotated[s.TaxQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await browse.list_rows(
        db,
        current,
        company_id,
        m.TaxHistoryAction,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/tax-history-actions/{object_id}",
    response_model=reads.TaxHistoryActionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_taxhistoryaction",
)
async def get_taxhistoryaction(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await browse.read(db, current, company_id, m.TaxHistoryAction, object_id)


@router.post(
    "/tax-rule-applicabilities",
    response_model=CommandOutput,
    status_code=201,
    operation_id="create_catalog_tax_applicability",
)
async def create_applicability(
    company_id: uuid.UUID,
    body: s.ApplicabilityInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request, current, company_id, body, key, m.TaxRuleApplicability, tasks.create_applicability
    )


@router.post(
    "/tax-release-previews",
    response_model=g.ReleasePreview,
    operation_id="preview_catalog_tax_release",
    dependencies=[Depends(preview_limit)],
)
async def preview_release(
    company_id: uuid.UUID,
    body: g.ReleaseInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> g.ReleasePreview:
    no_query(request)
    return await governance.preview(
        ConfigurationAccess(db, current, company_id),
        body,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/tax-releases",
    response_model=CommandOutput,
    status_code=201,
    operation_id="publish_catalog_tax_release",
)
async def publish_release(
    company_id: uuid.UUID,
    body: g.ReleaseCommit,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    async def handler(
        work: PricingWork, value: g.ReleaseCommit, object_id: uuid.UUID | None
    ) -> PricingRow:
        return await governance.publish(
            work, value, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
        )

    return await write(
        request, current, company_id, body, key, m.TaxRelease, handler, action="publish"
    )


@router.post(
    "/tax-withdrawals",
    response_model=CommandOutput,
    status_code=201,
    operation_id="withdraw_catalog_tax_definition",
)
async def withdraw_definition(
    company_id: uuid.UUID,
    body: g.WithdrawalInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        body,
        key,
        m.TaxHistoryAction,
        governance.withdraw,
        action="publish",
    )


@router.post(
    "/tax-impact-previews",
    response_model=g.TaxImpact,
    operation_id="preview_catalog_tax_impact",
    dependencies=[Depends(preview_limit)],
)
async def preview_impact(
    company_id: uuid.UUID,
    body: g.ImpactQuery,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> g.TaxImpact:
    no_query(request)
    return await governance.impact(ConfigurationAccess(db, current, company_id), body)


@router.post(
    "/tax-impact-reviews",
    response_model=g.ImpactReviewDetail,
    status_code=201,
    operation_id="start_catalog_tax_impact_review",
)
async def start_impact_review(
    company_id: uuid.UUID,
    body: g.ReleaseInput,
    request: Request,
    key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    """Queue a chunked background review for a release too large for a synchronous preview."""
    no_query(request)
    limit(request, current, company_id)
    result = await reviews.start(request.app.state.session_factory, current, company_id, body, key)
    return command_response(request, result, created=True)


@router.get(
    "/tax-impact-reviews/{review_id}",
    response_model=g.ImpactReviewDetail,
    operation_id="get_catalog_tax_impact_review",
)
async def get_impact_review(
    company_id: uuid.UUID,
    review_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> g.ImpactReviewDetail:
    no_query(request)
    return await reviews.read(db, current, company_id, review_id)


@router.get(
    "/tax-impact-reviews/{review_id}/findings",
    response_model=Page[g.ImpactFindingListItem],
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_tax_impact_findings",
)
async def list_impact_findings(
    company_id: uuid.UUID,
    review_id: uuid.UUID,
    query: Annotated[g.ImpactFindingQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[g.ImpactFindingListItem]:
    return await reviews.findings(
        db,
        current,
        company_id,
        review_id,
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
