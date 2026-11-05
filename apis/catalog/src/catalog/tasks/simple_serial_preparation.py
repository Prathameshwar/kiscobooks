"""Protected native serial requirements and validation before product admission."""

from typing import Any

from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError
from sqlalchemy import select
from voucher_execution.identifiers import IdentifierRequirement, validate_identifier_inputs

from catalog.domain.units import QuantityRule, validate_serial_rule
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.units import UnitOfMeasure
from catalog.schemas.configuration import AuthoringDefaults, EffectiveConfiguration
from catalog.schemas.simple_product_creation import SimpleCreationInput, SimpleSerialOptions
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import protected


async def serial_options(
    access: ConfigurationAccess, config: EffectiveConfiguration, kind: str
) -> SimpleSerialOptions:
    identity = config.profiles.inventory_template_revision_id
    if kind != "GOODS" or identity is None:
        return SimpleSerialOptions()
    template = await access.reference(InventoryProfileTemplateRevision, identity)
    if not template.serial_tracking:
        return SimpleSerialOptions()
    context = await access.context(InventoryProfileTemplateRevision)
    if not {"inventory", "serial_tracking"} <= context.features:
        raise ConflictError("Enable the configured serial inventory capabilities")
    if template.identifier_profile_id is None:
        raise ConflictError("Configure the serial identifier profile")
    profile = await access.reference(IdentifierProfile, template.identifier_profile_id)
    if not profile.is_active or profile.normalization_version != 1:
        raise ConflictError("Choose an active supported identifier profile")
    await protected(access, IdentifierProfileRequirement)
    rows = list(
        await access.db.scalars(
            select(IdentifierProfileRequirement)
            .where(
                IdentifierProfileRequirement.company_id == access.company,
                IdentifierProfileRequirement.profile_id == profile.id,
            )
            .order_by(IdentifierProfileRequirement.identifier_type)
            .limit(3)
        )
    )
    if not 1 <= len(rows) <= 2:
        raise ConflictError("Configure complete serial identifier requirements")
    requirements = []
    for row in rows:
        await access.require(row)
        requirements.append(
            IdentifierRequirement.model_validate(
                {key: getattr(row, key) for key in IdentifierRequirement.model_fields}
            )
        )
    return SimpleSerialOptions(enabled=True, requirements=requirements)


async def prepare_serials(
    access: ConfigurationAccess, defaults: AuthoringDefaults, body: SimpleCreationInput
) -> SimpleSerialOptions:
    options = await serial_options(access, defaults.configuration, body.kind)
    entries: list[tuple[str, Any]] = (
        [(f"batches.{index}.", entry) for index, entry in enumerate(body.batches)]
        if body.batch_enabled
        else [("", body)]
    )
    if not options.enabled:
        if any(entry.serials for _, entry in entries):
            raise ValidationFailedError("Serial entry is disabled by Product Configuration")
        return options
    base = await access.reference(UnitOfMeasure, body.base_unit_id)
    if base.quantity_increment != 1:
        raise ValidationFailedError("Serial tracking requires a base unit with increment one")
    assert defaults.quantity is not None
    validate_serial_rule(base.dimension, QuantityRule(base.decimal_places, base.quantity_increment))
    validate_serial_rule(
        base.dimension,
        QuantityRule(
            defaults.quantity.quantity_decimal_places, defaults.quantity.quantity_increment
        ),
    )
    seen: set[tuple[str, str]] = set()
    for prefix, entry in entries:
        if entry.opening_quantity != len(entry.serials):
            raise ValidationFailedError(
                "Opening quantity must equal the serial unit count",
                fields={prefix + "opening_quantity": "Enter one serial row per whole opening unit"},
            )
        for index, serial in enumerate(entry.serials):
            field = prefix + f"serials.{index}.identifiers"
            try:
                normalized = validate_identifier_inputs(options.requirements, serial.identifiers)
                for value, key in normalized:
                    identity = value.identifier_type, key
                    if identity in seen:
                        raise ValidationFailedError("This serial or IMEI appears on another unit")
                    seen.add(identity)
            except PlatformError as exc:
                raise ValidationFailedError(exc.message, fields={field: exc.message}) from exc
    return options
