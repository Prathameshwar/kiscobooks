"""Actor-owned, unsubmitted product wizard data; never a product or stock fact."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Uuid7
from sqlalchemy import JSON, BigInteger, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.configuration import ConfigurationRow


class AdvancedProductDraft(ConfigurationRow):
    __tablename__ = "advanced_product_draft"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "owner_user_id",
            "create_key",
            name="uq_advanced_product_draft_key",
        ),
        Index(
            "ix_advanced_product_draft_owner",
            "tenant_id",
            "company_id",
            "owner_user_id",
            "updated_at",
            "id",
        ),
        CheckConstraint("row_version >= 1", name="advanced_product_draft_version"),
        CheckConstraint("step BETWEEN 1 AND 4", name="advanced_product_draft_step"),
        MARIADB_TABLE_ARGS,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    create_key: Mapped[str] = mapped_column(String(64), nullable=False)
    create_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mode_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    family_field_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_field_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
