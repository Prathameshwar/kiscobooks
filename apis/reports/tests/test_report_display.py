import uuid

from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from conftest import COMPANY, SECRET, TENANT, headers
from test_framework_execution import accepted

from reports.models.framework import ReportJob


async def test_display_is_required_consistent_and_does_not_change_retained_runs(
    app, client, prefix
):
    path, created = await accepted(app, client, prefix)
    original = headers()
    context = verify_company_context(
        original["X-Company-Context"], original["X-Company-Signature"], SECRET.encode()
    )
    for display in (None, context.report_display.model_copy(update={"amount_precision": 4})):
        modified = context.model_copy(update={"report_display": display})
        token, signature = sign_company_context(modified, SECRET.encode())
        signed = headers() | {"X-Company-Context": token, "X-Company-Signature": signature}
        rejected = await client.post(
            path,
            headers=signed,
            json={
                "code": "SOURCE_RECONCILIATION",
                "generation_id": created["generation_id"],
            },
        )
        assert rejected.status_code == 409
    updated = context.model_copy(
        update={
            "report_display": context.report_display.model_copy(
                update={"company_label": "Renamed company", "quantity_precision": 0}
            )
        }
    )
    token, signature = sign_company_context(updated, SECRET.encode())
    current = headers() | {"X-Company-Context": token, "X-Company-Signature": signature}
    assert (await client.get(path + "/" + created["id"], headers=current)).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.get(ReportJob, uuid.UUID(created["id"]))
            assert job.display["company_label"] == "Example Company"
            assert job.display["quantity_precision"] == 3


async def test_run_freezes_authoritative_company_display(app, client, prefix):
    path, created = await accepted(app, client, prefix)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.get(ReportJob, uuid.UUID(created["id"]))
            assert job.display["date_format"] == "dd MMM yyyy"
            assert job.display["quantity_precision"] == 3
            assert job.display["company_label"] == "Example Company"
            assert job.display["digit_grouping"] == "indian"
    assert (
        await client.get(path + "/" + created["id"], headers=headers(company=COMPANY))
    ).status_code == 200
