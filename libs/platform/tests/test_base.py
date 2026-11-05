"""Declarative base and the naming convention."""

from __future__ import annotations

import uuid

from sqlalchemy import Index, UniqueConstraint

from billing_platform.db.base import MARIADB_TABLE_ARGS, Base
from billing_platform.db.platform_models import IdempotencyKey, Outbox
from billing_platform.ids import uuid7
from tests.helpers import table_of
from tests.models import TenantThing


def test_repr_shows_the_primary_key_only() -> None:
    """Never the whole row: a repr lands in logs, and a row can hold a token."""
    row_id = uuid7()
    row = TenantThing(id=row_id, tenant_id=uuid7(), name="secret-name")
    text = repr(row)

    assert text == f"<TenantThing id={row_id!r}>"
    assert "secret-name" not in text


def test_composite_primary_key_appears_in_full() -> None:
    from billing_platform.db.platform_models import ProcessedMessage

    message_id = uuid.UUID(int=1)
    text = repr(ProcessedMessage(consumer_name="billing.invoice", message_id=message_id))
    assert "consumer_name='billing.invoice'" in text
    assert f"message_id={message_id!r}" in text


def test_index_names_follow_the_convention() -> None:
    """Auto-named constraints cannot be reliably dropped in a ``downgrade``."""
    names = {ix.name for ix in table_of(Outbox).indexes}
    assert "ix_outbox_published_at_available_at" in names
    assert "ix_outbox_aggregate_type_aggregate_id" in names
    assert all(name is not None and name.startswith("ix_") for name in names)


def test_unique_constraint_names_follow_the_convention() -> None:
    constraints = {
        c.name for c in table_of(IdempotencyKey).constraints if isinstance(c, UniqueConstraint)
    }
    assert "uq_idempotency_key_tenant_id_endpoint_key_value" in constraints


def test_implicit_index_from_a_mixin_is_named() -> None:
    """``TenantMixin`` sets ``index=True``; the convention supplies the name."""
    tenant_indexes = [
        ix for ix in table_of(TenantThing).indexes if {c.name for c in ix.columns} == {"tenant_id"}
    ]
    assert [ix.name for ix in tenant_indexes] == ["ix_tenant_thing_tenant_id"]


def test_every_convention_key_produces_a_prefixed_name() -> None:
    for key, template in Base.metadata.naming_convention.items():
        assert isinstance(template, str)
        assert template.startswith(f"{key}_"), key


def test_mariadb_table_args_pin_engine_charset_and_collation() -> None:
    """A server rebuilt with a different default would otherwise change
    collation, and collation changes comparison semantics on every VARCHAR key."""
    assert MARIADB_TABLE_ARGS == {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
        "mysql_row_format": "DYNAMIC",
    }


def test_platform_tables_carry_the_mariadb_table_args() -> None:
    for model in (Outbox, IdempotencyKey):
        dialect_options = table_of(model).dialect_options["mysql"]
        assert dialect_options["engine"] == "InnoDB"
        assert dialect_options["charset"] == "utf8mb4"


def test_no_two_indexes_share_a_name() -> None:
    seen: dict[str, str] = {}
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            assert isinstance(index, Index)
            name = index.name
            assert name is not None
            assert name not in seen, f"{name} on both {seen.get(name)} and {table.name}"
            seen[name] = table.name
