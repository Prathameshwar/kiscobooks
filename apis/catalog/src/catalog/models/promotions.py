"""Catalog-owned, immutable promotion definition facts; no redemption state."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Quantity, UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column


class PromotionRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class Promotion(PromotionRow):
    __tablename__ = "promotion"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_scope"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_promotion_code"),
        CheckConstraint("row_version >= 1", name="version"),
        Index("ix_promotion_name", "tenant_id", "company_id", "name", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PromotionRevision(PromotionRow):
    __tablename__ = "promotion_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_revision_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "promotion_id",
            "version",
            name="uq_promotion_revision_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "promotion_id"],
            ["promotion.tenant_id", "promotion.company_id", "promotion.id"],
            name="fk_promotion_revision_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "return_policy_revision_id"],
            [
                "return_policy_revision.tenant_id",
                "return_policy_revision.company_id",
                "return_policy_revision.id",
            ],
            name="fk_promotion_revision_return_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "stack_policy_revision_id"],
            [
                "promotion_stack_policy.tenant_id",
                "promotion_stack_policy.company_id",
                "promotion_stack_policy.id",
            ],
            name="fk_promotion_revision_stack_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "stack_policy_revision_id", "stack_group_id"],
            [
                "promotion_stack_group.tenant_id",
                "promotion_stack_group.company_id",
                "promotion_stack_group.policy_revision_id",
                "promotion_stack_group.id",
            ],
            name="fk_promotion_revision_stack_group",
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("trigger_mode = 'AUTOMATIC'", name="trigger"),
        CheckConstraint("selection_mode = 'SNAPSHOT_ON_PUBLISH'", name="selection"),
        CheckConstraint("starts_at < ends_at", name="window"),
        CheckConstraint("priority BETWEEN 0 AND 32767", name="priority"),
        CheckConstraint("policy_generation >= 1 AND source_version >= 1", name="lineage"),
        CheckConstraint("LENGTH(source_sha256) = 64", name="hash"),
        Index(
            "ix_promotion_revision_window",
            "tenant_id",
            "company_id",
            "starts_at",
            "ends_at",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    promotion_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    starts_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    ends_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    stack_policy_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    stack_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    return_policy_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    published_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class PromotionBenefit(PromotionRow):
    __tablename__ = "promotion_benefit"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_benefit_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", name="uq_promotion_benefit_revision"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "promotion_revision.tenant_id",
                "promotion_revision.company_id",
                "promotion_revision.id",
            ],
            name="fk_promotion_benefit_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_revision_id"],
            [
                "item_unit_revision.tenant_id",
                "item_unit_revision.company_id",
                "item_unit_revision.id",
            ],
            name="fk_promotion_benefit_unit",
        ),
        CheckConstraint("kind = 'BUY_GET' AND pool = 'SAME_ITEM'", name="kind"),
        CheckConstraint(
            "qualifying_quantity > 0 AND reward_quantity > 0 AND reward_percent = 100 "
            "AND maximum_repeats BETWEEN 1 AND 1000",
            name="amounts",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    pool: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    qualifying_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    reward_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    reward_percent: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    maximum_repeats: Mapped[int] = mapped_column(Integer, nullable=False)


class PromotionSkuTarget(PromotionRow):
    __tablename__ = "promotion_sku_target"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_sku_target_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "revision_id", "item_id", name="uq_promotion_sku_target_item"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "promotion_revision.tenant_id",
                "promotion_revision.company_id",
                "promotion_revision.id",
            ],
            name="fk_promotion_sku_target_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_promotion_sku_target_item",
        ),
        Index("ix_promotion_sku_target_item", "tenant_id", "company_id", "item_id", "revision_id"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class PromotionPriceLevelTarget(PromotionRow):
    __tablename__ = "promotion_price_level_target"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_price_target_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "price_level_id",
            name="uq_promotion_price_target_level",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "promotion_revision.tenant_id",
                "promotion_revision.company_id",
                "promotion_revision.id",
            ],
            name="fk_promotion_price_target_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "price_level_id"],
            ["price_level.tenant_id", "price_level.company_id", "price_level.id"],
            name="fk_promotion_price_target_level",
        ),
        Index(
            "ix_promotion_price_target_level",
            "tenant_id",
            "company_id",
            "price_level_id",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    price_level_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class PromotionStackPolicy(PromotionRow):
    """One published policy revision; the group order is an immutable snapshot."""

    __tablename__ = "promotion_stack_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_stack_policy_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "code", "version", name="uq_promotion_stack_policy_version"
        ),
        CheckConstraint("version >= 1 AND maximum_applied BETWEEN 1 AND 10", name="bounds"),
        CheckConstraint("LENGTH(source_sha256) = 64", name="hash"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class PromotionStackGroup(PromotionRow):
    __tablename__ = "promotion_stack_group"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "policy_revision_id",
            "id",
            name="uq_promotion_stack_group_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "policy_revision_id",
            "position",
            name="uq_promotion_stack_group_position",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_revision_id"],
            [
                "promotion_stack_policy.tenant_id",
                "promotion_stack_policy.company_id",
                "promotion_stack_policy.id",
            ],
            name="fk_promotion_stack_group_policy",
        ),
        CheckConstraint("position BETWEEN 0 AND 19", name="position"),
        CheckConstraint("stage IN ('PRODUCT_SCHEME','BASKET','MANUAL')", name="stage"),
        CheckConstraint(
            "selection IN ('PRIORITY','BEST_SINGLE','CUSTOMER_CHOICE')", name="selection"
        ),
        MARIADB_TABLE_ARGS,
    )
    policy_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    selection: Mapped[str] = mapped_column(String(20), nullable=False)
    changes_basket: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PromotionStackPermission(PromotionRow):
    __tablename__ = "promotion_stack_permission"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "policy_revision_id",
            "earlier_group_id",
            "later_group_id",
            name="uq_promotion_stack_permission_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_revision_id"],
            [
                "promotion_stack_policy.tenant_id",
                "promotion_stack_policy.company_id",
                "promotion_stack_policy.id",
            ],
            name="fk_promotion_stack_permission_policy",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_revision_id", "earlier_group_id"],
            [
                "promotion_stack_group.tenant_id",
                "promotion_stack_group.company_id",
                "promotion_stack_group.policy_revision_id",
                "promotion_stack_group.id",
            ],
            name="fk_promotion_stack_permission_earlier",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_revision_id", "later_group_id"],
            [
                "promotion_stack_group.tenant_id",
                "promotion_stack_group.company_id",
                "promotion_stack_group.policy_revision_id",
                "promotion_stack_group.id",
            ],
            name="fk_promotion_stack_permission_later",
        ),
        CheckConstraint("earlier_group_id <> later_group_id", name="different_groups"),
        Index(
            "ix_promotion_stack_permission_later",
            "tenant_id",
            "company_id",
            "policy_revision_id",
            "later_group_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    policy_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    earlier_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    later_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    include_reward_units: Mapped[bool] = mapped_column(Boolean, nullable=False)


PROMOTION_MODELS = (
    Promotion,
    PromotionRevision,
    PromotionBenefit,
    PromotionSkuTarget,
    PromotionPriceLevelTarget,
    PromotionStackPolicy,
    PromotionStackGroup,
    PromotionStackPermission,
)

PUBLISHED_FACTS = (
    PromotionRevision,
    PromotionBenefit,
    PromotionSkuTarget,
    PromotionPriceLevelTarget,
    PromotionStackPolicy,
    PromotionStackGroup,
    PromotionStackPermission,
)

PUBLISHED_CHILDREN = (
    PromotionBenefit,
    PromotionSkuTarget,
    PromotionPriceLevelTarget,
)
_CREATED_REVISIONS = "catalog_promotion_revisions_created_in_transaction"
_CREATED_STACK_POLICIES = "catalog_promotion_stack_policies_created_in_transaction"


@event.listens_for(Session, "before_flush")
def protect_published_promotion_facts(db: Session, context: object, instances: object) -> None:
    if any(isinstance(row, PUBLISHED_FACTS) and db.is_modified(row) for row in db.dirty) or any(
        isinstance(row, PUBLISHED_FACTS) for row in db.deleted
    ):
        raise ConflictError("published promotion facts are immutable; publish a new revision")
    created = db.info.get(_CREATED_REVISIONS, set()) | {
        (row.tenant_id, row.company_id, row.id)
        for row in db.new
        if isinstance(row, PromotionRevision)
    }
    if any(
        (row.tenant_id, row.company_id, row.revision_id) not in created
        for row in db.new
        if isinstance(row, PUBLISHED_CHILDREN)
    ):
        raise ConflictError("published promotion facts are immutable; publish a new revision")
    created_stacks = db.info.get(_CREATED_STACK_POLICIES, set()) | {
        (row.tenant_id, row.company_id, row.id)
        for row in db.new
        if isinstance(row, PromotionStackPolicy)
    }
    if any(
        (row.tenant_id, row.company_id, row.policy_revision_id) not in created_stacks
        for row in db.new
        if isinstance(row, PromotionStackGroup | PromotionStackPermission)
    ):
        raise ConflictError("published stack policy facts are immutable; publish a new revision")


@event.listens_for(Session, "after_flush")
def remember_new_promotion_revisions(db: Session, context: object) -> None:
    created = db.info.setdefault(_CREATED_REVISIONS, set())
    created.update(
        (row.tenant_id, row.company_id, row.id)
        for row in db.new
        if isinstance(row, PromotionRevision)
    )
    stacks = db.info.setdefault(_CREATED_STACK_POLICIES, set())
    stacks.update(
        (row.tenant_id, row.company_id, row.id)
        for row in db.new
        if isinstance(row, PromotionStackPolicy)
    )


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def forget_new_promotion_revisions(db: Session) -> None:
    db.info.pop(_CREATED_REVISIONS, None)
    db.info.pop(_CREATED_STACK_POLICIES, None)
