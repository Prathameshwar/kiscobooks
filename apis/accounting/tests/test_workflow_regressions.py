"""Template identity, maximum import sizes and disposable verifier isolation."""

import os
import uuid
from typing import Any

import httpx
import pytest
from alembic import command as alembic_command
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.engine import make_url

from accounting.models import masters as m
from accounting.schemas.setup import TemplateSelection
from accounting.tasks.templates import content
from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import BASE, post
from tools import verify_mysql


def registrations() -> list[uuid.UUID]:
    # Two legitimate UUIDv7 identifiers issued within one millisecond.
    return [
        uuid.UUID("01900000-0000-7000-8000-000000000001"),
        uuid.UUID("01900000-0000-7000-8000-000000000002"),
    ]


async def test_templates_separate_registrations_with_the_same_uuid_timestamp(
    client: httpx.AsyncClient,
) -> None:
    first, second = registrations()
    context = [
        {
            "id": str(value),
            "tax_system": "gst_in",
            "regime": "regular",
            "jurisdiction_code": "IN-MH",
            "valid_from": "2020-01-01",
            "valid_to": None,
        }
        for value in (first, second)
    ]
    await post(
        client, "/accounting-setup/initialize", {}, h=headers(registrations=context), status=200
    )
    for value in (first, second):
        result = await post(
            client,
            "/accounting-setup/install",
            {
                "gst_registration_id": str(value),
                "local_component": "UTGST",
            },
            h=headers(registrations=context),
            status=200,
        )
        assert result["accounts_created"] >= 6, result
    profiles = (
        await client.get(BASE + "/account-tax-profiles", headers=headers(registrations=context))
    ).json()["items"]
    assert len(profiles) == 12
    details = [
        (
            await client.get(
                BASE + f'/account-tax-profiles/{row["id"]}', headers=headers(registrations=context)
            )
        ).json()
        for row in profiles
    ]
    assert {row["company_registration_id"] for row in details} == {str(first), str(second)}


async def test_maximum_import_batch_applies_and_replays_atomically(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await post(client, "/accounting-setup/initialize", {}, status=200)
    # The generic import no longer creates parties (a party arrives with its role and ledger
    # account), so the 200-row bound is exercised with another creatable master.
    body: dict[str, Any] = {
        "items": [
            {
                "key": f"row-{index:046d}",
                "resource": "payment-terms",
                "values": {"code": f"P{index}", "name": "Import"},
            }
            for index in range(200)
        ]
    }
    preview = await post(client, "/imports/preview", body, status=200)
    assert preview["valid"], preview
    apply = body | {"preview_token": preview["preview_token"]}
    h = headers()
    # httpx normally re-raises application errors; keep this test at the HTTP contract.
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://accounting.test",
    ) as http:
        result = await http.post(BASE + "/imports/apply", json=apply, headers=h)
        assert result.status_code == 200, result.text
        assert len(result.json()["records"]) == 200
        replay = await http.post(BASE + "/imports/apply", json=apply, headers=h)
        assert replay.json() == result.json()
    saved = await client.get(BASE + "/payment-terms?limit=200", headers=headers())
    assert len(saved.json()["items"]) == 200


def test_native_verifier_overrides_and_restores_application_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = "mysql+asyncmy://root@127.0.0.1:3306/accounting"
    monkeypatch.setenv("ACCOUNTING_DATABASE_URL", application)
    selected = []

    async def schema(server: str, name: str, create: bool) -> None:
        assert name.startswith("accounting_test_")

    async def verify(url: str) -> None:
        assert (make_url(url).database or "").startswith("accounting_test_")

    def migration(config: Any, target: str) -> None:
        selected.append(os.environ["ACCOUNTING_DATABASE_URL"])

    monkeypatch.setattr(verify_mysql, "schema", schema)
    monkeypatch.setattr(verify_mysql, "verify", verify)
    monkeypatch.setattr(alembic_command, "upgrade", migration)
    monkeypatch.setattr(alembic_command, "downgrade", migration)
    # pytest-asyncio has no event loop for this synchronous test.
    verify_mysql.main()
    assert len(selected) == 4  # initial upgrade, then fresh-schema upgrade/downgrade/upgrade
    assert all((make_url(url).database or "").startswith("accounting_test_") for url in selected)
    assert os.environ["ACCOUNTING_DATABASE_URL"] == application


async def test_v1_reinstall_preserves_used_accounts_and_repairs_collided_bindings(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    first, second = registrations()
    context = [
        {
            "id": str(value),
            "tax_system": "gst_in",
            "regime": "regular",
            "jurisdiction_code": "IN-MH",
            "valid_from": "2020-01-01",
            "valid_to": None,
        }
        for value in (first, second)
    ]
    await post(
        client, "/accounting-setup/initialize", {}, h=headers(registrations=context), status=200
    )
    selection = {"gst_registration_id": str(first), "local_component": "SGST"}
    installed = await post(
        client, "/accounting-setup/install", selection, h=headers(registrations=context), status=200
    )
    originals = {}
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            # Reproduce the persisted v1 layout, including the second installation's
            # erroneous references to the first registration's tax accounts.
            old = await db.get(
                m.AccountTemplateInstallation, uuid.UUID(installed["installation_id"])
            )
            old.template_version = "1"
            for row in await db.scalars(select(m.Account).where(m.Account.kind == "TAX")):
                direction, component, _ = row.code.split("_", 2)
                row.code = f"{direction}_{component}_{first.hex[:12].upper()}"
                row.system_key = "account." + row.code
                row.used_at = utcnow()
                originals[row.id] = row.code
            second_key, _, _, digest = content(
                TemplateSelection(gst_registration_id=second, local_component="SGST")
            )
            collided = m.AccountTemplateInstallation(
                id=uuid7(),
                tenant_id=TENANT,
                company_id=COMPANY,
                template_key=second_key,
                template_version="1",
                content_hash=digest,
                row_version=1,
            )
            db.add(collided)
            await db.flush()
            for identifier, code in originals.items():
                db.add(
                    m.AccountTemplateBinding(
                        id=uuid7(),
                        tenant_id=TENANT,
                        company_id=COMPANY,
                        installation_id=collided.id,
                        object_type="ACCOUNT",
                        object_id=identifier,
                        system_key="account." + code,
                        row_version=1,
                    )
                )
    preview = await post(
        client, "/accounting-setup/preview", selection, h=headers(registrations=context), status=200
    )
    assert preview["changes"] == [] and preview["conflicts"] == [], preview
    retained = await post(
        client, "/accounting-setup/install", selection, h=headers(registrations=context), status=200
    )
    assert retained["accounts_created"] == 0
    repaired = await post(
        client,
        "/accounting-setup/install",
        selection | {"gst_registration_id": str(second)},
        h=headers(registrations=context),
        status=200,
    )
    assert repaired["accounts_created"] == 6
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for identifier, code in originals.items():
                row = await db.get(m.Account, identifier)
                assert row.code == code and row.used_at is not None
            bindings = list(
                await db.scalars(
                    select(m.AccountTemplateBinding).where(
                        m.AccountTemplateBinding.installation_id
                        == uuid.UUID(repaired["installation_id"]),
                        m.AccountTemplateBinding.object_type == "ACCOUNT",
                    )
                )
            )
            profiles = list(
                await db.scalars(
                    select(m.AccountTaxProfile).where(
                        m.AccountTaxProfile.account_id.in_([row.object_id for row in bindings]),
                    )
                )
            )
            assert len(profiles) == 6
            assert {row.company_registration_id for row in profiles} == {second}
