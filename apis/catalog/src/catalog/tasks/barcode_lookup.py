"""Protected exact scan lookup; stock and voucher posting remain separate owners."""

import uuid
from typing import Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from catalog.domain.barcode_labels import render_label
from catalog.domain.barcodes import gtin_aliases, parse_scan
from catalog.models.product_definitions import ItemBarcode, ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from catalog.schemas.product_authoring import BarcodeResolution, BarcodeResolveInput
from catalog.tasks.configuration_access import ConfigurationAccess


async def label(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    item_id: uuid.UUID,
    barcode_id: uuid.UUID,
) -> bytes:
    actor.require_scope("item.read", target=ScopePath(company_id=company))
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(ItemBarcode, permission="item.read")
    if not {"value", "symbology", "is_active", "item_id"} <= context.readable():
        raise PermissionDeniedError("barcode label fields are protected")
    item = await access.reference(Item, item_id)
    await access.reference(ProductFamily, item.family_id)
    barcode = await company_object(db, ItemBarcode, barcode_id, company_id=company)
    await access.require(barcode)
    if barcode.item_id != item.id:
        raise PermissionDeniedError("barcode belongs to another SKU")
    if not barcode.is_active:
        raise ConflictError("inactive barcode labels cannot be generated")
    return await run_in_threadpool(render_label, barcode.value, barcode.symbology)


async def resolve(
    db: AsyncSession, actor: Actor, company: uuid.UUID, body: BarcodeResolveInput
) -> BarcodeResolution:
    actor.require_scope("item.read", target=ScopePath(company_id=company))
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(ItemBarcode, permission="item.read")
    fields = {"value", "symbology", "is_active", "item_id", "binding_id"}
    if not fields <= context.readable():
        raise PermissionDeniedError("barcode scan fields are protected")

    parsed = parse_scan(body.scan_value)
    values = {parsed.code}
    if parsed.gs1 or (parsed.code.isascii() and parsed.code.isdigit()):
        try:
            values.update(gtin_aliases(parsed.code))
        except ValidationFailedError:
            if parsed.gs1:
                raise
    rows = list(
        await db.scalars(
            select(ItemBarcode)
            .where(
                ItemBarcode.company_id == company,
                ItemBarcode.value.in_(values),
                ItemBarcode.is_active.is_(True),
            )
            .limit(2)
        )
    )
    if not rows:
        raise NotFoundError("barcode is unknown or inactive")
    if len(rows) != 1:
        raise ConflictError("scan resolves to multiple product codes")
    barcode = rows[0]
    await access.require(barcode)
    if parsed.gs1 and barcode.symbology != "GTIN":
        raise ConflictError("GS1 product identifier is not a GTIN")
    item = await access.reference(Item, barcode.item_id)
    family = await access.reference(ProductFamily, item.family_id)
    if item.status != "ACTIVE" or family.status != "ACTIVE":
        raise ConflictError("barcode product is not active")

    if barcode.binding_id is None:
        bindings = list(
            await db.scalars(
                select(ItemUnitBinding)
                .where(
                    ItemUnitBinding.company_id == company,
                    ItemUnitBinding.item_id == item.id,
                    ItemUnitBinding.usage_role == "BASE",
                )
                .limit(2)
            )
        )
        if len(bindings) != 1:
            raise ConflictError("barcode product has no unambiguous base unit")
        binding = bindings[0]
        await access.require(binding)
    else:
        binding = await access.reference(ItemUnitBinding, barcode.binding_id)
        if binding.item_id != item.id:
            raise ConflictError("barcode unit does not belong to its product")
    revisions = list(
        await db.scalars(
            select(ItemUnitRevision)
            .where(
                ItemUnitRevision.company_id == company,
                ItemUnitRevision.binding_id == binding.id,
                ItemUnitRevision.valid_from <= body.as_of,
                or_(ItemUnitRevision.valid_to.is_(None), ItemUnitRevision.valid_to >= body.as_of),
            )
            .limit(2)
        )
    )
    if len(revisions) != 1:
        raise ConflictError("barcode unit has no unambiguous effective revision")
    revision = revisions[0]
    await access.require(revision)
    if binding.usage_role == "MEASURED" or (
        revision.conversion_mode != "FIXED"
        or revision.numerator is None
        or revision.denominator is None
    ):
        raise ConflictError("barcode unit requires a fixed exact conversion")
    return BarcodeResolution(
        barcode_id=barcode.id,
        matched_value=barcode.value,
        item_id=item.id,
        item_version=item.row_version,
        sku=item.sku,
        name=item.name,
        unit_id=binding.unit_id,
        binding_id=binding.id,
        unit_revision_id=revision.id,
        usage_role=cast(Literal["BASE", "SALE", "PURCHASE", "BOTH", "PACK"], binding.usage_role),
        numerator=revision.numerator,
        denominator=revision.denominator,
        lot_hint=parsed.lot,
        expiry_yymmdd_hint=parsed.expiry_yymmdd,
        serial_hint=parsed.serial,
    )
