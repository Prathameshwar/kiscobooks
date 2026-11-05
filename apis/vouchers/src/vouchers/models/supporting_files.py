"""Registered immutable Purchase evidence; revisions retain references independently."""

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.types import Uuid7
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vouchers.models.core import Record


class PurchaseSupportingFile(Record, Base):
    __tablename__ = "purchase_supporting_file"
    __table_args__ = (
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="size"),
        CheckConstraint("LENGTH(content_hash) = 64", name="hash"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_purchase_file_scope"),
        UniqueConstraint(
            "tenant_id", "company_id", "voucher_id", "content_hash", name="uq_purchase_file_content"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "voucher_id"],
            ["voucher.tenant_id", "voucher.company_id", "voucher.id"],
            name="fk_purchase_supporting_file_voucher",
        ),
        MARIADB_TABLE_ARGS,
    )
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    object_key: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(60), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(160), nullable=False)
