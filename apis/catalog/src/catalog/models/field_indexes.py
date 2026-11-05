"""Resumable derived-index preparation; definitions remain owned by Identity."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class FieldIndexState(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "field_index_state"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "company_id", "entity_type", "field_key", name="uq_field_index_state_key"
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_field_index_state_scope"),
        CheckConstraint("generation >= 0 AND row_version >= 1", name="field_index_version"),
        CheckConstraint(
            "ready_generation IS NULL OR "
            "(ready_generation >= 1 AND ready_generation <= generation)",
            name="field_index_ready_generation",
        ),
        CheckConstraint(
            "building_generation IS NULL OR "
            "(building_generation >= 1 AND building_generation <= generation)",
            name="field_index_building_generation",
        ),
        CheckConstraint(
            "retired_generation IS NULL OR "
            "(retired_generation >= 1 AND retired_generation <= generation)",
            name="field_index_retired_generation",
        ),
        CheckConstraint(
            "(ready_generation IS NULL) = (ready_digest IS NULL)", name="field_index_ready_pair"
        ),
        CheckConstraint(
            "(building_generation IS NULL) = (building_digest IS NULL)",
            name="field_index_building_pair",
        ),
        CheckConstraint(
            "building_generation IS NULL OR retired_generation IS NULL",
            name="field_index_cleanup_first",
        ),
        CheckConstraint(
            "ready_generation IS NULL OR building_generation IS NULL "
            "OR ready_generation < building_generation",
            name="field_index_monotonic_build",
        ),
        CheckConstraint(
            "ready_generation IS NULL OR retired_generation IS NULL "
            "OR ready_generation <> retired_generation",
            name="field_index_retired_not_ready",
        ),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ready_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ready_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    building_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    building_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class FieldRebuildJob(IdMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "field_rebuild_job"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "state_id",
            "generation",
            name="uq_field_rebuild_job_generation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "state_id"],
            ["field_index_state.tenant_id", "field_index_state.company_id", "field_index_state.id"],
            name="fk_field_rebuild_job_state",
        ),
        CheckConstraint(
            "generation >= 1 AND source_version >= 1 AND row_version >= 1 "
            "AND processed_count >= 0 AND cleanup_count >= 0",
            name="field_rebuild_counters",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="field_rebuild_status",
        ),
        CheckConstraint("phase IN ('build','cleanup','complete')", name="field_rebuild_phase"),
        Index("ix_field_rebuild_job_poll", "tenant_id", "company_id", "phase", "status", "id"),
        Index("ix_field_rebuild_job_state", "tenant_id", "company_id", "state_id"),
        MARIADB_TABLE_ARGS,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    state_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    definition_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    phase: Mapped[str] = mapped_column(String(12), nullable=False, default="build")
    checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    processed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cleanup_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
