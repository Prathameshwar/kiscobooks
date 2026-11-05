"""Run Product Master review regressions in a disposable migrated MySQL schema."""

import httpx
import pytest
from billing_platform.ids import uuid7
from pydantic import SecretStr

from catalog.config import Settings
from catalog.main import create_app
from tests.conftest import ACTOR_SECRET, stable_product_source_clock
from tests.test_product_integrity_fixes import (
    test_future_unit_grid_conflict,
    test_minimum_patch_ignores_sku_grid,
)
from tests.test_product_master_review_fixes import (
    test_expired_product_revision_identifies_reloadable_revision,
    test_simple_patch_checks_child_field_denies_before_persistence,
    test_simple_patch_validates_references_before_persisting,
)
from tests.test_simple_products import test_simple_create_read_edit_and_replay
from tools.mysql_smoke import run_verifier


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        with pytest.MonkeyPatch.context() as patch:
            stable_product_source_clock.__wrapped__(patch)
            async with app.router.lifespan_context(app):
                factory = app.state.session_factory
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://catalog.test",
                ) as client:
                    for reference, status in (
                        ("missing", 404),
                        ("wrong_company", 403),
                        ("wrong_tenant", 404),
                    ):
                        await test_simple_patch_validates_references_before_persisting(
                            client, factory, uuid7(), uuid7(), reference, status
                        )
                    await test_simple_patch_checks_child_field_denies_before_persistence(
                        client, factory, uuid7()
                    )
                    await test_expired_product_revision_identifies_reloadable_revision(
                        client, factory, uuid7(), patch
                    )
                    for check in (
                        test_future_unit_grid_conflict,
                        test_minimum_patch_ignores_sku_grid,
                    ):
                        await check(client, factory, uuid7())
                    for kind in ("GOODS", "SERVICE"):
                        await test_simple_create_read_edit_and_replay(
                            client, factory, uuid7(), kind
                        )
        return {
            "scoped_reference_cases": 3,
            "child_field_denial": "PASS",
            "expired_revision_recovery": "PASS",
            "quantity_grid_regressions": 2,
            "simple_product_replays": 2,
        }
    finally:
        await app.state.engine.dispose()


if __name__ == "__main__":
    run_verifier(verify, roundtrip=False)
