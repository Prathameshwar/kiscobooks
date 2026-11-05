"""Native product-type defaults and lifecycle dependencies; no remote execution."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from catalog.domain.product_types import TypeRequirements
from catalog.domain.profiles import InventoryRules
from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.handling import HandlingProfile, HandlingProfileRevision
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.returns import ReturnPolicy, ReturnPolicyRevision
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision
from catalog.schemas.handling import HandlingRevisionInput
from catalog.schemas.inventory_templates import InventoryRevisionInput
from catalog.schemas.warranties import WarrantyRevisionInput
from catalog.tasks.inventory_templates import invalid_identifier, requirements
from catalog.tasks.return_conditions import conditions
from catalog.tasks.returns import incomplete_conditions

ProfileRevision = (
    InventoryProfileTemplateRevision
    | WarrantyPolicyRevision
    | ReturnPolicyRevision
    | HandlingProfileRevision
)


@dataclass(frozen=True)
class Binding:
    field: str
    model: type[ProfileRevision]
    parent: type[ClassificationMaster]
    parent_field: str
    schema: type[BaseModel] | None


BINDINGS = (
    Binding(
        "inventory_template_revision_id",
        InventoryProfileTemplateRevision,
        InventoryProfileTemplate,
        "template_id",
        InventoryRevisionInput,
    ),
    Binding(
        "warranty_revision_id",
        WarrantyPolicyRevision,
        WarrantyPolicy,
        "policy_id",
        WarrantyRevisionInput,
    ),
    Binding("return_policy_revision_id", ReturnPolicyRevision, ReturnPolicy, "policy_id", None),
    Binding(
        "handling_revision_id",
        HandlingProfileRevision,
        HandlingProfile,
        "profile_id",
        HandlingRevisionInput,
    ),
)


async def validate_defaults(
    db: AsyncSession, company: uuid.UUID, rules: TypeRequirements, incoming: Mapping[str, Any]
) -> None:
    inventory: InventoryRules | None = None
    for binding in BINDINGS:
        revision_id = incoming[binding.field]
        if revision_id is None:
            continue
        revision = await company_object(db, binding.model, revision_id, company_id=company)
        parent = await company_object(
            db, binding.parent, getattr(revision, binding.parent_field), company_id=company
        )
        if revision.published_at is None or not parent.is_active:
            raise ConflictError("product types require active published profile defaults")
        if isinstance(revision, ReturnPolicyRevision):
            await conditions(db, revision)
        else:
            assert binding.schema is not None
            values = {key: getattr(revision, key) for key in binding.schema.model_fields}
            if isinstance(revision, InventoryProfileTemplateRevision):
                values = await requirements(db, company, values)
                identifier = values.pop("identifier_profile_id")
                inventory = InventoryRules(**values, has_identifier_profile=identifier is not None)
            else:
                binding.schema.model_validate(values)
    rules.validate_profile_defaults(
        inventory=inventory, has_handling=incoming["handling_revision_id"] is not None
    )


async def validate_lifecycle(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    activating = isinstance(row, ProductType) and row.is_active and not before.get("is_active")
    retiring = not row.is_active and before.get("is_active")
    for binding in BINDINGS:
        revision = binding.model
        if retiring and isinstance(row, binding.parent):
            dependent = (
                select(ProductTypeRevision.id)
                .join(
                    revision,
                    (revision.tenant_id == ProductTypeRevision.tenant_id)
                    & (revision.company_id == ProductTypeRevision.company_id)
                    & (revision.id == getattr(ProductTypeRevision, binding.field)),
                )
                .join(
                    ProductType,
                    (ProductType.tenant_id == ProductTypeRevision.tenant_id)
                    & (ProductType.company_id == ProductTypeRevision.company_id)
                    & (ProductType.id == ProductTypeRevision.product_type_id),
                )
                .where(
                    ProductTypeRevision.company_id == row.company_id,
                    getattr(revision, binding.parent_field) == row.id,
                    ProductType.is_active.is_(True),
                )
                .limit(1)
            )
            if await db.scalar(dependent) is not None:
                raise ConflictError("profile is referenced by an active product type")
        if activating:
            invalid: list[ColumnElement[bool]] = [
                revision.id.is_(None),
                revision.published_at.is_(None),
                binding.parent.id.is_(None),
                binding.parent.is_active.is_(False),
            ]
            if revision is ReturnPolicyRevision:
                invalid.append(incomplete_conditions())
            if revision is InventoryProfileTemplateRevision:
                invalid.append(invalid_identifier())
            dependent = (
                select(ProductTypeRevision.id)
                .outerjoin(
                    revision,
                    (revision.tenant_id == ProductTypeRevision.tenant_id)
                    & (revision.company_id == ProductTypeRevision.company_id)
                    & (revision.id == getattr(ProductTypeRevision, binding.field)),
                )
                .outerjoin(
                    binding.parent,
                    (binding.parent.tenant_id == revision.tenant_id)
                    & (binding.parent.company_id == revision.company_id)
                    & (binding.parent.id == getattr(revision, binding.parent_field)),
                )
                .where(
                    ProductTypeRevision.company_id == row.company_id,
                    ProductTypeRevision.product_type_id == row.id,
                    getattr(ProductTypeRevision, binding.field).is_not(None),
                    or_(*invalid),
                )
                .limit(1)
            )
            if await db.scalar(dependent) is not None:
                raise ConflictError("product type references an unavailable profile definition")
