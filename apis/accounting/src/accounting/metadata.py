"""Service-local schema view; never migrate another service's registered models."""

from typing import cast

from sqlalchemy import MetaData, Table

from accounting.models import MODELS

TABLES = frozenset(model.__tablename__ for model in MODELS)
MIGRATION_HEAD = "0235"


def service_metadata() -> MetaData:
    metadata = MetaData()
    for model in MODELS:
        cast(Table, model.__table__).to_metadata(metadata)
    return metadata
