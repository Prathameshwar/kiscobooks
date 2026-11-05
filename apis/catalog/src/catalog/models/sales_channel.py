"""Company-owned sales-channel master.

A sales channel is a company's own classification of where a price series
applies — WEB, STORE, MARKETPLACE, and so on. ``item_price_series.channel_code``
carries the composite FK; a NULL ``channel_code`` means the series applies to
every channel, which matches the previous free-string ``channel_key`` behaviour.

Extends :class:`ClassificationMaster` so the shared master CRUD pipeline
(``tasks/classification.py``) handles it end to end: idempotency, audit events,
field policy, list/detail schemas.
"""

from billing_platform.db.base import MARIADB_TABLE_ARGS
from sqlalchemy import Boolean, CheckConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from catalog.models.classification import ClassificationMaster


class SalesChannel(ClassificationMaster):
    __tablename__ = "sales_channel"
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_sales_channel_id"),
        UniqueConstraint("tenant_id", "company_id", "code", name="uq_sales_channel_code"),
        CheckConstraint("row_version >= 1", name=conv("ck_sales_channel_row_version")),
        MARIADB_TABLE_ARGS,
    )


SALES_CHANNEL_MODELS = (SalesChannel,)
