"""Native invoice/credit effects cross the signed feed into reconciled report grains."""

import datetime as dt
import secrets
from decimal import Decimal
from pathlib import Path

import pytest
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.contract import Fact, FactPage, Manifest, digest
from reporting_contract.transport import Owner, request

from tests.conftest import COMPANY, TENANT
from tests.invoice_helpers import posted_purchase
from tests.test_fiscal_api import BASE
from tests.test_invoice_credit_api import action, balance, post_action
from tests.test_voucher_tax import th


async def snapshot(client, app):
    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    key, secret = "reports.invoice.test", SecretStr(secrets.token_hex(32))
    app.state.settings.report_credentials[key] = SnapshotCredential(secret=secret, scopes=(scope,))
    owner = Owner(origin="http://127.0.0.1", key_id=key, secret=secret, scopes=(scope,))
    path = f"/internal/v1/reporting/{TENANT}/{COMPANY}/snapshots/{uuid7()}"
    manifest = Manifest.model_validate(await request(client, owner, "POST", path))
    rows, cursor = [], None
    while True:
        page = FactPage.model_validate(
            await request(
                client,
                owner,
                "GET",
                path + "/facts",
                {
                    "limit": "20",
                    **({"after": str(cursor)} if cursor else {}),
                },
            )
        )
        rows.extend(page.items)
        cursor = page.next_after
        if cursor is None:
            break
    return manifest, rows


@pytest.mark.parametrize("reverse", [False, True])
async def test_native_invoice_tax_credit_registers_and_frozen_gl_bridge(
    client, app, monkeypatch, reverse
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/src"))
    from reports.domain.reconcile import reconcile
    from reports.domain.statements import calculate
    from reports.schemas.requests import RunRequest

    data = await posted_purchase(client, app, reverse=reverse, components=True)
    frozen, facts = await snapshot(client, app)
    reconcile(facts, frozen.control)
    query = RunRequest(
        code="PURCHASE_REGISTER",
        generation_id=uuid7(),
        date_from="2026-04-01",
        date_to="2026-04-30",
    )

    def report(code, rows=facts, **changes):
        return calculate(
            rows, query.model_copy(update={"code": code, **changes}), frozen.control.coverage_start
        )[0]

    purchases = report("PURCHASE_REGISTER")
    assert len(purchases) == 1 and purchases[0]["payable"] == (
        "1000.0000" if reverse else "1180.0000"
    )
    assert report("SALES_REGISTER") == []
    assert len(report("INVOICE_COMPONENT_REGISTER")) == 6
    taxes = report("INVOICE_TAX_REGISTER")
    assert len(taxes) == 1 and taxes[0]["tax_amount"] == "180.0000"
    assert "payable" not in taxes[0]
    gl = report("INVOICE_GL_BRIDGE")
    assert sum(Decimal(row["signed_debit"]) for row in gl) == 0
    bridge = report("TAX_GL_BRIDGE")
    assert len(bridge) == (2 if reverse else 1)
    assert {row["tax_purpose"] for row in bridge} == (
        {"PENDING_IGST", "RCM_IGST"} if reverse else {"PENDING_IGST"}
    )
    assert all(row["component_id"] == str(data["component"].id) for row in bridge)
    assert report("INVOICE_SETTLEMENT_REGISTER") == []
    positions = report("INVOICE_CREDIT_REGISTER")
    assert len(positions) == 1 and positions[0]["pending"] == "180.0000"
    assert report("TRIAL_BALANCE")[-1]["difference"] == "0.0000"
    for code in ("BALANCE_SHEET", "PROFIT_LOSS", "INCOME_EXPENSE"):
        assert report(code)
    if reverse:
        assert report("INVOICE_TAX_REGISTER", date_basis="TAX_POINT") == []
        june = report(
            "INVOICE_TAX_REGISTER",
            date_basis="TAX_POINT",
            date_from=dt.date(2026, 6, 1),
            date_to=dt.date(2026, 6, 30),
        )
        assert len(june) == 1 and june[0]["posting_date"] == "2026-04-02"
        return

    verified = await client.post(
        BASE + "/invoice-credit-actions", json=action(data["component"]), headers=th()
    )
    assert verified.status_code == 201, verified.text
    current = await balance(client, data["component"])
    claimed = await client.post(
        BASE + "/invoice-credit-actions",
        json=action(
            data["component"],
            kind="CLAIM",
            amount="100",
            expected_event_id=current["latest_event_id"],
        ),
        headers=th(),
    )
    assert claimed.status_code == 201, claimed.text
    assert (await post_action(client, claimed.json())).status_code == 200
    latest, updated = await snapshot(client, app)
    reconcile(updated, latest.control)
    current_positions = report("INVOICE_CREDIT_REGISTER", updated)
    position = next(row for row in current_positions if row["row_kind"] == "CREDIT_POSITION")
    assert position["claimed"] == "100.0000" and position["eligible_unclaimed"] == "80.0000"
    assert len(report("TAX_GL_BRIDGE", updated)) == 3
    assert report("INVOICE_CREDIT_REGISTER") == positions
    assert report("INVOICE_CREDIT_REGISTER", updated, date_to=dt.date(2026, 4, 2)) == [
        positions[0] | {"as_of": "2026-04-02"}
    ]
    assert report("TRIAL_BALANCE", updated)[-1]["difference"] == "0.0000"
    assert report("PURCHASE_REGISTER", updated) == purchases

    # A valid wire checksum must not hide an inconsistent native allocation.
    broken = []
    changed = False
    for fact in updated:
        if fact.entity == "invoice_allocation_fact" and not changed:
            changed = True
            value = {
                "entity": fact.entity,
                "source_id": str(fact.source_id),
                "data": fact.data | {"amount": "-9"},
            }
            fact = Fact.model_validate(value | {"content_hash": digest(value)})
        broken.append(fact)
    with pytest.raises(ConflictError, match="reconcile|conserve"):
        reconcile(broken, latest.control)

    wrong_tax_purpose = []
    changed = False
    for fact in updated:
        if fact.entity == "invoice_posting_line" and fact.data["tax_purpose"] and not changed:
            changed = True
            value = {
                "entity": fact.entity,
                "source_id": str(fact.source_id),
                "data": fact.data | {"tax_purpose": "OUTPUT_IGST"},
            }
            fact = Fact.model_validate(value | {"content_hash": digest(value)})
        wrong_tax_purpose.append(fact)
    assert changed
    with pytest.raises(ConflictError, match="tax GL purposes"):
        reconcile(wrong_tax_purpose, latest.control)
