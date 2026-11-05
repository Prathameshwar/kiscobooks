"""Indexed native references that freeze the meaning of product definitions."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import Base
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroupParent
from catalog.models.configuration import CONFIGURATION_MODELS
from catalog.models.product_definitions import PRODUCT_DEFINITION_MODELS, FamilyGroupAssignment
from catalog.models.products import Item
from catalog.models.tax import ACTIVATION_MODELS, TAX_MODELS
from catalog.tasks.field_context import load_field_context

SEMANTIC_FIELDS = frozenset(
    {
        "code",
        "is_active",
        "dimension",
        "decimal_places",
        "quantity_increment",
        "value_type",
        "measurement_dimension",
        "is_variant_capable",
        "definition_id",
        "unit_id",
        "value_text",
        "value_integer",
        "value_decimal",
        "value_boolean",
        "value_date",
        "value_datetime",
        "allowed_kind",
        "membership_mode",
        "scheme_id",
        "manufacturer_id",
        "kind",
        "normalization_version",
        "matching_mode",
    }
)


async def product_dependencies(db: AsyncSession, row: Any) -> bool:
    """Walk only the fixed schema's direct references and revision-to-master references.

    Every query is an indexed existence lookup. Revision subqueries include both
    tenant and company explicitly; every subquery uses mapped ORM entities.
    No table or column name comes from request data.
    """
    mapped = {mapper.local_table: mapper.class_ for mapper in Base.registry.mappers}
    for model in (
        *CONFIGURATION_MODELS,
        *PRODUCT_DEFINITION_MODELS,
        *TAX_MODELS,
        *ACTIVATION_MODELS,
    ):
        for foreign in model.__table__.foreign_keys:
            if foreign.column.name != "id":
                continue
            related = foreign.column.table
            related_model = mapped[related]
            field = getattr(model, foreign.parent.name)
            candidates = []
            if related.name == row.__tablename__:
                candidates.append(field == row.id)
            elif "tenant_id" in related.c and "company_id" in related.c:
                for parent in related.foreign_keys:
                    if parent.column.name == "id" and parent.column.table.name == row.__tablename__:
                        candidates.append(
                            field.in_(
                                select(related_model.id).where(
                                    related_model.tenant_id == row.tenant_id,
                                    related_model.company_id == row.company_id,
                                    getattr(related_model, parent.parent.name) == row.id,
                                )
                            )
                        )
            for criterion in candidates:
                if (
                    await db.scalar(
                        select(model.id)
                        .where(
                            model.company_id == row.company_id,
                            criterion,
                        )
                        .limit(1)
                    )
                    is not None
                ):
                    return True
    return False


async def guard_active_group_move(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    group_id: uuid.UUID,
    parents: list[ItemGroupParent],
    start: dt.date,
) -> None:
    """Conservatively protect current/future descendants until adoption migration exists."""
    descendants: dict[uuid.UUID, set[uuid.UUID]] = {}
    for edge in parents:
        if edge.parent_group_id is not None and (edge.valid_to is None or edge.valid_to >= start):
            descendants.setdefault(edge.parent_group_id, set()).add(edge.group_id)
    affected = {group_id}
    pending = [group_id]
    while pending:
        children = descendants.get(pending.pop(), set()) - affected
        affected.update(children)
        pending.extend(children)
    for entity, fields in (
        ("catalog.item", {"status", "family_id"}),
        ("catalog.family_group_assignment", {"family_id", "group_id", "valid_to"}),
    ):
        # A move must enforce dependency integrity even for a group-only administrator.
        # Native field denies still apply; the result exposes no dependent identifiers.
        context = await load_field_context(db, actor, company, entity, permission="item_group.move")
        if not fields <= context.readable():
            raise PermissionDeniedError("group move requires readable product dependencies")
    dependent = await db.scalar(
        select(FamilyGroupAssignment.id)
        .join(
            Item,
            (Item.tenant_id == FamilyGroupAssignment.tenant_id)
            & (Item.company_id == FamilyGroupAssignment.company_id)
            & (Item.family_id == FamilyGroupAssignment.family_id),
        )
        .where(
            FamilyGroupAssignment.company_id == company,
            FamilyGroupAssignment.group_id.in_(affected),
            or_(FamilyGroupAssignment.valid_to.is_(None), FamilyGroupAssignment.valid_to >= start),
            Item.status == "ACTIVE",
        )
        .limit(1)
    )
    if dependent is not None:
        raise ConflictError("group move affects active products; adoption migration is required")
