"""Opening capture authority is independent of native journal posting authority."""

import pytest
from billing_platform.company_context import verify_company_context
from starlette.requests import Request

from accounting.api.auth import Access, decode_actor_context
from accounting.api.financial_opening import field_set
from tests.conftest import COMPANY, SECRET
from tests.test_field_policy import policy
from tests.test_ledger_api import LEDGER_PERMISSIONS, ledger_headers


@pytest.mark.parametrize("deny_reference", [False, True])
async def test_capture_permissions_use_opening_authority_and_native_field_denies(deny_reference):
    headers = ledger_headers(
        permissions=LEDGER_PERMISSIONS - {"ledger.post_journal"},
        policies=[policy("reference", access="write", entity="accounting.open_item")]
        if deny_reference
        else [],
    )
    actor = decode_actor_context(
        headers["X-Actor-Context"], headers["X-Actor-Signature"], SECRET.encode()
    )
    context = verify_company_context(
        headers["X-Company-Context"], headers["X-Company-Signature"], SECRET.encode()
    )
    result = await field_set(
        COMPANY, Request({"type": "http", "query_string": b""}), Access(actor, context)
    )
    permissions = result["capture_permissions"]
    assert permissions["journal_lines"]["amount"]
    assert permissions["open_items"]["amount"]
    assert permissions["open_items"]["reference"] is not deny_reference


async def test_controller_can_capture_and_prepare_without_journal_post_authority(client, app):
    from tests.test_financial_opening_api import ROOT, body_for
    from tests.test_fiscal_api import BASE

    body = await body_for(client, app)
    permissions = LEDGER_PERMISSIONS - {"ledger.post_journal"}
    response = await client.get(
        ROOT + "/field-set", headers=ledger_headers(permissions=permissions)
    )
    assert response.status_code == 200, response.text
    assert response.json()["capture_permissions"]["journal_lines"]["amount"]
    created = await client.post(ROOT, json=body, headers=ledger_headers(permissions=permissions))
    assert created.status_code == 201, created.text
    row = created.json()
    prepared = await client.post(
        ROOT + f"/{row['id']}/prepare-drafts",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Controller reviewed capture only",
        },
        headers=ledger_headers(permissions=permissions),
    )
    assert prepared.status_code == 200, prepared.text
    journal = await client.get(
        BASE + "/journals/" + prepared.json()["journal_ids"][0], headers=ledger_headers()
    )
    posted = await client.post(
        BASE + "/journals/" + journal.json()["id"] + "/post",
        json={"expected_version": journal.json()["row_version"]},
        headers=ledger_headers(permissions=permissions),
    )
    assert posted.status_code == 403, posted.text
