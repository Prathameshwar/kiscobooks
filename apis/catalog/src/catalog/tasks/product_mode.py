"""Company-locked live authoring capability; historical stock remains independent."""

import hashlib
import hmac
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.pagination import CursorCodec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import BulkJob
from catalog.models.configuration import ProductEntryOptionPolicy
from catalog.models.product_authoring import CompanyProductAuthoringConfiguration as Mode
from catalog.models.product_definitions import FamilyAttribute, ItemVariantKey
from catalog.models.products import Item, ProductFamily
from catalog.schemas.product_mode import (
    ProductModeCommit,
    ProductModeDetail,
    ProductModePreview,
    ProductModeRequest,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.field_context import load_field_context
from catalog.tasks.policy_state import policy_state

ENTITY = "catalog.company_product_authoring_configuration"


async def current(db: AsyncSession, company: uuid.UUID, *, lock: bool = False) -> Mode | None:
    query = select(Mode).where(Mode.company_id == company).execution_options(populate_existing=True)
    row = await db.scalar(query.with_for_update() if lock else query)
    assert row is None or isinstance(row, Mode)
    return row


async def version(db: AsyncSession, company: uuid.UUID, *, lock: bool = False) -> int:
    row = await current(db, company, lock=lock)
    return row.row_version if row else 0


async def enabled(db: AsyncSession, company: uuid.UUID, *, lock: bool = False) -> bool:
    row = await current(db, company, lock=lock)
    return bool(row and row.product_family_sku_enabled)


async def require_advanced(db: AsyncSession, company: uuid.UUID) -> None:
    if not await enabled(db, company, lock=True):
        raise ConflictError("Enable product families and SKUs in Product Configuration first.")


async def check_version(db: AsyncSession, company: uuid.UUID, expected: int) -> None:
    if await version(db, company, lock=True) != expected:
        raise ConflictError("Product authoring mode changed; review the product again.")


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, *, lock: bool = False
) -> ProductModeDetail:
    context = await load_field_context(db, actor, company, ENTITY)
    required = {"product_family_sku_enabled", "row_version"}
    if not required <= context.readable():
        raise PermissionDeniedError("product authoring configuration is protected")
    row = await current(db, company, lock=lock)
    if row and not required <= context.readable(
        {
            "product_family_sku_enabled": row.product_family_sku_enabled,
            "row_version": row.row_version,
        }
    ):
        raise PermissionDeniedError("product authoring configuration is protected")
    state = await policy_state(db, actor, company, lock=lock)
    return ProductModeDetail(
        company_id=company,
        product_family_sku_enabled=bool(row and row.product_family_sku_enabled),
        row_version=row.row_version if row else 0,
        policy_generation=state.generation if state else 1,
    )


async def blockers(db: AsyncSession, company: uuid.UUID, *, lock: bool = False) -> list[str]:
    # Existence-only checks deliberately disclose no protected product identities.
    members = select(Item.family_id).where(Item.company_id == company).group_by(Item.family_id)
    invalid_members = members.having(
        (func.count(Item.id) != 1) | (func.sum(func.coalesce(Item.default_slot, 0)) != 1)
    )
    checks = (
        (
            "variant_structure",
            select(ProductFamily.id).where(
                ProductFamily.company_id == company, ProductFamily.structure_mode != "SIMPLE"
            ),
        ),
        ("multiple_or_nondefault_items", invalid_members),
        (
            "family_without_default_item",
            select(ProductFamily.id).where(
                ProductFamily.company_id == company,
                ~select(Item.id)
                .where(
                    Item.company_id == company,
                    Item.family_id == ProductFamily.id,
                    Item.default_slot == 1,
                )
                .exists(),
            ),
        ),
        (
            "variant_axes",
            select(FamilyAttribute.id).where(
                FamilyAttribute.company_id == company, FamilyAttribute.is_axis.is_(True)
            ),
        ),
        ("variant_keys", select(ItemVariantKey.id).where(ItemVariantKey.company_id == company)),
        (
            "explicit_variant_policy",
            select(ProductEntryOptionPolicy.id).where(
                ProductEntryOptionPolicy.company_id == company,
                (ProductEntryOptionPolicy.variants_mode == "REQUIRED")
                | (ProductEntryOptionPolicy.variants_default.is_(True)),
            ),
        ),
        (
            "pending_bulk_jobs",
            select(BulkJob.id).where(
                BulkJob.company_id == company,
                BulkJob.state.not_in(("SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED")),
            ),
        ),
    )
    return [
        reason
        for reason, query in checks
        if await db.scalar(query.limit(1).with_for_update() if lock else query.limit(1)) is not None
    ]


def codec(actor: Actor, company: uuid.UUID, secret: bytes) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.product-mode.v1", hashlib.sha256),
        context=f"product-mode:{actor.tenant_id}:{company}:{actor.user_id}",
        ttl_seconds=900,
    )


async def preview(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    body: ProductModeRequest,
    secret: bytes,
    *,
    lock: bool = False,
) -> ProductModePreview:
    detail = await read(db, actor, company, lock=lock)
    actor.require_scope("product_configuration.manage", target=ScopePath(company_id=company))
    if (body.expected_version, body.expected_generation) != (
        detail.row_version,
        detail.policy_generation,
    ):
        raise ConflictError("Product authoring preview is stale; reload configuration.")
    reasons = (
        await blockers(db, company, lock=lock)
        if detail.product_family_sku_enabled and not body.product_family_sku_enabled
        else []
    )
    payload = {**body.model_dump(exclude={"preview_token"}), "blockers": reasons}
    return ProductModePreview(
        **detail.model_dump(),
        requested_enabled=body.product_family_sku_enabled,
        blockers=reasons,
        preview_token=codec(actor, company, secret).encode(payload),
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: ProductModeCommit,
    key: str,
    secret: bytes,
) -> CommandResult[ProductModeDetail]:
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        ENTITY + ".update",
        key,
        body.model_dump(mode="json"),
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        context = await load_field_context(
            db, actor, company, ENTITY, permission="product_configuration.manage"
        )
        await read(db, actor, company)
        await policy_state(db, actor, company, lock=receipt is None)
        existing = await current(db, company, lock=receipt is None)
        actual = (
            {
                "product_family_sku_enabled": existing.product_family_sku_enabled,
                "change_reason": existing.change_reason,
                "row_version": existing.row_version,
            }
            if existing
            else {}
        )
        context.assert_writable(
            frozenset({"product_family_sku_enabled", "change_reason", "row_version"}),
            before=actual,
            after={
                **actual,
                "product_family_sku_enabled": body.product_family_sku_enabled,
                "change_reason": body.change_reason,
            },
        )
        if receipt is not None:
            context.assert_writable(
                frozenset(receipt["after"]), before=receipt["before"], after=receipt["after"]
            )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        fresh = await preview(db, actor, company, body, secret, lock=True)
        reviewed = codec(actor, company, secret).decode(body.preview_token)
        request = ProductModeRequest.model_validate(body.model_dump(exclude={"preview_token"}))
        if reviewed != {**request.model_dump(), "blockers": fresh.blockers}:
            raise ConflictError("Product authoring preview changed; preview again.")
        if fresh.blockers:
            raise ConflictError(
                "Cannot disable product families and SKUs: " + ", ".join(fresh.blockers)
            )
        row = await current(db, company, lock=True)
        before = (
            {
                "product_family_sku_enabled": row.product_family_sku_enabled,
                "row_version": row.row_version,
                "change_reason": row.change_reason,
            }
            if row
            else {}
        )
        if row is None:
            row = Mode(
                id=uuid7(),
                tenant_id=actor.tenant_id,
                company_id=company,
                product_family_sku_enabled=body.product_family_sku_enabled,
                row_version=1,
                change_reason=body.change_reason,
                created_by=actor.user_id,
                updated_by=actor.user_id,
            )
            db.add(row)
        else:
            if row.row_version >= 2**31 - 1:
                raise ConflictError("Product authoring configuration version exhausted")
            row.product_family_sku_enabled = body.product_family_sku_enabled
            row.change_reason, row.row_version = body.change_reason, row.row_version + 1
            row.updated_at, row.updated_by = utcnow(), actor.user_id
        state = await policy_state(db, actor, company, lock=True)
        assert state is not None
        if state.generation >= 2**63 - 1:
            raise ConflictError("Company policy generation exhausted")
        state.generation += 1
        after = {
            "product_family_sku_enabled": row.product_family_sku_enabled,
            "row_version": row.row_version,
            "change_reason": row.change_reason,
        }
        context = await load_field_context(
            db, actor, company, ENTITY, permission="product_configuration.manage"
        )
        context.assert_writable(frozenset(after), before=before, after=after)
        audit_change(
            db,
            actor,
            company,
            ENTITY,
            row.id,
            "update" if before else "create",
            frozenset(after),
            before=before,
            after=after,
        )
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id), "before": before, "after": after})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> ProductModeDetail:
        return await read(db, actor, company)

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render
    )
