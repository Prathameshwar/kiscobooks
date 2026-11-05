"""Native table options participate in schema parity, beyond Alembic's column diff."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from accounting.metadata import service_metadata


@pytest.mark.mysql
async def test_inventory_handoff_table_options_match_its_owner(engine: AsyncEngine) -> None:
    if engine.dialect.name != "mysql":
        pytest.skip("requires a migrated disposable native Accounting database")
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT TABLE_COLLATION, ROW_FORMAT FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='inventory_report_record'"
                )
            )
        ).one()
    options = service_metadata().tables["inventory_report_record"].kwargs
    assert row[0] == options["mysql_collate"]
    assert row[1].upper() == options["mysql_row_format"]
