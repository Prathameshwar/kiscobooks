"""Final review regressions: preview promises and installed master integrity."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models import masters as m
from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import BASE, post, prepare
from tests.test_workflow_regressions import registrations


@pytest.mark.parametrize(
    "fault", ["missing", "registration", "scheme", "component", "duty", "purpose"]
)
async def test_upgrade_rejects_mismatched_tax_profiles(
    client: httpx.AsyncClient,
    app: FastAPI,
    fault: str,
) -> None:
    first, second = registrations()
    context = [
        {
            "id": str(value),
            "tax_system": "gst_in",
            "regime": "regular",
            "valid_from": "2020-01-01",
            "valid_to": None,
        }
        for value in (first, second)
    ]
    await prepare(client, h=headers(registrations=context))
    body = {"gst_registration_id": str(first), "local_component": "SGST"}
    installed = await post(
        client, "/accounting-setup/install", body, h=headers(registrations=context), status=200
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            installation = await db.get(
                m.AccountTemplateInstallation, uuid.UUID(installed["installation_id"])
            )
            assert installation is not None
            installation.template_version = "2"
            profile = await db.scalar(
                select(m.AccountTaxProfile).where(
                    m.AccountTaxProfile.component == "CGST",
                    m.AccountTaxProfile.purpose == "OUTPUT_PAYABLE",
                )
            )
            assert profile is not None
            if fault == "missing":
                await db.delete(profile)
            else:
                field, value = {
                    "registration": ("company_registration_id", second),
                    "scheme": ("scheme", "OTHER"),
                    "component": ("component", "SGST"),
                    "duty": ("duty_type", "CESS"),
                    "purpose": ("purpose", "INPUT_RECOVERABLE"),
                }[fault]
                setattr(profile, field, value)
    preview = await post(
        client, "/accounting-setup/preview", body, h=headers(registrations=context), status=200
    )
    assert len(preview["conflicts"]) == 1 and "OUTPUT_CGST" in preview["conflicts"][0]
    result = await client.post(
        BASE + "/accounting-setup/install", json=body, headers=headers(registrations=context)
    )
    assert result.status_code == 409, result.text


@pytest.mark.parametrize("fault", ["kind", "status", "group", "code_collision"])
async def test_preview_and_upgrade_reject_incompatible_existing_accounts(
    client: httpx.AsyncClient, app: FastAPI, fault: str
) -> None:
    groups = await prepare(client)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            installation = await db.scalar(select(m.AccountTemplateInstallation))
            assert installation is not None
            installation.template_version = "2"
            account = await db.scalar(select(m.Account).where(m.Account.code == "CASH_MAIN"))
            assert account is not None
            if fault == "kind":
                account.kind = "GENERAL"
            elif fault == "status":
                account.status = "INACTIVE"
            elif fault == "group":
                account.group_id = uuid.UUID(groups["BANKS"])
            else:
                account.system_key = None
            identifier = account.id
    body = {"business_accounts": False}
    preview = await post(client, "/accounting-setup/preview", body, status=200)
    assert any("CASH_MAIN" in item for item in preview["conflicts"]), preview
    assert not any(item["code"] == "CASH_MAIN" for item in preview["changes"])
    result = await client.post(BASE + "/accounting-setup/install", json=body, headers=headers())
    assert result.status_code == 409, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert len(list(await db.scalars(select(m.AccountTemplateInstallation)))) == 1
            account = await db.get(m.Account, identifier)
            assert account is not None and account.row_version == 1
            setup = await db.scalar(
                select(m.AccountingSetup).where(m.AccountingSetup.company_id == COMPANY)
            )
            assert setup is not None and setup.template_version == "5"
