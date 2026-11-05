"""Shared document structures with tenant/company composite ownership."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, IdMixin, TenantMixin
from billing_platform.db.types import Money, Quantity, UtcDateTime, Uuid7
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv


class Record(IdMixin, TenantMixin, AuditMixin):
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VoucherCompanyGuard(Record, Base):
    __tablename__ = "voucher_company_guard"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id"),
        MARIADB_TABLE_ARGS,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VoucherType(Record, Base):
    __tablename__ = "voucher_type"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "code"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VoucherTypeRevision(Record, Base):
    __tablename__ = "voucher_type_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "type_id", "revision_number"),
        UniqueConstraint(
            "tenant_id", "company_id", "type_id", "id", name="uq_voucher_type_revision_owner"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_id"],
            ["voucher_type.tenant_id", "voucher_type.company_id", "voucher_type.id"],
            name="fk_voucher_type_revision_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    policy: Mapped[Any] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherTypeSection(Record, Base):
    __tablename__ = "voucher_type_section"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "type_revision_id", "section"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_revision_id"],
            [
                "voucher_type_revision.tenant_id",
                "voucher_type_revision.company_id",
                "voucher_type_revision.id",
            ],
            name="fk_voucher_type_section_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    requirement: Mapped[str] = mapped_column(String(20), nullable=False)
    minimum_stage: Mapped[str] = mapped_column(String(20), nullable=False)


class VoucherClass(Record, Base):
    __tablename__ = "voucher_class"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "type_revision_id", "code"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_revision_id"],
            [
                "voucher_type_revision.tenant_id",
                "voucher_type_revision.company_id",
                "voucher_type_revision.id",
            ],
            name="fk_voucher_class_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    policy: Mapped[Any] = mapped_column(JSON, nullable=False)


class VoucherConfigurationProfile(Record, Base):
    __tablename__ = "voucher_configuration_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "code"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    family: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VoucherConfigurationRevision(Record, Base):
    __tablename__ = "voucher_configuration_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "profile_id", "revision_number"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "profile_id"],
            [
                "voucher_configuration_profile.tenant_id",
                "voucher_configuration_profile.company_id",
                "voucher_configuration_profile.id",
            ],
            name="fk_voucher_configuration_revision_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    policy: Mapped[Any] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherConfigurationBinding(Record, Base):
    __tablename__ = "voucher_configuration_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "configuration_revision_id"],
            [
                "voucher_configuration_revision.tenant_id",
                "voucher_configuration_revision.company_id",
                "voucher_configuration_revision.id",
            ],
            name="fk_voucher_configuration_binding_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_id"],
            ["voucher_type.tenant_id", "voucher_type.company_id", "voucher_type.id"],
            name="fk_voucher_configuration_binding_2",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="binding_dates"),
        Index(
            "ix_voucher_configuration_binding_0",
            "tenant_id",
            "company_id",
            "type_id",
            "family",
            "valid_from",
        ),
        MARIADB_TABLE_ARGS,
    )
    configuration_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    family: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class Voucher(Record, Base):
    __tablename__ = "voucher"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_id"],
            ["voucher_type.tenant_id", "voucher_type.company_id", "voucher_type.id"],
            name="fk_voucher_1",
        ),
        Index("ix_voucher_0", "tenant_id", "company_id", "status", "id"),
        Index("ix_voucher_type_list", "tenant_id", "company_id", "type_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VoucherRevision(Record, Base):
    __tablename__ = "voucher_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "voucher_id", "revision_number"),
        UniqueConstraint(
            "tenant_id", "company_id", "voucher_id", "id", name="uq_voucher_revision_owner"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_revision_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_revision_id"],
            [
                "voucher_type_revision.tenant_id",
                "voucher_type_revision.company_id",
                "voucher_type_revision.id",
            ],
            name="fk_voucher_revision_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "class_id"],
            ["voucher_class.tenant_id", "voucher_class.company_id", "voucher_class.id"],
            name="fk_voucher_revision_3",
        ),
        Index("ix_voucher_revision_0", "tenant_id", "company_id", "document_date", "id"),
        Index(
            "ix_voucher_revision_date_list",
            "tenant_id",
            "company_id",
            "document_date",
            "voucher_id",
            "revision_number",
        ),
        Index(
            "ix_voucher_revision_type_list",
            "tenant_id",
            "company_id",
            "type_revision_id",
            "voucher_id",
            "revision_number",
        ),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    type_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    class_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    document_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    stock_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    statutory_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    credit_terms_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    fiscal_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    custom_fields: Mapped[Any] = mapped_column(JSON, nullable=False)
    definition_snapshot: Mapped[Any] = mapped_column(JSON, nullable=False)
    configuration_evidence: Mapped[Any] = mapped_column(JSON, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    assignment_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class VoucherLine(Record, Base):
    __tablename__ = "voucher_line"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "line_key"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "sequence"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_line_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    line_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)


class VoucherItemDetail(Record, Base):
    __tablename__ = "voucher_item_detail"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "line_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id", "line_id"],
            [
                "voucher_line.tenant_id",
                "voucher_line.company_id",
                "voucher_line.revision_id",
                "voucher_line.id",
            ],
            name="fk_voucher_item_detail_1",
        ),
        CheckConstraint("actual_quantity >= 0 AND billed_quantity >= 0", name="quantities"),
        CheckConstraint(
            "planned_quantity IS NULL OR planned_quantity >= 0", name="planned_quantity"
        ),
        Index(
            "ix_voucher_item_list",
            "tenant_id",
            "company_id",
            "item_id",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_version: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    actual_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    billed_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    planned_quantity: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    custom_fields: Mapped[Any] = mapped_column(JSON, nullable=False)


class VoucherFulfillmentTerms(Record, Base):
    """Revision-owned non-posting requisition, quotation and order terms."""

    __tablename__ = "voucher_fulfillment_terms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_fulfillment_terms_revision",
        ),
        CheckConstraint(
            "purpose IN ('PROCURE','INTERNAL_ISSUE','SALE','PURCHASE','QUOTE')",
            name="purpose",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    required_by: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    destination_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_terms: Mapped[str] = mapped_column(String(1000), nullable=False)
    payment_terms: Mapped[str] = mapped_column(String(1000), nullable=False)


class VoucherParty(Record, Base):
    __tablename__ = "voucher_party"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_party_1",
        ),
        Index(
            "ix_voucher_party_list",
            "tenant_id",
            "company_id",
            "party_id",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class VoucherReference(Record, Base):
    __tablename__ = "voucher_reference"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_reference_1",
        ),
        # Duplicate detection for imported external/return references.
        Index("ix_voucher_reference_lookup", "tenant_id", "company_id", "purpose", "reference"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    reference_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class VoucherAttachment(Record, Base):
    __tablename__ = "voucher_attachment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_attachment_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    object_key: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class VoucherLink(Record, Base):
    __tablename__ = "voucher_link"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_link_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_link_2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_link_3",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    source_voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class VoucherApproval(Record, Base):
    __tablename__ = "voucher_approval"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_approval_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherTransition(Record, Base):
    __tablename__ = "voucher_transition"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_transition_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_transition_2",
        ),
        Index("ix_voucher_transition_0", "tenant_id", "company_id", "voucher_id", "id"),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    voucher_version: Mapped[int] = mapped_column(Integer, nullable=False)


class VoucherOperation(Record, Base):
    __tablename__ = "voucher_operation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "execution_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_operation_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_operation_2",
        ),
        Index("ix_voucher_operation_0", "tenant_id", "company_id", "status", "id"),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[Any | None] = mapped_column(JSON, nullable=True)


class VoucherPostingReference(Record, Base):
    __tablename__ = "voucher_posting_reference"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "owner", "effect_kind", "effect_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "operation_id"],
            ["voucher_operation.tenant_id", "voucher_operation.company_id", "voucher_operation.id"],
            name="fk_voucher_posting_reference_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    owner: Mapped[str] = mapped_column(String(30), nullable=False)
    effect_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    effect_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)


class VoucherNumberSeries(Record, Base):
    __tablename__ = "voucher_number_series"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "code"),
        CheckConstraint(
            "start_value >= 1 AND start_value < 9223372036854775807",
            name=conv("ck_voucher_number_series_start_value"),
        ),
        CheckConstraint(
            "numbering_mode IN ('AUTOMATIC','AUTOMATIC_WITH_OVERRIDE','MANUAL')",
            name=conv("ck_voucher_number_series_mode"),
        ),
        CheckConstraint(
            "reset_policy IN ('FINANCIAL_YEAR','NEVER')",
            name=conv("ck_voucher_number_series_reset"),
        ),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    suffix: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", server_default=text("''")
    )
    padding: Mapped[int] = mapped_column(Integer, nullable=False)
    start_value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    numbering_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="AUTOMATIC", server_default="AUTOMATIC"
    )
    reset_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="FINANCIAL_YEAR", server_default="FINANCIAL_YEAR"
    )
    include_year: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class VoucherNumberCounter(Record, Base):
    __tablename__ = "voucher_number_counter"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "series_id", "fiscal_start_date"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "series_id"],
            [
                "voucher_number_series.tenant_id",
                "voucher_number_series.company_id",
                "voucher_number_series.id",
            ],
            name="fk_voucher_number_counter_1",
        ),
        CheckConstraint("next_value > 0", name="positive"),
        MARIADB_TABLE_ARGS,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    fiscal_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


class VoucherNumberAssignment(Record, Base):
    __tablename__ = "voucher_number_assignment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "series_id", "fiscal_start_date", "sequence"),
        UniqueConstraint("tenant_id", "company_id", "revision_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "series_id"],
            [
                "voucher_number_series.tenant_id",
                "voucher_number_series.company_id",
                "voucher_number_series.id",
            ],
            name="fk_voucher_number_assignment_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_number_assignment_2",
        ),
        Index(
            "ix_voucher_number_search",
            "tenant_id",
            "company_id",
            "display_number",
            "revision_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    fiscal_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_number: Mapped[str] = mapped_column(String(100), nullable=False)


class VoucherTemplate(Record, Base):
    __tablename__ = "voucher_template"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "code"),
        MARIADB_TABLE_ARGS,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class VoucherTemplateRevision(Record, Base):
    __tablename__ = "voucher_template_revision"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "template_id", "revision_number"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "template_id"],
            ["voucher_template.tenant_id", "voucher_template.company_id", "voucher_template.id"],
            name="fk_voucher_template_revision_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    fields: Mapped[Any] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherArtifact(Record, Base):
    __tablename__ = "voucher_artifact"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "revision_id",
            "template_revision_id",
            "permission_hash",
            "render_context_hash",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_artifact_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "template_revision_id"],
            [
                "voucher_template_revision.tenant_id",
                "voucher_template_revision.company_id",
                "voucher_template_revision.id",
            ],
            name="fk_voucher_artifact_2",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    template_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body: Mapped[str | None] = mapped_column(
        Text().with_variant(MEDIUMTEXT(), "mysql", "mariadb"), nullable=True
    )
    permission_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    render_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherDefinitionProjection(Record, Base):
    __tablename__ = "voucher_definition_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "entity_type", "field_key"),
        MARIADB_TABLE_ARGS,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    definition: Mapped[Any] = mapped_column(JSON, nullable=False)
    presentation: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class VoucherFieldAdoption(Record, Base):
    __tablename__ = "voucher_field_adoption"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "definition_id", "source_version"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "definition_id"],
            [
                "voucher_definition_projection.tenant_id",
                "voucher_definition_projection.company_id",
                "voucher_definition_projection.id",
            ],
            name="fk_voucher_field_adoption_1",
        ),
        MARIADB_TABLE_ARGS,
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    definition: Mapped[Any] = mapped_column(JSON, nullable=False)
    presentation: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherCustomClaim(Record, Base):
    __tablename__ = "voucher_custom_claim"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "scope_company_id", "entity_type", "field_key", "value_hash"),
        Index("ix_voucher_custom_claim_0", "tenant_id", "company_id", "entity_id"),
        MARIADB_TABLE_ARGS,
    )
    scope_company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_value: Mapped[str] = mapped_column(Text, nullable=False)


class VoucherCustomSequence(Record, Base):
    __tablename__ = "voucher_custom_sequence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "entity_type", "field_key", "cycle_key"),
        CheckConstraint("next_value > 0", name="positive"),
        MARIADB_TABLE_ARGS,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cycle_key: Mapped[str] = mapped_column(String(40), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


class VoucherCustomIndex(Record, Base):
    __tablename__ = "voucher_custom_index"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "entity_id", "field_key", "member_number"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_voucher_custom_index_1",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_custom_index_2",
        ),
        Index(
            "ix_voucher_custom_index_0",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "value_text",
            "voucher_id",
        ),
        Index(
            "ix_voucher_custom_index_1",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "value_number",
            "voucher_id",
        ),
        Index(
            "ix_voucher_custom_index_2",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "value_date",
            "voucher_id",
        ),
        Index(
            "ix_voucher_custom_index_3",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "value_datetime_at",
            "voucher_id",
        ),
        Index(
            "ix_voucher_custom_index_4",
            "tenant_id",
            "company_id",
            "entity_type",
            "field_key",
            "value_bool",
            "voucher_id",
        ),
        MARIADB_TABLE_ARGS,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    member_number: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[str | None] = mapped_column(
        String(200, collation="utf8mb4_bin").with_variant(
            String(200, collation="BINARY"), "sqlite"
        ),
        nullable=True,
    )
    value_number: Mapped[Decimal | None] = mapped_column(Quantity, nullable=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    value_datetime_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)


class VoucherMasterEvidence(Record, Base):
    __tablename__ = "voucher_master_evidence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "owner", "entity_type", "source_id"),
        MARIADB_TABLE_ARGS,
    )
    owner: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    facts: Mapped[Any] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherItemRegulatoryProjection(Record, Base):
    """Indexed Catalog revision projection; historical voucher resolution is date-bound."""

    __tablename__ = "voucher_item_regulatory_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_item_reg_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "classification_id", name="uq_voucher_item_reg_source"
        ),
        Index("ix_voucher_item_reg_asof", "tenant_id", "company_id", "item_id", "valid_from", "id"),
        CheckConstraint("row_version >= 1", name=conv("ck_voucher_item_reg_version")),
        CheckConstraint("source_version >= 1", name=conv("ck_voucher_item_reg_source_version")),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_voucher_item_reg_dates")
        ),
        CheckConstraint(
            "product_kind IN ('NON_DRUG','MEDICINE','FOOD')", name=conv("ck_voucher_item_reg_kind")
        ),
        CheckConstraint(
            "(product_kind = 'NON_DRUG' AND licence_class IS NULL "
            "AND prescription_schedule IS NULL AND food_category_code IS NULL) "
            "OR (product_kind = 'FOOD' AND licence_class IS NULL "
            "AND prescription_schedule IS NULL AND food_category_code IS NOT NULL) "
            "OR (product_kind = 'MEDICINE' "
            "AND licence_class IN ('OTHER_THAN_C_C1_X','C_C1_EXCLUDING_X','SCHEDULE_X') "
            "AND prescription_schedule IN ('NONE','H','H1','X') AND food_category_code IS NULL)",
            name=conv("ck_voucher_item_reg_class_shape"),
        ),
        MARIADB_TABLE_ARGS,
    )
    classification_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    product_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    licence_class: Mapped[str | None] = mapped_column(String(24), nullable=True)
    prescription_schedule: Mapped[str | None] = mapped_column(String(4), nullable=True)
    food_category_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    reviewed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherPartyDrugLicenceProjection(Record, Base):
    """Indexed Accounting licence revisions for one counterparty trading premises."""

    __tablename__ = "voucher_party_drug_licence_projection"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_voucher_party_drug_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "licence_id", name="uq_voucher_party_drug_source"
        ),
        Index(
            "ix_voucher_party_drug_asof",
            "tenant_id",
            "company_id",
            "party_id",
            "address_id",
            "licence_form",
            "valid_from",
            "id",
        ),
        CheckConstraint("row_version >= 1", name=conv("ck_voucher_party_drug_version")),
        CheckConstraint("source_version >= 1", name=conv("ck_voucher_party_drug_source_version")),
        CheckConstraint(
            "licence_form IN ('20','20B','21','21B')", name=conv("ck_voucher_party_drug_form")
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=conv("ck_voucher_party_drug_dates")
        ),
        MARIADB_TABLE_ARGS,
    )
    licence_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    licence_form: Mapped[str] = mapped_column(String(4), nullable=False)
    licence_number: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    reviewed_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherTypeOrigin(Record, Base):
    __tablename__ = "voucher_type_origin"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "type_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "type_id"],
            ["voucher_type.tenant_id", "voucher_type.company_id", "voucher_type.id"],
            name="fk_voucher_type_origin_child",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "source_revision_id"],
            [
                "voucher_type_revision.tenant_id",
                "voucher_type_revision.company_id",
                "voucher_type_revision.id",
            ],
            name="fk_voucher_type_origin_source",
        ),
        MARIADB_TABLE_ARGS,
    )
    type_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class VoucherFinancialDetail(Record, Base):
    __tablename__ = "voucher_financial_detail"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_financial_detail_revision",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)


class VoucherAccountDetail(Record, Base):
    __tablename__ = "voucher_account_detail"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "line_key"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_account_detail_revision",
        ),
        CheckConstraint("amount > 0 AND exchange_rate > 0", name="voucher_account_detail_c0"),
        CheckConstraint("side IN ('DEBIT', 'CREDIT')", name="voucher_account_detail_c1"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    tracking: Mapped[str] = mapped_column(String(20), nullable=False)
    bill_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class VoucherTender(Record, Base):
    __tablename__ = "voucher_tender"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "tender_key"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_tender_revision",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id", "line_key"],
            [
                "voucher_account_detail.tenant_id",
                "voucher_account_detail.company_id",
                "voucher_account_detail.revision_id",
                "voucher_account_detail.line_key",
            ],
            name="fk_voucher_tender_account",
        ),
        CheckConstraint("amount > 0", name="voucher_tender_c0"),
        # Duplicate detection for cheque numbers and transfer references.
        Index("ix_voucher_tender_reference", "tenant_id", "company_id", "reference"),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tender_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    instrument_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    recognition: Mapped[str] = mapped_column(String(20), nullable=False)


class VoucherBillInstruction(Record, Base):
    __tablename__ = "voucher_bill_instruction"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id"),
        UniqueConstraint("tenant_id", "company_id", "revision_id", "allocation_key"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "revision_id"],
            ["voucher_revision.tenant_id", "voucher_revision.company_id", "voucher_revision.id"],
            name="fk_voucher_bill_instruction_revision",
        ),
        CheckConstraint("amount > 0", name="voucher_bill_instruction_c0"),
        CheckConstraint(
            "(debt_item_id IS NULL) <> (debt_line_key IS NULL)", name="voucher_bill_instruction_c1"
        ),
        CheckConstraint(
            "(credit_item_id IS NULL) <> (credit_line_key IS NULL)",
            name="voucher_bill_instruction_c2",
        ),
        MARIADB_TABLE_ARGS,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_key: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    debt_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    debt_line_key: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    credit_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    credit_line_key: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
