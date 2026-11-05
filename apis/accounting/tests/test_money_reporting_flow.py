"""Cross-service acceptance through native posting and signed owner facts."""

import datetime as dt
import secrets
import uuid
from decimal import Decimal
from pathlib import Path

from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.contract import FactPage, Manifest
from reporting_contract.transport import Owner, request
from voucher_execution.transport import ExecutionClient, command_digest

from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_money_profiles import revise
from tests.test_openings_sources import party_accounts
from tests.test_voucher_money import delegated, money_command


async def test_native_receipt_signed_export_reports_and_reversal_preserve_frozen_history(
    client, app, monkeypatch
):
    # Integration test only; applications exchange contracts and never share ORM reads.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/src"))
    from reports.domain.reconcile import reconcile
    from reports.domain.statements import calculate
    from reports.schemas.requests import RunRequest

    original, period, authority = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    original["lines"][1]["account_id"] = customer["id"]
    command = await money_command(app, original, period)
    money = command.source_payload["financial"]
    money["accounts"][1]["tracking"] = "ADVANCE"
    money["purpose"] = "ADVANCE"
    command = revise(command, kind="RECEIPT", financial=money)
    execution_key, execution_secret = "voucher.money.test", SecretStr(secrets.token_hex(32))
    app.state.settings.voucher_money_enabled = True
    app.state.settings.voucher_execution_credentials[execution_key] = SnapshotCredential(
        secret=execution_secret, scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),)
    )
    transport = ExecutionClient(
        client, "http://127.0.0.1", execution_key, execution_secret.get_secret_value().encode()
    )
    result = await transport.send(command)
    assert result.outcome == "COMMITTED"
    assert await transport.status(command) == result
    assert await transport.send(command) == result

    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    key, secret = "reports.money.test", SecretStr(secrets.token_hex(32))
    app.state.settings.report_credentials[key] = SnapshotCredential(secret=secret, scopes=(scope,))
    owner = Owner(origin="http://127.0.0.1", key_id=key, secret=secret, scopes=(scope,))
    base = f"/internal/v1/reporting/{TENANT}/{COMPANY}"

    async def snapshot():
        identity = uuid7()
        manifest = Manifest.model_validate(
            await request(client, owner, "POST", base + f"/snapshots/{identity}")
        )
        rows, cursor = [], None
        while True:
            params = {"limit": "20"} | ({"after": str(cursor)} if cursor else {})
            page = FactPage.model_validate(
                await request(client, owner, "GET", base + f"/snapshots/{identity}/facts", params)
            )
            rows.extend(page.items)
            cursor = page.next_after
            if cursor is None:
                break
        reconcile(rows, manifest.control)
        return manifest, rows

    frozen, facts = await snapshot()
    query = RunRequest(
        code="RECEIPT_REGISTER",
        generation_id=uuid.uuid4(),
        date_from=dt.date(2026, 4, 1),
        date_to=dt.date(2026, 4, 30),
    )
    receipts, _ = calculate(facts, query, frozen.control.coverage_start)
    assert len(receipts) == 1 and receipts[0]["amount"] == "100.2500"
    assert (
        receipts[0]["execution_id"] == str(command.execution_id) and receipts[0]["mode"] == "CASH"
    )
    bills, _ = calculate(
        facts, query.model_copy(update={"code": "ADVANCES"}), frozen.control.coverage_start
    )
    assert (
        len(bills) == 1
        and bills[0]["remaining"] == "100.2500"
        and bills[0]["tracking"] == "ADVANCE"
    )
    assert all("authority" not in str(row.data) for row in facts)

    reverse = command.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": command.execution_id,
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "posting_date": dt.date(2026, 4, 3),
            "correction_reason": "Correct mistaken advance",
            "authority": delegated(),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    assert (await transport.send(reverse)).outcome == "COMMITTED"
    updated, updated_facts = await snapshot()
    current, _ = calculate(updated_facts, query, updated.control.coverage_start)
    assert len(current) == 2 and sum(Decimal(row["signed_amount"]) for row in current) == 0
    balance, _ = calculate(
        updated_facts,
        query.model_copy(update={"code": "TRIAL_BALANCE"}),
        updated.control.coverage_start,
    )
    assert balance[-1]["difference"] == "0.0000"
    unchanged, _ = calculate(facts, query, frozen.control.coverage_start)
    assert unchanged == receipts
