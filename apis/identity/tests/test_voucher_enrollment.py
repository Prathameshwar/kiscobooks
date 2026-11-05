"""Automatic Vouchers source scope is native, explicit, signed and audited."""

import secrets
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential, request_headers, verify_response
from billing_platform.service_auth import CompanyServiceScope, service_request_bytes
from pydantic import SecretStr
from sqlalchemy import select

from identity.models import Company, PlatformInstallation
from tests.factories import build_catalog_source_enrollment, seed_two_companies


async def test_signed_voucher_discovery_native_eligibility_cursor_and_audit(
    client, app, session, tenant_a, tenant_b
):
    first, second = await seed_two_companies(session, tenant_a, tenant_b)
    secret, key_id = secrets.token_hex(32), "vouchers.enrollment.test"
    settings = app.state.settings
    settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant_a, company_id=first),),
    )
    path = "/internal/v1/voucher-enrollments"

    def signed(method, endpoint, raw=b"", query=""):
        framed = service_request_bytes(method=method, path=endpoint, query=query, body=raw)
        return request_headers(
            requester="vouchers",
            owner="identity",
            key_id=key_id,
            secret=secret.encode(),
            framed=framed,
        ), framed

    raw = canonical_json({"limit": 1})
    assert (await client.post(path, content=raw)).status_code == 401
    headers, framed = signed("POST", path, raw)
    assert (await client.post(path, content=raw, headers=headers)).status_code == 403
    settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret), allow_enrolled_companies=True
    )
    with unfiltered():
        session.add(
            PlatformInstallation(
                id=uuid7(), key="platform", completed_at=utcnow(), tenant_id=tenant_a
            )
        )
        session.add_all(
            [
                build_catalog_source_enrollment(tenant_id=tenant, company_id=company)
                for tenant, company in ((tenant_a, first), (tenant_b, second))
            ]
        )
        await session.commit()
    response = await client.post(path, content=raw, headers=headers)
    assert response.status_code == 200, response.text
    verify_response(
        requester="vouchers",
        owner="identity",
        key_id=key_id,
        secret=secret.encode(),
        framed=framed,
        body=response.content,
        headers=response.headers,
    )
    assert len(response.json()["scopes"]) == 1 and response.json()["next_cursor"]
    next_raw = canonical_json({"limit": 1, "cursor": response.json()["next_cursor"]})
    next_headers, _ = signed("POST", path, next_raw)
    other = await client.post(path, content=next_raw, headers=next_headers)
    assert other.status_code == 200 and other.json()["next_cursor"] is None
    assert {
        scope["company_id"] for scope in response.json()["scopes"] + other.json()["scopes"]
    } == {str(first), str(second)}
    changed = canonical_json({"limit": 2, "cursor": response.json()["next_cursor"]})
    changed_headers, _ = signed("POST", path, changed)
    assert (await client.post(path, content=changed, headers=changed_headers)).status_code == 422
    source_path = f"/internal/v1/voucher-sources/{tenant_a}/{first}/vouchers.voucher"
    source_headers, _ = signed("GET", source_path)
    assert (await client.get(source_path, headers=source_headers)).status_code == 200
    with tenant_scope(tenant_a):
        company = await session.get(Company, first)
        company.status = "suspended"
        await session.commit()
    source_headers, _ = signed("GET", source_path)
    assert (await client.get(source_path, headers=source_headers)).status_code == 401
    all_raw = b"{}"
    all_headers, _ = signed("POST", path, all_raw)
    remaining = await client.post(path, content=all_raw, headers=all_headers)
    assert remaining.json()["scopes"] == [{"tenant_id": str(tenant_b), "company_id": str(second)}]
    with unfiltered():
        evidence = await session.scalar(
            select(Outbox).where(Outbox.event_type == "voucher_source.discovery_read")
        )
        assert evidence and evidence.tenant_id == tenant_a
