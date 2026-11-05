"""Native stable quota identity and versioned proposed caps; no balances or counters."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    DECIMAL,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


class PromotionLimitDefinition(ClassificationMaster):
    __tablename__ = "promotion_limit_definition"
    __table_args__ = (
        *master_constraints("promotion_limit_definition"),
        CheckConstraint("scope_kind IN ('CAMPAIGN','PROMOTION','PROGRAM')", name="scope"),
        CheckConstraint(
            "metric IN ('TOTAL_USES','PER_CUSTOMER_USES','PER_ORDER_USES','REWARD_UNITS','BUDGET')",
            name="metric",
        ),
        CheckConstraint("period_basis IN ('LIFETIME','DAY','MONTH','YEAR','ORDER')", name="period"),
        CheckConstraint(
            "(metric = 'PER_ORDER_USES' AND period_basis = 'ORDER') OR (metric <> "
            "'PER_ORDER_USES' AND period_basis <> 'ORDER')",
            name="order_period",
        ),
        CheckConstraint(
            "(metric = 'BUDGET' AND currency IS NOT NULL AND unit_id IS NULL) OR (metric = "
            "'REWARD_UNITS' AND currency IS NULL AND unit_id IS NOT NULL) OR (metric IN "
            "('TOTAL_USES','PER_CUSTOMER_USES','PER_ORDER_USES') AND currency IS NULL AND "
            "unit_id IS NULL)",
            name="measure",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "unit_id"],
            ["unit_of_measure.tenant_id", "unit_of_measure.company_id", "unit_of_measure.id"],
            name="fk_promotion_limit_unit",
        ),
        Index("ix_promotion_limit_definition_scope", "tenant_id", "company_id", "scope_kind", "id"),
        Index("ix_promotion_limit_definition_metric", "tenant_id", "company_id", "metric", "id"),
        Index("ix_promotion_limit_definition_unit", "tenant_id", "company_id", "unit_id"),
        MARIADB_TABLE_ARGS,
    )
    scope_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    metric: Mapped[str] = mapped_column(String(20), nullable=False)
    period_basis: Mapped[str] = mapped_column(String(12), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class PublishedDefinitionRow(IdMixin, TenantMixin, AuditMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    published_source_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    publication_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)


class PromotionLimitRevision(PublishedDefinitionRow):
    __tablename__ = "promotion_limit_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_promotion_limit_revision_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "definition_id", "id", name="uq_limit_revision_parent_scope"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "definition_id",
            "revision",
            name="uq_promotion_limit_revision_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id"],
            [
                "promotion_limit_definition.tenant_id",
                "promotion_limit_definition.company_id",
                "promotion_limit_definition.id",
            ],
            name="fk_promotion_limit_revision_parent",
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="version"),
        CheckConstraint(
            "(published_at IS NULL AND published_source_version IS NULL AND "
            "publication_generation IS NULL) OR (published_at IS NOT NULL AND "
            "published_source_version IS NOT NULL AND publication_generation IS NOT NULL AND "
            "published_source_version >= 1 AND publication_generation >= 1)",
            name="publication",
        ),
        CheckConstraint(
            "(maximum_count IS NOT NULL AND maximum_count > 0 "
            "AND maximum_quantity IS NULL AND maximum_amount IS NULL) OR (maximum_count IS "
            "NULL AND maximum_quantity IS NOT NULL AND maximum_quantity > 0 AND maximum_amount "
            "IS NULL) OR (maximum_count IS NULL AND maximum_quantity IS NULL AND "
            "maximum_amount IS NOT NULL AND maximum_amount > 0)",
            name="cap",
        ),
        Index(
            "ix_promotion_limit_revision_published",
            "tenant_id",
            "company_id",
            "definition_id",
            "published_at",
            "revision",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    maximum_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    maximum_quantity: Mapped[Decimal | None] = mapped_column(DECIMAL(19, 4), nullable=True)
    maximum_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(19, 4), nullable=True)


@event.listens_for(Session, "before_flush")
def protect_published_definitions(db: Session, context: object, instances: object) -> None:
    for row in (*db.dirty, *db.deleted):
        if not isinstance(row, PublishedDefinitionRow):
            continue
        history = inspect(row).attrs.published_at.history
        previous = history.deleted[0] if history.deleted else row.published_at
        if previous is not None and (row in db.deleted or db.is_modified(row)):
            raise ConflictError(
                "published commercial definitions are immutable; create a new revision"
            )


PROMOTION_LIMIT_MODELS = (PromotionLimitDefinition, PromotionLimitRevision)
