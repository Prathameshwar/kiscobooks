import datetime as dt
import secrets
import time
import uuid

from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    sign_service_body,
)
from conftest import COMPANY, TENANT, headers
from pydantic import SecretStr
from sqlalchemy import func, select
from test_foundation import create_type, draft

from vouchers.config import SourceCredential
from vouchers.models import core as m


async def test_signed_terminal_receipt_identity_and_replay(client, prefix, app):
    kind = await create_type(client, prefix)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    operation_id, execution_id = uuid7(), uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                m.VoucherOperation(
                    id=operation_id,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    voucher_id=uuid.UUID(voucher["id"]),
                    revision_id=uuid.UUID(voucher["revision_id"]),
                    execution_id=execution_id,
                    purpose="POST",
                    status="PENDING",
                    content_hash=voucher["content_hash"],
                    configuration_hash=voucher["configuration_hash"],
                    request_hash="a" * 64,
                )
            )
    secret = secrets.token_hex(32)
    key_id = "accounting.result"
    app.state.settings.source_credentials[key_id] = SourceCredential(
        issuer="accounting",
        operations=frozenset({"vouchers.execution.result"}),
        secret=SecretStr(secret),
        scopes=[CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)],
    )
    wire = {
        "tenant_id": str(TENANT),
        "company_id": str(COMPANY),
        "operation_id": str(operation_id),
        "execution_id": str(execution_id),
        "content_hash": voucher["content_hash"],
        "configuration_hash": voucher["configuration_hash"],
        "request_hash": "a" * 64,
        "outcome": "COMMITTED",
        "committed_at": dt.datetime.now(dt.UTC).isoformat(),
        "committed_generation": 1,
        "effects": [
            {"owner": "accounting", "effect_kind": "SOURCE_RECEIPT", "effect_id": str(uuid7())}
        ],
    }

    async def send(payload):
        body = canonical_json(payload)
        stamp = int(time.time())
        operation = "vouchers.execution.result"
        path = "/internal/v1/execution-results"
        key = ServiceKey("accounting", "vouchers", frozenset({operation}), secret.encode())
        signature = sign_service_body(
            key,
            key_id=key_id,
            operation=operation,
            timestamp=stamp,
            body=service_request_bytes(method="POST", path=path, query="", body=body),
        )
        return await client.post(
            path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Service-Key-Id": key_id,
                "X-Service-Issuer": "accounting",
                "X-Service-Timestamp": str(stamp),
                "X-Service-Signature": signature,
            },
        )

    assert (await client.post("/internal/v1/execution-results", json=wire)).status_code == 401
    for _ in range(2):
        result = await send(wire)
        assert result.status_code == 200, result.text
    changed = await send(wire | {"request_hash": "b" * 64})
    assert changed.status_code == 409
    cancelled = await send(
        wire
        | {
            "outcome": "CANCELLED",
            "effects": [],
            "committed_at": None,
            "committed_generation": None,
        }
    )
    assert cancelled.status_code == 409
    class DenyLimiter:
        def allow(self, key, *, limit):
            assert key.startswith("service:accounting.result:")
            assert limit == 1200
            return False

    app.state.write_limiter = DenyLimiter()
    assert (await send(wire)).status_code == 429
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(m.VoucherPostingReference.id))) == 1


async def test_artifact_recovery_keeps_execution_identity(client, prefix, app):
    kind = await create_type(client, prefix)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    template = (
        await client.post(
            prefix + "/voucher-templates",
            json={"code": "RETRY", "title": "Draft"},
            headers=headers(),
        )
    ).json()
    artifact = (
        await client.post(
            prefix + "/vouchers/" + voucher["id"] + "/artifacts",
            json={"expected_version": 1, "template_revision_id": template["revision_id"]},
            headers=headers(),
        )
    ).json()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.scalar(
                select(m.VoucherOperation).where(
                    m.VoucherOperation.execution_id == uuid.UUID(artifact["id"])
                )
            )
            operation_id = str(operation.id)
    key = headers()
    for _ in range(2):
        result = await client.post(
            prefix + "/voucher-operations/" + operation_id + "/recover",
            json={"expected_version": 1},
            headers=key,
        )
        assert result.status_code == 202, result.text
        assert result.json()["execution_id"] == artifact["id"]
        assert result.json()["row_version"] == 2


async def test_operation_discloses_stable_rejection_code_without_private_command(
    client, prefix, app
):
    from test_execution_delivery import prepare
    from voucher_execution import ExecutionResult

    from vouchers.tasks.operations import apply_result

    command = await prepare(client, prefix, app)
    result = ExecutionResult.model_validate(
        {
            name: getattr(command, name)
            for name in (
                "tenant_id",
                "company_id",
                "operation_id",
                "execution_id",
                "content_hash",
                "configuration_hash",
                "request_hash",
            )
        }
        | {"outcome": "REJECTED", "rejection_code": "CLOSED_PERIOD"}
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await apply_result(db, result)
    path = prefix + "/voucher-operations/" + str(command.operation_id)
    response = await client.get(path, headers=headers())
    assert response.status_code == 200 and response.json()["rejection_code"] == "CLOSED_PERIOD"
    assert "command" not in response.json() and "authority" not in response.text
    assert (await client.get(path, headers=headers(permissions=frozenset()))).status_code == 403
