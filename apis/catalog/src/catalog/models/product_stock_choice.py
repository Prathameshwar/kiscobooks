"""A product's explicit tracking choice, pinned before native activation."""

import uuid
from typing import Any

from billing_platform.db.base import MARIADB_TABLE_ARGS
from billing_platform.db.types import Uuid7
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog.models.product_definitions import ProductDefinitionRow


class ItemStockChoice(ProductDefinitionRow):
    __tablename__ = "item_stock_choice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_stock_choice_scope"),
        UniqueConstraint("tenant_id", "company_id", "item_id", name="uq_stock_choice_item"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "item_id"],
            ["item.tenant_id", "item.company_id", "item.id"],
            name="fk_stock_choice_item",
        ),
        CheckConstraint("row_version >= 1", name="stock_choice_version"),
        MARIADB_TABLE_ARGS,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    batch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


@event.listens_for(ItemStockChoice, "before_update")
@event.listens_for(ItemStockChoice, "before_delete")
def immutable_choice(mapper: Any, connection: Any, target: ItemStockChoice) -> None:
    from billing_platform.errors import ConflictError

    if inspect(target).persistent:
        raise ConflictError("A product's activated stock choice is immutable")
