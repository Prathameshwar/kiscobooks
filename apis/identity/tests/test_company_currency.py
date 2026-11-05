"""Foreign transaction currencies are explicit company settings."""

import base64
import secrets

from billing_platform.db import unfiltered
from billing_platform.ids import uuid7
from pydantic import SecretStr


async def test_company_currency_allowance_is_feature_gated_scoped_and_versioned(
    app, client, session, tenant_a, tenant_b
) -> None:
    from tests.api_support import actor_headers, grant
    from tests.factories import build_currency, seed_two_companies

    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    with unfiltered():
        session.add(
            build_currency(
                "USD",
                numeric_code="840",
                name="US Dollar",
                symbol="$",
                major_unit_name="Dollars",
                minor_unit_name="Cents",
                minor_unit_name_plural="Cents",
            )
        )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["company.update", "company.read"], scope_type="company", scope_id=company_a)
        ],
    )
    path = f"/v1/companies/{company_a}/transaction-currencies/USD"
    bank_path = f"/v1/companies/{company_a}/bank-accounts"
    bank_body = {
        "label": "Foreign account",
        "account_name": "Owner",
        "bank_name": "Bank",
        "currency_code": "USD",
        "account_number": "12345678",
    }
    assert (await client.post(bank_path, headers=headers, json=bank_body)).status_code == 409
    before = await client.put(path, headers=headers, json={"is_active": True})
    assert before.status_code == 409, before.text
    enabled = await client.post(
        f"/v1/companies/{company_a}/features/multi_currency/enable", headers=headers
    )
    assert enabled.status_code == 200, enabled.text
    created = await client.put(path, headers=headers, json={"is_active": True})
    assert created.status_code == 200, created.text
    assert created.json()["row_version"] == 1
    listed = await client.get(f"/v1/companies/{company_a}/transaction-currencies", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["base_currency"] == "INR"
    assert [row["currency_code"] for row in listed.json()["allowances"]] == ["USD"]
    app.state.settings.bank_active_key_id = "test"
    app.state.settings.bank_encryption_keys = {
        "test": SecretStr(base64.b64encode(secrets.token_bytes(32)).decode())
    }
    bank = await client.post(bank_path, headers=headers, json=bank_body)
    assert bank.status_code == 201, bank.text
    stale = await client.put(
        path, headers=headers, json={"is_active": False, "expected_version": 2}
    )
    assert stale.status_code == 409, stale.text
    retired = await client.put(
        path, headers=headers, json={"is_active": False, "expected_version": 1}
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["row_version"] == 2 and not retired.json()["is_active"]
    assert (await client.post(bank_path, headers=headers, json=bank_body)).status_code == 409
    denied = await client.put(
        f"/v1/companies/{company_b}/transaction-currencies/USD",
        headers=headers,
        json={"is_active": True},
    )
    assert denied.status_code == 403, denied.text
