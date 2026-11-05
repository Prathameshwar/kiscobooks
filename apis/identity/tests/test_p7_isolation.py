"""Two-tenant isolation for every Phase 7 table (CLAUDE.md §7).

Plus the two structural, security-relevant assertions the phase exit calls for
(docs/identity-db-plan.md §4): ``user_api_token`` has no column that could hold a raw
token, and the redaction-target columns exist on ``company_bank_account``.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    CompanyBankAccount,
    CompanyContact,
    CompanyDocument,
    UserApiToken,
    UserNotificationPreference,
)
from tests.factories import (
    build_company_bank_account,
    build_company_contact,
    build_company_document,
    build_user,
    build_user_api_token,
    build_user_notification_preference,
    seed_two_companies,
)

# No module-level asyncio mark: this file mixes async isolation tests (covered by
# asyncio_mode="auto") with two synchronous schema-shape checks.


async def _count(session: AsyncSession, model: Any, tenant_id: uuid.UUID) -> int:
    with tenant_scope(tenant_id):
        return int(await session.scalar(select(func.count(model.id))) or 0)


async def test_company_child_table_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    with unfiltered():
        session.add(build_company_contact(tenant_id=tenant_a, company_id=company_a))
        session.add(build_company_contact(tenant_id=tenant_b, company_id=company_b))
        session.add(build_company_bank_account(tenant_id=tenant_a, company_id=company_a))
        session.add(build_company_bank_account(tenant_id=tenant_b, company_id=company_b))
        session.add(build_company_document(tenant_id=tenant_a, company_id=company_a))
        session.add(build_company_document(tenant_id=tenant_b, company_id=company_b))
        await session.commit()
    for model in (CompanyContact, CompanyBankAccount, CompanyDocument):
        assert await _count(session, model, tenant_a) == 1
        assert await _count(session, model, tenant_b) == 1


async def test_user_child_table_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    ua, ub = uuid7(), uuid7()
    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, user_id=ua, email="a@alpha.example"))
        session.add(build_user(tenant_id=tenant_b, user_id=ub, email="b@beta.example"))
        await session.flush()
        session.add(build_user_notification_preference(tenant_id=tenant_a, user_id=ua))
        session.add(build_user_notification_preference(tenant_id=tenant_b, user_id=ub))
        session.add(build_user_api_token(tenant_id=tenant_a, user_id=ua, token_hash="a" * 64))
        session.add(build_user_api_token(tenant_id=tenant_b, user_id=ub, token_hash="b" * 64))
        await session.commit()
    for model in (UserNotificationPreference, UserApiToken):
        assert await _count(session, model, tenant_a) == 1
        assert await _count(session, model, tenant_b) == 1


def test_api_token_stores_no_raw_token() -> None:
    """The table can only hold a hash and a prefix — there is nowhere to put a raw
    token, which is the structural guarantee behind 'shown once, never stored'."""
    columns = set(table_of(UserApiToken).c.keys())
    assert "token_hash" in columns
    assert "token_prefix" in columns
    assert "token" not in columns and "raw_token" not in columns and "secret" not in columns


def test_bank_account_has_redaction_target_columns() -> None:
    columns = set(table_of(CompanyBankAccount).c.keys())
    assert {"account_number", "iban"} <= columns
