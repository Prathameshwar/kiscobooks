"""Native stack-policy drafts; publication uses the existing immutable facts."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.promotions import PromotionRow


def scope(table: str) -> UniqueConstraint:
    return UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{table}_scope")


def draft_reference(name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", "draft_id"],
        [
            "promotion_stack_draft.tenant_id",
            "promotion_stack_draft.company_id",
            "promotion_stack_draft.id",
        ],
        name=name,
    )


class PromotionStackDraft(PromotionRow):
    __tablename__ = "promotion_stack_draft"
    __table_args__ = (
        scope("promotion_stack_draft"),
        CheckConstraint("row_version >= 1 AND maximum_applied BETWEEN 1 AND 10", name="bounds"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="status"),
        CheckConstraint(
            "group_count BETWEEN 0 AND 20 AND permission_count BETWEEN 0 AND 190", name="counts"
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND published_policy_id IS NULL) OR "
            "(status = 'PUBLISHED' AND published_policy_id IS NOT NULL)",
            name="publication",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "published_policy_id"],
            [
                "promotion_stack_policy.tenant_id",
                "promotion_stack_policy.company_id",
                "promotion_stack_policy.id",
            ],
            name="fk_stack_draft_publication",
        ),
        Index("ix_promotion_stack_draft_code", "tenant_id", "company_id", "code", "id"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    maximum_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    group_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    permission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class PromotionStackDraftGroup(PromotionRow):
    __tablename__ = "promotion_stack_draft_group"
    __table_args__ = (
        scope("promotion_stack_draft_group"),
        UniqueConstraint(
            "tenant_id", "company_id", "draft_id", "id", name="uq_stack_draft_group_parent"
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "draft_id", "position", name="uq_stack_draft_group_position"
        ),
        draft_reference("fk_stack_draft_group_parent"),
        CheckConstraint("position BETWEEN 0 AND 19", name="position"),
        CheckConstraint("stage IN ('PRODUCT_SCHEME','BASKET','MANUAL')", name="stage"),
        CheckConstraint(
            "selection IN ('PRIORITY','BEST_SINGLE','CUSTOMER_CHOICE')", name="selection"
        ),
        CheckConstraint(
            "NOT (changes_basket = 1 AND selection = 'BEST_SINGLE')", name="comparable"
        ),
        MARIADB_TABLE_ARGS,
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    selection: Mapped[str] = mapped_column(String(20), nullable=False)
    changes_basket: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PromotionStackDraftPermission(PromotionRow):
    __tablename__ = "promotion_stack_draft_permission"
    __table_args__ = (
        scope("promotion_stack_draft_permission"),
        draft_reference("fk_stack_draft_permission_parent"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "draft_id",
            "earlier_group_id",
            "later_group_id",
            name="uq_stack_draft_permission_pair",
        ),
        *(
            ForeignKeyConstraint(
                ["tenant_id", "company_id", "draft_id", column],
                [
                    "promotion_stack_draft_group.tenant_id",
                    "promotion_stack_draft_group.company_id",
                    "promotion_stack_draft_group.draft_id",
                    "promotion_stack_draft_group.id",
                ],
                name="fk_stack_draft_permission_" + side,
            )
            for side, column in (("earlier", "earlier_group_id"), ("later", "later_group_id"))
        ),
        CheckConstraint("earlier_group_id <> later_group_id", name="distinct"),
        MARIADB_TABLE_ARGS,
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    earlier_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    later_group_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    include_reward_units: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


PROMOTION_AUTHORING_MODELS = (
    PromotionStackDraft,
    PromotionStackDraftGroup,
    PromotionStackDraftPermission,
)
