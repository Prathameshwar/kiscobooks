import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from billing_platform.db.claims import candidate_statement, insert_candidate
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import TenantContextError, tenant_scope
from billing_platform.ids import uuid7
from tests.models import ExemptThing, TenantThing


async def test_candidate_requires_owner_transaction_and_preserves_existing_row(
    engine: AsyncEngine,
) -> None:
    factory = create_session_factory(engine, guarded=True)
    owner, identity = uuid7(), uuid7()
    with tenant_scope(owner):
        async with factory() as db:
            with pytest.raises(TenantContextError):
                await insert_candidate(db, TenantThing, {"tenant_id": uuid7(), "name": "bad"})
            with pytest.raises(RuntimeError):
                await insert_candidate(db, TenantThing, {"tenant_id": owner, "name": "unscoped"})
            async with db.begin():
                await insert_candidate(
                    db, TenantThing, {"tenant_id": owner, "id": identity, "name": "kept"}
                )
                await insert_candidate(
                    db,
                    TenantThing,
                    {"tenant_id": owner, "id": identity, "name": "must-not-replace"},
                )
            assert (await db.scalars(select(TenantThing))).one().name == "kept"
    with pytest.raises(TypeError):
        candidate_statement("sqlite", ExemptThing, {"code": "US"})
