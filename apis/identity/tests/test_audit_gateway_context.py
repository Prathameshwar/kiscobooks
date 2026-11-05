import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.api.auth import Actor
from identity.services.audit_context import historical_read_policies
from tests.factories import (
    build_field_policy,
    build_role,
    build_role_assignment,
    build_user,
    seed_two_tenants,
)


@pytest.mark.parametrize("entity", ["accounting.party", "catalog.item", "vouchers.voucher"])
async def test_audit_policies_keep_scoped_roles_and_exclude_revoked_assignments(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    entity: str,
) -> None:
    company = uuid.uuid4()
    async with factory() as db:
        await seed_two_tenants(db, tenant_a, tenant_b)
        with tenant_scope(tenant_a):
            user, role = build_user(tenant_id=tenant_a), build_role(tenant_id=tenant_a)
            db.add_all([user, role])
            await db.flush()
            assignment = build_role_assignment(
                tenant_id=tenant_a,
                subject_id=user.id,
                role_id=role.id,
                scope_type="company",
                scope_id=company,
                valid_from=utcnow().date() - dt.timedelta(days=1),
            )
            db.add_all(
                [
                    assignment,
                    build_field_policy(
                        tenant_id=tenant_a,
                        subject_id=role.id,
                        entity_type=entity,
                        field_key="country_code",
                        access="read",
                    ),
                ]
            )
            await db.flush()
            current = Actor(tenant_id=tenant_a, user_id=user.id)
            policies = await historical_read_policies(db, current)
            assert len(policies) == 1
            assert policies[0]["subject_scope_id"] == str(company)
            assert policies[0]["subject_scope_type"] == "company"
            assignment.is_active = False
            await db.flush()
            assert await historical_read_policies(db, current) == []


async def test_audit_scope_requires_company_selection_and_step_up(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    import pytest
    from fastapi import FastAPI
    from starlette.requests import Request

    from identity.services.audit_context import historical_read_scope
    from identity.services.step_up import StepUpRequiredError
    from tests.factories import build_company

    async with factory() as db:
        await seed_two_tenants(db, tenant_a, tenant_b)
        with tenant_scope(tenant_a):
            company = build_company(tenant_id=tenant_a, requires_step_up=True)
            db.add(company)
            await db.flush()
            current = Actor(tenant_id=tenant_a, user_id=uuid.uuid4())

            def request(uri: str) -> Request:
                return Request(
                    {
                        "type": "http",
                        "app": FastAPI(),
                        "headers": [
                            (b"x-original-uri", uri.encode()),
                        ],
                    }
                )

            with pytest.raises(StepUpRequiredError):
                await historical_read_scope(db, request("/audit/v1/audit-events"), current)
            with pytest.raises(StepUpRequiredError):
                await historical_read_scope(
                    db, request("/audit/v1/audit-events?company_id=" + str(company.id)), current
                )
            company.requires_step_up = False
            await db.flush()
            assert await historical_read_scope(
                db, request("/audit/v1/audit-events?company_id=" + str(company.id)), current
            ) == {
                "company_id": str(company.id),
            }
