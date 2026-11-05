"""Seed only the disposable native audit proof's Catalog source snapshot."""

import asyncio
import os
import re
import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.engine import make_url

from catalog.tasks.projections import activate_snapshot
from tests.source_factories import company_record, snapshot


async def main() -> None:
    url = os.environ["CATALOG_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or not re.fullmatch(
        r"audit_proof_[0-9a-f]{24}_catalog", parsed.database or ""
    ):
        raise ValueError("isolated proof schema required")
    tenant, company, user = (
        uuid.UUID(os.environ["CATALOG_PROOF_" + key]) for key in ("TENANT", "COMPANY", "USER")
    )
    engine = create_engine(url)
    try:
        with tenant_scope(tenant):
            async with create_session_factory(engine)() as db, db.begin():
                await activate_snapshot(
                    db,
                    snapshot(
                        tenant,
                        company,
                        (
                            company_record(company),
                            SnapshotRecord(kind="user", id=user, data={"status": "active"}),
                        ),
                        version=int(os.environ["CATALOG_PROOF_VERSION"]),
                    ),
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
