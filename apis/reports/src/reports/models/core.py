"""Scoped source generations, native financial projections and frozen report runs."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, cast

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, Session, mapped_column


class Record(IdMixin, TenantMixin, AuditMixin):
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


def scope(name: str, refs: dict[str, str] | None = None, *extra: Any) -> tuple[Any, ...]:
    return (
        UniqueConstraint("tenant_id", "company_id", "id", name=f"uq_{name}_scope"),
        *(
            ForeignKeyConstraint(
                ["tenant_id", "company_id", key],
                [f"{target}.tenant_id", f"{target}.company_id", f"{target}.id"],
                name=f"fk_{name}_{key}",
            )
            for key, target in (refs or {}).items()
        ),
        Index(f"ix_{name}_page", "tenant_id", "company_id", "id"),
        *extra,
        MARIADB_TABLE_ARGS,
    )


class ReportCompany(Record, Base):
    __tablename__ = "report_company"
    __table_args__ = scope(
        "report_company",
        {},
        UniqueConstraint("tenant_id", "company_id", name="uq_report_company_identity"),
    )


class ReportGeneration(Record, Base):
    __tablename__ = "report_generation"
    __table_args__ = scope(
        "report_generation",
        {},
        Index("ix_report_generation_work", "tenant_id", "company_id", "status", "id"),
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    applied_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    target_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class ReportBundle(Record, Base):
    __tablename__ = "report_bundle"
    __table_args__ = scope(
        "report_bundle",
        {"generation_id": "report_generation"},
        UniqueConstraint(
            "tenant_id", "company_id", "generation_id", "source_id", name="uq_report_bundle_source"
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="STAGING")
    last_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class ReportStagedFact(Record, Base):
    __tablename__ = "report_staged_fact"
    __table_args__ = scope(
        "report_staged_fact",
        {"bundle_id": "report_bundle"},
        UniqueConstraint(
            "tenant_id", "company_id", "bundle_id", "ordinal", name="uq_report_staged_fact_ordinal"
        ),
    )
    bundle_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportFact(Record, Base):
    __tablename__ = "report_fact"
    __table_args__ = scope(
        "report_fact",
        {"generation_id": "report_generation"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "generation_id",
            "entity",
            "source_id",
            name="uq_report_fact_source",
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ReportLine(Record, Base):
    __tablename__ = "report_line"
    __table_args__ = scope(
        "report_line",
        {"generation_id": "report_generation"},
        UniqueConstraint(
            "tenant_id", "company_id", "generation_id", "source_id", name="uq_report_line_source"
        ),
        Index(
            "ix_report_line_account_date",
            "tenant_id",
            "company_id",
            "generation_id",
            "account_id",
            "posting_date",
            "id",
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    component: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class ReportAccountTotal(Record, Base):
    __tablename__ = "report_account_total"
    __table_args__ = scope(
        "report_account_total",
        {"generation_id": "report_generation"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "generation_id",
            "account_id",
            "currency",
            "grain",
            "start_date",
            name="uq_report_account_total_grain",
        ),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    grain: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    debit: Mapped[Decimal] = mapped_column(Money, nullable=False)
    credit: Mapped[Decimal] = mapped_column(Money, nullable=False)


class ReportActivation(Record, Base):
    __tablename__ = "report_activation"
    __table_args__ = scope(
        "report_activation",
        {"generation_id": "report_generation"},
        UniqueConstraint("tenant_id", "company_id", name="uq_report_activation_company"),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class ReportSourceClaim(Record, Base):
    __tablename__ = "report_source_claim"
    __table_args__ = scope(
        "report_source_claim",
        {},
        UniqueConstraint(
            "tenant_id", "company_id", "entity", "source_id", name="uq_report_source_claim_identity"
        ),
    )
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    financial_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ReportDefinition(Record, Base):
    __tablename__ = "report_definition"
    __table_args__ = scope(
        "report_definition",
        {},
        UniqueConstraint(
            "tenant_id", "company_id", "code", "version", name="uq_report_definition_version"
        ),
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ReportRun(Record, Base):
    __tablename__ = "report_run"
    __table_args__ = scope(
        "report_run",
        {"generation_id": "report_generation", "definition_id": "report_definition"},
        Index("ix_report_run_work", "tenant_id", "company_id", "status", "id"),
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    permission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class ReportRow(Record, Base):
    __tablename__ = "report_row"
    __table_args__ = scope(
        "report_row",
        {"run_id": "report_run"},
        UniqueConstraint(
            "tenant_id", "company_id", "run_id", "ordinal", name="uq_report_row_ordinal"
        ),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportArtifact(Record, Base):
    __tablename__ = "report_artifact"
    __table_args__ = scope(
        "report_artifact",
        {"run_id": "report_run"},
        UniqueConstraint("tenant_id", "company_id", "run_id", name="uq_report_artifact_run"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(
        Text().with_variant(MEDIUMTEXT(), "mysql", "mariadb"), nullable=False
    )


for _model in (
    ReportCompany,
    ReportGeneration,
    ReportBundle,
    ReportStagedFact,
    ReportFact,
    ReportLine,
    ReportAccountTotal,
    ReportActivation,
    ReportSourceClaim,
    ReportDefinition,
    ReportRun,
    ReportRow,
    ReportArtifact,
):
    cast(Table, _model.__table__).append_constraint(
        CheckConstraint("row_version > 0", name=_model.__tablename__ + "_version")
    )
for _model, _check in (
    (
        ReportGeneration,
        "status IN ('PENDING','BUILDING','READY','QUARANTINED') AND applied_sequence >= 0",
    ),
    (ReportBundle, "status IN ('STAGING','APPLIED') AND last_ordinal >= 0"),
    (ReportRun, "status IN ('PENDING','COMPLETE','BLOCKED')"),
    (
        ReportLine,
        "side IN ('DEBIT','CREDIT') AND base_amount > 0 AND "
        "((component = 'PRINCIPAL' AND amount > 0) OR "
        "(component = 'FX' AND amount = 0 AND party_id IS NOT NULL))",
    ),
    (ReportAccountTotal, "grain IN ('DAY','MONTH') AND debit >= 0 AND credit >= 0"),
):
    cast(Table, _model.__table__).append_constraint(
        CheckConstraint(_check, name=_model.__tablename__ + "_valid")
    )


@event.listens_for(Session, "before_flush")
def immutable(db: Session, context: object, instances: object) -> None:
    for row in db.new:
        if isinstance(row, ReportFact | ReportLine | ReportAccountTotal):
            status = db.scalar(
                select(ReportGeneration.status).where(
                    ReportGeneration.company_id == row.company_id,
                    ReportGeneration.id == row.generation_id,
                )
            )
            if status not in {"PENDING", "BUILDING"}:
                raise ConflictError("cannot append to a frozen generation")
        if isinstance(row, ReportRow | ReportArtifact):
            status = db.scalar(
                select(ReportRun.status).where(
                    ReportRun.company_id == row.company_id, ReportRun.id == row.run_id
                )
            )
            if status != "PENDING":
                raise ConflictError("cannot append to a frozen report")
    for row in db.dirty | db.deleted:
        if not isinstance(row, Record):
            continue
        state = inspect(row)
        assert state is not None
        if row in db.deleted:
            raise ConflictError("report history cannot be deleted")
        if not db.is_modified(row):
            continue
        changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
        fixed = {"id", "tenant_id", "company_id", "created_at", "created_by"}
        if isinstance(row, ReportGeneration):
            fixed |= {"snapshot_id"}
        if isinstance(row, ReportBundle):
            fixed |= {"generation_id", "source_id", "manifest"}
        if isinstance(row, ReportRun):
            fixed |= {"generation_id", "definition_id", "permission_hash", "parameters"}
        if isinstance(row, ReportFact):
            fixed |= {"generation_id", "entity", "source_id"}
        if changed & fixed:
            raise ConflictError("report evidence identity is immutable")
        if isinstance(row, ReportBundle):
            previous = state.attrs.status.history.deleted
            if (previous and previous[0] == "APPLIED") or (
                not previous and row.status == "APPLIED"
            ):
                raise ConflictError("applied source receipts are immutable")
        if isinstance(
            row,
            ReportStagedFact
            | ReportLine
            | ReportAccountTotal
            | ReportSourceClaim
            | ReportDefinition
            | ReportRow
            | ReportArtifact,
        ):
            raise ConflictError("report source/output evidence is immutable")
        if isinstance(row, ReportGeneration):
            old = state.attrs.status.history.deleted
            if (old and old[0] in {"READY", "QUARANTINED"}) or (
                not old and row.status in {"READY", "QUARANTINED"}
            ):
                raise ConflictError("report generation is frozen")
        if isinstance(row, ReportRun):
            old = state.attrs.status.history.deleted
            if (old and old[0] in {"COMPLETE", "BLOCKED"}) or (
                not old and row.status in {"COMPLETE", "BLOCKED"}
            ):
                raise ConflictError("report run is frozen")
        if isinstance(row, ReportFact):
            status = db.scalar(
                select(ReportGeneration.status).where(
                    ReportGeneration.company_id == row.company_id,
                    ReportGeneration.id == row.generation_id,
                )
            )
            if status not in {"PENDING", "BUILDING"}:
                raise ConflictError("report generation facts are frozen")
