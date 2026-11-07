"""Physical registration freezes capabilities without claiming a money posting."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import select

from identity.models import Company, CompanyFeature
from identity.services import posting
from tests.factories import build_company_feature
from tests.test_stock_posting_client import fixture


@pytest.mark.parametrize("outcome", ["confirmed", "aborted"])
async def test_tracking_registration_feature_locks_are_distinct_from_posting(
    app,
    session,
    tenant_a,
    tenant_b,
    outcome,
):
    company_id, user_id, _, _, _ = await fixture(app, session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        for key in ("batch_tracking", "expiry_tracking"):
            session.add(
                build_company_feature(tenant_id=tenant_a, company_id=company_id, feature_key=key)
            )
        await session.commit()
        company = await session.get(Company, company_id)
        row = await posting.reserve(
            session,
            company,
            operation_id=uuid7(),
            actor_user_id=user_id,
            expected_hash=posting.digest(await posting.configuration(session, company)),
            features=["batch_tracking", "expiry_tracking"],
            owner_service="accounting-tracking",
        )
        with pytest.raises(ConflictError):
            await posting.guard_disable(session, company_id, "batch_tracking")
        await posting.terminate(
            session,
            company,
            row,
            outcome=outcome,
            reference="accounting-tracking:" + str(row.operation_id),
            posted_at=utcnow() if outcome == "confirmed" else None,
        )
        assert company.first_posted_at is None
        features = {
            f.feature_key: f
            for f in await session.scalars(
                select(CompanyFeature).where(
                    CompanyFeature.company_id == company_id,
                )
            )
        }
        assert features["inventory"].locked_at is None
        assert (features["batch_tracking"].locked_at is not None) == (outcome == "confirmed")
        assert (features["expiry_tracking"].locked_at is not None) == (outcome == "confirmed")
