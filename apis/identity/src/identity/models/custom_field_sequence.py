"""``custom_field_sequence`` — allocation state for ``auto_number`` custom fields.

docs/identity-schema.md §6.4, docs/custom-fields.md. Allocated via ``SELECT … FOR UPDATE``
inside the entity's transaction. **Not gap-free** — a rolled-back create consumes a
number; gap-free statutory numbering belongs in ``document_sequence`` (``billing``), never
here. ``definition_id`` and ``company_id`` carry no FK (allocation state, not a relationship
to constrain).
"""

from __future__ import annotations

import uuid

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.mixins import IdMixin, TenantMixin
from billing_platform.db.types import Uuid7
from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CustomFieldSequence(IdMixin, TenantMixin, Base):
    """docs/identity-schema.md §6.4."""

    __tablename__ = "custom_field_sequence"
    __table_args__ = (
        UniqueConstraint(
            "definition_id",
            "company_id",
            "cycle_key",
            name="uq_custom_field_sequence_def_company_cycle",
        ),
        MARIADB_TABLE_ARGS,
    )

    definition_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    #: ``''`` | fiscal_year_id | ``'2026'`` | ``'2026-09'`` per the definition's reset rule.
    cycle_key: Mapped[str] = mapped_column(String(40), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
