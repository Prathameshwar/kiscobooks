"""Rotate the global generation in the same transaction as ORM source writes.

Registration is Identity-local. This covers CRUD, seeding, and delivery acknowledgements;
no network operation or post-commit callback can lose invalidation after a process crash.
"""

from __future__ import annotations

from typing import Any, cast

from billing_platform.db.language import Language
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.ids import uuid7
from sqlalchemy import Table, event, inspect
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, SessionTransaction

from identity.models.reference_cache import ReferenceCacheGeneration
from identity.models.timezone import Timezone

DIRTY_KEY = "identity_reference_cache_dirty"
WATCHED = (Country, State, Currency, Language, Timezone, ReferenceRevision, ReferenceSyncState)


def pending_changes(session: Session) -> bool:
    return bool(session.info.get(DIRTY_KEY)) or any(
        isinstance(row, WATCHED)
        and (row in session.new or row in session.deleted or session.is_modified(row))
        for row in (*session.new, *session.dirty, *session.deleted)
    )


@event.listens_for(Session, "before_flush")
def rotate_generation(session: Session, flush_context: Any, instances: Any) -> None:
    if not any(
        isinstance(row, WATCHED)
        and (row in session.new or row in session.deleted or session.is_modified(row))
        for row in (*session.new, *session.dirty, *session.deleted)
    ):
        return
    connection = session.connection()
    # Historical-schema seed tests and processes importing several service model
    # registries may not own this Identity-only table. Cache positive discovery per
    # connection; an upgrade can turn an earlier negative result into a real table.
    marker = "identity_reference_generation_table"
    if not connection.info.get(marker):
        if not inspect(connection).has_table("reference_cache_generation"):
            return
        connection.info[marker] = True
    table = cast(Table, ReferenceCacheGeneration.__table__)
    token = uuid7()
    # Reviewed global-only Core DML. Unique-key upsert acquires the generation lock
    # before native writes; concurrent transactions cannot publish the same generation.
    values = {"id": uuid7(), "key": "global", "token": token}
    if connection.dialect.name in {"mysql", "mariadb"}:
        statement = mysql_insert(table).values(**values)
        connection.execute(statement.on_duplicate_key_update(token=token))
    elif connection.dialect.name == "sqlite":
        statement_sqlite = sqlite_insert(table).values(**values)
        connection.execute(
            statement_sqlite.on_conflict_do_update(index_elements=["key"], set_={"token": token})
        )
    else:
        raise RuntimeError("unsupported reference cache database")
    session.info[DIRTY_KEY] = True


@event.listens_for(Session, "after_transaction_end")
def clear_dirty(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop(DIRTY_KEY, None)
