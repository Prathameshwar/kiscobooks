"""Native aggregates, immutable index evidence and legacy calculation coexist."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_native_ledger import prepared, request

from reports.domain.statements import Facts
from reports.domain.trial_balance import calculate
from reports.models.hierarchy import ReportHierarchyNode
from reports.queries.native_context import NativeContext
from reports.queries.trial_balance import execute


async def test_native_trial_balance_matches_independent_hierarchy_across_years(app):
    identities, facts, _ = await prepared(app)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            context = await NativeContext.load(db, COMPANY, identities[2])
            for dates in (
                {"date_from": "2026-04-01", "date_to": "2026-04-30"},
                {
                    "date_from": "2027-04-01",
                    "date_to": "2027-04-30",
                    "comparative_from": "2026-04-01",
                    "comparative_to": "2026-04-30",
                },
                {"date_from": "2026-04-03", "date_to": "2026-04-03"},
            ):
                query = request(identities[2], "TRIAL_BALANCE", **dates)
                assert await execute(db, context, query, 100000) == calculate(
                    Facts(facts), query, context.coverage
                )
            with pytest.raises(ConflictError, match="capacity|bound"):
                await execute(db, context, query, 1)


async def test_hierarchy_table_is_tenant_scoped_and_has_indexed_parent_paging(app):
    from reports.metadata import service_metadata

    table = service_metadata().tables["report_hierarchy_node"]
    assert any(
        tuple(index.columns.keys())
        == ("tenant_id", "company_id", "job_id", "attempt", "period", "parent_key", "ordinal")
        for index in table.indexes
    )
    assert "amount" not in table.columns
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert list(await db.scalars(select(ReportHierarchyNode))) == []
