"""Live company authoring mode, independent of dated product adoption."""

from billing_platform.db.base import MARIADB_TABLE_ARGS
from sqlalchemy import Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.configuration import ConfigurationRow


class CompanyProductAuthoringConfiguration(ConfigurationRow):
    __tablename__ = "company_product_authoring_configuration"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", name="uq_company_product_authoring_company"),
        CheckConstraint("row_version >= 1", name="product_authoring_version"),
        MARIADB_TABLE_ARGS,
    )
    product_family_sku_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    change_reason: Mapped[str] = mapped_column(String(250), nullable=False)
