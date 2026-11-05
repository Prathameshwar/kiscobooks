"""Fixed, audited type/group defaults from verified company enrollment facts."""

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Literal, TypeVar, cast

from billing_platform.db.base import Base
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import changes
from catalog.models.classification import ClassificationMaster, ItemGroup, ItemGroupParent
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.projections import CompanyProjection
from catalog.schemas.classification import GroupCreate
from catalog.schemas.commercial import ProductTypeCreate
from catalog.tasks.commercial_history import requirements
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.projections import require_identity_context
from catalog.tasks.unit_defaults import inventory_enabled

Row = TypeVar("Row", bound=Base)
Master = TypeVar("Master", bound=ClassificationMaster)
REASON = "company-product-defaults-v1"


@dataclass
class ProductDefaultsResult:
    status: Literal["READY", "NOT_APPLICABLE", "NEEDS_REVIEW"]
    created_records: int = 0


async def existing_default(
    db: AsyncSession, company: uuid.UUID, model: type[Master]
) -> Master | None:
    # Code survives renames; reuse a pre-existing named Default with a different code.
    return cast(
        Master | None,
        await db.scalar(
            select(model)
            .where(
                model.company_id == company,
                or_(func.lower(model.code) == "default", func.lower(model.name) == "default"),
            )
            .order_by(case((func.lower(model.code) == "default", 0), else_=1), model.id)
            .limit(1)
        ),
    )


async def ensure_product_defaults(db: AsyncSession, company: uuid.UUID) -> ProductDefaultsResult:
    """Trusted provisioner only; never grants a user authoring/publication authority."""
    tenant = require_current_tenant()
    await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    if profile.status != "active":
        return ProductDefaultsResult("NOT_APPLICABLE")
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    product_type = await existing_default(db, company, ProductType)
    group = await existing_default(db, company, ItemGroup)
    # Preserve deliberately inactive/incompatible defaults for administrator review.
    if (product_type and (not product_type.is_active or product_type.kind != "BOTH")) or (
        group and (not group.is_active or group.allowed_kind != "BOTH")
    ):
        return ProductDefaultsResult("NEEDS_REVIEW")
    pack = json.loads(
        files("catalog.seeds").joinpath("company_product_defaults_v1.json").read_text("utf-8")
    )
    type_values = ProductTypeCreate.model_validate(pack["type"]).model_dump()
    group_values = GroupCreate.model_validate(pack["group"]).model_dump()
    revision_values = dict(pack["revision"])
    if await inventory_enabled(db, company):
        revision_values["inventory_modes"] = ["NON_STOCK", "STOCK"]
    revision_values, _rules = requirements("BOTH", revision_values)
    result = ProductDefaultsResult("READY")

    def evidence(
        row: Base, identity: uuid.UUID, action: Literal["create", "publish"], values: dict[str, Any]
    ) -> None:
        entity = "catalog." + row.__tablename__
        event = audit_event(entity, action)
        payload = audit_payload(
            action=event,
            category=category(entity, action),
            entity_type=entity,
            entity_id=identity,
            actor_user_id=None,
            company_id=company,
            changes=changes(entity, frozenset(values), after=values, creating=action == "create"),
            reason=REASON,
        )
        payload.update(actor_type="system", source_service="catalog")
        emit(
            db,
            tenant_id=tenant,
            aggregate_type=entity,
            aggregate_id=identity,
            event_type=event,
            payload=payload,
        )

    async def create(model: type[Row], **values: Any) -> Row:
        identity = uuid7()
        row = model(id=identity, tenant_id=tenant, company_id=company, **values)
        db.add(row)
        await db.flush()
        evidence(row, identity, "create", values)
        result.created_records += 1
        return row

    if product_type is None:
        product_type = await create(ProductType, row_version=1, is_active=True, **type_values)
        revision = await create(
            ProductTypeRevision,
            product_type_id=product_type.id,
            revision=1,
            row_version=1,
            kind="BOTH",
            published_at=None,
            **revision_values,
        )
        revision.published_at = utcnow()
        revision.row_version = 2
        evidence(
            revision,
            revision.id,
            "publish",
            {**revision_values, "published_at": revision.published_at},
        )
    elif (
        await db.scalar(
            select(ProductTypeRevision.id)
            .where(
                ProductTypeRevision.company_id == company,
                ProductTypeRevision.product_type_id == product_type.id,
                ProductTypeRevision.published_at.is_not(None),
            )
            .limit(1)
        )
        is None
    ):
        # An existing user-authored draft is never silently published by enrollment.
        return ProductDefaultsResult("NEEDS_REVIEW")
    if group is None:
        group_values.pop("valid_from")
        group_values.pop("parent_group_id")
        group = await create(ItemGroup, row_version=1, is_active=True, **group_values)
        await create(
            ItemGroupParent,
            group_id=group.id,
            parent_group_id=None,
            valid_from=dt.date(1000, 1, 1),
            valid_to=None,
        )
    if result.created_records:
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation exhausted")
        state.generation += 1
        await db.flush()
    return result
