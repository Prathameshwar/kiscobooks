"""Immutable Tax Analysis evidence for a tax-bearing journal or party-document voucher.

One row per journal, written in the transaction that creates the draft. Posting re-derives
the analysis from the stored request and refuses if it differs; once the journal is posted
the row is never recomputed or edited.
"""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money, Uuid7
from sqlalchemy import JSON, Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class JournalTax(Record):
    __tablename__ = "journal_tax"
    __table_args__ = constraints(
        "journal_tax",
        {
            "journal_id": "journal",
            "party_id": "party",
            "party_registration_id": "party_tax_registration",
            "withholding_section_id": "withholding_section",
            "certificate_id": "withholding_certificate",
        },
        UniqueConstraint("tenant_id", "company_id", "journal_id", name="uq_journal_tax_journal"),
        CheckConstraint("direction IN ('SALE', 'PURCHASE')", name="journal_tax_direction"),
        CheckConstraint(
            "taxable_value >= 0 AND tax_total >= 0 AND line_count BETWEEN 1 AND 200",
            name="journal_tax_amount",
        ),
        CheckConstraint(
            "(withholding_kind IS NULL AND withholding_section_id IS NULL AND "
            "withholding_amount IS NULL AND withholding_base IS NULL AND withholding_tax IS NULL "
            "AND certificate_id IS NULL AND certificate_base IS NULL) OR "
            "(withholding_kind IN ('TDS', 'TCS') AND withholding_section_id IS NOT NULL AND "
            "withholding_amount >= 0 AND withholding_base >= 0 AND withholding_tax >= 0 AND "
            "((certificate_id IS NULL AND certificate_base IS NULL) OR "
            "(certificate_id IS NOT NULL AND certificate_base >= 0)))",
            name="journal_tax_withholding",
        ),
        CheckConstraint("LENGTH(snapshot_hash) = 64", name="journal_tax_hash"),
        Index(
            "ix_journal_tax_withholding",
            "tenant_id",
            "company_id",
            "party_id",
            "withholding_section_id",
            "id",
        ),
        Index("ix_journal_tax_registration", "tenant_id", "company_id", "party_registration_id"),
        Index("ix_journal_tax_section", "tenant_id", "company_id", "withholding_section_id"),
        Index("ix_journal_tax_certificate", "tenant_id", "company_id", "certificate_id"),
    )
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: Identity-owned; the signed company context row, so no local foreign key.
    company_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    party_registration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(10), nullable=True)
    supply_context: Mapped[str | None] = mapped_column(String(12), nullable=True)
    supply_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    withholding_kind: Mapped[str | None] = mapped_column(String(3), nullable=True)
    withholding_section_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    #: The transaction amount counted toward the party's annual threshold.
    withholding_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    withholding_base: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    withholding_tax: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    certificate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid7, nullable=True)
    certificate_base: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    #: Leading journal lines the caller entered; the rest were generated from the analysis.
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)


VOUCHER_TAX_MODELS = (JournalTax,)
