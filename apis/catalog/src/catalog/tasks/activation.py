"""Signed immediate activation with immutable product/configuration/price/tax evidence."""

import datetime as dt
import hashlib
import hmac
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.pagination import CursorCodec
from sqlalchemy import select

from catalog.domain.product_authoring import variant_identity
from catalog.models import (
    FamilyAttribute,
    FamilyAttributeOption,
    InventoryProfileTemplateRevision,
    ItemAttributeValue,
    ItemVariantKey,
    ProductConfigurationAdoption,
)
from catalog.models.tax import ItemActivation, ItemActivationSource, ItemInventoryProfile
from catalog.models.warehouse_policies import (
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from catalog.schemas.activation import ActivationCommit, ActivationPreview
from catalog.schemas.product_authoring import AdoptionCommit
from catalog.tasks import product_stock_choice
from catalog.tasks.activation_prices import coverage
from catalog.tasks.activation_tax import coverage as tax_coverage
from catalog.tasks.product_adoption import adopt
from catalog.tasks.product_adoption import prepare as adoption_preview
from catalog.tasks.product_attributes import bounded
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import requirements
from catalog.tasks.products import references
from catalog.tasks.tax_resolution import Pins


def codec(work: ProductWork, secret: bytes) -> CursorCodec:
    assert work.item is not None
    return CursorCodec(
        hmac.digest(secret, b"catalog.activation.v1", hashlib.sha256),
        context=f"activation:{work.actor.tenant_id}:{work.company}:{work.actor.user_id}:{work.item.id}",
        ttl_seconds=900,
    )


async def variants(work: ProductWork, pins: Pins) -> list[str]:
    assert work.item is not None
    attributes = await bounded(work, FamilyAttribute, "family_id", work.family.id)
    options = await bounded(work, FamilyAttributeOption, "family_id", work.family.id, 1024)
    values = await bounded(work, ItemAttributeValue, "item_id", work.item.id)
    for value in [*attributes, *options, *values]:
        pins.add(value)
    if work.family.structure_mode != "VARIANT":
        return []
    axes = {
        row.definition_id: frozenset(
            option.option_id for option in options if option.definition_id == row.definition_id
        )
        for row in attributes
        if row.is_axis
    }
    selected = {
        row.definition_id: row.option_id
        for row in values
        if row.definition_id in axes and row.option_id is not None
    }
    if not axes or selected.keys() != axes.keys():
        return ["variant_axes"]
    digest, canonical = variant_identity(axes, selected)
    keys = await bounded(work, ItemVariantKey, "item_id", work.item.id, 1)
    if not keys or keys[0].combination_hash != digest or keys[0].canonical_combination != canonical:
        return ["variant_identity"]
    pins.add(keys[0])
    return []


async def prepare(
    work: ProductWork, as_of: dt.date, secret: bytes, *, item_version: int | None = None
) -> tuple[ActivationPreview, Any]:
    assert work.item is not None
    work.actor.require_scope("item.activate", target=ScopePath(company_id=work.company))
    company = (await work.access.context(type(work.item))).company
    if as_of != utcnow().astimezone(ZoneInfo(company.timezone)).date():
        raise ConflictError("activation must use the current company business date")
    if work.item.status != "DRAFT" or work.family.status not in {"DRAFT", "ACTIVE"}:
        raise ConflictError("only a draft SKU in a current family can activate")
    await references(work.db, work.actor, work.company, work.family, work.item)
    definition, config = await requirements(work, as_of, proposed=True)
    pins = Pins()
    pins.add(work.item)
    pins.add(work.family)
    stock_choice = await product_stock_choice.selection(work.access, work.item.id)
    if stock_choice is not None:
        await product_stock_choice.validate(work, config, stock_choice.batch_enabled)
        pins.add(stock_choice)
    from catalog.tasks.activation_categories import coverage as category_coverage
    from catalog.tasks.product_custom_fields import requirements as custom_requirements

    missing = [
        *definition.missing,
        *await custom_requirements(work),
        *await variants(work, pins),
        *await category_coverage(work, as_of, pins),
    ]
    if stock_choice is None or not stock_choice.batch_enabled:
        missing += await coverage(work, config, as_of, pins)
    taxes, tax_missing = await tax_coverage(work, as_of, pins)
    missing += tax_missing
    if config.profiles.inventory_template_revision_id is None:
        policy = await work.db.scalar(
            select(ItemWarehousePolicy).where(
                ItemWarehousePolicy.company_id == work.company,
                ItemWarehousePolicy.item_id == work.item.id,
            )
        )
        active_member = await work.db.scalar(
            select(ItemWarehousePermission.id)
            .where(
                ItemWarehousePermission.company_id == work.company,
                ItemWarehousePermission.item_id == work.item.id,
                ItemWarehousePermission.is_active.is_(True),
            )
            .limit(1)
        )
        active_band = await work.db.scalar(
            select(ItemReplenishmentPolicy.id)
            .where(
                ItemReplenishmentPolicy.company_id == work.company,
                ItemReplenishmentPolicy.item_id == work.item.id,
                ItemReplenishmentPolicy.is_active.is_(True),
            )
            .limit(1)
        )
        if (
            active_member is not None
            or active_band is not None
            or (
                policy is not None
                and (
                    policy.selection_mode != "ALLOW_ALL_ACTIVE"
                    or any(
                        getattr(policy, field) is not None
                        for field in (
                            "default_sale_warehouse_id",
                            "default_purchase_warehouse_id",
                            "default_customer_return_warehouse_id",
                            "default_opening_warehouse_id",
                        )
                    )
                )
            )
        ):
            missing.append("inventory_profile_for_location_policy")
    version = item_version if item_version is not None else work.item.row_version
    pins.rows["catalog.item", work.item.id].entity_version = version
    sources = sorted(pins.rows.values(), key=lambda entry: (entry.entity_type, entry.entity_id))
    # The executor increments the SKU version before the handler; compare the reviewed version.
    for tax_result in taxes:
        for pin in tax_result["sources"]:
            if pin["entity_type"] == "catalog.item" and pin["entity_id"] == str(work.item.id):
                pin["entity_version"] = version
    digest = hashlib.sha256(
        canonical_json(
            {
                "date": str(as_of),
                # A fresh Identity checkpoint is still required on every request.
                # Its transport watermark may advance without changing any reviewed
                # setting; bind the values and policy generation, not that counter.
                "configuration": config.model_dump(mode="json", exclude={"source_version"}),
                "taxes": taxes,
                "sources": [entry.model_dump(mode="json") for entry in sources],
                "missing": sorted(set(missing)),
            }
        )
    ).hexdigest()
    return ActivationPreview(
        item_id=work.item.id,
        as_of=as_of,
        expected_version=version,
        expected_family_version=work.family.row_version,
        eligible=not missing,
        missing=sorted(set(missing)),
        sources=sources,
        policy_generation=config.policy_generation,
        source_version=config.source_version,
        preview_token=codec(work, secret).encode({"digest": digest}),
    ), config


async def activate(
    work: ProductWork,
    body: ActivationCommit,
    secret: bytes,
    *,
    prepared: tuple[ActivationPreview, Any] | None = None,
) -> None:
    assert work.item is not None
    if work.family.row_version != body.expected_family_version:
        raise ConflictError("family changed; preview activation again")
    reviewed = codec(work, secret).decode(body.preview_token)
    # Only an internal caller holding the same company transaction may reuse its
    # just-computed review. HTTP activation always re-evaluates the signed preview.
    fresh, config = prepared or await prepare(
        work, body.as_of, secret, item_version=body.expected_version
    )
    if reviewed != codec(work, secret).decode(fresh.preview_token):
        raise ConflictError("activation preview changed; preview again")
    if not fresh.eligible:
        raise ConflictError("product activation has missing required definitions")
    prepared_adoption = await adoption_preview(
        work, body.as_of, secret, item_version=body.expected_version, for_activation=True
    )
    await adopt(
        work,
        AdoptionCommit(
            expected_version=body.expected_version,
            as_of=body.as_of,
            preview_token=prepared_adoption[0].preview_token,
        ),
        secret,
        for_activation=True,
        prepared=prepared_adoption,
    )
    source = await work.db.scalar(
        select(ProductConfigurationAdoption)
        .where(
            ProductConfigurationAdoption.company_id == work.company,
            ProductConfigurationAdoption.item_id == work.item.id,
        )
        .order_by(ProductConfigurationAdoption.revision.desc())
        .limit(1)
    )
    assert source is not None
    if config.profiles.inventory_template_revision_id is not None:
        if work.family.kind != "GOODS":
            raise ConflictError("services cannot instantiate stock profiles")
        template = await work.access.reference(
            InventoryProfileTemplateRevision, config.profiles.inventory_template_revision_id
        )
        profile = await work.new(
            ItemInventoryProfile,
            item_id=work.item.id,
            base_unit_id=work.item.base_unit_id,
            template_revision_id=template.id,
            **product_stock_choice.profile_values(
                template, await product_stock_choice.selection(work.access, work.item.id)
            ),
        )
        work.db.add(profile)
    activation = await work.new(
        ItemActivation,
        item_id=work.item.id,
        adoption_id=source.id,
        activated_on=body.as_of,
        source_version=fresh.source_version,
        policy_generation=fresh.policy_generation,
        preview_hash=reviewed["digest"],
    )
    work.db.add(activation)
    await work.db.flush([activation])
    for pin in fresh.sources:
        record = await work.new(
            ItemActivationSource, activation_id=activation.id, **pin.model_dump()
        )
        work.db.add(record)
    before = await work.access.values(work.item)
    work.item.status = "ACTIVE"
    await work.record(work.item, before, "update")
    if work.family.status == "DRAFT":
        if work.family.row_version >= 2**31 - 1:
            raise ConflictError("family version exhausted")
        before = await work.access.values(work.family)
        work.family.status = "ACTIVE"
        work.family.row_version += 1
        work.family.updated_at, work.family.updated_by = utcnow(), work.actor.user_id
        await work.record(work.family, before, "update")
