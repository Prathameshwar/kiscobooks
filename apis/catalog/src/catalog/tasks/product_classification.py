"""Dated primary classification and bounded merchandising/source relationships."""

import datetime as dt
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import or_, select

from catalog.models.classification import ItemGroup
from catalog.models.commercial import Manufacturer, ManufacturerSite
from catalog.models.product_definitions import (
    FamilyGroupAssignment,
    FamilyManufacturer,
)
from catalog.schemas.product_authoring import (
    CategoryAssignmentInput,
    GroupAssignmentInput,
    ManufacturerAssignmentInput,
)
from catalog.tasks.product_commands import ProductWork


async def assign_group(work: ProductWork, body: GroupAssignmentInput) -> None:
    row = await work.new(
        FamilyGroupAssignment,
        family_id=work.family.id,
        group_id=body.group_id,
        valid_from=body.valid_from,
        valid_to=None,
    )
    group = await work.access.reference(ItemGroup, body.group_id)
    if group.allowed_kind not in {work.family.kind, "BOTH"}:
        raise ValidationFailedError("group does not admit the product kind")
    context = await work.access.context(FamilyGroupAssignment)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("group assignment history is protected")
    existing = list(
        await work.db.scalars(
            select(FamilyGroupAssignment)
            .where(
                FamilyGroupAssignment.company_id == work.company,
                FamilyGroupAssignment.family_id == work.family.id,
                or_(
                    FamilyGroupAssignment.valid_to.is_(None),
                    FamilyGroupAssignment.valid_to >= body.valid_from,
                ),
            )
            .order_by(FamilyGroupAssignment.valid_from)
            .limit(2)
        )
    )
    if len(existing) > 1 or (existing and existing[0].valid_from >= body.valid_from):
        raise ConflictError("new primary-group assignment conflicts with existing dated history")
    if existing:
        today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
        if body.valid_from < today:
            raise ConflictError("group reassignment cannot rewrite effective history")
        previous = existing[0]
        await work.access.require(previous)
        before = await work.access.values(previous)
        previous.valid_to = body.valid_from - dt.timedelta(days=1)
        previous.row_version += 1
        await work.record(previous, before, "close")
    work.db.add(row)


async def assign_categories(
    work: ProductWork, body: CategoryAssignmentInput, secret: bytes | None = None
) -> None:
    from catalog.tasks.category_schedule import replace

    await replace(work, body, secret)


async def assign_manufacturer(work: ProductWork, body: ManufacturerAssignmentInput) -> None:
    row = await work.new(
        FamilyManufacturer,
        family_id=work.family.id,
        production_role=body.role,
        **body.model_dump(exclude={"role", "expected_version"}),
    )
    if work.family.kind != "GOODS":
        raise ValidationFailedError("services do not have physical manufacturer assignments")
    from catalog.tasks.product_choices import require_choice

    await require_choice(work, "manufacturer", as_of=body.valid_from)
    await work.access.reference(Manufacturer, body.manufacturer_id)
    if body.site_id is not None:
        site = await work.access.reference(ManufacturerSite, body.site_id)
        if site.manufacturer_id != body.manufacturer_id:
            raise PermissionDeniedError("site belongs to another manufacturer")
    context = await work.access.context(FamilyManufacturer)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("manufacturer assignment history is protected")
    conflict = select(FamilyManufacturer.id).where(
        FamilyManufacturer.company_id == work.company,
        FamilyManufacturer.family_id == work.family.id,
        FamilyManufacturer.manufacturer_id == body.manufacturer_id,
        FamilyManufacturer.production_role == body.role,
        or_(FamilyManufacturer.valid_to.is_(None), FamilyManufacturer.valid_to >= body.valid_from),
    )
    if body.valid_to is not None:
        conflict = conflict.where(FamilyManufacturer.valid_from <= body.valid_to)
    if await work.db.scalar(conflict.limit(1)) is not None:
        raise ConflictError("manufacturer assignment overlaps its existing history")
    work.db.add(row)
