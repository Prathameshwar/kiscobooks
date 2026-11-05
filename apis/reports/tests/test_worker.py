import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import response_headers
from billing_platform.service_auth import CompanyServiceScope, service_request_bytes
from conftest import COMPANY, TENANT
from fixtures import dataset, manifest, source
from pydantic import SecretStr
from reporting_contract.transport import Owner
from sqlalchemy import select
from test_foundation import generation

from reports.models import core as m
from reports.tasks.worker import poll, synchronize


async def test_signed_snapshot_catchup_restart_and_generation_cutover(client, prefix, app):
    record = await generation(client, prefix)
    items = dataset()
    owner = Owner(
        origin="http://127.0.0.1",
        key_id="reports.test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    changed = next(row for row in items if row.entity == "fiscal_period")
    updated = source(
        changed.entity, changed.source_id, changed.data | {"status": "CLOSED", "row_version": 2}
    )
    full = [updated if row.source_id == changed.source_id else row for row in items]
    change = manifest([updated], sequence=2, kind="CHANGE", full=full)
    snapshots = {}
    calls = []
    fail = True

    def handle(request):
        nonlocal fail
        path = request.url.path
        calls.append(path)
        if path.endswith("/head"):
            value = {"sequence": 2, "manifest": change.model_dump(mode="json")}
        elif "/snapshots/" in path and not path.endswith("/facts"):
            identity = uuid.UUID(path.rsplit("/", 1)[-1])
            snapshots.setdefault(identity, manifest(items, identity=identity))
            value = snapshots[identity].model_dump(mode="json")
        elif path.endswith("/changes/2"):
            value = change.model_dump(mode="json")
        else:
            identity = uuid.UUID(path.split("/")[-2])
            after = int(request.url.params.get("after", "0"))
            selected = items if identity in snapshots else [updated]
            if after == 3 and fail:
                fail = False
                raise httpx.ReadError("simulated lost page", request=request)
            page = selected[after : after + 3]
            value = {
                "manifest_id": str(identity),
                "items": [row.model_dump(mode="json") for row in page],
                "next_after": after + len(page) if after + len(page) < len(selected) else None,
            }
        body = canonical_json(value)
        framed = service_request_bytes(
            method=request.method, path=path, query=request.url.query.decode(), body=request.content
        )
        return httpx.Response(
            200,
            content=body,
            headers=response_headers(
                owner,
                owner="accounting",
                requester="reports",
                key_id=owner.key_id,
                request_bytes=framed,
                body=body,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
        with pytest.raises(httpx.ReadError):
            await synchronize(
                app.state.session_factory,
                transport,
                owner,
                TENANT,
                COMPANY,
                uuid.UUID(record["id"]),
            )
        await synchronize(
            app.state.session_factory, transport, owner, TENANT, COMPANY, uuid.UUID(record["id"])
        )
        await synchronize(
            app.state.session_factory, transport, owner, TENANT, COMPANY, uuid.UUID(record["id"])
        )
    assert len(snapshots) == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(m.ReportGeneration, uuid.UUID(record["id"]))
            assert row.status == "READY" and row.applied_sequence == 2
            fact = await db.scalar(
                select(m.ReportFact).where(m.ReportFact.entity == "fiscal_period")
            )
            assert fact.data["status"] == "CLOSED"
            bundles = list(await db.scalars(select(m.ReportBundle)))
            assert len(bundles) == 2 and all(item.status == "APPLIED" for item in bundles)


async def test_bad_signature_quarantines_without_publishing(client, prefix, app):
    row = await generation(client, prefix)
    owner = Owner(
        origin="http://127.0.0.1",
        key_id="reports.test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as transport:
        await poll(app.state.session_factory, transport, owner)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            generation_row = await db.get(m.ReportGeneration, uuid.UUID(row["id"]))
            assert generation_row.status == "QUARANTINED"
            assert await db.scalar(select(m.ReportActivation)) is None
