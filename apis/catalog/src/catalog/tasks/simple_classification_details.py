"""Protected category/manufacturer selections for the Simple creation form."""

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import select

from catalog.domain.categories import CategoryCardinalityError
from catalog.models.classification import CategoryScheme
from catalog.models.commercial import Manufacturer, ManufacturerSite
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.schemas.simple_product_creation import (
    SimpleCreationInput,
    SimpleRequiredCategoryScheme,
)
from catalog.tasks.category_membership import references
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import protected


async def required_schemes(access: ConfigurationAccess) -> list[SimpleRequiredCategoryScheme]:
    await protected(access, CategoryScheme)
    schemes = list(
        await access.db.scalars(
            select(CategoryScheme)
            .where(
                CategoryScheme.company_id == access.company,
                CategoryScheme.is_active.is_(True),
                CategoryScheme.is_required.is_(True),
            )
            .order_by(CategoryScheme.name, CategoryScheme.id)
            .limit(129)
        )
    )
    if len(schemes) > 128:
        raise ConflictError("Required category schemes exceed the product membership limit")
    result = []
    for scheme in schemes:
        await access.require(scheme)
        result.append(
            SimpleRequiredCategoryScheme.model_validate(
                {
                    "id": scheme.id,
                    "name": scheme.name,
                    "membership_mode": scheme.membership_mode,
                }
            )
        )
    return result


async def validate_details(
    access: ConfigurationAccess,
    config: EffectiveConfiguration,
    body: SimpleCreationInput,
) -> None:
    if config.options.category_mode == "DISABLED":
        if body.categories:
            raise ValidationFailedError(
                "Categories are disabled",
                fields={"categories": "Disabled by product configuration"},
            )
    else:
        schemes = await required_schemes(access)
        missing = [
            scheme.name
            for scheme in schemes
            if scheme.id not in {entry.scheme_id for entry in body.categories}
        ]
        if missing or (config.options.category_mode == "REQUIRED" and not body.categories):
            raise ValidationFailedError(
                "Choose the required categories",
                fields={
                    "categories": "Choose a category for: " + ", ".join(missing)
                    if missing
                    else "Required by product configuration",
                },
            )
        try:
            await references(access, body.categories)
        except CategoryCardinalityError as error:
            raise ValidationFailedError(
                error.message, fields={"categories": error.message}
            ) from error
    if body.manufacturer_id is not None:
        await access.reference(Manufacturer, body.manufacturer_id)
        if body.manufacturer_site_id is not None:
            site = await access.reference(ManufacturerSite, body.manufacturer_site_id)
            if site.manufacturer_id != body.manufacturer_id:
                raise PermissionDeniedError("site belongs to another manufacturer")
