import datetime as dt
import uuid

from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from conftest import COMPANY, SECRET, TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft
from test_invoice_capture import invoice_body, seed_accounts
from test_money_capture import money, project
from test_purchase_lifecycle_integrity import owner
from voucher_execution import ExecutionResult

from vouchers.models import core as m
from vouchers.schemas.sources import SourceBundle
from vouchers.tasks.operations import apply_result
from vouchers.tasks.sources import apply_bundle


def authority_headers(**kwargs):
    result = headers(**kwargs)
    context = verify_company_context(
        result["X-Company-Context"], result["X-Company-Signature"], SECRET.encode()
    )
    token, signature = sign_company_context(
        context.model_copy(update={"policy_namespaces": frozenset({"accounting", "vouchers"})}),
        SECRET.encode(),
    )
    return result | {"X-Company-Context": token, "X-Company-Signature": signature}


async def approved(client, prefix, app):
    kind = await create_type(client, prefix, kind="JOURNAL")
    financial = money()
    await project(app, financial["accounts"])
    day = dt.date.today().isoformat()
    item, _ = await draft(
        client, prefix, kind["revision_id"], financial=financial, posting_date=day
    )
    path = prefix + "/vouchers/" + item["id"]
    assert (
        await client.post(path + "/submit", json={"expected_version": 1}, headers=headers())
    ).status_code == 200
    assert (
        await client.post(
            path + "/approve", json={"expected_version": 2}, headers=headers(user=uuid7())
        )
    ).status_code == 200
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {"start_date": day, "end_date": day},
                    }
                ],
            }
        ),
        "accounting",
    )
    return path


async def test_post_reverse_release_gates_authority_and_durable_replay(client, prefix, app):
    path = await approved(client, prefix, app)
    assert (
        await client.post(path + "/post", json={"expected_version": 3}, headers=authority_headers())
    ).status_code == 409
    app.state.settings.invoice_execution_enabled = True
    assert (
        await client.post(path + "/post", json={"expected_version": 3}, headers=authority_headers())
    ).status_code == 409
    app.state.settings.invoice_execution_enabled = False
    app.state.settings.money_execution_enabled = True
    assert (await client.post(path + "/post", json={"expected_version": 3})).status_code == 401
    other = uuid7()
    assert (
        await client.post(
            path.replace(str(COMPANY), str(other)) + "/post",
            json={"expected_version": 3},
            headers=authority_headers(company=other),
        )
    ).status_code == 403
    assert (
        await client.post(
            path + "/post", json={"expected_version": "wrong"}, headers=authority_headers()
        )
    ).status_code == 422
    assert (
        await client.post(
            path + "/post",
            json={"expected_version": 3},
            headers=headers(policy_namespaces=frozenset()),
        )
    ).status_code == 401
    assert (
        await client.post(
            path + "/post", json={"expected_version": 3}, headers=headers(permissions=frozenset())
        )
    ).status_code == 403
    key = authority_headers()
    result = await client.post(path + "/post", json={"expected_version": 3}, headers=key)
    assert result.status_code == 202, result.text
    retry = await client.post(path + "/post", json={"expected_version": 3}, headers=key)
    assert retry.json()["execution_id"] == result.json()["execution_id"]
    assert (
        await client.post(path + "/post", json={"expected_version": 3}, headers=authority_headers())
    ).status_code == 409
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            operation = await db.get(m.VoucherOperation, uuid.UUID(result.json()["operation_id"]))
            assert operation.command["protocol_version"] == 2
            assert operation.command["authority"]["actor_context"] == key["X-Actor-Context"]
            await apply_result(
                db,
                ExecutionResult(
                    protocol_version=2,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    operation_id=operation.id,
                    execution_id=operation.execution_id,
                    content_hash=operation.content_hash,
                    configuration_hash=operation.configuration_hash,
                    request_hash=operation.request_hash,
                    outcome="COMMITTED",
                    committed_at=dt.datetime.now(dt.UTC),
                    committed_generation=1,
                    effects=[
                        {
                            "owner": "accounting",
                            "effect_kind": "SOURCE_RECEIPT",
                            "effect_id": uuid7(),
                        }
                    ],
                ),
            )
    correction = {
        "expected_version": 4,
        "posting_date": dt.date.today().isoformat(),
        "reason": "Correct the journal",
    }
    assert (await client.post(path + "/reverse", json=correction)).status_code == 401
    assert (
        await client.post(
            path + "/reverse", json=correction, headers=authority_headers(permissions=frozenset())
        )
    ).status_code == 403
    assert (
        await client.post(
            path.replace(str(COMPANY), str(other)) + "/reverse",
            json=correction,
            headers=authority_headers(company=other),
        )
    ).status_code == 403
    assert (
        await client.post(
            path + "/reverse", json=correction | {"reason": ""}, headers=authority_headers()
        )
    ).status_code == 422
    reversed_response = await client.post(
        path + "/reverse", json=correction, headers=authority_headers()
    )
    assert reversed_response.status_code == 202, reversed_response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            operation = await db.get(
                m.VoucherOperation, uuid.UUID(reversed_response.json()["operation_id"])
            )
            assert operation.purpose == "REVERSE"
            assert operation.command["reversal_of_execution_id"] == result.json()["execution_id"]
            await apply_result(
                db,
                ExecutionResult(
                    protocol_version=2,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    operation_id=operation.id,
                    execution_id=operation.execution_id,
                    content_hash=operation.content_hash,
                    configuration_hash=operation.configuration_hash,
                    request_hash=operation.request_hash,
                    outcome="COMMITTED",
                    committed_at=dt.datetime.now(dt.UTC),
                    committed_generation=1,
                    effects=[
                        {
                            "owner": "accounting",
                            "effect_kind": "SOURCE_RECEIPT",
                            "effect_id": uuid7(),
                        }
                    ],
                ),
            )
            await db.flush()
            assert (await db.scalar(select(m.Voucher))).status == "REVERSED"


async def test_invoice_producer_has_separate_gate_and_accepted_account_scope(
    client, prefix, app, monkeypatch
):
    kind = await create_type(client, prefix, kind="SALES", policy={"invoice": {}})
    body = invoice_body()
    body["components"] = []
    await seed_accounts(app, body)
    day = dt.date.today().isoformat()
    item, _ = await draft(client, prefix, kind["revision_id"], invoice=body, posting_date=day)
    path = prefix + "/vouchers/" + item["id"]
    # Acceptance is stored only after the owner's own preview of this revision confirms the hash.
    owner(app, monkeypatch, "a" * 64)
    accepted = await client.post(
        path + "/invoice-acceptance",
        json={"expected_version": 1, "calculation_hash": "a" * 64},
        headers=headers(),
    )
    assert accepted.status_code == 200, accepted.text
    assert (
        await client.post(path + "/submit", json={"expected_version": 2}, headers=headers())
    ).status_code == 200
    assert (
        await client.post(
            path + "/approve", json={"expected_version": 3}, headers=headers(user=uuid7())
        )
    ).status_code == 200
    assert (
        await client.post(path + "/issue", json={"expected_version": 4}, headers=headers())
    ).status_code == 409
    await apply_bundle(
        app.state.session_factory,
        SourceBundle.model_validate(
            {
                "message_id": str(uuid7()),
                "tenant_id": str(TENANT),
                "company_id": str(COMPANY),
                "masters": [
                    {
                        "source_id": str(uuid7()),
                        "entity_type": "fiscal_period",
                        "source_version": 1,
                        "status": "ACTIVE",
                        "facts": {"start_date": day, "end_date": day},
                    }
                ],
            }
        ),
        "accounting",
    )
    assert (
        await client.post(path + "/post", json={"expected_version": 4}, headers=authority_headers())
    ).status_code == 409
    app.state.settings.money_execution_enabled = True
    assert (
        await client.post(path + "/post", json={"expected_version": 4}, headers=authority_headers())
    ).status_code == 409
    app.state.settings.money_execution_enabled = False
    app.state.settings.invoice_execution_enabled = True
    capabilities = await client.get(prefix + "/voucher-capabilities", headers=headers())
    assert capabilities.json()["invoice_execution"] is True
    ready = {row["kind"]: row["execution_ready"] for row in capabilities.json()["kinds"]}
    assert ready["SALES"] and ready["PURCHASE"] and not ready["JOURNAL"]
    result = await client.post(
        path + "/post", json={"expected_version": 4}, headers=authority_headers()
    )
    assert result.status_code == 202, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.get(m.VoucherOperation, uuid.UUID(result.json()["operation_id"]))
            assert operation.command["kind"] == "SALES"
            accepted = operation.command["source_payload"]["invoice"]
            assert accepted["accepted_calculation_hash"] == "a" * 64
            assert operation.command["source_payload"].get("financial") is None
    assert (
        await client.post(
            path + "/reverse",
            json={"expected_version": 4, "posting_date": day, "reason": "Invoice correction"},
            headers=authority_headers(),
        )
    ).status_code == 409
