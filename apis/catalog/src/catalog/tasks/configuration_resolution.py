"""Bounded dated default inheritance with protected provenance and hard constraints."""

import uuid
from typing import Any, cast

from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.classification import MAX_DEPTH
from catalog.domain.configuration import OptionSetting, resolve_option
from catalog.domain.pricing_dimensions import PRICING_DIMENSIONS
from catalog.domain.product_types import TypeRequirements
from catalog.models.classification import ItemGroup, ItemGroupParent
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.configuration import ProductConfigurationRevision, ProductConfigurationScope
from catalog.models.products import Item, ProductFamily
from catalog.schemas.configuration import (
    ConfigurationOrigin,
    ConfigurationSetting,
    ConfigurationSource,
    DraftInput,
    EffectiveConfiguration,
    EffectiveQuery,
    EntryOptions,
    NumericInput,
    PricingRequirements,
    ProfileDefaults,
    ScopeKind,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_context import family_group
from catalog.tasks.configuration_values import (
    GOODS_OPTIONS,
    GOODS_PROFILES,
    applicable_layer,
    option_setting,
)
from catalog.tasks.policy_state import policy_state
from catalog.tasks.profile_bindings import validate_defaults


async def resolve(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: EffectiveQuery,
    *,
    revisions: tuple[uuid.UUID, ...] | None = None,
    resolution_version: int = 1,
    draft: DraftInput | None = None,
) -> EffectiveConfiguration:
    if resolution_version not in {1, 2}:
        raise ConflictError("unsupported configuration adoption resolution version")
    legacy_pins = revisions is not None and resolution_version == 1
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(ProductConfigurationScope)
    ownership = set(context.native.fields) if legacy_pins else {"scope_kind", "owner_id"}
    if ownership - context.readable():
        raise PermissionDeniedError("configuration scope selection requires readable ownership")
    family = None
    item = None
    type_revision = None
    type_id = query.product_type_id
    if query.product_type_revision_id is not None:
        type_revision = await access.reference(ProductTypeRevision, query.product_type_revision_id)
        if type_id is not None and type_id != type_revision.product_type_id:
            raise PermissionDeniedError("type revision belongs to another type")
        type_id = type_revision.product_type_id
    if query.item_id is not None:
        item = await access.reference(Item, query.item_id)
        if query.family_id is not None and query.family_id != item.family_id:
            raise PermissionDeniedError("SKU belongs to another family")
    family_id = item.family_id if item else query.family_id
    if family_id is not None:
        family = await access.reference(ProductFamily, family_id)
        if family.kind != query.kind:
            raise ConflictError("configuration kind differs from product kind")
        if type_revision is not None and type_revision.id != family.product_type_revision_id:
            raise PermissionDeniedError("type revision differs from product structure")
        type_revision = await access.reference(ProductTypeRevision, family.product_type_revision_id)
        if type_id is not None and type_id != type_revision.product_type_id:
            raise PermissionDeniedError("product belongs to another type")
        type_id = type_revision.product_type_id
    if type_id is not None and type_revision is None:
        await access.reference(ProductType, type_id)
        revision_context = await access.context(ProductTypeRevision)
        if set(revision_context.native.fields) - revision_context.readable():
            raise PermissionDeniedError("type defaults require readable type requirements")
        type_revision = await db.scalar(
            select(ProductTypeRevision)
            .where(
                ProductTypeRevision.company_id == company,
                ProductTypeRevision.product_type_id == type_id,
                ProductTypeRevision.published_at.is_not(None),
            )
            .order_by(ProductTypeRevision.revision.desc())
            .limit(1)
        )
        if type_revision is None:
            raise ConflictError("configuration type has no published requirements")
    if type_revision is not None and type_revision.kind not in {query.kind, "BOTH"}:
        raise ConflictError("configuration kind does not match the type")

    groups: list[uuid.UUID] = []
    shared_groups: set[uuid.UUID] = set()
    current_group = query.group_id
    if family is not None:
        assignment = await family_group(access, family.id, query.as_of)
        assigned_group = assignment.group_id if assignment else None
        if current_group is not None and current_group != assigned_group:
            raise PermissionDeniedError("group differs from the product's dated assignment")
        current_group = assigned_group
    while current_group is not None:
        if current_group in groups or len(groups) >= MAX_DEPTH:
            raise ConflictError("configuration group ancestry is cyclic or exceeds its bound")
        group = await access.reference(ItemGroup, current_group)
        if group.allowed_kind not in {query.kind, "BOTH"}:
            raise ConflictError("group does not admit the product kind")
        groups.append(group.id)
        if group.allowed_kind == "BOTH":
            shared_groups.add(group.id)
        edges_context = await access.context(ItemGroupParent)
        if set(edges_context.native.fields) - edges_context.readable():
            raise PermissionDeniedError("configuration ancestry requires readable group history")
        edges = list(
            await db.scalars(
                select(ItemGroupParent)
                .where(
                    ItemGroupParent.company_id == company,
                    ItemGroupParent.group_id == group.id,
                    ItemGroupParent.valid_from <= query.as_of,
                    or_(
                        ItemGroupParent.valid_to.is_(None), ItemGroupParent.valid_to >= query.as_of
                    ),
                )
                .limit(2)
            )
        )
        if len(edges) != 1:
            raise ConflictError("configuration group ancestry is missing or ambiguous")
        current_group = edges[0].parent_group_id
    owners = [("COMPANY", company)]
    # Old pins remain readable; no public current-default request selects these layers.
    if legacy_pins:
        if type_id is not None:
            owners.append(("TYPE", type_id))
        owners.extend(("GROUP", group) for group in reversed(groups))
        if family is not None:
            owners.append(("FAMILY", family.id))
        if item is not None:
            owners.append(("SKU", item.id))

    layers: list[DraftInput] = []
    layer_kinds: list[str] = []
    sources: list[ConfigurationSource] = []
    origins: list[ConfigurationOrigin] = []
    settings: dict[str, ConfigurationSetting] = {}
    expected = set(revisions or ())
    for kind, owner in owners:
        scope = await db.scalar(
            select(ProductConfigurationScope).where(
                ProductConfigurationScope.company_id == company,
                ProductConfigurationScope.scope_kind == kind,
                ProductConfigurationScope.owner_id == owner,
            )
        )
        if scope is None:
            continue
        await access.scope_owner(scope)
        shared = (
            kind == "COMPANY"
            or (kind == "GROUP" and owner in shared_groups)
            or (kind == "TYPE" and type_revision is not None and type_revision.kind == "BOTH")
        )
        if draft is not None and draft.scope_id == scope.id:
            layers.append(applicable_layer(draft, service=query.kind == "SERVICE", shared=shared))
            origins.append(ConfigurationOrigin(kind="DRAFT", scope_id=scope.id))
            layer_kinds.append(kind)
            continue
        revision_context = await access.context(ProductConfigurationRevision)
        if set(revision_context.native.fields) - revision_context.readable():
            raise PermissionDeniedError(
                "effective configuration requires readable revision sources"
            )
        stmt = select(ProductConfigurationRevision).where(
            ProductConfigurationRevision.company_id == company,
            ProductConfigurationRevision.scope_id == scope.id,
            ProductConfigurationRevision.effective_from <= query.as_of,
        )
        if revisions is not None:
            stmt = stmt.where(ProductConfigurationRevision.id.in_(revisions))
        matches = list(
            await db.scalars(
                stmt.order_by(ProductConfigurationRevision.effective_from.desc()).limit(2)
            )
        )
        if revisions is not None and len(matches) > 1:
            raise ConflictError("adoption contains conflicting configuration revisions")
        if not matches:
            continue
        row = matches[0]
        expected.discard(row.id)
        layers.append(
            applicable_layer(
                await access.input(row), service=query.kind == "SERVICE", shared=shared
            )
        )
        origins.append(ConfigurationOrigin(kind="REVISION", scope_id=scope.id, revision_id=row.id))
        layer_kinds.append(kind)
        sources.append(
            ConfigurationSource(
                scope_id=scope.id,
                scope_kind=cast(ScopeKind, scope.scope_kind),
                revision_id=row.id,
                revision=row.revision,
                effective_from=row.effective_from,
            )
        )
    if expected:
        raise ConflictError("pinned configuration no longer matches the product ownership/date")

    values: dict[str, Any] = {}
    for field in EntryOptions.model_fields:
        if not field.endswith("_mode"):
            continue
        key = field.removesuffix("_mode")
        baseline = OptionSetting("OPTIONAL", False)
        baseline_origin = ConfigurationOrigin(kind="NATIVE")
        if type_revision is not None:
            if key == "variants" and not type_revision.allow_variants:
                baseline = OptionSetting("DISABLED")
            if key == "brand" and type_revision.require_brand:
                baseline = OptionSetting("REQUIRED")
            if key == "manufacturer" and type_revision.require_manufacturer:
                baseline = OptionSetting("REQUIRED")
        if type_revision is not None and baseline.mode != "OPTIONAL":
            baseline_origin = ConfigurationOrigin(kind="TYPE", type_revision_id=type_revision.id)
        if query.kind == "SERVICE" and key in GOODS_OPTIONS:
            baseline = OptionSetting("DISABLED")
            baseline_origin = ConfigurationOrigin(kind="NATIVE")
        result = resolve_option(
            tuple(
                OptionSetting(
                    getattr(layer.options, field), getattr(layer.options, key + "_default")
                )
                for layer in layers
            ),
            baseline=baseline,
        )
        values[field], values[key + "_default"] = result.mode, result.default_enabled
        settings["options." + key] = option_setting(
            "options." + key,
            result,
            baseline,
            baseline_origin,
            [
                (
                    OptionSetting(
                        getattr(layer.options, field), getattr(layer.options, key + "_default")
                    ),
                    origin,
                )
                for layer, origin in zip(layers, origins, strict=True)
            ],
            applicable=not (query.kind == "SERVICE" and key in GOODS_OPTIONS),
        )
    profiles = ProfileDefaults().model_dump()
    profile_layers = list(zip(layer_kinds, layers, strict=True))
    profile_origins = list(origins)
    if type_revision is not None:
        defaults: dict[str, Any] = {}
        for field in (
            "inventory_template_revision",
            "warranty_revision",
            "return_policy_revision",
            "handling_revision",
        ):
            value = getattr(type_revision, field + "_id")
            if value is not None and not (query.kind == "SERVICE" and field in GOODS_PROFILES):
                defaults[field + "_mode"], defaults[field + "_id"] = "VALUE", value
        # Company choices override optional native defaults for new/current settings.
        # Preserve the original ordering only when reading immutable adoption pins.
        insertion = 1 if legacy_pins and profile_layers and profile_layers[0][0] == "COMPANY" else 0
        profile_origins.insert(
            insertion, ConfigurationOrigin(kind="TYPE", type_revision_id=type_revision.id)
        )
        profile_layers.insert(
            insertion,
            (
                "TYPE_BASELINE",
                DraftInput(
                    scope_id=company,
                    effective_from=query.as_of,
                    change_reason="Type defaults",
                    profiles=ProfileDefaults.model_validate(defaults),
                ),
            ),
        )
    numeric: dict[str, dict[str, Any]] = {}
    for (_, layer), origin in zip(profile_layers, profile_origins, strict=True):
        for field, mode in layer.profiles.model_dump().items():
            if field.endswith("_mode") and mode != "INHERIT":
                profiles[field] = mode
                path = "profiles." + field.removesuffix("_mode")
                settings[path] = ConfigurationSetting(field=path, origins=[origin])
                profiles[field.removesuffix("_mode") + "_id"] = getattr(
                    layer.profiles, field.removesuffix("_mode") + "_id"
                )
        for numeric_row in layer.numeric_defaults:
            existing = numeric.setdefault(
                numeric_row.dimension, {"dimension": numeric_row.dimension}
            )
            incoming = numeric_row.model_dump(exclude_none=True)
            if numeric_row.price_decimal_places is not None:
                # Precision, currency and optional increment form one replacement setting.
                incoming["price_increment"] = numeric_row.price_increment
            existing.update(incoming)
            for key in incoming.keys() - {"dimension"}:
                path = "numeric_defaults." + numeric_row.dimension + "." + key
                settings[path] = ConfigurationSetting(field=path, origins=[origin])
    for field in ProfileDefaults.model_fields:
        if not field.endswith("_mode"):
            continue
        key = field.removesuffix("_mode")
        path = "profiles." + key
        settings.setdefault(
            path, ConfigurationSetting(field=path, origins=[ConfigurationOrigin(kind="NATIVE")])
        )
        if (
            query.kind == "SERVICE" and (key in GOODS_PROFILES or key == "goods_type_revision")
        ) or (query.kind == "GOODS" and key == "service_type_revision"):
            settings[path] = ConfigurationSetting(
                field=path,
                origins=[ConfigurationOrigin(kind="NATIVE")],
                applicable=False,
                overrideable=False,
                reason="goods_only" if query.kind == "SERVICE" else "service_only",
            )
            profiles[key + "_mode"], profiles[key + "_id"] = "INHERIT", None
    selected = ProfileDefaults.model_validate(profiles)
    await access.profile_references(selected)
    if type_revision is not None:
        rules = TypeRequirements(
            type_revision.kind,
            frozenset(type_revision.inventory_modes),
            frozenset(type_revision.tracking_modes),
            frozenset(type_revision.unit_dimensions),
            type_revision.allow_variants,
            type_revision.require_brand,
            type_revision.require_manufacturer,
            type_revision.require_expiry,
        )
        await validate_defaults(db, company, rules, selected.model_dump())
    if query.kind == "SERVICE" and any(
        (
            selected.inventory_template_revision_id,
            selected.handling_revision_id,
            selected.identifier_profile_id,
        )
    ):
        raise ConflictError("services cannot select physical tracking/handling profiles")
    pricing: dict[str, Any] = {}
    for field in PRICING_DIMENSIONS:
        selected_mode, selected_origin = "ENABLED", ConfigurationOrigin(kind="NATIVE")
        for layer, origin in zip(layers, origins, strict=True):
            mode = getattr(layer.pricing, field)
            if mode != "INHERIT":
                selected_mode, selected_origin = mode, origin
        pricing[field] = selected_mode
        path = "pricing." + field
        settings[path] = ConfigurationSetting(field=path, origins=[selected_origin])
    for field in ("purchase_reference_mode", "sale_price_mode", "mrp_mode"):
        choices = tuple(
            OptionSetting(
                getattr(layer.pricing, field),
                False if getattr(layer.pricing, field) == "OPTIONAL" else None,
            )
            for layer in layers
        )
        baseline = (
            OptionSetting("DISABLED")
            if query.kind == "SERVICE" and field == "mrp_mode"
            else OptionSetting("OPTIONAL", False)
        )
        chosen = resolve_option(choices, baseline=baseline)
        pricing[field] = chosen.mode
        path = "pricing." + field
        settings[path] = option_setting(
            path,
            chosen,
            baseline,
            ConfigurationOrigin(kind="NATIVE"),
            list(zip(choices, origins, strict=True)),
            applicable=not (query.kind == "SERVICE" and field == "mrp_mode"),
        )
    pricing["sale_level_count"] = max(
        [1] + [layer.pricing.sale_level_count or 1 for layer in layers]
    )
    path = "pricing.sale_level_count"
    settings[path] = ConfigurationSetting(
        field=path,
        origins=[
            origin
            for layer, origin in zip(layers, origins, strict=True)
            if layer.pricing.sale_level_count == pricing["sale_level_count"]
        ]
        or [ConfigurationOrigin(kind="NATIVE")],
    )
    if pricing["sale_level_count"] > 1 and "multi_price_levels" not in context.features:
        raise ConflictError("additional sale levels require an available company capability")
    if pricing["sale_level_count"] > 1 and pricing["multiple_price_levels_mode"] == "DISABLED":
        raise ConflictError(
            "enable multiple selling-price levels before requiring additional levels"
        )
    state = await policy_state(db, actor, company)
    return EffectiveConfiguration(
        company_id=company,
        as_of=query.as_of,
        kind=query.kind,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        sources=sources,
        options=EntryOptions.model_validate(values),
        numeric_defaults=[NumericInput.model_validate(row) for _, row in sorted(numeric.items())],
        profiles=selected,
        pricing=PricingRequirements.model_validate(pricing),
        settings=[value for _, value in sorted(settings.items())],
    )
