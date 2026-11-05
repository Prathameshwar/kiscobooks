"""Native MySQL verifies the durable creation workflow and receipt retention."""

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


async def test_native_creation_and_retained_receipts(native_pricing_database, monkeypatch):  # noqa: F811
    from tests.test_simple_creation_configuration_review import (
        test_options_include_selected_default_type_requirements,
        test_published_configuration_controls_form_and_ready_product,
        test_start_does_not_disclose_protected_code_or_save_unreadable_receipt,
    )
    from tests.test_simple_product_creation import (
        test_creation_receipts_are_tenant_isolated,
        test_gst_hsn_or_sac_applies_to_both_directions,
        test_opening_workflow_uses_exact_native_manifest_and_resumes_uncertain_create,
        test_rejected_input_can_be_corrected_but_committed_or_uncertain_create_cannot,
        test_rejected_post_can_retry_same_voucher_but_pending_post_cannot_duplicate,
        test_save_creates_active_product_and_live_prices,
    )

    engine, config = native_pricing_database
    await asyncio.to_thread(command.upgrade, config, "head")
    factory = create_session_factory(engine, guarded=True)
    await test_creation_receipts_are_tenant_isolated(factory, uuid7(), uuid7())
    app = create_app(Settings(actor_signing_secret=SecretStr(ACTOR_SECRET)), engine=engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://catalog.test"
        ) as client:
            for kind in ("GOODS", "SERVICE"):
                await test_save_creates_active_product_and_live_prices(
                    client, factory, uuid7(), kind, inventory=True
                )
                await test_gst_hsn_or_sac_applies_to_both_directions(client, factory, uuid7(), kind)
                await test_options_include_selected_default_type_requirements(
                    client, factory, uuid7(), kind
                )
                await test_published_configuration_controls_form_and_ready_product(
                    client, factory, uuid7(), kind
                )
            await test_start_does_not_disclose_protected_code_or_save_unreadable_receipt(
                client, factory, uuid7()
            )
            with monkeypatch.context() as patch:
                await test_opening_workflow_uses_exact_native_manifest_and_resumes_uncertain_create(
                    client, factory, uuid7(), patch
                )
            with monkeypatch.context() as patch:
                await test_rejected_post_can_retry_same_voucher_but_pending_post_cannot_duplicate(
                    client, factory, uuid7(), patch
                )
            with monkeypatch.context() as patch:
                await test_rejected_input_can_be_corrected_but_committed_or_uncertain_create_cannot(
                    client, factory, uuid7(), patch
                )
    with pytest.raises(RuntimeError, match="retain simple product creation receipts"):
        await asyncio.to_thread(command.downgrade, config, "0217")
