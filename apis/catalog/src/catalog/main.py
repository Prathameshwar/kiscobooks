"""Catalog foundation: scoped API, truthful readiness and uniform safe error responses."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from billing_platform.db import create_engine, create_session_factory
from billing_platform.diagnostics import log_failure, safe_trace_id
from billing_platform.errors import ErrorBody, ErrorEnvelope, PlatformError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from catalog.api.activation import router as activation_router
from catalog.api.advanced_product_creation import router as advanced_creation_router
from catalog.api.attribute_sets import router as attribute_sets_router
from catalog.api.attributes import router as attributes_router
from catalog.api.bom_assignments import router as bom_assignments_router
from catalog.api.bom_definitions import router as bom_definitions_router
from catalog.api.bom_options import router as bom_options_router
from catalog.api.boms import router as boms_router
from catalog.api.bulk import router as bulk_router
from catalog.api.classification import router as classification_router
from catalog.api.commercial import router as commercial_router
from catalog.api.commercial_history import router as commercial_history_router
from catalog.api.configuration import router as configuration_router
from catalog.api.customer_pricing import router as customer_pricing_router
from catalog.api.field_adoption import router as field_adoption_router
from catalog.api.field_indexes import router as field_indexes_router
from catalog.api.field_metadata import router as field_metadata_router
from catalog.api.handling import router as handling_router
from catalog.api.handling_revisions import router as handling_revisions_router
from catalog.api.identifier_masters import router as identifier_masters_router
from catalog.api.inventory_revisions import router as inventory_revisions_router
from catalog.api.inventory_templates import router as inventory_templates_router
from catalog.api.manufacturing_operation_revisions import (
    router as manufacturing_operation_revisions_router,
)
from catalog.api.manufacturing_operations import router as manufacturing_operations_router
from catalog.api.manufacturing_route_revisions import router as manufacturing_route_revisions_router
from catalog.api.manufacturing_routes import router as manufacturing_routes_router
from catalog.api.master_aliases import router as master_aliases_router
from catalog.api.master_external_keys import router as master_external_keys_router
from catalog.api.master_imports import router as master_imports_router
from catalog.api.master_usage import router as master_usage_router
from catalog.api.options import router as options_router
from catalog.api.pricing import router as pricing_router
from catalog.api.product_authoring import router as product_authoring_router
from catalog.api.product_mode import router as product_mode_router
from catalog.api.products import router as products_router
from catalog.api.profiles import router as profiles_router
from catalog.api.promotion_limit_revisions import router as promotion_limit_revisions_router
from catalog.api.promotion_limits import router as promotion_limits_router
from catalog.api.promotion_stacks import router as promotion_stacks_router
from catalog.api.regulatory import router as regulatory_router
from catalog.api.releases import router as releases_router
from catalog.api.return_revisions import router as return_revisions_router
from catalog.api.returns import router as returns_router
from catalog.api.routes import router
from catalog.api.sales_channels import router as sales_channels_router
from catalog.api.scheme_governance import router as scheme_governance_router
from catalog.api.simple_product_creation import router as simple_creation_router
from catalog.api.simple_product_import import router as simple_import_router
from catalog.api.simple_product_setup import router as simple_product_setup_router
from catalog.api.simple_products import router as simple_products_router
from catalog.api.stock_report_sources import router as stock_report_sources_router
from catalog.api.stock_sources import router as stock_sources_router
from catalog.api.tax import router as tax_router
from catalog.api.unit_relations import router as unit_relations_router
from catalog.api.units import router as units_router
from catalog.api.warehouse_groups import router as warehouse_groups_router
from catalog.api.warehouse_policies import router as warehouse_policies_router
from catalog.api.warehouses import router as warehouses_router
from catalog.api.warranties import router as warranties_router
from catalog.api.warranty_revisions import router as warranty_revisions_router
from catalog.config import Settings
from catalog.domain.field_registry import registry
from catalog.metadata import MIGRATION_HEAD, TABLES
from catalog.models import (
    AttributeDefinition,
    AttributeOption,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
    Brand,
    BrandManufacturer,
    BrandSeries,
    CategoryScheme,
    CompanyProductAuthoringConfiguration,
    ItemCategory,
    ItemGroup,
    ItemGroupParent,
    Manufacturer,
    ManufacturerSite,
    PackType,
    ProductType,
    ProductTypeRevision,
    UnitConversion,
    UnitOfMeasure,
    UnitTaxCode,
)
from catalog.models.boms import BOM_MODELS
from catalog.models.bulk import BULK_MODELS
from catalog.models.configuration import CONFIGURATION_MODELS
from catalog.models.handling import HandlingProfile, HandlingProfileRevision
from catalog.models.identifier_masters import IdentifierNamespace, IdentifierType
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import (
    ManufacturingRoute,
    ManufacturingRouteRevision,
    ManufacturingRouteStep,
)
from catalog.models.master_references import MasterAlias, MasterExternalKey
from catalog.models.pricing import PRICING_MODELS
from catalog.models.product_definitions import PRODUCT_DEFINITION_MODELS
from catalog.models.product_stock_choice import ItemStockChoice
from catalog.models.products import Item, ProductFamily
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.promotion_authoring import PROMOTION_AUTHORING_MODELS
from catalog.models.promotion_limits import PROMOTION_LIMIT_MODELS
from catalog.models.promotions import PROMOTION_MODELS
from catalog.models.regulatory import ItemRegulatoryClassification
from catalog.models.releases import RELEASE_MODELS
from catalog.models.returns import ReturnPolicy, ReturnPolicyCondition, ReturnPolicyRevision
from catalog.models.sales_channel import SalesChannel
from catalog.models.tax import ACTIVATION_MODELS, TAX_MODELS
from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouse_policies import WAREHOUSE_POLICY_MODELS
from catalog.models.warehouses import (
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseBin,
    WarehouseOperationPolicyRevision,
)
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision


def _trace_id(request: Request) -> str | None:
    return safe_trace_id(request.headers.get("x-trace-id"))


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorBody(
        code=code,
        message=message,
        trace_id=_trace_id(request),
    )
    return JSONResponse(
        status_code=status, content=ErrorEnvelope(error=body).model_dump(exclude_none=True)
    )


class _FailureBoundary:
    """Stop private exception text escaping to the server's default traceback log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            request = Request(scope)
            log_failure(
                logging.getLogger("catalog.http"),
                service="catalog",
                event="http.unexpected_failure",
                error=exc,
                trace_id=_trace_id(request),
            )
            if started:
                # Status is already on the wire; abort without leaking the original error.
                raise RuntimeError("response stream failed") from None
            await _error(request, 500, "internal_error", "request could not be completed")(
                scope, receive, send
            )


def create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None) -> FastAPI:
    # BaseSettings resolves required fields from CATALOG_* environment variables.
    configuration = settings or Settings()  # type: ignore[call-arg]
    problems = registry.validate_against_models(
        {
            model.__name__: model
            for model in (
                *BULK_MODELS,
                *BOM_MODELS,
                *PROMOTION_AUTHORING_MODELS,
                *PROMOTION_LIMIT_MODELS,
                *PROMOTION_MODELS,
                *CONFIGURATION_MODELS,
                CompanyProductAuthoringConfiguration,
                *PRODUCT_DEFINITION_MODELS,
                ItemStockChoice,
                *PRICING_MODELS,
                *TAX_MODELS,
                *ACTIVATION_MODELS,
                Warehouse,
                WarehouseBin,
                CompanyWarehouseConfiguration,
                WarehouseOperationPolicyRevision,
                WarehouseGroup,
                WarehouseGroupParent,
                WarehouseGroupAssignment,
                *WAREHOUSE_POLICY_MODELS,
                *RELEASE_MODELS,
                ProductFamily,
                Item,
                ItemRegulatoryClassification,
                MasterAlias,
                MasterExternalKey,
                UnitOfMeasure,
                PackType,
                IdentifierType,
                IdentifierNamespace,
                UnitConversion,
                UnitTaxCode,
                ItemGroup,
                ItemGroupParent,
                CategoryScheme,
                ItemCategory,
                AttributeDefinition,
                AttributeOption,
                AttributeSet,
                AttributeSetRevision,
                AttributeSetMember,
                IdentifierProfile,
                IdentifierProfileRequirement,
                InventoryProfileTemplate,
                InventoryProfileTemplateRevision,
                ManufacturingRoute,
                ManufacturingRouteRevision,
                ManufacturingRouteStep,
                ManufacturingOperation,
                ManufacturingOperationRevision,
                WarrantyPolicy,
                WarrantyPolicyRevision,
                HandlingProfile,
                HandlingProfileRevision,
                SalesChannel,
                ReturnPolicy,
                ReturnPolicyRevision,
                ReturnPolicyCondition,
                Brand,
                BrandSeries,
                Manufacturer,
                ManufacturerSite,
                BrandManufacturer,
                ProductType,
                ProductTypeRevision,
            )
        }
    )
    if problems:
        raise RuntimeError("Catalog native field registry differs from its models")
    database = engine if engine is not None else create_engine(configuration.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is None:
                await database.dispose()

    app = FastAPI(title="Catalog API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(_FailureBoundary)
    app.state.settings = configuration
    app.state.engine = database
    app.state.session_factory = create_session_factory(database, guarded=True)
    from catalog.api.voucher_sources import router as voucher_sources_router

    app.include_router(voucher_sources_router)
    app.include_router(router)
    app.include_router(configuration_router)
    app.include_router(product_mode_router)
    app.include_router(simple_products_router)
    app.include_router(simple_product_setup_router)
    app.include_router(bulk_router)
    app.include_router(master_imports_router)
    app.include_router(simple_import_router)
    app.include_router(products_router)
    from billing_platform.rate_limit import WindowLimiter

    app.state.pricing_limiter = WindowLimiter()
    app.include_router(pricing_router)
    app.include_router(product_authoring_router)
    app.include_router(scheme_governance_router)
    app.include_router(master_aliases_router)
    app.include_router(master_usage_router)
    app.include_router(master_external_keys_router)
    app.include_router(classification_router)
    app.include_router(attributes_router)
    app.include_router(profiles_router)
    app.include_router(identifier_masters_router)
    app.include_router(inventory_templates_router)
    app.include_router(inventory_revisions_router)
    app.include_router(manufacturing_routes_router)
    app.include_router(bom_options_router)
    app.include_router(boms_router)
    app.include_router(promotion_limits_router)
    app.include_router(promotion_limit_revisions_router)
    app.include_router(promotion_stacks_router)
    app.include_router(bom_definitions_router)
    app.include_router(bom_assignments_router)
    app.include_router(manufacturing_route_revisions_router)
    app.include_router(manufacturing_operations_router)
    app.include_router(manufacturing_operation_revisions_router)
    app.include_router(warranties_router)
    app.include_router(warranty_revisions_router)
    app.include_router(returns_router)
    app.include_router(return_revisions_router)
    app.include_router(handling_router)
    app.include_router(handling_revisions_router)
    app.include_router(sales_channels_router)
    app.include_router(customer_pricing_router)
    app.include_router(attribute_sets_router)
    app.include_router(commercial_router)
    app.include_router(commercial_history_router)
    app.include_router(field_metadata_router)
    app.include_router(field_indexes_router)
    app.include_router(field_adoption_router)
    app.include_router(options_router)
    app.include_router(tax_router)
    app.include_router(activation_router)
    app.include_router(simple_creation_router)
    app.include_router(advanced_creation_router)
    app.include_router(units_router)
    app.include_router(unit_relations_router)
    app.include_router(warehouses_router)
    app.include_router(warehouse_groups_router)
    app.include_router(warehouse_policies_router)
    app.include_router(releases_router)
    app.include_router(regulatory_router)
    app.include_router(stock_sources_router)
    app.include_router(stock_report_sources_router)

    @app.exception_handler(PlatformError)
    async def platform_error(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(_trace_id(request)).model_dump(mode="json", exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's input/context may contain secrets; never serialize it to the caller.
        return _error(request, 422, "validation_failed", "request validation failed")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _error(request, exc.status_code, "http_error", "request could not be handled")

    # Public infrastructure probes return no tenant data, secrets or database details.
    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(configuration.database_check_timeout_seconds):
                async with database.connect() as connection:
                    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                    if not (TABLES | {"alembic_version"}) <= set(names):
                        raise RuntimeError("foundation schema is incomplete")
                    heads = (
                        (await connection.execute(text("SELECT version_num FROM alembic_version")))
                        .scalars()
                        .all()
                    )
                    if heads != [MIGRATION_HEAD]:
                        raise RuntimeError("foundation migration version differs")
        except (SQLAlchemyError, RuntimeError, TimeoutError):
            return _error(request, 503, "dependency_unavailable", "database is not ready")
        return JSONResponse({"status": "ready"})

    from billing_platform.request_logging import RequestCorrelation

    app.add_middleware(RequestCorrelation)
    return app
