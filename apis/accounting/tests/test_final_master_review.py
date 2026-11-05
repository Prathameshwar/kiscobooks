"""Final review regressions for dependent profiles and validation-only reads."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.domain.rules import validate_tax_head
from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from tests.conftest import TENANT, headers
from tests.test_field_policy import policy
from tests.test_masters import BASE, activate, post, prepare
from tests.test_workflows import seeded_account


def test_tax_purpose_head_matrix() -> None:
    for purpose in ("INPUT_RECOVERABLE", "OUTPUT_PAYABLE", "RCM_PAYABLE", "DEPOSIT", "ADJUSTMENT"):
        for nature in ("ASSET", "LIABILITY"):
            expected = "ASSET" if purpose in {"INPUT_RECOVERABLE", "DEPOSIT"} else "LIABILITY"
            if purpose == "ADJUSTMENT" or nature == expected:
                validate_tax_head(purpose, nature)
            else:
                with pytest.raises(ValidationFailedError):
                    validate_tax_head(purpose, nature)


async def tax_account(client: httpx.AsyncClient, group: str) -> dict[str, Any]:
    account = await post(
        client,
        "/accounts",
        {
            "code": "PROFILED_TAX",
            "name": "Tax payable",
            "group_id": group,
            "kind": "TAX",
        },
    )
    await post(
        client,
        "/account-tax-profiles",
        {
            "account_id": account["id"],
            "scheme": "OTHER",
            "component": "OTHER",
            "duty_type": "TDS",
            "purpose": "OUTPUT_PAYABLE",
        },
    )
    return account


@pytest.mark.parametrize("kind", ["TAX", "BANK"])
async def test_profiled_draft_account_cannot_change_kind(
    client: httpx.AsyncClient, kind: str
) -> None:
    groups = await prepare(client)
    if kind == "TAX":
        account = await tax_account(client, groups["TAX_PAYABLE"])
    else:
        bank = uuid7()
        account = await post(
            client,
            "/accounts",
            {
                "code": "PROFILED_BANK",
                "name": "Bank",
                "group_id": groups["BANKS"],
                "kind": "BANK",
            },
        )
        await post(
            client,
            "/account-bank-profiles",
            {
                "account_id": account["id"],
                "company_bank_id": str(bank),
            },
            h=headers(bank_ids={bank}),
        )
    result = await client.patch(
        BASE + "/accounts/" + account["id"],
        json={"expected_version": 1, "kind": "GENERAL"},
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    saved = await client.get(BASE + "/accounts/" + account["id"], headers=headers())
    assert saved.json()["kind"] == kind and saved.json()["row_version"] == 1


async def test_draft_tax_account_edit_preserves_profile_purpose(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    account = await tax_account(client, groups["TAX_PAYABLE"])
    result = await client.patch(
        BASE + "/accounts/" + account["id"],
        json={"expected_version": 1, "group_id": groups["CURRENT_ASSETS"]},
        headers=headers(),
    )
    assert result.status_code == 422, result.text
    # A move to another group with the same head remains supported before activation.
    moved = await client.patch(
        BASE + "/accounts/" + account["id"],
        json={"expected_version": 1, "group_id": groups["CURRENT_LIABILITIES"]},
        headers=headers(),
    )
    assert moved.status_code == 200, moved.text
    assert (await activate(client, "/accounts", moved.json()))["status"] == "ACTIVE"


async def test_import_cannot_invalidate_an_existing_tax_profile(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    account = await tax_account(client, groups["TAX_PAYABLE"])
    preview = await post(
        client,
        "/imports/preview",
        {
            "items": [
                {
                    "key": "bad-move",
                    "resource": "accounts",
                    "action": "update",
                    "object_id": account["id"],
                    "values": {
                        "expected_version": 1,
                        "group_id": groups["CURRENT_ASSETS"],
                    },
                }
            ]
        },
        status=200,
    )
    assert preview["valid"] is False and preview["preview_token"] is None
    assert preview["issues"] == [{"key": "bad-move", "code": "invalid_record"}]
    saved = await client.get(BASE + "/accounts/" + account["id"], headers=headers())
    assert saved.json()["group_id"] == account["group_id"] and saved.json()["row_version"] == 1


async def test_activation_rechecks_legacy_tax_profile_head_and_rolls_back_audit(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    groups = await prepare(client)
    account = await tax_account(client, groups["TAX_PAYABLE"])
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.Account, uuid.UUID(account["id"]))
            assert row is not None
            row.group_id = uuid.UUID(groups["CURRENT_ASSETS"])
    result = await client.post(
        BASE + "/accounts/" + account["id"] + "/activate",
        json={"expected_version": 1},
        headers=headers(),
    )
    assert result.status_code == 422, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(m.Account, uuid.UUID(account["id"]))
            assert row is not None and row.status == "DRAFT" and row.row_version == 1
            history = list(
                await db.scalars(
                    select(MasterRevision).where(
                        MasterRevision.entity_type == "account",
                        MasterRevision.object_id == row.id,
                    )
                )
            )
            assert [revision.action for revision in history] == ["create"]


async def test_draft_validation_cannot_probe_read_denied_values(client: httpx.AsyncClient) -> None:
    await prepare(client)
    cash = await seeded_account(client, "account.CASH_MAIN")
    row = await post(
        client,
        "/posting-mapping-drafts",
        {
            "values": {
                "purpose": "CASH_RECEIPT",
                "account_id": cash["id"],
                "currency": "INR",
                "valid_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
            }
        },
    )
    path = BASE + "/posting-mapping-drafts/" + row["id"]
    for field in ("currency", "account_id", "valid_from"):
        rule = policy(
            field,
            entity="accounting.account_posting_mapping",
            condition={"field": "purpose", "cmp": "eq", "value": "CASH_RECEIPT"},
        )
        h = headers(policies=[rule])
        detail = await client.get(path, headers=h)
        assert detail.status_code == 200 and field not in detail.json()["values"]
        result = await client.post(path + "/validate", headers=h)
        assert result.status_code == 403, (field, result.text)
    assert (await client.post(path + "/validate", headers=headers())).status_code == 200
