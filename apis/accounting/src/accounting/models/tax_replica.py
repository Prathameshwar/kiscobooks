"""Read-only local copies of Catalog's published GST definitions (tax-accounting Phase 5).

Rows carry Catalog's own UUIDv7 identifiers and are written only by the
``accounting.catalog_tax.v1`` consumer. ``source_version`` is Catalog's company policy
generation at the change; a row moves only to a strictly newer generation. Lifecycle mirrors
Catalog: classifications and rates are dated (withdrawal sets ``valid_to``), rules carry
``is_active``. Nothing here is edited through the Accounting API and nothing is deleted.

Catalog withdraws only rows that have not started yet and publishes ``valid_to ==
valid_from`` for them, which read as a plain date range would be a one-day window. Dated
replicas therefore keep the publication's ``source_action``; a WITHDRAW row is never
effective on any date (``accounting.domain.tax_replica.effective_on``). Withdrawal is sticky.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import Money, Quantity, UtcDateTime, Uuid7, utcnow
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class ReplicaRow(IdMixin, TenantMixin, Base):
    __abstract__ = True
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: The inbox message that last changed the row; traceable to Catalog's outbox.
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    replicated_at: Mapped[dt.datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


def replica(name: str) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        CheckConstraint("source_version >= 1", name="source_version"),
    )


def action() -> CheckConstraint:
    return CheckConstraint("source_action IN ('PUBLISH','UPDATE','WITHDRAW')", name="source_action")


def dated() -> CheckConstraint:
    return CheckConstraint(
        "valid_from >= '1000-01-01' AND (valid_to IS NULL OR valid_to >= valid_from)",
        name="dates",
    )


class TaxClassificationReplica(ReplicaRow):
    __tablename__ = "tax_classification_replica"
    __table_args__ = (
        *replica("tax_classification_replica"),
        dated(),
        action(),
        CheckConstraint(
            "jurisdiction = 'IN' AND ((code_system = 'HSN' AND item_kind = 'GOODS') OR "
            "(code_system = 'SAC' AND item_kind = 'SERVICE'))",
            name="kind",
        ),
        Index(
            "ix_tax_classification_replica_code",
            "tenant_id",
            "company_id",
            "code_system",
            "code",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False)
    code_system: Mapped[str] = mapped_column(String(3), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The last applied publication's action; WITHDRAW is never effective (sticky).
    source_action: Mapped[str] = mapped_column(
        String(8), nullable=False, default="PUBLISH", server_default="PUBLISH"
    )


class TaxRuleReplica(ReplicaRow):
    __tablename__ = "tax_rule_replica"
    __table_args__ = (
        *replica("tax_rule_replica"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_tax_rule_replica_code"),
        CheckConstraint(
            "tax_system = 'gst_in' AND jurisdiction = 'IN' AND item_kind IN ('GOODS','SERVICE') "
            "AND treatment IN ('TAXABLE','NIL_RATED','EXEMPT','NON_GST')",
            name="shape",
        ),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_system: Mapped[str] = mapped_column(String(10), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(2), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(7), nullable=False)
    treatment: Mapped[str] = mapped_column(String(10), nullable=False)
    tax_category_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class TaxRateReplica(ReplicaRow):
    """One dated rate of a rule's series, flattened: Catalog's series is (rule, applicability).

    No foreign key to the rule replica: Catalog events for different entities may arrive in
    any order, and a rate must not wait on its rule's message.
    """

    __tablename__ = "tax_rate_replica"
    __table_args__ = (
        *replica("tax_rate_replica"),
        dated(),
        action(),
        CheckConstraint(
            "applicability IN ('INTRA_STATE','INTRA_UT','INTER_STATE')",
            name="applicability",
        ),
        Index(
            "ix_tax_rate_replica_rule",
            "tenant_id",
            "company_id",
            "rule_id",
            "applicability",
            "valid_from",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    applicability: Mapped[str] = mapped_column(String(12), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The last applied publication's action; WITHDRAW is never effective (sticky).
    source_action: Mapped[str] = mapped_column(
        String(8), nullable=False, default="PUBLISH", server_default="PUBLISH"
    )


class TaxRateComponentReplica(ReplicaRow):
    __tablename__ = "tax_rate_component_replica"
    __table_args__ = (
        *replica("tax_rate_component_replica"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "rate_id"],
            ["tax_rate_replica.tenant_id", "tax_rate_replica.company_id", "tax_rate_replica.id"],
            name="fk_tax_rate_component_replica_rate_id",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "rate_id", "component_key", name="uq_tax_rate_component_key"
        ),
        CheckConstraint(
            "component IN ('CGST','SGST','UTGST','IGST','CESS') AND "
            "rounding_mode IN ('HALF_UP','UP','DOWN') AND position BETWEEN 0 AND 15",
            name="component",
        ),
        CheckConstraint(
            "(kind = 'PERCENT' AND percentage IS NOT NULL AND percentage >= 0 "
            "AND (component = 'CESS' OR percentage <= 100) AND amount IS NULL AND currency IS "
            "NULL AND unit_id IS NULL AND basis_quantity IS NULL) OR (kind = 'FIXED_PER_UNIT' "
            "AND component = 'CESS' AND percentage IS NULL AND amount IS NOT NULL AND amount > 0 "
            "AND currency IS NOT NULL AND unit_id IS NOT NULL AND basis_quantity IS NOT NULL "
            "AND basis_quantity > 0)",
            name="shape",
        ),
        Index(
            "ix_tax_rate_component_replica_order",
            "tenant_id",
            "company_id",
            "rate_id",
            "position",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    rate_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    component_key: Mapped[str] = mapped_column(String(30), nullable=False)
    component: Mapped[str] = mapped_column(String(5), nullable=False)
    kind: Mapped[str] = mapped_column(String(14), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    basis_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    rounding_mode: Mapped[str] = mapped_column(String(7), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


TAX_REPLICA_MODELS = (
    TaxClassificationReplica,
    TaxRuleReplica,
    TaxRateReplica,
    TaxRateComponentReplica,
)
