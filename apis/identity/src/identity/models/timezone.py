"""Global IANA timezone catalogue, materialized at installation from pinned tzdata."""

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column


class Timezone(Base):
    __tablename__ = "timezone"
    __table_args__ = MARIADB_TABLE_ARGS

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
