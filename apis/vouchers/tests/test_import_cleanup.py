import datetime as dt
import uuid

import pytest
import test_imports_api as import_fixtures
from billing_platform.db import create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from sqlalchemy import func, select
from test_imports_api import auth, bill, purchase_type, upload, validated, voucher_count

from vouchers.models import imports as m
from vouchers.tasks.import_cleanup import cleanup_imports

masters = import_fixtures.masters


async def test_retention_is_scoped_repeatable_and_preserves_drafts(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    ready = await validated(client, prefix, job)
    done = await client.post(
        prefix + f"/voucher-imports/{job['id']}/commit",
        headers=auth(),
        json={
            "expected_version": ready["row_version"],
            "selection_digest": ready["selection_digest"],
        },
    )
    assert done.json()["created_count"] == 1
    factory = create_session_factory(app.state.engine, guarded=True)
    future = utcnow() + dt.timedelta(days=8)
    assert (await cleanup_imports(factory, uuid.uuid4(), COMPANY, now=future))["payload_jobs"] == 0
    assert (await cleanup_imports(factory, TENANT, uuid.uuid4(), now=future))["payload_jobs"] == 0
    counts = await cleanup_imports(factory, TENANT, COMPANY, now=future)
    assert counts["payload_jobs"] == 1
    assert not any((await cleanup_imports(factory, TENANT, COMPANY, now=future)).values())
    path = prefix + f"/voucher-imports/{job['id']}"
    options = {"kind": "RESULT", "format": "CSV"}
    ticket = (await client.post(path + "/download-ticket", headers=auth(), json=options)).json()
    report = await client.post(
        path + "/download", headers=auth(), json=options | {"token": ticket["token"]}
    )
    assert report.status_code == 200 and "CREATED" in report.text, report.text
    with tenant_scope(TENANT):
        async with factory() as db:
            assert await db.scalar(select(m.VoucherImportRevision.snapshot)) is None
            assert await db.scalar(select(m.VoucherImportRevision.content)) is None
            assert await db.scalar(select(func.count(m.VoucherImportResult.id))) == 2
            assert await db.scalar(select(func.count(m.VoucherImportEffect.id))) == 1
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "vouchers.import_job.cleanup")
            )
            assert event.payload["category"] == "system"
    counts = await cleanup_imports(factory, TENANT, COMPANY, now=utcnow() + dt.timedelta(days=400))
    assert counts["history_jobs"] == 1
    assert await voucher_count(app) == 1
    with tenant_scope(TENANT):
        async with factory() as db:
            assert await db.scalar(select(func.count(m.VoucherImportResult.id))) == 0
            assert await db.scalar(select(func.count(m.VoucherImportEffect.id))) == 1
            assert await db.scalar(select(func.count(m.VoucherImportRevision.id))) == 1


async def test_revision_and_result_evidence_cannot_be_rewritten(client, prefix, app, masters):
    kind = await purchase_type(client, prefix)
    await masters.evidence(app)
    job = (await upload(client, prefix, kind["id"], [bill("A")])).json()
    await validated(client, prefix, job)
    with tenant_scope(TENANT):
        for model, field, value in (
            (m.VoucherImportRevision, "snapshot", {}),
            (m.VoucherImportResult, "result", {}),
            (m.VoucherImportAttempt, "outcome", "altered"),
        ):
            with pytest.raises(ConflictError, match="immutable"):
                async with app.state.session_factory() as db, db.begin():
                    row = await db.scalar(select(model))
                    setattr(row, field, value)
