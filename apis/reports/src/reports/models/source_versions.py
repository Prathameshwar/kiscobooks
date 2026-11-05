"""Source epochs retain version intervals; immutable cuts pin exact owner sequences."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

from billing_platform.db.base import Base
from billing_platform.db.history import previous_scalar
from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import InstanceState, Mapped, Session, mapped_column

from reports.models.core import Record, scope
from reports.queries.projection import source_projection


class ReportSourceEpoch(Record, Base):
    __tablename__ = "report_source_epoch"
    __table_args__ = scope(
        "report_source_epoch",
        {"active_generation_id": "report_generation"},
        CheckConstraint(
            "head_sequence >= 0 AND status IN ('BUILDING','READY','QUARANTINED')",
            name="report_source_epoch_valid",
        ),
    )
    status: Mapped[str] = mapped_column(String(20), default="BUILDING", nullable=False)
    active_generation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    head_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    owner_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    query_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )


class ReportSourceCut(Record, Base):
    __tablename__ = "report_source_cut"
    __table_args__ = scope(
        "report_source_cut",
        {"epoch_id": "report_source_epoch", "generation_id": "report_generation"},
        UniqueConstraint(
            "tenant_id", "company_id", "generation_id", name="uq_report_source_cut_generation"
        ),
        CheckConstraint("sequence >= 0", name="report_source_cut_sequence"),
    )
    epoch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ReportFactVersion(Record, Base):
    __tablename__ = "report_fact_version"
    __table_args__ = scope(
        "report_fact_version",
        {"epoch_id": "report_source_epoch", "bundle_id": "report_bundle"},
        Index(
            "ix_report_fact_inventory_grain",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "inventory_kind",
            "source_id",
            "valid_from_sequence",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "source_id",
            "valid_from_sequence",
            name="uq_report_fact_version_source",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "bundle_id", "ordinal", name="uq_report_fact_version_ordinal"
        ),
        Index(
            "ix_report_fact_version_added",
            "tenant_id",
            "company_id",
            "epoch_id",
            "valid_from_sequence",
            "entity",
            "source_id",
        ),
        Index(
            "ix_report_fact_version_closed",
            "tenant_id",
            "company_id",
            "epoch_id",
            "valid_to_sequence",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_relation",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "relation_id",
            "source_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_account",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "account_id",
            "source_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_date",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "posting_date",
            "source_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_gst_period",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "relation_id",
            "posting_date",
            "source_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_origin",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "origin_id",
            "source_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_fact_version_line_order",
            "tenant_id",
            "company_id",
            "epoch_id",
            "entity",
            "relation_id",
            "line_sequence",
            "source_id",
            "valid_from_sequence",
        ),
        CheckConstraint(
            "valid_from_sequence >= 0 AND (valid_to_sequence IS NULL OR "
            "valid_to_sequence > valid_from_sequence) AND ordinal > 0",
            name="report_fact_version_interval",
        ),
        CheckConstraint(
            "wire_bytes > 0 AND wire_bytes <= 1048576", name="report_fact_version_bytes"
        ),
    )
    epoch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    bundle_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valid_to_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    wire_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    line_sequence: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed(
            "CASE WHEN entity = 'journal_line' THEN "
            "CAST(json_extract(data, '$.sequence') AS SIGNED) ELSE NULL END",
            persisted=True,
        ),
    )
    # Reviewed native projection of high-volume predicates/aggregates. JSON retains exact evidence.
    relation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    origin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    posting_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    base_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    base_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    side: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    inventory_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ReportGenerationRequest(Record, Base):
    __tablename__ = "report_generation_request"
    __table_args__ = scope(
        "report_generation_request",
        {
            "generation_id": "report_generation",
            "parent_cut_id": "report_source_cut",
            "epoch_id": "report_source_epoch",
        },
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "generation_id",
            name="uq_report_generation_request_generation",
        ),
        CheckConstraint(
            "strategy IN ('FRESH','REFRESH','COMPACT') AND "
            "((strategy = 'FRESH' AND parent_cut_id IS NULL) OR "
            "(strategy <> 'FRESH' AND parent_cut_id IS NOT NULL))",
            name="report_generation_request_valid",
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    strategy: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_cut_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    epoch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    target_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


VERSION_MODELS = (ReportSourceEpoch, ReportSourceCut, ReportFactVersion, ReportGenerationRequest)


@event.listens_for(Session, "before_flush")
def version_evidence(db: Session, context: object, instances: object) -> None:
    epochs: dict[tuple[uuid.UUID, uuid.UUID], ReportSourceEpoch] = {}

    def epoch_for(row: ReportFactVersion) -> ReportSourceEpoch:
        key = row.company_id, row.epoch_id
        if key not in epochs:
            parent = db.scalar(
                select(ReportSourceEpoch)
                .where(
                    ReportSourceEpoch.company_id == row.company_id,
                    ReportSourceEpoch.id == row.epoch_id,
                )
                .with_for_update()
            )
            if parent is None or parent.status == "QUARANTINED":
                raise ConflictError("source epoch is unavailable")
            epochs[key] = parent
        return epochs[key]

    for row in db.new:
        if isinstance(row, ReportFactVersion):
            try:
                projected = source_projection(row.entity, row.data)
            except (ValueError, TypeError, ArithmeticError) as exc:
                raise ConflictError("source projection is invalid") from exc
            for key, value in projected.items():
                if getattr(row, key) not in (None, value):
                    raise ConflictError("source projection differs from retained payload")
                setattr(row, key, value)
            size = len(canonical_json(row.data)) + 256
            if size > 1024 * 1024 or row.wire_bytes not in {None, size}:
                raise ConflictError("source byte evidence differs or exceeds its bound")
            row.wire_bytes = size
            parent = epoch_for(row)
            minimum = parent.head_sequence + (1 if parent.status == "READY" else 0)
            if row.valid_from_sequence < minimum or row.valid_to_sequence is not None:
                raise ConflictError("source version would alter a retained cutoff")
    for row in db.dirty | db.deleted:
        if not isinstance(
            row, ReportSourceEpoch | ReportSourceCut | ReportFactVersion | ReportGenerationRequest
        ):
            continue
        if row in db.deleted:
            raise ConflictError("retained source history cannot be deleted")
        if not db.is_modified(row):
            continue
        state = cast(InstanceState[Any], inspect(row))
        changed = {value.key for value in state.attrs if value.history.has_changes()}
        if isinstance(row, ReportFactVersion):
            parent = epoch_for(row)
            if (
                changed != {"valid_to_sequence"}
                or previous_scalar(db, row, "valid_to_sequence") is not None
                or (row.valid_to_sequence is None or row.valid_to_sequence <= parent.head_sequence)
            ):
                raise ConflictError("only a future source interval may be closed once")
        if isinstance(row, ReportSourceCut):
            if changed != {"verification"} or previous_scalar(db, row, "verification") is not None:
                raise ConflictError("source cutoff is immutable")
        if isinstance(row, ReportSourceEpoch):
            if changed - {"head_sequence", "status", "row_version", "active_generation_id"}:
                raise ConflictError("source epoch identity is immutable")
            if "head_sequence" in changed and row.head_sequence < previous_scalar(
                db, row, "head_sequence"
            ):
                raise ConflictError("source epoch cannot regress")
        if isinstance(row, ReportGenerationRequest):
            if changed - {"epoch_id", "target_manifest"}:
                raise ConflictError("generation source request is immutable")
            for key in changed:
                if previous_scalar(db, row, key) is not None:
                    raise ConflictError("generation source request is immutable")
