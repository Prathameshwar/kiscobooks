"""Purchase tax setup remains readable when pending input GST accounts exist."""

import httpx

from tests.test_fiscal_api import BASE, finance_headers
from tests.test_high_priority_defaults import initialize, registration


async def test_pending_input_profiles_are_in_native_tax_profile_list(
    client: httpx.AsyncClient,
) -> None:
    reg = registration()
    await initialize(client, registrations=[reg], features={"reverse_charge"})
    result = await client.get(
        BASE + "/account-tax-profiles?limit=200",
        headers=finance_headers(registrations=[reg], features={"reverse_charge"}),
    )
    assert result.status_code == 200, result.text
    purposes = {row["purpose"] for row in result.json()["items"]}
    assert {"INPUT_PENDING", "INPUT_RECOVERABLE", "RCM_PAYABLE"} <= purposes
