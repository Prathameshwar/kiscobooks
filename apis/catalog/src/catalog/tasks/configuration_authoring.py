"""Native authoring suggestions and explicit acceptance against current source versions."""

from decimal import Decimal

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.money import MoneyError
from sqlalchemy import select

from catalog.domain.configuration import narrow_quantity_default
from catalog.domain.pricing import RateGrid
from catalog.domain.units import QuantityRule
from catalog.models.commercial import ProductTypeRevision
from catalog.models.configuration import ProductConfigurationScope
from catalog.models.products import ProductFamily
from catalog.models.units import UnitOfMeasure
from catalog.schemas.configuration import (
    AuthoringDefaults,
    AuthoringDefaultsQuery,
    DefaultsAcceptance,
    EffectiveQuery,
    PriceSuggestion,
    QuantitySuggestion,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_resolution import resolve


async def suggestions(
    access: ConfigurationAccess, query: AuthoringDefaultsQuery
) -> AuthoringDefaults:
    try:
        return await _suggestions(access, query)
    except MoneyError as exc:
        raise ValidationFailedError(
            "configuration numeric defaults do not fit the selected unit or price grid"
        ) from exc


async def _suggestions(
    access: ConfigurationAccess, query: AuthoringDefaultsQuery
) -> AuthoringDefaults:
    selection = EffectiveQuery.model_validate(
        query.model_dump(exclude={"unit_id", "unit_revision_id", "currency", "include_price"})
    )
    selected_type = query.product_type_revision_id
    if query.item_id is not None:
        from catalog.tasks.product_requirements import configuration, product_work

        work = await product_work(access.db, access.actor, access.company, query.item_id)
        effective = await configuration(work, query.as_of, query=selection)
        selected_type = work.family.product_type_revision_id
    else:
        effective = await resolve(access.db, access.actor, access.company, selection)
    if query.item_id is None and query.family_id is not None:
        family = await access.reference(ProductFamily, query.family_id)
        selected_type = family.product_type_revision_id
    elif selected_type is None and query.product_type_id is not None:
        context = await access.context(ProductTypeRevision)
        if set(context.native.fields) - context.readable():
            raise PermissionDeniedError("type default fields are protected")
        selected_type = await access.db.scalar(
            select(ProductTypeRevision.id)
            .where(
                ProductTypeRevision.company_id == access.company,
                ProductTypeRevision.product_type_id == query.product_type_id,
                ProductTypeRevision.published_at.is_not(None),
            )
            .order_by(ProductTypeRevision.revision.desc())
            .limit(1)
        )
    elif selected_type is None:
        selected_type = (
            effective.profiles.goods_type_revision_id
            if query.kind == "GOODS"
            else effective.profiles.service_type_revision_id
        )
        if selected_type is not None:
            effective = await resolve(
                access.db,
                access.actor,
                access.company,
                EffectiveQuery(
                    as_of=query.as_of,
                    kind=query.kind,
                    group_id=query.group_id,
                    product_type_revision_id=selected_type,
                ),
            )
    missing = [] if selected_type is not None else ["product_type_revision"]
    revision = None
    unit_id = query.unit_id
    if query.unit_revision_id is not None:
        if query.item_id is None:
            raise ConflictError("a unit revision requires its owning SKU")
        from catalog.tasks.pricing_foundation import unit

        revision, binding = await unit(access, query.item_id, query.unit_revision_id, query.as_of)
        if unit_id is not None and unit_id != binding.unit_id:
            raise PermissionDeniedError("unit differs from the selected revision")
        unit_id = binding.unit_id
    quantity = None
    price = None
    adjustments = []
    if unit_id is not None:
        master = await access.reference(UnitOfMeasure, unit_id)
        if selected_type is not None:
            type_revision = await access.reference(ProductTypeRevision, selected_type)
            if master.dimension not in type_revision.unit_dimensions:
                raise ConflictError("unit dimension does not match the selected product type")
        baseline = QuantityRule(master.decimal_places, master.quantity_increment)
        if revision is not None:
            baseline = narrow_quantity_default(
                baseline,
                QuantityRule(revision.quantity_decimal_places, revision.quantity_increment),
            )
        configured = next(
            (row for row in effective.numeric_defaults if row.dimension == master.dimension), None
        )
        default = None
        if configured is not None and configured.quantity_decimal_places is not None:
            assert configured.quantity_increment is not None
            default = QuantityRule(
                configured.quantity_decimal_places, configured.quantity_increment
            )
        narrowed = narrow_quantity_default(default, baseline)
        if default is not None and default != narrowed:
            adjustments.append("quantity_narrowed_to_unit_grid")
        quantity = QuantitySuggestion(
            unit_id=master.id,
            quantity_decimal_places=narrowed.decimal_places,
            quantity_increment=narrowed.increment,
            fractional_entry=narrowed.decimal_places > 0
            and (revision is None or revision.fractional_entry),
        )
        if query.include_price:
            context = await access.context(ProductConfigurationScope)
            code = (
                query.currency
                or (configured.currency if configured else None)
                or context.company.base_currency
            )
            from catalog.tasks.pricing_foundation import currency

            await currency(access, code)
            if configured is not None and configured.currency not in {None, code}:
                raise ConflictError("configured price defaults use a different currency")
            places = configured.price_decimal_places if configured is not None else None
            increment = configured.price_increment if configured is not None else None
            basis = configured.price_basis_quantity if configured is not None else None
            basis = basis if basis is not None else Decimal("1.0000")
            baseline.validate(basis)
            if (
                revision is not None
                and not revision.fractional_entry
                and basis != basis.to_integral_value()
            ):
                raise ConflictError("price basis requires an allowed whole unit quantity")
            RateGrid(places if places is not None else 4, increment)
            price = PriceSuggestion(
                currency=code,
                price_decimal_places=places if places is not None else 4,
                price_increment=increment,
                price_basis_quantity=basis,
            )
    else:
        missing.append("unit")
    return AuthoringDefaults(
        product_type_revision_id=selected_type,
        quantity=quantity,
        price=price,
        configuration=effective,
        missing=missing,
        adjustments=adjustments,
        acceptance=DefaultsAcceptance(
            as_of=query.as_of,
            group_id=query.group_id,
            expected_generation=effective.policy_generation,
            expected_source_version=effective.source_version,
        ),
    )


async def accepted(
    access: ConfigurationAccess, acceptance: DefaultsAcceptance, query: AuthoringDefaultsQuery
) -> AuthoringDefaults:
    if query.as_of != acceptance.as_of:
        raise ConflictError("default acceptance date differs from the authored revision")
    value = await suggestions(access, query.model_copy(update={"group_id": acceptance.group_id}))
    if (
        value.configuration.policy_generation != acceptance.expected_generation
        or value.configuration.source_version != acceptance.expected_source_version
    ):
        raise ConflictError("configuration defaults changed; preview again")
    return value
