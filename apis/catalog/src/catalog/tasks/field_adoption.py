"""Accepted definitions are Catalog-owned acknowledgements, never editable masters."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import CustomDefinition
from billing_platform.db.claims import insert_candidate
from billing_platform.db.tenant_context import require_current_tenant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.field_adoption import CustomFieldAdoption
from catalog.models.projections import CustomFieldDefinitionProjection

PRODUCT_ENTITIES = frozenset({"catalog.item", "catalog.product_family"})


async def state(
    db: AsyncSession, company: uuid.UUID, entity: str, *, lock: bool = False
) -> CustomFieldAdoption | None:
    if lock:
        await insert_candidate(
            db,
            CustomFieldAdoption,
            {
                "tenant_id": require_current_tenant(),
                "company_id": company,
                "entity_type": entity,
                "definitions": [],
                "row_version": 1,
            },
        )
    stmt = select(CustomFieldAdoption).where(
        CustomFieldAdoption.company_id == company, CustomFieldAdoption.entity_type == entity
    )
    if lock:
        stmt = stmt.with_for_update()
    row = await db.scalar(stmt.execution_options(populate_existing=True))
    assert row is None or isinstance(row, CustomFieldAdoption)
    return row


async def accepted_definitions(
    db: AsyncSession,
    company: uuid.UUID,
    entity: str,
    candidates: tuple[CustomDefinition, ...],
    selected: Mapping[str, CustomFieldDefinitionProjection],
    features: frozenset[str],
) -> tuple[CustomDefinition, ...]:
    adopted = await state(db, company, entity)
    previous = {
        value["key"]: CustomDefinition.model_validate(value)
        for value in (adopted.definitions if adopted else [])
    }
    result = []
    for candidate in candidates:
        source = selected[candidate.key]
        if not source.requires_adoption:
            result.append(candidate)
            continue
        accepted = previous.get(candidate.key)
        if accepted is None:
            accepted = candidate.model_copy(update={"is_active": False})
        if source.requires_feature is not None and source.requires_feature not in features:
            accepted = accepted.model_copy(update={"is_active": False})
        result.append(accepted)
    return tuple(result)


async def claim_definitions(
    db: AsyncSession, entity: str, definitions: tuple[CustomDefinition, ...]
) -> tuple[CustomDefinition, ...]:
    if entity not in PRODUCT_ENTITIES:
        return definitions
    guard = await state(db, SCOPE_ALL, entity, lock=True)
    assert guard is not None
    merged = {d.key: d for d in definitions}
    for value in guard.definitions:
        rule = CustomDefinition.model_validate(value)
        merged[rule.key] = rule
    return tuple(merged.values())
