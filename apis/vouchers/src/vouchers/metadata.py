"""Only this service's tables participate in its independent migration chain."""

from billing_platform.db.base import Base
from sqlalchemy import MetaData

from vouchers import models as models
from vouchers.models import (
    commercial,
    core,
    counter,
    imports,
    invoice,
    printing,
    stock,
    stock_opening_import,
    stock_retirement,
    supporting_files,
    unit_sources,
)

TABLES = frozenset(
    value.__tablename__
    for module in (
        core,
        invoice,
        commercial,
        counter,
        imports,
        stock,
        stock_retirement,
        stock_opening_import,
        unit_sources,
        supporting_files,
        printing,
    )
    for value in vars(module).values()
    if isinstance(value, type) and hasattr(value, "__tablename__")
) | {"outbox", "processed_message", "idempotency_key"}
MIGRATION_HEAD = "0116"


def service_metadata() -> MetaData:
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    for name in sorted(TABLES):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata
