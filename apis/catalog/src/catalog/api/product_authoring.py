"""Native product authoring routes; all mutations require item authority and idempotency."""

import uuid
from typing import Annotated, Literal, cast

from billing_platform.errors import ErrorEnvelope
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.auth import actor
from catalog.api.dependencies import session
from catalog.api.units import Idempotency, no_query, unique_query
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.schemas import product_definition_reads as responses
from catalog.schemas.attribute_forms import ProductAttributeForm
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.schemas.effective_item import (
    EffectiveItemFacts,
    EffectiveUnit,
    InventorySelection,
    StockExecutionReadiness,
)
from catalog.schemas.product_authoring import (
    AdoptionCommit,
    AdoptionPreview,
    AdoptionQuery,
    AttributeAssignmentInput,
    AuthoringQuery,
    AuthoringResult,
    BarcodeGenerateInput,
    BarcodeInput,
    BarcodeResolution,
    BarcodeResolveInput,
    BarcodeStateInput,
    CategoryAssignmentInput,
    FamilyAttributesInput,
    GroupAssignmentInput,
    ManufacturerAssignmentInput,
    ProductRequirements,
    QuantityPreviewInput,
    QuantityPreviewResult,
    UnitBindingInput,
    UnitRevisionInput,
    VariantInput,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks import (
    barcode_lookup,
    product_adoption,
    product_attributes,
    product_classification,
    product_quantity,
    product_stock_choice,
    product_units,
)
from catalog.tasks.product_attributes import bounded
from catalog.tasks.product_commands import Handler, ProductWork, execute
from catalog.tasks.product_definition_reads import RESOURCES, list_rows, read
from catalog.tasks.product_requirements import (
    configuration,
    current_rows,
    group_on,
    product_work,
    requirements,
)
from catalog.tasks.regulatory import effective as effective_regulatory

router = APIRouter(
    prefix="/v1/companies/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post(
    "/items/{object_id}/barcode-state",
    response_model=AuthoringResult,
    operation_id="set_catalog_barcode_state",
)
async def set_barcode_state(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BarcodeStateInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "barcode_state",
        product_units.barcode_state,
        item=True,
    )


async def write(
    request: Request,
    current: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    body: ExpectedVersion,
    key: str,
    action: str,
    handler: Handler,
    item: bool = False,
) -> JSONResponse:
    no_query(request)
    result = await execute(
        request.app.state.session_factory,
        current,
        company,
        object_id,
        body,
        key,
        action,
        handler,
        item=item,
    )
    return JSONResponse(
        status_code=result.status,
        content=result.value.model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "Idempotency-Replayed": str(result.replayed).lower()},
    )


@router.post(
    "/product-families/{object_id}/groups",
    response_model=AuthoringResult,
    operation_id="assign_group_catalog_product",
)
async def assign_group(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: GroupAssignmentInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "assign_group",
        product_classification.assign_group,
        item=False,
    )


@router.put(
    "/product-families/{object_id}/categories",
    response_model=AuthoringResult,
    operation_id="assign_categories_catalog_product",
)
async def assign_categories(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: CategoryAssignmentInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    async def commit_categories(work: ProductWork, incoming: CategoryAssignmentInput) -> None:
        await product_classification.assign_categories(
            work,
            incoming,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        )

    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "assign_categories",
        commit_categories,
        item=False,
    )


@router.post(
    "/product-families/{object_id}/manufacturers",
    response_model=AuthoringResult,
    operation_id="assign_manufacturer_catalog_product",
)
async def assign_manufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: ManufacturerAssignmentInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "assign_manufacturer",
        product_classification.assign_manufacturer,
        item=False,
    )


@router.put(
    "/product-families/{object_id}/attributes",
    response_model=AuthoringResult,
    operation_id="configure_attributes_catalog_product",
)
async def configure_attributes(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: FamilyAttributesInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "configure_attributes",
        product_attributes.configure_family,
        item=False,
    )


@router.post(
    "/product-families/{object_id}/variants",
    response_model=AuthoringResult,
    operation_id="create_variant_catalog_product",
)
async def create_variant(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: VariantInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "create_variant",
        product_attributes.create_variant,
        item=False,
    )


@router.put(
    "/items/{object_id}/attributes",
    response_model=AuthoringResult,
    operation_id="assign_attributes_catalog_product",
)
async def assign_attributes(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AttributeAssignmentInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "assign_attributes",
        product_attributes.assign_values,
        item=True,
    )


@router.post(
    "/items/{object_id}/unit-bindings",
    response_model=AuthoringResult,
    operation_id="bind_unit_catalog_product",
)
async def bind_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: UnitBindingInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "bind_unit",
        product_units.bind_unit,
        item=True,
    )


@router.post(
    "/items/{object_id}/unit-revisions",
    response_model=AuthoringResult,
    operation_id="revise_unit_catalog_product",
)
async def revise_unit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: UnitRevisionInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "revise_unit",
        product_units.bind_unit,
        item=True,
    )


@router.post(
    "/items/{object_id}/barcodes",
    response_model=AuthoringResult,
    operation_id="create_barcode_catalog_product",
)
async def create_barcode(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BarcodeInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "create_barcode",
        product_units.add_barcode,
        item=True,
    )


@router.post(
    "/items/{object_id}/barcodes/generate",
    response_model=AuthoringResult,
    operation_id="generate_internal_catalog_barcode",
)
async def generate_barcode(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: BarcodeGenerateInput,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "generate_barcode",
        product_units.generate_barcode,
        item=True,
    )


@router.post(
    "/barcodes/resolve",
    response_model=BarcodeResolution,
    operation_id="resolve_catalog_barcode_scan",
)
async def resolve_barcode_scan(
    company_id: uuid.UUID,
    body: BarcodeResolveInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BarcodeResolution:
    no_query(request)
    return await barcode_lookup.resolve(db, current, company_id, body)


@router.get(
    "/product-families/{object_id}/groups",
    response_model=Page[responses.FamilyGroupAssignmentListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_familygroupassignment",
)
async def list_familygroupassignment(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["FamilyGroupAssignment"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-families/{object_id}/groups/{record_id}",
    response_model=responses.FamilyGroupAssignmentDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_familygroupassignment",
)
async def get_familygroupassignment(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db, current, company_id, object_id, record_id, RESOURCES["FamilyGroupAssignment"]
    )


@router.get(
    "/product-families/{object_id}/categories",
    response_model=Page[responses.FamilyCategoryListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_familycategory",
)
async def list_familycategory(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["FamilyCategory"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-families/{object_id}/categories/{record_id}",
    response_model=responses.FamilyCategoryDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_familycategory",
)
async def get_familycategory(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, record_id, RESOURCES["FamilyCategory"])


@router.get(
    "/product-families/{object_id}/manufacturers",
    response_model=Page[responses.FamilyManufacturerListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_familymanufacturer",
)
async def list_familymanufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["FamilyManufacturer"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-families/{object_id}/manufacturers/{record_id}",
    response_model=responses.FamilyManufacturerDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_familymanufacturer",
)
async def get_familymanufacturer(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db, current, company_id, object_id, record_id, RESOURCES["FamilyManufacturer"]
    )


@router.get(
    "/product-families/{object_id}/attributes",
    response_model=Page[responses.FamilyAttributeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_familyattribute",
)
async def list_familyattribute(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["FamilyAttribute"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-families/{object_id}/attributes/{record_id}",
    response_model=responses.FamilyAttributeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_familyattribute",
)
async def get_familyattribute(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, record_id, RESOURCES["FamilyAttribute"])


@router.get(
    "/product-families/{object_id}/attribute-options",
    response_model=Page[responses.FamilyAttributeOptionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_familyattributeoption",
)
async def list_familyattributeoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["FamilyAttributeOption"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-families/{object_id}/attribute-options/{record_id}",
    response_model=responses.FamilyAttributeOptionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_familyattributeoption",
)
async def get_familyattributeoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db, current, company_id, object_id, record_id, RESOURCES["FamilyAttributeOption"]
    )


@router.get(
    "/items/{object_id}/attributes",
    response_model=Page[responses.ItemAttributeValueListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itemattributevalue",
)
async def list_itemattributevalue(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ItemAttributeValue"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/items/{object_id}/attributes/{record_id}",
    response_model=responses.ItemAttributeValueDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itemattributevalue",
)
async def get_itemattributevalue(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db, current, company_id, object_id, record_id, RESOURCES["ItemAttributeValue"]
    )


@router.get(
    "/items/{object_id}/unit-bindings",
    response_model=Page[responses.ItemUnitBindingListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itemunitbinding",
)
async def list_itemunitbinding(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ItemUnitBinding"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/items/{object_id}/unit-bindings/{record_id}",
    response_model=responses.ItemUnitBindingDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itemunitbinding",
)
async def get_itemunitbinding(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, record_id, RESOURCES["ItemUnitBinding"])


@router.get(
    "/items/{object_id}/barcodes",
    response_model=Page[responses.ItemBarcodeListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itembarcode",
)
async def list_itembarcode(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ItemBarcode"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/items/{object_id}/barcodes/{record_id}",
    response_model=responses.ItemBarcodeDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itembarcode",
)
async def get_itembarcode(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, record_id, RESOURCES["ItemBarcode"])


@router.get(
    "/items/{object_id}/barcodes/{record_id}/label.svg",
    response_class=Response,
    operation_id="get_catalog_barcode_label_svg",
)
async def get_barcode_label_svg(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Response:
    no_query(request)
    svg = await barcode_lookup.label(db, current, company_id, object_id, record_id)
    return Response(
        svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="barcode.svg"',
        },
    )


@router.get(
    "/items/{object_id}/configuration-adoptions",
    response_model=Page[responses.ProductConfigurationAdoptionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_productconfigurationadoption",
)
async def list_productconfigurationadoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ProductConfigurationAdoption"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/items/{object_id}/configuration-adoptions/{record_id}",
    response_model=responses.ProductConfigurationAdoptionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_productconfigurationadoption",
)
async def get_productconfigurationadoption(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db, current, company_id, object_id, record_id, RESOURCES["ProductConfigurationAdoption"]
    )


@router.get(
    "/items/{object_id}/requirements",
    response_model=ProductRequirements,
    dependencies=[Depends(unique_query)],
    operation_id="get_catalog_product_requirements",
)
async def product_requirements(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AdoptionQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProductRequirements:
    result, _ = await requirements(
        await product_work(db, current, company_id, object_id), query.as_of
    )
    return result


@router.get(
    "/items/{object_id}/effective-facts",
    response_model=EffectiveItemFacts,
    dependencies=[Depends(unique_query)],
    operation_id="get_catalog_item_effective_facts",
)
async def effective_item_facts(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AdoptionQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> EffectiveItemFacts:
    work = await product_work(db, current, company_id, object_id)
    assert work.item is not None
    await work.access.require(work.item)
    await work.access.require(work.family)
    complete, effective = await requirements(work, query.as_of)
    group = await group_on(work, query.as_of)
    if group is not None:
        await work.access.require(group)
    bindings = await bounded(work, ItemUnitBinding, "item_id", work.item.id, 64)
    units = []
    for binding in bindings:
        active = await current_rows(
            work, ItemUnitRevision, "binding_id", binding.id, query.as_of, limit=2
        )
        for revision in active:
            units.append(
                EffectiveUnit(
                    binding_id=binding.id,
                    revision_id=revision.id,
                    revision=revision.revision,
                    unit_id=binding.unit_id,
                    usage_role=cast(
                        Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK", "MEASURED"],
                        binding.usage_role,
                    ),
                    valid_from=revision.valid_from,
                    valid_to=revision.valid_to,
                    conversion_mode=cast(Literal["FIXED", "MEASURED"], revision.conversion_mode),
                    numerator=revision.numerator,
                    denominator=revision.denominator,
                    nominal_ratio=revision.nominal_ratio,
                    quantity_decimal_places=revision.quantity_decimal_places,
                    quantity_increment=revision.quantity_increment,
                    fractional_entry=revision.fractional_entry,
                )
            )
    inventory = None
    if effective.profiles.inventory_template_revision_id is not None:
        source = await work.access.reference(
            InventoryProfileTemplateRevision, effective.profiles.inventory_template_revision_id
        )
        inventory = InventorySelection(
            template_revision_id=source.id,
            **product_stock_choice.profile_values(
                source, await product_stock_choice.selection(work.access, work.item.id)
            ),
        )
    if work.family.kind == "SERVICE" or (
        inventory is None and "inventory_profile" not in complete.missing
    ):
        execution = StockExecutionReadiness(state="NOT_APPLICABLE", reasons=[])
    else:
        reasons = ["accounting_stock_execution_unavailable"]
        if not complete.product_definition_complete:
            reasons.append("product_definition_incomplete")
        if inventory is None:
            reasons.append("inventory_profile_missing")
        else:
            if inventory.valuation_method == "SPECIFIC":
                reasons.append("specific_valuation_unavailable")
            if inventory.negative_stock_policy != "BLOCK":
                reasons.append("negative_stock_nonblocking_unavailable")
        execution = StockExecutionReadiness(state="UNAVAILABLE", reasons=reasons)
    return EffectiveItemFacts(
        company_id=company_id,
        item_id=work.item.id,
        family_id=work.family.id,
        as_of=query.as_of,
        kind=cast(Literal["GOODS", "SERVICE"], work.family.kind),
        item_status=cast(Literal["DRAFT", "ACTIVE", "DISCONTINUED"], work.item.status),
        item_version=work.item.row_version,
        family_version=work.family.row_version,
        product_type_revision_id=work.family.product_type_revision_id,
        group_id=group.group_id if group else None,
        group_assignment_id=group.id if group else None,
        base_unit_id=work.item.base_unit_id,
        units=units,
        sellable=work.item.sellable,
        purchasable=work.item.purchasable,
        min_sale_quantity=work.item.min_sale_quantity,
        configuration=effective,
        requirements=complete,
        inventory=inventory,
        regulatory=await effective_regulatory(work.access, work.item.id, query.as_of),
        stock_execution=execution,
    )


@router.get(
    "/items/{object_id}/configuration",
    response_model=EffectiveConfiguration,
    dependencies=[Depends(unique_query)],
    operation_id="get_catalog_product_configuration",
)
async def product_configuration(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AdoptionQuery, Query()],
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> EffectiveConfiguration:
    return await configuration(await product_work(db, current, company_id, object_id), query.as_of)


@router.get(
    "/items/{object_id}/configuration-adoption/preview",
    response_model=AdoptionPreview,
    dependencies=[Depends(unique_query)],
    operation_id="preview_catalog_product_adoption",
)
async def adoption_preview(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AdoptionQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AdoptionPreview:
    return await product_adoption.preview(
        db,
        current,
        company_id,
        object_id,
        query.as_of,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.post(
    "/items/{object_id}/configuration-adoption",
    response_model=AuthoringResult,
    operation_id="adopt_catalog_product_configuration",
)
async def adoption_commit(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: AdoptionCommit,
    request: Request,
    idempotency_key: Idempotency,
    current: Actor = Depends(actor),
) -> JSONResponse:
    async def commit(work: ProductWork, incoming: AdoptionCommit) -> None:
        await product_adoption.adopt(
            work,
            incoming,
            request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        )

    return await write(
        request,
        current,
        company_id,
        object_id,
        body,
        idempotency_key,
        "adopt_configuration",
        commit,
        item=True,
    )


@router.post(
    "/items/{object_id}/quantity-preview",
    response_model=QuantityPreviewResult,
    operation_id="preview_catalog_product_quantity",
)
async def quantity_preview(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: QuantityPreviewInput,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> QuantityPreviewResult:
    # Read-only definition validation; this operation never writes inventory or money.
    no_query(request)
    return await product_quantity.preview(
        await product_work(db, current, company_id, object_id), body
    )


@router.get(
    "/item-unit-bindings/{object_id}/revisions",
    response_model=Page[responses.ItemUnitRevisionListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_itemunitrevision",
)
async def list_itemunitrevision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ItemUnitRevision"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/item-unit-bindings/{object_id}/revisions/{record_id}",
    response_model=responses.ItemUnitRevisionDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_itemunitrevision",
)
async def get_itemunitrevision(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(db, current, company_id, object_id, record_id, RESOURCES["ItemUnitRevision"])


@router.get(
    "/product-configuration-adoptions/{object_id}/sources",
    response_model=Page[responses.ProductConfigurationAdoptionSourceListItem],
    response_model_exclude_unset=True,
    dependencies=[Depends(unique_query)],
    operation_id="list_catalog_productconfigurationadoptionsource",
)
async def list_productconfigurationadoptionsource(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    query: Annotated[AuthoringQuery, Query()],
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[BaseModel]:
    return await list_rows(
        db,
        current,
        company_id,
        object_id,
        RESOURCES["ProductConfigurationAdoptionSource"],
        query,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )


@router.get(
    "/product-configuration-adoptions/{object_id}/sources/{record_id}",
    response_model=responses.ProductConfigurationAdoptionSourceDetail,
    response_model_exclude_unset=True,
    operation_id="get_catalog_productconfigurationadoptionsource",
)
async def get_productconfigurationadoptionsource(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> BaseModel:
    no_query(request)
    return await read(
        db,
        current,
        company_id,
        object_id,
        record_id,
        RESOURCES["ProductConfigurationAdoptionSource"],
    )


@router.get(
    "/items/{object_id}/attribute-form",
    response_model=ProductAttributeForm,
    operation_id="get_catalog_product_attribute_form",
)
async def attribute_form(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProductAttributeForm:
    no_query(request)
    from catalog.tasks.attribute_forms import form

    return await form(db, current, company_id, object_id)
