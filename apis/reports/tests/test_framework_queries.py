"""Query shapes must retain session-level tenant protection, including nested reads."""

import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.tenant_context import TenantContextError
from conftest import COMPANY, TENANT
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from test_foundation import generation, load

from reports.models.core import ReportLine


async def test_direct_orm_alias_join_keeps_every_occurrence_scoped(app, client, prefix):
    created = await generation(client, prefix)
    await load(app, created["id"])
    other = aliased(ReportLine)
    query = (
        select(ReportLine.id, other.id, other.base_amount)
        .join(other, other.source_id == ReportLine.source_id)
        .where(ReportLine.company_id == COMPANY, other.company_id == COMPANY)
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = (await db.execute(query)).all()
            assert len(rows) == 2 and all(a == b for a, b, _ in rows)
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            assert (await db.execute(query)).all() == []


async def test_scoped_aggregate_alias_and_subquery_keep_exact_values(app, client, prefix):
    created = await generation(client, prefix)
    await load(app, created["id"])
    statement = (
        select(ReportLine.side, func.sum(ReportLine.base_amount).label("base_amount"))
        .where(ReportLine.company_id == COMPANY)
        .group_by(ReportLine.side)
        .order_by(ReportLine.side)
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            values = (await db.execute(statement)).all()
            assert values == [("CREDIT", Decimal("100.0000")), ("DEBIT", Decimal("100.0000"))]
            assert all(isinstance(value, Decimal) for _side, value in values)
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            assert (await db.execute(statement)).all() == []
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            # A raw Core alias cannot borrow another ORM occurrence's tenant protection.
            unsafe = ReportLine.__table__.alias("unsafe")
            with pytest.raises(TenantContextError):
                await db.execute(select(ReportLine.id, unsafe.c.id))
            # RF0: this aliased aggregate shape is rejected by the current guard.
            # Keep the fail-closed behavior until a separately reviewed query change.
            line = aliased(ReportLine)
            grouped = (
                select(line.company_id, line.side, func.sum(line.base_amount).label("base_amount"))
                .where(line.company_id == COMPANY)
                .group_by(line.company_id, line.side)
                .subquery()
            )
            totals = aliased(ReportLine, grouped, adapt_on_names=True)
            with pytest.raises(TenantContextError):
                await db.execute(select(totals.side, totals.base_amount))
