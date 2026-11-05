"""Printing must freeze owner-resolved display facts, not browser guesses."""

import uuid

from billing_platform.db import tenant_scope

from identity.api.auth import Actor
from identity.services.accounting_context import company_context
from tests.factories import seed_two_companies


async def test_voucher_context_carries_trusted_print_display(session, tenant_a, tenant_b):
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        context = await company_context(
            session, Actor(tenant_a, uuid.uuid4()), company, entity_prefix="vouchers."
        )
        assert context.report_display is not None
        assert context.report_display.base_currency == context.base_currency
        assert context.report_display.amount_precision == context.finance.amount_precision
        assert context.report_display.company_label
