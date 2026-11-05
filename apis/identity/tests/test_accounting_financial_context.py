"""Identity supplies authoritative financial facts to Accounting."""

import datetime as dt
import uuid
from decimal import Decimal

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import Company
from identity.services.accounting_context import company_context
from identity.services.posting import configuration, digest
from tests.factories import seed_two_companies


async def test_financial_context_comes_from_company_configuration(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        company = await session.get(Company, company_id)
        assert company is not None
        company.books_begin_date = dt.date(2026, 4, 15)
        company.default_payment_terms_days = 45
        company.credit_limit_default = Decimal("75000.1250")
        company.cash_receipt_limit = Decimal("2000")
        company.backdated_posting_limit_days = 7
        await session.flush()
        context = await company_context(session, Actor(tenant_a, uuid7()), company_id)
        facts = context.finance
        assert facts is not None and facts.version == 1
        assert facts.company_active
        assert facts.books_begin_date == company.books_begin_date
        assert facts.fiscal_year_start_month == company.fiscal_year_start_month
        assert facts.fiscal_year_start_day == company.fiscal_year_start_day
        assert facts.default_payment_terms_days == 45
        assert facts.credit_limit_default == Decimal("75000.1250")
        assert type(facts.credit_limit_default) is Decimal
        assert facts.cash_receipt_limit == Decimal("2000")
        assert facts.backdated_posting_limit_days == 7
        assert facts.rounding_mode == company.rounding_mode
        assert facts.timezone == company.timezone
        assert facts.configuration_hash == digest(await configuration(session, company))
        company.status = "inactive"
        await session.flush()
        inactive = await company_context(session, Actor(tenant_a, uuid7()), company_id)
        assert inactive.finance is not None and not inactive.finance.company_active
