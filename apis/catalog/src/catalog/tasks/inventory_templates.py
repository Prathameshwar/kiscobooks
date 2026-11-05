"""Inventory-template validation and real local dependency lifecycle checks."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from catalog.domain.profiles import IdentifierRequirement, validate_identifier_requirements
from catalog.models.classification import ClassificationMaster
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.tax import ItemInventoryProfile
from catalog.schemas.inventory_templates import InventoryRevisionInput


def invalid_identifier() -> ColumnElement[bool]:
    revision = InventoryProfileTemplateRevision
    valid = (
        select(IdentifierProfile.id)
        .where(
            IdentifierProfile.tenant_id == revision.tenant_id,
            IdentifierProfile.company_id == revision.company_id,
            IdentifierProfile.id == revision.identifier_profile_id,
            IdentifierProfile.is_active.is_(True),
            IdentifierProfile.normalization_version == 1,
            select(IdentifierProfileRequirement.id)
            .where(
                IdentifierProfileRequirement.tenant_id == IdentifierProfile.tenant_id,
                IdentifierProfileRequirement.company_id == IdentifierProfile.company_id,
                IdentifierProfileRequirement.profile_id == IdentifierProfile.id,
            )
            .exists(),
        )
        .correlate(revision)
        .exists()
    )
    return revision.identifier_profile_id.is_not(None) & ~valid


async def requirements(
    db: AsyncSession, company: uuid.UUID, incoming: Mapping[str, Any]
) -> dict[str, Any]:
    body = InventoryRevisionInput.model_validate(incoming)
    if body.identifier_profile_id is not None:
        profile = await company_object(
            db, IdentifierProfile, body.identifier_profile_id, company_id=company
        )
        if not profile.is_active or profile.normalization_version != 1:
            raise ConflictError("inventory requires an active supported identifier profile")
        rows = list(
            await db.scalars(
                select(IdentifierProfileRequirement)
                .where(
                    IdentifierProfileRequirement.company_id == company,
                    IdentifierProfileRequirement.profile_id == profile.id,
                )
                .limit(3)
            )
        )
        validate_identifier_requirements(
            tuple(
                IdentifierRequirement(
                    row.identifier_type,
                    row.namespace_rule,
                    row.min_count,
                    row.max_count,
                    row.requires_slot,
                )
                for row in rows
            )
        )
    return body.model_dump()


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    revision = InventoryProfileTemplateRevision
    if isinstance(row, InventoryProfileTemplate):
        if before and row.code != before["code"]:
            used = await db.scalar(
                select(revision.id)
                .where(revision.company_id == row.company_id, revision.template_id == row.id)
                .limit(1)
            )
            if used is not None:
                raise ConflictError("referenced inventory template identity is immutable")
        if row.is_active and before and not before["is_active"]:
            invalid = (
                select(revision.id)
                .where(
                    revision.company_id == row.company_id,
                    revision.template_id == row.id,
                    revision.published_at.is_not(None),
                    invalid_identifier(),
                )
                .limit(1)
            )
            if await db.scalar(invalid) is not None:
                raise ConflictError(
                    "published inventory templates require valid active identifier profiles"
                )
    if isinstance(row, IdentifierProfile) and before.get("is_active") and not row.is_active:
        pinned_use = (
            select(ItemInventoryProfile.id)
            .where(
                ItemInventoryProfile.company_id == row.company_id,
                ItemInventoryProfile.identifier_profile_id == row.id,
            )
            .limit(1)
        )
        if await db.scalar(pinned_use) is not None:
            raise ConflictError("identifier profile is pinned by an activated item")
        active_use = (
            select(revision.id)
            .join(
                InventoryProfileTemplate,
                (InventoryProfileTemplate.company_id == revision.company_id)
                & (InventoryProfileTemplate.id == revision.template_id),
            )
            .where(
                revision.company_id == row.company_id,
                revision.identifier_profile_id == row.id,
                revision.published_at.is_not(None),
                InventoryProfileTemplate.is_active.is_(True),
            )
            .limit(1)
        )
        if await db.scalar(active_use) is not None:
            raise ConflictError("identifier profile is referenced by an active inventory template")
