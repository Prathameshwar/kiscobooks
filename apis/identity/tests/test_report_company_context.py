import uuid

from billing_platform.db import tenant_scope

from identity.api.auth import Actor
from identity.services.accounting_context import company_context
from identity.services.display import resolve_display
from tests.factories import build_company, build_field_policy, build_user, seed_two_companies


async def test_report_context_includes_report_and_accounting_read_denies(
    session, tenant_a, tenant_b
):
    company, _foreign = await seed_two_companies(session, tenant_a, tenant_b)
    reader = uuid.uuid4()
    with tenant_scope(tenant_a):
        session.add_all(
            [
                build_field_policy(
                    tenant_id=tenant_a,
                    subject_type="user",
                    subject_id=reader,
                    entity_type=entity,
                    field_key="name",
                    access="read",
                    effect="deny",
                )
                for entity in ("reports.report", "accounting.account")
            ]
        )
        await session.flush()
        context = await company_context(
            session, Actor(tenant_a, reader), company, entity_prefix="reports."
        )
        assert context.policy_namespaces == {"accounting", "reports"}
        assert context.report_display is not None
        assert context.report_display.base_currency == context.base_currency
        assert context.report_display.amount_precision == context.finance.amount_precision
        ordinary = await company_context(session, Actor(tenant_a, reader), company)
        assert ordinary.report_display is None
        assert {row["entity_type"] for row in context.policies} == {
            "reports.report",
            "accounting.account",
        }


def test_browser_and_report_display_share_the_owner_override_policy():
    tenant = uuid.uuid4()
    company = build_company(tenant_id=tenant, quantity_precision=3)
    user = build_user(
        tenant_id=tenant, date_format="yyyy-MM-dd", digit_grouping="western", locale="de-DE"
    )
    resolved = resolve_display(company, user)
    assert resolved["quantity_precision"] == 3
    assert resolved["date_format"] == "yyyy-MM-dd"
    assert resolved["digit_grouping"] == "western"
    assert resolved["locale"] == "de-DE"
    assert resolved["rounding_mode"] == company.rounding_mode
