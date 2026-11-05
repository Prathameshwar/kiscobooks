"""Submitted advanced definitions; native product rows remain the authority."""

import hashlib
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.schemas.advanced_product_creation import (
    AdvancedDefinitionCreate,
    AdvancedDefinitionStatus,
)
from catalog.tasks.field_context import load_field_context


def status(row: AdvancedProductCreation) -> AdvancedDefinitionStatus:
    entries = row.progress.get("skus", {})
    return AdvancedDefinitionStatus.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "status": row.status,
            "step": row.step,
            "row_version": row.row_version,
            "family_id": row.family_id,
            "sku_ids": [uuid.UUID(value) for value in row.sku_ids],
            "sku_progress": [
                {
                    "item_id": value,
                    **{
                        key: entries.get(value, {})[key]
                        for key in (
                            "setup_done",
                            "price_draft_ids",
                            "published_price_ids",
                              "purchase_reference_id",
                              "mrp_id",
                            "activated",
                              "opening_state",
                              "opening_step",
                              "opening_control_id",
                              "opening_voucher_id",
                              "opening_operation_id",
                        )
                        if key in entries.get(value, {})
                    },
                }
                for value in row.sku_ids
            ],
        }
    )


def audit(db: AsyncSession, row: AdvancedProductCreation, actor: Actor, action: str) -> None:
    event = "catalog.advanced_product_creation." + action
    emit(
        db,
        tenant_id=row.tenant_id,
        aggregate_type="catalog.advanced_product_creation",
        aggregate_id=row.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="admin",
            entity_type="catalog.advanced_product_creation",
            entity_id=row.id,
            actor_user_id=actor.user_id,
            company_id=row.company_id,
        ),
    )


async def owned(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AdvancedProductCreation:
    actor.require_scope("item.read", target=ScopePath(company_id=company))
    row = await company_object(
        db, AdvancedProductCreation, creation_id, company_id=company, lock=lock
    )
    if row.owner_user_id != actor.user_id:
        raise PermissionDeniedError("Only the submitting user can read this creation")
    return row


async def record_definition(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    key: str,
    body: AdvancedDefinitionCreate,
    family_id: uuid.UUID,
    sku_ids: list[uuid.UUID],
) -> uuid.UUID:
    request = body.model_dump(mode="json", exclude_unset=True)
    row = AdvancedProductCreation(
        id=uuid7(),
        tenant_id=actor.tenant_id,
        company_id=company,
        created_by=actor.user_id,
        updated_by=actor.user_id,
        owner_user_id=actor.user_id,
        command_key=key,
        request_hash=hashlib.sha256(canonical_json(request)).hexdigest(),
        request=request,
        status="DEFINED",
        step="SETUP",
        row_version=1,
        family_id=family_id,
        sku_ids=[str(value) for value in sku_ids],
        progress={},
    )
    db.add(row)
    audit(db, row, actor, "create")
    return row.id


async def read_status(
    db: AsyncSession, actor: Actor, company: uuid.UUID, creation_id: uuid.UUID
) -> AdvancedDefinitionStatus:
    row = await owned(db, actor, company, creation_id)
    await load_field_context(db, actor, company, "catalog.product_family")
    await load_field_context(db, actor, company, "catalog.item")
    return status(row)
