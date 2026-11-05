"""Deferred owner work is admitted durably without claiming a completed effect."""

import pytest
from sqlalchemy import func, select

from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.import_contracts import CommitImport, ImportAction
from billing_platform.import_reads import record_history
from tests.models import TenantThing
from tests.test_import_framework import Adapter, invoke, row, stage


class DeferredAdapter(Adapter):
    async def prepare_import(self, db, record, mode, results, key, *, validate):
        result = await self.execute(db, record, mode, results, key)
        return result if validate else {"receipt_id": result["id"], "pending": True}


async def test_bounded_validation_and_admission_resume_without_repeating_work(factory, tenant_a):
    adapter = DeferredAdapter(tenant_a)
    adapter.command_group_limit = 1
    with tenant_scope(tenant_a):
        job = await stage(factory, adapter, [row("one"), row("two")])
        first = await invoke(
            factory,
            adapter,
            "validate",
            ImportAction(expected_version=job["row_version"]),
            job["id"],
        )
        assert first["state"] == "VALIDATING" and first["review_digest"] is None
        ready = await invoke(
            factory,
            adapter,
            "validate",
            ImportAction(expected_version=first["row_version"]),
            job["id"],
        )
        assert ready["state"] == "READY"
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == 0
        first = await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(
                expected_version=ready["row_version"], review_digest=ready["review_digest"]
            ),
            job["id"],
        )
        assert first["state"] == "IMPORTING" and first["review_digest"] == ready["review_digest"]
        # Accepted input survives source expiry; current authority still controls
        # admission and configuration is rechecked by each native command.
        import datetime as dt
        import uuid

        from billing_platform.db.types import utcnow
        from billing_platform.errors import PermissionDeniedError
        from billing_platform.import_cleanup import cleanup_imports
        from billing_platform.import_models import ImportJob

        async with factory.begin() as db:
            stored = await db.get(ImportJob, uuid.UUID(job["id"]))
            stored.expires_at = utcnow() - dt.timedelta(seconds=1)
        await cleanup_imports(factory, tenant_a, adapter.company, "example")
        adapter.denied = True
        with pytest.raises(PermissionDeniedError):
            await invoke(
                factory,
                adapter,
                "commit",
                CommitImport(
                    expected_version=first["row_version"], review_digest=first["review_digest"]
                ),
                job["id"],
            )
        adapter.denied = False
        adapter.context = "native-policy-rechecked"
        final = await invoke(
            factory,
            adapter,
            "commit",
            CommitImport(
                expected_version=first["row_version"], review_digest=first["review_digest"]
            ),
            job["id"],
        )
        assert final["state"] == "PARTIAL" and final["completed_count"] == 0
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == 2


async def test_pending_work_is_not_success_and_cannot_be_replaced(factory, tenant_a):
    adapter = DeferredAdapter(tenant_a)
    with tenant_scope(tenant_a):
        job = await stage(factory, adapter, [row("one")])
        ready = await invoke(
            factory,
            adapter,
            "validate",
            ImportAction(expected_version=job["row_version"]),
            job["id"],
        )
        async with factory() as db:
            assert await db.scalar(select(func.count(TenantThing.id))) == 0
        body = CommitImport(
            expected_version=ready["row_version"], review_digest=ready["review_digest"]
        )
        pending = await invoke(factory, adapter, "commit", body, job["id"], key="admit-once")
        assert pending["state"] == "PARTIAL" and pending["completed_count"] == 0
        replay = await invoke(factory, adapter, "commit", body, job["id"], key="admit-once")
        assert replay == pending
        async with factory() as db:
            import uuid

            assert await db.scalar(select(func.count(TenantThing.id))) == 1
            records = await record_history(
                db, adapter, uuid.UUID(job["id"]), b"deferred-test-key-not-a-live-secret", limit=25
            )
            assert records["items"][0]["status"] == "PENDING"
            assert records["items"][0]["business_id"] is None
        for action in ("validate", "retry", "cancel"):
            with pytest.raises(ConflictError, match="resume"):
                await invoke(
                    factory,
                    adapter,
                    action,
                    ImportAction(expected_version=pending["row_version"]),
                    job["id"],
                )
        # Payload retention must not erase the record links needed to finish owner commands.
        import datetime as dt

        from billing_platform.db.types import utcnow
        from billing_platform.import_cleanup import cleanup_imports
        from billing_platform.import_models import ImportJobRecord

        await cleanup_imports(
            factory,
            tenant=tenant_a,
            company=adapter.company,
            namespace="example",
            now=utcnow() + dt.timedelta(days=366),
        )
        async with factory() as db:
            assert await db.scalar(select(func.count(ImportJobRecord.id))) == 1
