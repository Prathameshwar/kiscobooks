"""Verify B15 promotion/stack migrations and scope on a disposable loopback MySQL schema."""

import os

from billing_platform.db import create_session_factory
from billing_platform.ids import uuid7
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from catalog.metadata import MIGRATION_HEAD, service_metadata
from catalog.models.promotions import PROMOTION_MODELS, PromotionRevision
from tests.test_promotion_storage import (
    test_promotion_revision_rejects_foreign_stack_group,
    test_promotion_tables_are_tenant_isolated,
    test_published_stack_policy_cannot_change_or_gain_children,
    test_stack_permission_rejects_foreign_group,
    test_stored_same_item_facts_reconstruct_bounded_deal,
)
from tools.mysql_smoke import run_verifier


async def verify(url: str) -> dict[str, object]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:

            def scoped_schema(sync: Connection) -> None:
                inspector = inspect(sync)
                metadata = service_metadata()
                for model in PROMOTION_MODELS:
                    name = model.__tablename__
                    table = metadata.tables[name]
                    actual_columns = {column["name"] for column in inspector.get_columns(name)}
                    expected_columns = set(table.columns.keys())
                    assert actual_columns == expected_columns, (
                        name,
                        expected_columns - actual_columns,
                        actual_columns - expected_columns,
                    )
                    expected_fks = {constraint.name for constraint in table.foreign_key_constraints}
                    actual_fks = {
                        constraint["name"] for constraint in inspector.get_foreign_keys(name)
                    }
                    assert expected_fks == actual_fks, (name, expected_fks - actual_fks)
                    expected_indexes = {index.name for index in table.indexes}
                    actual_indexes = {index["name"] for index in inspector.get_indexes(name)}
                    assert expected_indexes <= actual_indexes, (
                        name,
                        expected_indexes - actual_indexes,
                    )
                revision_fks = {
                    constraint["name"]
                    for constraint in inspector.get_foreign_keys(PromotionRevision.__tablename__)
                }
                assert {
                    "fk_promotion_revision_stack_policy",
                    "fk_promotion_revision_stack_group",
                } <= revision_fks

            await connection.run_sync(scoped_schema)
        factory = create_session_factory(engine)
        await test_promotion_tables_are_tenant_isolated(factory, uuid7(), uuid7())
        await test_stack_permission_rejects_foreign_group(factory, uuid7(), uuid7())
        await test_promotion_revision_rejects_foreign_stack_group(factory, uuid7(), uuid7())
        await test_published_stack_policy_cannot_change_or_gain_children(factory, uuid7())
        await test_stored_same_item_facts_reconstruct_bounded_deal(factory, uuid7())
        return {
            "head": MIGRATION_HEAD,
            "promotion_schema_parity": True,
            "promotion_native_checks": 5,
        }
    finally:
        await engine.dispose()


def main() -> None:
    os.environ.setdefault("CATALOG_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    run_verifier(verify)


if __name__ == "__main__":
    main()
