"""Return eligibility definitions; return posting and dispositions remain Billing-owned."""

import datetime as dt
import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import UtcDateTime, Uuid7
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

from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import master_constraints


class ReturnPolicy(ClassificationMaster):
    __tablename__ = "return_policy"
    __table_args__ = (*master_constraints("return_policy"), MARIADB_TABLE_ARGS)


class ReturnPolicyRevision(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "return_policy_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_return_policy_rev_scope"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "policy_id",
            "revision",
            name="uq_return_policy_rev_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "policy_id"],
            ["return_policy.tenant_id", "return_policy.company_id", "return_policy.id"],
            name="fk_return_policy_rev_parent",
        ),
        Index(
            "ix_return_policy_rev_published",
            "tenant_id",
            "company_id",
            "policy_id",
            "published_at",
            "revision",
            "id",
        ),
        CheckConstraint("revision >= 1 AND row_version >= 1", name="return_policy_rev_version"),
        CheckConstraint("condition_count BETWEEN 0 AND 5", name="return_policy_rev_count"),
        CheckConstraint(
            "(returns_allowed = 1 AND window_days IS NOT NULL AND window_days BETWEEN 0 AND 36500) "
            "OR (returns_allowed = 0 AND window_days IS NULL AND condition_count = 0)",
            name="return_policy_rev_window",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    returns_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ReturnPolicyCondition(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "return_policy_condition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            [
                "return_policy_revision.tenant_id",
                "return_policy_revision.company_id",
                "return_policy_revision.id",
            ],
            name="fk_return_policy_condition_rev",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "condition_code",
            name="uq_return_policy_condition_code",
        ),
        CheckConstraint(
            "condition_code IN ('ORIGINAL_PACKAGING','PROOF_OF_PURCHASE',"
            "'COMPLETE_ACCESSORIES','UNUSED','UNDAMAGED')",
            name="return_policy_condition_code",
        ),
        Index(
            "ix_return_policy_condition_page",
            "tenant_id",
            "company_id",
            "revision_id",
            "condition_code",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    condition_code: Mapped[str] = mapped_column(String(30), nullable=False)
