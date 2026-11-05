"""Native storage checks for import rollback, replay, pricing and opening orchestration."""

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

pytestmark = [pytest.mark.mysql, pytest.mark.usefixtures("stable_product_source_clock")]


async def test_native_simple_imports(native_pricing_database, monkeypatch):  # noqa: F811
    from tests.test_simple_product_import import (
        test_gst_import_resolves_hsn_sac_and_rule_codes,
        test_invalid_rows_correction_report_history_and_isolation,
        test_opening_import_keeps_exact_cost_and_resumes_lost_native_response,
        test_simple_template_validates_ready_product_and_retains_only_pending_commands,
    )

    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    factory = create_session_factory(engine, guarded=True)
    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
        ) as client:
            for kind, file_format in (("GOODS", "CSV"), ("SERVICE", "TSV"), ("GOODS", "XLSX")):
                await (
                    test_simple_template_validates_ready_product_and_retains_only_pending_commands(
                        client, factory, uuid7(), kind, file_format
                    )
                )
            await test_invalid_rows_correction_report_history_and_isolation(
                client, factory, uuid7(), uuid7()
            )
            for kind in ("GOODS", "SERVICE"):
                await test_gst_import_resolves_hsn_sac_and_rule_codes(
                    client, factory, uuid7(), kind
                )
            await test_opening_import_keeps_exact_cost_and_resumes_lost_native_response(
                client, factory, uuid7(), monkeypatch
            )


@pytest.mark.parametrize("with_prices", [False, True])
async def test_native_mrp_import_validation(native_pricing_database, with_prices):  # noqa: F811
    from tests.test_simple_product_import import (
        test_mrp_validation_uses_native_numeric_revision_without_saving_prices,
    )

    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    if not with_prices:
        await asyncio.to_thread(command.downgrade, config, "0218")
        await asyncio.to_thread(command.upgrade, config, "head")
    factory = create_session_factory(engine, guarded=True)
    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
        ) as client:
            await test_mrp_validation_uses_native_numeric_revision_without_saving_prices(
                client, factory, uuid7(), with_prices
            )
