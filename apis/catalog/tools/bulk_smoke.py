"""Native bulk transactions, recovery and scope checks in an owned disposable schema."""

import asyncio
import uuid

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import Connection, func, select, text

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import MIGRATION_HEAD, TABLES, service_metadata
from catalog.models.bulk import BulkChangeSetEffect
from catalog.tasks.bulk_execution import step
from tests.bulk_factories import proofs, setup, unit_row
from tests.conftest import ACTOR_SECRET
from tests.test_bulk_boundaries import (
    test_symbolic_dependency_is_replayed_then_resolved_to_real_effect,
)
from tests.test_bulk_lifecycle import (
    queue,
    review,
    test_cancel_and_revision_preserve_completed_effects,
    test_expiry_erases_private_payloads_without_deleting_job_identity,
    test_failed_commit_rolls_back_and_crash_retry_has_one_effect,
)
from tests.test_bulk_products_prices import (
    test_price_adjustment_publishes_exact_future_revision_with_rounding,
    test_product_aggregate_uses_native_create_and_staged_sku_target,
)
from tests.test_bulk_storage import (
    test_all_six_bulk_tables_are_tenant_isolated,
    test_record_change_set_cannot_cross_company_or_job,
)
from tests.test_bulk_workflow import (
    test_bulk_preview_rolls_back_then_commit_is_sealed_and_replayable,
)
from tools.mysql_smoke import run_verifier


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            async with app.state.engine.connect() as connection:

                def differences(sync: Connection) -> list[object]:
                    return list(
                        compare_metadata(MigrationContext.configure(sync), service_metadata())
                    )

                drift = await connection.run_sync(differences)
                assert not drift, drift
                version = await connection.scalar(text("SELECT VERSION()"))
            factory = app.state.session_factory
            await test_all_six_bulk_tables_are_tenant_isolated(factory, uuid7(), uuid7())
            await test_record_change_set_cannot_cross_company_or_job(factory, uuid7())
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client:
                for check in (
                    test_bulk_preview_rolls_back_then_commit_is_sealed_and_replayable,
                    test_symbolic_dependency_is_replayed_then_resolved_to_real_effect,
                    test_cancel_and_revision_preserve_completed_effects,
                    test_expiry_erases_private_payloads_without_deleting_job_identity,
                    test_product_aggregate_uses_native_create_and_staged_sku_target,
                    test_price_adjustment_publishes_exact_future_revision_with_rounding,
                ):
                    await check(client, factory, uuid7())
                for crash in (False, True):
                    with pytest.MonkeyPatch.context() as patch:
                        await test_failed_commit_rolls_back_and_crash_retry_has_one_effect(
                            client, factory, uuid7(), patch, crash
                        )
                tenant = uuid7()
                company, user, auth = await setup(factory, tenant)
                root, job = await review(
                    client,
                    factory,
                    tenant,
                    company,
                    user,
                    auth,
                    {"format": "JSON", "records": [unit_row("race")]},
                )
                await queue(client, root, auth, job)
                result = await asyncio.gather(
                    *(
                        step(
                            factory,
                            proofs(tenant, company, user),
                            tenant,
                            company,
                            user,
                            uuid.UUID(job["id"]),
                            ACTOR_SECRET.encode(),
                        )
                        for _ in range(2)
                    )
                )
                assert sorted(result) == [False, True]
                with tenant_scope(tenant):
                    async with factory() as db:
                        assert await db.scalar(select(func.count(BulkChangeSetEffect.id))) == 1
        return {
            "server_version": version,
            "tables": len(TABLES),
            "head": MIGRATION_HEAD,
            "schema_drift": [],
            "bulk_tenant_isolation_tables": 6,
            "workflows": 8,
            "scope_constraints": "passed",
            "concurrent_worker_effects": 1,
        }
    finally:
        await app.state.engine.dispose()


def main() -> None:
    run_verifier(verify)


if __name__ == "__main__":
    main()
