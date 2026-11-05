"""Vouchers receives company capabilities only through a signed owner-scoped export."""

from billing_platform.db import tenant_scope
from billing_platform.owner_snapshot import SnapshotCredential, request_headers, verify_response
from billing_platform.service_auth import CompanyServiceScope, service_request_bytes
from pydantic import SecretStr

from tests.factories import build_company_feature, seed_two_companies


async def test_signed_company_snapshot_is_scoped_versioned_and_tracks_features(
    client, app, session, tenant_a, tenant_b
):
    import secrets

    company, other = await seed_two_companies(session, tenant_a, tenant_b)
    secret = secrets.token_hex(32)
    key_id = "vouchers.company-defaults.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),),
    )
    path = f"/internal/v1/voucher-sources/{tenant_a}/{company}/company"

    async def read(target=path):
        framed = service_request_bytes(method="GET", path=target, query="", body=b"")
        result = await client.get(
            target,
            headers=request_headers(
                requester="vouchers",
                owner="identity",
                key_id=key_id,
                secret=secret.encode(),
                framed=framed,
            ),
        )
        if result.status_code == 200:
            verify_response(
                requester="vouchers",
                owner="identity",
                key_id=key_id,
                secret=secret.encode(),
                framed=framed,
                body=result.content,
                headers=result.headers,
            )
        return result

    assert (await client.get(path)).status_code == 401
    first = await read()
    assert first.status_code == 200, first.text
    fact = first.json()["bundle"]["masters"][0]
    assert fact["source_id"] == str(company) and fact["entity_type"] == "company"
    assert not fact["facts"]["inventory"] and set(fact["facts"]) == {
        "inventory",
        "bom_definitions",
        "approval_workflow",
        "multi_currency",
    }
    with tenant_scope(tenant_a):
        session.add(
            build_company_feature(
                tenant_id=tenant_a, company_id=company, feature_key="inventory", is_enabled=True
            )
        )
        await session.commit()
    second = await read()
    assert second.status_code == 200, second.text
    latest = second.json()["bundle"]["masters"][0]
    assert latest["source_version"] > fact["source_version"] and latest["facts"]["inventory"]
    assert (await read(path.replace(str(company), str(other)))).status_code == 401
    assert (await read(path.replace(str(tenant_a), str(tenant_b)))).status_code == 401
