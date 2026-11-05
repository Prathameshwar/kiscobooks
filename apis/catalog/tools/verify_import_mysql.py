"""Exercise shared imports against a fresh disposable native Catalog schema."""

import datetime as dt
import os

import httpx
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.import_cleanup import cleanup_imports
from billing_platform.import_contracts import FileFormat
from billing_platform.import_models import ImportChangeSetEffect, ImportJob, ImportJobRevision
from pydantic import SecretStr
from sqlalchemy import func, select

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import service_metadata
from tests.conftest import ACTOR_SECRET
from tests.test_master_imports import (
    test_goods_and_service_imports_reuse_native_family_command,
    test_import_fixed_price_draft_and_publish_in_one_aggregate,
    test_price_import_and_tenant_authority,
    test_template_includes_serializable_effective_custom_configuration,
)
from tools.mysql_smoke import run_verifier


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.state.engine.connect() as db:
            changes = await db.run_sync(
                lambda connection: compare_metadata(
                    MigrationContext.configure(connection), service_metadata()
                )
            )
            assert not changes, changes
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client,
        ):
            cases: tuple[tuple[str, FileFormat], ...] = (
                ("GOODS", "CSV"),
                ("SERVICE", "TSV"),
                ("GOODS", "XLSX"),
            )
            for kind, file_format in cases:
                await test_goods_and_service_imports_reuse_native_family_command(
                    client, app.state.session_factory, uuid7(), kind, file_format
                )
            await test_price_import_and_tenant_authority(client, app.state.session_factory, uuid7())
            await test_import_fixed_price_draft_and_publish_in_one_aggregate(
                client, app.state.session_factory, uuid7()
            )
            await test_template_includes_serializable_effective_custom_configuration(
                client, app.state.session_factory, uuid7()
            )
            tenant = uuid7()
            await test_goods_and_service_imports_reuse_native_family_command(
                client, app.state.session_factory, tenant, "GOODS", "CSV"
            )
            with tenant_scope(tenant):
                async with app.state.session_factory() as db:
                    company = await db.scalar(select(ImportJob.company_id))
                    assert company is not None
            counts = await cleanup_imports(
                app.state.session_factory,
                tenant,
                company,
                "catalog",
                now=utcnow() + dt.timedelta(days=400),
            )
            assert counts == {"payload_jobs": 1, "templates": 1, "history_jobs": 1}, counts
            with tenant_scope(tenant):
                async with app.state.session_factory() as db:
                    assert await db.scalar(select(ImportJobRevision.batch)) is None
                    assert await db.scalar(select(func.count(ImportChangeSetEffect.id))) == 1
        return {"import_workflows": 7, "model_parity": "PASS", "cleanup": "PASS"}
    finally:
        await app.state.engine.dispose()


if __name__ == "__main__":
    os.environ.setdefault("CATALOG_TEST_MYSQL_SERVER_URL", "mysql+asyncmy://root@127.0.0.1:13396")
    run_verifier(verify)
