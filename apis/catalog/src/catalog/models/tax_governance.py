"""Immutable tax applicability, publication receipts and correction evidence."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.pricing import PricingRow
from catalog.models.tax import reference, scope


class TaxRuleApplicability(PricingRow):
    __tablename__ = "tax_rule_applicability"
    __table_args__ = (
        *scope("tax_rule_applicability"),
        reference("tax_applicability", "rule_id", "tax_rule"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "rule_id",
            "code_system",
            "code",
            "match_kind",
            name="uq_tax_applicability_match",
        ),
        CheckConstraint(
            "code_system IN ('HSN','SAC') AND match_kind IN ('EXACT','PREFIX')", name="match"
        ),
        MARIADB_TABLE_ARGS,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code_system: Mapped[str] = mapped_column(String(3), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    match_kind: Mapped[str] = mapped_column(String(6), nullable=False)


class TaxRelease(PricingRow):
    __tablename__ = "tax_release"
    __table_args__ = (
        *scope("tax_release"),
        CheckConstraint("change_count BETWEEN 1 AND 100", name="size"),
        MARIADB_TABLE_ARGS,
    )
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TaxHistoryAction(PricingRow):
    __tablename__ = "tax_history_action"
    __table_args__ = (
        *scope("tax_history_action"),
        reference("tax_history", "release_id", "tax_release"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "resource",
            "target_id",
            "action",
            name="uq_tax_history_action",
        ),
        CheckConstraint(
            "resource IN ('tax_classification','tax_rate','catalog_tax_binding')", name="resource"
        ),
        CheckConstraint("action IN ('PUBLISH','SUPERSEDE','WITHDRAW')", name="action"),
        Index("ix_tax_history_previous", "tenant_id", "company_id", "resource", "previous_id"),
        MARIADB_TABLE_ARGS,
    )
    # Polymorphic references follow the same scoped application checks as master aliases.
    resource: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    previous_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    previous_valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    release_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)


class TaxImpactReview(PricingRow):
    """A chunked background impact report that a release publishes against.

    The report is bound to the company policy generation, the Identity source version and the
    business date it was computed at. Any Catalog product or tax change advances the generation,
    so a report that still matches it describes exactly the state being published.
    """

    __tablename__ = "tax_impact_review"
    __table_args__ = (
        *scope("tax_impact_review"),
        CheckConstraint("status IN ('PENDING','COMPLETE','STALE','FAILED')", name="status"),
        CheckConstraint("change_count BETWEEN 1 AND 100", name="size"),
        CheckConstraint(
            "item_count >= 0 AND checked_count >= 0 AND finding_count >= 0 "
            "AND blocking_count >= 0",
            name="counts",
        ),
        Index("ix_tax_impact_review_poll", "tenant_id", "company_id", "status", "id"),
        MARIADB_TABLE_ARGS,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    # The reviewed release input, replayed inside a rolled-back savepoint by every chunk.
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    business_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="PENDING")
    checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class TaxImpactFinding(PricingRow):
    """One non-complete product/direction/date result of an impact review."""

    __tablename__ = "tax_impact_finding"
    __table_args__ = (
        *scope("tax_impact_finding"),
        reference("tax_impact_finding", "review_id", "tax_impact_review"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "review_id",
            "item_id",
            "direction",
            "as_of",
            name="uq_tax_impact_finding_check",
        ),
        CheckConstraint(
            "direction IN ('SALE','PURCHASE') "
            "AND status IN ('MISSING','REQUIRE_EXPLICIT','INVALID')",
            name="result",
        ),
        Index("ix_tax_impact_finding_page", "tenant_id", "company_id", "review_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    review_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    missing: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
