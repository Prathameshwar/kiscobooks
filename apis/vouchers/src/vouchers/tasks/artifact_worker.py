"""Restart-safe local artifact worker: python -m vouchers.tasks.artifact_worker."""

import asyncio

from billing_platform.db import create_engine, create_session_factory, tenant_scope, unfiltered
from sqlalchemy import select

from vouchers.config import Settings
from vouchers.models.core import VoucherArtifact
from vouchers.tasks.artifacts import render_pending


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    try:
        while True:
            # Reviewed cross-tenant work discovery only; processing re-enters tenant scope.
            with unfiltered():
                async with factory() as db:
                    batch = (
                        await db.execute(
                            select(VoucherArtifact.id, VoucherArtifact.tenant_id)
                            .where(VoucherArtifact.status == "PENDING")
                            .order_by(VoucherArtifact.id)
                            .limit(50)
                        )
                    ).all()
            for artifact_id, tenant_id in batch:
                with tenant_scope(tenant_id):
                    async with factory() as db, db.begin():
                        await render_pending(db, artifact_id)
            await asyncio.sleep(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg] # settings accepts env-file at runtime
