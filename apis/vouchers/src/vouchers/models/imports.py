"""Staged bulk voucher import jobs; every effect is an ordinary native draft."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Money, UtcDateTime, Uuid7
from billing_platform.import_journal import AttemptEvidence, ResultEvidence, RevisionEvidence
from billing_platform.import_models import ImportTemplateSnapshot as ImportTemplateSnapshot
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record

JOB_STATES = (
    "STAGED",
    "VALIDATING",
    "READY",
    "COMMITTING",
    "SUCCEEDED",
    "PARTIAL",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
)
IMPORT_KINDS = (
    "PURCHASE",
    "SALES",
    "CREDIT_NOTE",
    "DEBIT_NOTE",
    "PAYMENT",
    "RECEIPT",
    "CONTRA",
    "JOURNAL",
)
ROW_STATES = (
    "STAGED",
    "VALID",
    "WARNING",
    "INVALID",
    "BLOCKED",
    "CREATED",
    "FAILED",
    "NOT_SELECTED",
)


def states(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def job_reference(name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", "company_id", "job_id"],
        ["voucher_import_job.tenant_id", "voucher_import_job.company_id", "voucher_import_job.id"],
        name=f"fk_{name}_job",
    )


class VoucherImportJob(Record, Base):
    __tablename__ = "voucher_import_job"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_job_scope"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_id", "type_revision_id"],
            [
                "voucher_type_revision.tenant_id",
                "voucher_type_revision.company_id",
                "voucher_type_revision.type_id",
                "voucher_type_revision.id",
            ],
            name="fk_voucher_import_job_type",
        ),
        Index("ix_voucher_import_job_actor", "tenant_id", "company_id", "actor_user_id", "id"),
        CheckConstraint(f"state IN ({states(JOB_STATES)})", name="state"),
        CheckConstraint(f"kind IN ({states(IMPORT_KINDS)})", name="kind"),
        CheckConstraint("source_format IN ('CSV', 'TSV', 'XLSX', 'JSON')", name="source_format"),
        Index("ix_voucher_import_job_expiry", "tenant_id", "company_id", "expires_at", "id"),
        Index(
            "ix_voucher_import_job_state", "tenant_id", "company_id", "actor_user_id", "state", "id"
        ),
        CheckConstraint("on_error IN ('STOP', 'CONTINUE_INDEPENDENT')", name="on_error"),
        CheckConstraint(
            "duplicate_rule IN ('DATE_NUMBER_PARTY', 'DATE_NUMBER', 'DATE_NUMBER_ACCOUNT')",
            name="duplicate_rule",
        ),
        CheckConstraint(
            "schema_version = 1 AND voucher_count BETWEEN 1 AND 500 AND valid_count >= 0 "
            "AND warning_count >= 0 AND invalid_count >= 0 AND created_count >= 0 "
            "AND failed_count >= 0",
            name="counts",
        ),
        MARIADB_TABLE_ARGS,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_format: Mapped[str] = mapped_column(String(10), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="STAGED")
    on_error: Mapped[str] = mapped_column(String(30), nullable=False, default="STOP")
    # Same bill number and date, plus the supplier party or ledger unless DATE_NUMBER.
    duplicate_rule: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DATE_NUMBER_PARTY", server_default="DATE_NUMBER_PARTY"
    )
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voucher_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class VoucherImportArtifact(Record, Base):
    __tablename__ = "voucher_import_artifact"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_artifact_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", name="uq_voucher_import_artifact_job"
        ),
        job_reference("voucher_import_artifact"),
        Index("ix_voucher_import_artifact_expiry", "tenant_id", "company_id", "expires_at", "id"),
        CheckConstraint("byte_count BETWEEN 0 AND 8388608", name="bytes"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Private uploaded bytes; blanked once the job expires.
    content: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql", "mariadb"), nullable=False, deferred=True
    )
    expires_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)


class VoucherImportRow(Record, Base):
    """One staged voucher (its header and lines), validated and committed as a unit."""

    __tablename__ = "voucher_import_row"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_row_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "import_key", name="uq_voucher_import_row_key"
        ),
        Index(
            "ix_voucher_import_row_work", "tenant_id", "company_id", "job_id", "state", "ordinal"
        ),
        Index("ix_voucher_import_row_page", "tenant_id", "company_id", "job_id", "ordinal", "id"),
        job_reference("voucher_import_row"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_import_row_voucher",
        ),
        CheckConstraint(f"state IN ({states(ROW_STATES)})", name="state"),
        CheckConstraint("ordinal BETWEEN 1 AND 500", name="ordinal"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    import_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="STAGED")
    # Normalised textual cells and their source sheet/row positions.
    source_input: Mapped[Any] = mapped_column(JSON, nullable=False)
    source_rows: Mapped[Any] = mapped_column(JSON, nullable=False)
    errors: Mapped[Any] = mapped_column(JSON, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Native draft content with pinned master identities and versions, set by validation.
    prepared_input: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    configuration_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    declared_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    computed_payable: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    computed_tax_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    supplier_difference: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)


class VoucherImportEffect(Record, Base):
    """Written in the draft's own transaction; a retry can never create a second draft."""

    __tablename__ = "voucher_import_effect"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_effect_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "import_key", name="uq_voucher_import_effect_key"
        ),
        job_reference("voucher_import_effect"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id", "revision_id"],
            [
                "voucher_revision.tenant_id",
                "voucher_revision.company_id",
                "voucher_revision.voucher_id",
                "voucher_revision.id",
            ],
            name="fk_voucher_import_effect_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_import_effect_voucher",
        ),
        Index("ix_voucher_import_effect_voucher", "tenant_id", "company_id", "voucher_id"),
        MARIADB_TABLE_ARGS,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    import_key: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class VoucherImportRevision(RevisionEvidence, Record, Base):
    __tablename__ = "voucher_import_revision"
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_revision_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "job_id", "id", name="uq_voucher_import_revision_job"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "job_id",
            "revision",
            name="uq_voucher_import_revision_number",
        ),
        job_reference("voucher_import_revision"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "template_id"],
            [
                "import_template_snapshot.tenant_id",
                "import_template_snapshot.company_id",
                "import_template_snapshot.id",
            ],
            name="fk_voucher_import_revision_template",
        ),
        MARIADB_TABLE_ARGS,
    )


class VoucherImportAttempt(AttemptEvidence, Record, Base):
    __tablename__ = "voucher_import_attempt"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_import_attempt_scope"),
        job_reference("voucher_import_attempt"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "job_id", "revision_id"],
            [
                "voucher_import_revision.tenant_id",
                "voucher_import_revision.company_id",
                "voucher_import_revision.job_id",
                "voucher_import_revision.id",
            ],
            name="fk_voucher_import_attempt_revision",
        ),
        Index("ix_voucher_import_attempt_job", "tenant_id", "company_id", "job_id", "id"),
        MARIADB_TABLE_ARGS,
    )


class VoucherImportResult(ResultEvidence, Record, Base):
    __tablename__ = "voucher_import_result"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "attempt_id",
            "record_key",
            name="uq_voucher_import_result_key",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "attempt_id"],
            [
                "voucher_import_attempt.tenant_id",
                "voucher_import_attempt.company_id",
                "voucher_import_attempt.id",
            ],
            name="fk_voucher_import_result_attempt",
        ),
        Index(
            "ix_voucher_import_result_page",
            "tenant_id",
            "company_id",
            "attempt_id",
            "ordinal",
            "id",
        ),
        MARIADB_TABLE_ARGS,
    )
