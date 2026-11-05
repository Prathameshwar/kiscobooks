from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7

from identity.models import Company, PostingReservation
from identity.services.posting import configuration, digest, guard_disable, reserve, terminate
from tests.factories import build_company_feature, build_user, seed_two_companies


async def test_posting_validates_actor_features_prerequisites_and_locks_first_use(
    session, tenant_a, tenant_b
):
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.flush()

        async def attempt(features=(), actor=None):
            return await reserve(
                session,
                company,
                operation_id=uuid7(),
                actor_user_id=actor or user.id,
                expected_hash=digest(await configuration(session, company)),
                features=list(features),
            )

        company.status = "inactive"
        with pytest.raises(ConflictError, match="not active"):
            await attempt()
        company.status = "active"
        with pytest.raises(ValidationFailedError, match="actor"):
            await attempt(actor=uuid.uuid4())
        user.status = "suspended"
        with pytest.raises(ValidationFailedError, match="actor"):
            await attempt()
        user.status = "active"
        with pytest.raises(ValidationFailedError, match="unavailable feature"):
            await attempt(["not_a_feature"])
        with pytest.raises(ValidationFailedError, match="unavailable feature"):
            await attempt(["expiry_tracking"])
        expiry = build_company_feature(
            tenant_id=tenant_a, company_id=company_id, feature_key="expiry_tracking"
        )
        session.add(expiry)
        await session.flush()
        with pytest.raises(ValidationFailedError, match="prerequisites"):
            await attempt(["expiry_tracking"])
        inventory = build_company_feature(tenant_id=tenant_a, company_id=company_id)
        batch = build_company_feature(
            tenant_id=tenant_a, company_id=company_id, feature_key="batch_tracking"
        )
        budgets = build_company_feature(
            tenant_id=tenant_a, company_id=company_id, feature_key="budgets"
        )
        session.add_all([inventory, batch, budgets])
        await session.flush()
        row = await attempt(["expiry_tracking", "budgets"])
        assert row.features == ["batch_tracking", "budgets", "expiry_tracking", "inventory"]
        with pytest.raises(ConflictError, match="frozen"):
            await guard_disable(session, company_id, "inventory")
        await guard_disable(session, company_id, "multi_currency")
        with pytest.raises(ValidationFailedError, match="invalid posting outcome"):
            await terminate(
                session, company, row, outcome="unknown", reference="result", posted_at=None
            )
        earlier = utcnow() - dt.timedelta(days=1)
        company.first_posted_at = earlier
        inventory.locked_at = earlier
        now = utcnow()
        await terminate(
            session, company, row, outcome="confirmed", reference="posted", posted_at=now
        )
        assert company.first_posted_at == earlier and inventory.locked_at == earlier
        assert batch.locked_at == expiry.locked_at == now
        assert budgets.locked_at is None
        await terminate(
            session, company, row, outcome="confirmed", reference="posted", posted_at=now
        )
        with pytest.raises(ConflictError):
            await terminate(
                session, company, row, outcome="confirmed", reference="posted", posted_at=earlier
            )
        await guard_disable(session, company_id, "inventory")


async def test_pending_reservations_are_bounded_and_require_reconciliation(
    session, tenant_a, tenant_b
):
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.flush()
        state_hash = digest(await configuration(session, company))
        for _ in range(101):
            session.add(
                PostingReservation(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company_id,
                    operation_id=uuid7(),
                    actor_user_id=user.id,
                    request_hash="a" * 64,
                    configuration_hash=state_hash,
                    features=[],
                    status="pending",
                )
            )
        await session.flush()
        with pytest.raises(ConflictError, match="reconcile pending"):
            await reserve(
                session,
                company,
                operation_id=uuid7(),
                actor_user_id=user.id,
                expected_hash=state_hash,
                features=[],
            )
        with pytest.raises(ConflictError, match="frozen"):
            await guard_disable(session, company_id, "inventory")
