"""Native stage/preview/commit measurement; synthetic owner facts, real Catalog commands."""

import copy
import os
import statistics
import uuid
from time import perf_counter

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import SecretStr
from sqlalchemy import func, select

from catalog.config import Settings
from catalog.main import create_app
from catalog.models import Item, ProductFamily
from catalog.models.bulk import BulkChangeSetEffect, BulkJob
from catalog.tasks.bulk_execution import step
from tests.bulk_factories import post, proofs
from tests.conftest import ACTOR_SECRET
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tools.mysql_smoke import run_verifier


async def verify(url: str) -> dict[str, object]:
    count = int(os.environ.get("CATALOG_BULK_BENCHMARK_ROWS", "2000"))
    assert 1 <= count <= 2000
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            factory, tenant = app.state.session_factory, uuid7()
            company, user, _, body = await setup_product(factory, tenant)
            facts = all_facts(company, user)
            version, last_refresh, renewals = 2, 0.0, 0

            async def renew() -> None:
                nonlocal version, last_refresh, renewals
                if perf_counter() - last_refresh < 10:
                    return
                version += 1
                # Independent synthetic owner facts preserve source identities and
                # content across refreshes. Actual HTTP ownership is tested separately.
                await setup_source(factory, tenant, company, user, version=version, facts=facts)
                last_refresh, renewals = perf_counter(), renewals + 1

            def auth() -> dict[str, str]:
                return headers(
                    company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS)
                )

            records = []
            for index in range(count):
                data = copy.deepcopy(body)
                data["code"] = f"PRODUCT-{index:05d}"
                data["default_item"]["sku"] = f"SKU-{index:05d}"
                records.append(
                    {
                        "key": f"sku-{index}",
                        "change_set": f"group-{index // 10}",
                        "resource": "product_family",
                        "data": data,
                    }
                )
            await renew()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client:
                root = f"/v1/companies/{company}/bulk-jobs"
                started = perf_counter()
                job = await post(client, root, auth(), "", {"format": "JSON", "records": records})
                stage_ms = (perf_counter() - started) * 1000
                await post(
                    client,
                    root,
                    auth(),
                    f"/{job['id']}/validate",
                    {"expected_version": job["row_version"]},
                )
                job_id = uuid.UUID(job["id"])

                async def drain(expected: str) -> list[float]:
                    timings: list[float] = []
                    for index in range(count + 2):
                        await renew()
                        with tenant_scope(tenant):
                            async with factory() as db:
                                state = await db.scalar(
                                    select(BulkJob.state).where(
                                        BulkJob.company_id == company, BulkJob.id == job_id
                                    )
                                )
                        if state == expected:
                            return timings
                        assert state in {"VALIDATING", "QUEUED", "RUNNING"}, state
                        start = perf_counter()
                        await step(
                            factory,
                            proofs(tenant, company, user, version=version),
                            tenant,
                            company,
                            user,
                            job_id,
                            ACTOR_SECRET.encode(),
                        )
                        timings.append((perf_counter() - start) * 1000)
                        if (index + 1) % 10 == 0:
                            print(f"bulk benchmark {expected}: {index + 1} chunks", flush=True)
                    raise AssertionError("benchmark exceeded the worker bound")

                validation = await drain("READY")
                with tenant_scope(tenant):
                    async with factory() as db:
                        assert (
                            await db.scalar(
                                select(func.count(Item.id)).where(Item.company_id == company)
                            )
                            == 0
                        )
                await renew()
                ready = (await client.get(root + "/" + job["id"], headers=auth())).json()
                await post(
                    client,
                    root,
                    auth(),
                    f"/{job['id']}/commit",
                    {
                        "expected_version": ready["row_version"],
                        "selection_digest": ready["selection_digest"],
                    },
                )
                committed = await drain("SUCCEEDED")
                with tenant_scope(tenant):
                    async with factory() as db:
                        for model in (ProductFamily, Item):
                            assert (
                                await db.scalar(
                                    select(func.count(model.id)).where(model.company_id == company)
                                )
                                == count
                            )
                        effects = await db.scalar(
                            select(func.count(BulkChangeSetEffect.id)).where(
                                BulkChangeSetEffect.company_id == company
                            )
                        )
                        assert effects == (count + 9) // 10
                await renew()
                assert not await step(
                    factory,
                    proofs(tenant, company, user, version=version),
                    tenant,
                    company,
                    user,
                    job_id,
                    ACTOR_SECRET.encode(),
                )

                def measured(values: list[float]) -> dict[str, float]:
                    return {
                        "total_ms": round(sum(values), 2),
                        "median_chunk_ms": round(statistics.median(values), 2),
                        "maximum_chunk_ms": round(max(values), 2),
                    }

                return {
                    "rows": count,
                    "created_skus": count,
                    "change_set_effects": effects,
                    "stage_ms": round(stage_ms, 2),
                    "preview": measured(validation),
                    "commit": measured(committed),
                    "owner_fixture_renewals": renewals,
                    "preview_mutations": 0,
                    "completed_replay_effects": 0,
                    "owner_source": (
                        "synthetic facts; real HTTP owner verified by integration suite"
                    ),
                }
    finally:
        await app.state.engine.dispose()


def main() -> None:
    run_verifier(verify)


if __name__ == "__main__":
    main()
