"""Daily aggregates are exact derived data, scoped and immutable with their source cut."""

import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_native_ledger import prepared
from test_source_versions import staged

from reports.models.daily_balances import GRAIN, ReportDailyBalance
from reports.models.source_versions import ReportSourceCut
from reports.tasks import daily_projection
from reports.tasks.source_publication import publish


async def test_daily_projection_partitions_high_cardinality_without_a_company_group_cap(
    app, monkeypatch
):
    monkeypatch.setattr(daily_projection, "MAXIMUM_GROUPS", 2)
    identities, _ = await staged(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )
        await publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(ReportDailyBalance)))
            assert len(rows) > 2
            assert sum(row.line_count for row in rows) == 20


async def test_daily_projection_tenant_scope_and_immutability(app):
    await prepared(app)
    other = uuid.uuid4()
    await prepared(app, tenant=other)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(ReportDailyBalance)))
            assert rows and {row.tenant_id for row in rows} == {TENANT}
            assert all(isinstance(row.amount, Decimal) for row in rows)
        for remove in (False, True):
            async with app.state.session_factory() as db:
                row = await db.scalar(
                    select(ReportDailyBalance).where(ReportDailyBalance.id == rows[0].id)
                )
                if remove:
                    await db.delete(row)
                else:
                    row.base_amount += Decimal(1)
                with pytest.raises(ConflictError, match="immutable|cannot be deleted"):
                    await db.flush()
                await db.rollback()


async def test_daily_projection_resume_rejects_forged_totals_and_verifies_completeness(
    app, monkeypatch
):
    identities, _ = await staged(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identities[2])
            )

        async def interrupted(*args):
            raise RuntimeError("injected interruption after daily persistence")

        with monkeypatch.context() as patch:
            patch.setattr(daily_projection, "verify", interrupted)
            with pytest.raises(RuntimeError, match="injected"):
                await publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            row = await db.scalar(
                select(ReportDailyBalance).where(ReportDailyBalance.cut_id == cut.id)
            )
            values = {key: getattr(row, key) for key in GRAIN}
            count = row.line_count
            amount = row.base_amount
        async with app.state.session_factory() as db:
            db.add(
                ReportDailyBalance(
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    cut_id=cut.id,
                    base_amount=amount + 1,
                    **values,
                )
            )
            with pytest.raises(ConflictError, match="exact posted"):
                await db.flush()
            await db.rollback()
        await publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            evidence = (
                await db.scalar(select(ReportSourceCut).where(ReportSourceCut.id == cut.id))
            ).verification
            with pytest.raises(ConflictError, match="reconcile"):
                await daily_projection.verify(db, cut, count - 1, evidence)
