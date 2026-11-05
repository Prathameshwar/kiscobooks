"""``company_bank_account`` — a company's bank account for receipts and payouts.

docs/identity-schema.md §3.10. ``account_number`` and ``iban`` are **log-redaction
targets** (CLAUDE.md §5.11): they are stored (a receipt needs them) but must never reach
a log line — the redaction is applied wherever these are logged, and the API returns them
only to an authorized reader.
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import AuditMixin, DeactivableMixin, IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import CHAR, Boolean, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column


class CompanyBankAccount(IdMixin, TenantMixin, AuditMixin, DeactivableMixin, Base):
    """docs/identity-schema.md §3.10."""

    __tablename__ = "company_bank_account"
    __table_args__ = (
        Index("ix_company_bank_account_company_id_currency", "company_id", "currency_code"),
        # The currency FK needs a supporting index leading with its own column, or
        # InnoDB invents one that reads as autogenerate drift (§1.7 first exception).
        Index("ix_company_bank_account_currency_code", "currency_code"),
        MARIADB_TABLE_ARGS,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid7, ForeignKey("company.id", name="fk_company_bank_account_company_id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Redacted from logs (§5.11).
    account_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: Redacted from logs (§5.11).
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    swift: Mapped[str | None] = mapped_column(String(11), nullable=True)
    ifsc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        CHAR(3),
        ForeignKey("currency.code", name="fk_company_bank_account_currency_code"),
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Legacy plaintext columns remain nullable for backfill; new writes leave them empty.
    details_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    account_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    iban_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
