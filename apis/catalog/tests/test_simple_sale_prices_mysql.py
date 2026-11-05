"""Native MySQL proof for multiple prices, activation, import and retained reports."""

import asyncio

import httpx
import pytest
from alembic import command
from billing_platform.db import create_session_factory
from billing_platform.ids import uuid7
from pydantic import SecretStr

from catalog.config import Settings
from catalog.main import create_app
from tests.conftest import ACTOR_SECRET
from tests.test_pricing_dimension_migration_mysql import native_pricing_database  # noqa: F401
from tests.test_simple_product_import import fresh_company_context

pytestmark = [pytest.mark.mysql, pytest.mark.usefixtures("stable_product_source_clock")]


@pytest.mark.parametrize("flow", ["CREATE", "GOODS", "SERVICE"])
async def test_native_multiple_sale_prices(native_pricing_database, flow):  # noqa: F811
    from tests.test_simple_import_sale_prices import (
        test_named_sale_columns_import_activate_report_and_protect_retained_values,
    )
    from tests.test_simple_sale_prices import (
        test_options_and_four_initial_prices_are_published_once,
    )

    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    factory = create_session_factory(engine, guarded=True)
    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://catalog.test",
            event_hooks={"request": [fresh_company_context]},
        ) as client:
            if flow == "CREATE":
                await test_options_and_four_initial_prices_are_published_once(
                    client, factory, uuid7()
                )
            else:
                await test_named_sale_columns_import_activate_report_and_protect_retained_values(
                    client, factory, uuid7(), flow, "CSV" if flow == "GOODS" else "XLSX"
                )
