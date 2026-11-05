import datetime as dt
import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import SnapshotCredential, request_headers
from billing_platform.service_auth import CompanyServiceScope, service_request_bytes
from pydantic import SecretStr
from reporting_contract.authority import AuthoritySource, fetch_authority

from identity.models import Tenant
from tests.factories import (
    build_field_policy,
    build_role,
    build_role_assignment,
    build_role_permission,
)
from tests.test_catalog_authorizations import seed


async def test_dynamic_report_authority_retains_closed_history_and_refuses_revocation(
    app, session, tenant_a, tenant_b
):
    from identity.models import Company
    from tests.factories import build_report_enrollment

    company, _, user, source, _ = await configure(app, session, tenant_a, tenant_b)
    source = source.model_copy(update={"scopes": (), "allow_enrolled_companies": True})
    app.state.settings.report_authority_credentials[source.key_id] = SnapshotCredential(
        secret=source.secret, allow_enrolled_companies=True
    )
    with tenant_scope(tenant_a):
        enrollment = build_report_enrollment(tenant_a, company)
        session.add(enrollment)
        row = await session.get(Company, company)
        row.status = "closed"
        await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:

        async def fetch():
            return await fetch_authority(
                client,
                source,
                tenant=tenant_a,
                company=company,
                actor=user,
                permissions=frozenset({"report.read"}),
            )

        assert (await fetch()).read_allowed
        with tenant_scope(tenant_a):
            enrollment.status = "DISABLED"
            await session.commit()
        with pytest.raises(httpx.HTTPStatusError):
            await fetch()


async def configure(app, session, tenant, other):
    company, foreign, user = await seed(session, tenant, other)
    secret = SecretStr(secrets.token_hex(32))
    scopes = (CompanyServiceScope(tenant_id=tenant, company_id=company),)
    app.state.settings.report_authority_credentials["reports.test"] = SnapshotCredential(
        secret=secret, scopes=scopes
    )
    source = AuthoritySource(
        origin="http://127.0.0.1", key_id="reports.test", secret=secret, scopes=scopes
    )
    with tenant_scope(tenant):
        role = build_role(tenant_id=tenant)
        session.add(role)
        await session.flush()
        permission = build_role_permission(
            tenant_id=tenant, role_id=role.id, permission_key="report.read"
        )
        session.add_all(
            [
                permission,
                build_role_assignment(
                    tenant_id=tenant,
                    role_id=role.id,
                    subject_id=user,
                    scope_type="company",
                    scope_id=company,
                    valid_from=dt.date(2020, 1, 1),
                ),
            ]
        )
        await session.commit()
    return company, foreign, user, source, permission


@pytest.mark.parametrize("entity_type", ["accounting.account", "catalog.item", "catalog.warehouse"])
async def test_signed_worker_proof_rechecks_revocation_and_current_field_denies(
    app, session, tenant_a, tenant_b, entity_type
):
    company, _, user, source, permission = await configure(app, session, tenant_a, tenant_b)
    required = frozenset({"report.read"})
    if entity_type.startswith("catalog."):
        required |= {"item.read", "warehouse.read"}
        with tenant_scope(tenant_a):
            session.add_all(
                [
                    build_role_permission(
                        tenant_id=tenant_a, role_id=permission.role_id, permission_key=key
                    )
                    for key in ("item.read", "warehouse.read")
                ]
            )
            await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:

        async def fetch():
            return await fetch_authority(
                client,
                source,
                tenant=tenant_a,
                company=company,
                actor=user,
                permissions=required,
            )

        proof = await fetch()
        assert proof.read_allowed and proof.permissions == required
        with tenant_scope(tenant_a):
            policy = build_field_policy(
                tenant_id=tenant_a,
                entity_type=entity_type,
                field_key="name",
                subject_type="user",
                subject_id=user,
                scope_type="company",
                scope_id=company,
                access="read",
                effect="deny",
            )
            session.add(policy)
            await session.commit()
        with pytest.raises(PermissionDeniedError):
            await fetch()
        if entity_type.startswith("catalog."):
            financial = await fetch_authority(
                client,
                source,
                tenant=tenant_a,
                company=company,
                actor=user,
                permissions=frozenset({"report.read"}),
            )
            assert financial.read_allowed
        with tenant_scope(tenant_a):
            policy.is_active = False
            await session.delete(permission)
            await session.commit()
        with pytest.raises(PermissionDeniedError):
            await fetch()


async def test_report_authority_service_scope_and_input_bounds(
    app, client, session, tenant_a, tenant_b
):
    company, foreign, user, source, _permission = await configure(app, session, tenant_a, tenant_b)
    path = f"/internal/v1/report-authority/{tenant_a}/{company}"
    body = canonical_json(
        {"request_id": str(uuid.uuid4()), "user_id": str(user), "permissions": ["report.read"]}
    )
    assert (await client.post(path, content=body)).status_code == 401

    async def request(target, raw):
        framed = service_request_bytes(method="POST", path=target, query="", body=raw)
        headers = request_headers(
            requester="reports",
            owner="identity",
            key_id=source.key_id,
            secret=source.secret.get_secret_value().encode(),
            framed=framed,
        )
        return await client.post(target, content=raw, headers=headers)

    assert (await request(path, body)).status_code == 200
    assert (
        await request(f"/internal/v1/report-authority/{tenant_b}/{foreign}", body)
    ).status_code == 401
    assert (await request(path, b"{}")).status_code == 422
    assert (await request(path, b"x" * 4097)).status_code == 422
    forbidden = canonical_json(
        {"request_id": str(uuid.uuid4()), "user_id": str(user), "permissions": ["unit.manage"]}
    )
    assert (await request(path, forbidden)).status_code == 422
    with tenant_scope(tenant_a):
        tenant = await session.get(Tenant, tenant_a)
        tenant.status = "suspended"
        await session.commit()
    assert (await request(path, body)).status_code == 403


async def test_reorder_worker_proof_requires_current_company_policy_permission(
    app, session, tenant_a, tenant_b
):
    company, _, user, source, permission = await configure(app, session, tenant_a, tenant_b)
    required = frozenset({"report.read", "item_warehouse_policy.read"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:

        async def fetch():
            return await fetch_authority(
                client,
                source,
                tenant=tenant_a,
                company=company,
                actor=user,
                permissions=required,
            )

        with pytest.raises((PermissionDeniedError, httpx.HTTPStatusError)):
            await fetch()
        with tenant_scope(tenant_a):
            policy_permission = build_role_permission(
                tenant_id=tenant_a,
                role_id=permission.role_id,
                permission_key="item_warehouse_policy.read",
            )
            session.add(policy_permission)
            await session.commit()
        proof = await fetch()
        assert proof.read_allowed and proof.permissions == required
        with tenant_scope(tenant_a):
            await session.delete(policy_permission)
            await session.commit()
        with pytest.raises((PermissionDeniedError, httpx.HTTPStatusError)):
            await fetch()
