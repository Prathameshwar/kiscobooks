import datetime as dt
import secrets
import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import service_request_bytes, service_response_bytes
from conftest import COMPANY, SECRET, TENANT, USER, headers
from sqlalchemy import select
from test_foundation import create_type, draft
from voucher_execution import ExecutionCommand, ExecutionResult
from voucher_execution.transport import ExecutionClient, command_digest, verify
from voucher_execution.transport import headers as signed_headers

from vouchers.models import core as m
from vouchers.schemas.documents import VoucherInput
from vouchers.tasks.execution_worker import deliver, enqueue


async def prepare(client, prefix, app):
    kind = await create_type(client, prefix)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    assert (
        await client.post(
            prefix + "/vouchers/" + voucher["id"] + "/submit",
            headers=headers(),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            prefix + "/vouchers/" + voucher["id"] + "/approve",
            headers=headers(user=uuid7()),
            json={"expected_version": 2},
        )
    ).status_code == 200
    from billing_platform.company_context import verify_company_context
    from billing_platform.gateway import decode_actor_context

    from vouchers.api.auth import Access

    signed = headers()
    current = Access(
        decode_actor_context(
            signed["X-Actor-Context"], signed["X-Actor-Signature"], SECRET.encode()
        ),
        verify_company_context(
            signed["X-Company-Context"], signed["X-Company-Signature"], SECRET.encode()
        ),
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            approvals = tuple(
                await db.scalars(
                    select(m.VoucherApproval.id).where(m.VoucherApproval.action == "approve")
                )
            )
    payload = {key: value for key, value in voucher.items() if key in VoucherInput.model_fields}
    body = ExecutionCommand(
        tenant_id=TENANT,
        company_id=COMPANY,
        voucher_id=uuid.UUID(voucher["id"]),
        revision_id=uuid.UUID(voucher["revision_id"]),
        operation_id=uuid7(),
        execution_id=uuid7(),
        purpose="POST",
        kind="MEMORANDUM",
        company_configuration_hash="a" * 64,
        approval_ids=approvals,
        content_hash=voucher["content_hash"],
        configuration_hash=voucher["configuration_hash"],
        request_hash="0" * 64,
        source_payload=payload,
        actor_user_id=USER,
        authority_expires_at=utcnow() + dt.timedelta(minutes=2),
    )
    body = body.model_copy(update={"request_hash": command_digest(body)})
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await enqueue(db, current, body)
    return body


async def test_unknown_network_outcome_reconciles_same_attempt_and_blocks_configuration(
    client, prefix, app
):
    body = await prepare(client, prefix, app)
    abandoned = await client.post(
        prefix + f"/vouchers/{body.voucher_id}/cancel",
        headers=headers(),
        json={"expected_version": 3, "reason": "Must wait for owner"},
    )
    assert abandoned.status_code == 409
    result = ExecutionResult(
        tenant_id=TENANT,
        company_id=COMPANY,
        operation_id=body.operation_id,
        execution_id=body.execution_id,
        content_hash=body.content_hash,
        configuration_hash=body.configuration_hash,
        request_hash=body.request_hash,
        outcome="REJECTED",
        rejection_code="UNSUPPORTED_PROFILE",
    )
    secret = secrets.token_bytes(32)
    key = "execution.test"
    stored = None
    posts = 0

    async def owner(request):
        nonlocal stored, posts
        operation = (
            "voucher.execution.status" if request.method == "GET" else "voucher.execution.command"
        )
        framed = service_request_bytes(
            method=request.method, path=request.url.path, query="", body=request.content
        )
        verify(secret, key, operation, framed, request.headers)
        if request.method == "POST":
            posts += 1
            assert (
                ExecutionCommand.model_validate_json(request.content).execution_id
                == body.execution_id
            )
            stored = result.model_dump(mode="json")
            raise httpx.ReadTimeout("injected lost response", request=request)
        if stored is None:
            return httpx.Response(404)
        raw = canonical_json(stored)
        return httpx.Response(
            200,
            content=raw,
            headers=signed_headers(
                secret,
                key,
                operation + ".response",
                service_response_bytes(request_bytes=framed, response_body=raw),
                response=True,
            ),
        )

    blocked = await client.post(
        prefix + "/voucher-types",
        headers=headers(),
        json={"code": "BLOCKED", "name": "Blocked", "kind": "MEMORANDUM"},
    )
    assert blocked.status_code == 409
    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as http:
        transport = ExecutionClient(http, "http://127.0.0.1", key, secret)
        with pytest.raises(httpx.ReadTimeout):
            await deliver(app.state.session_factory, transport, TENANT, COMPANY, body.operation_id)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                operation = await db.get(m.VoucherOperation, body.operation_id)
                assert operation.status == "PENDING" and operation.attempt_count == 1
        assert await deliver(
            app.state.session_factory, transport, TENANT, COMPANY, body.operation_id
        )
    assert posts == 1
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            operation = await db.get(m.VoucherOperation, body.operation_id)
            assert (
                operation.status == "REJECTED"
                and operation.execution_id == body.execution_id
                and operation.attempt_count == 2
            )
    unblocked = await client.post(
        prefix + "/voucher-types",
        headers=headers(),
        json={"code": "ALLOWED", "name": "Allowed", "kind": "MEMORANDUM"},
    )
    assert unblocked.status_code == 201


async def test_cancel_waits_for_owner_receipt_and_recovery_keeps_identity(client, prefix, app):
    body = await prepare(client, prefix, app)
    cancelled = await client.post(
        prefix + f"/voucher-operations/{body.operation_id}/cancel",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert cancelled.status_code == 202 and cancelled.json()["status"] == "PENDING"
    recovered = await client.post(
        prefix + f"/voucher-operations/{body.operation_id}/recover",
        headers=headers(),
        json={"expected_version": 2},
    )
    assert recovered.status_code == 202 and recovered.json()["execution_id"] == str(
        body.execution_id
    )
    secret = secrets.token_bytes(32)
    key = "execution.test"

    async def owner(request):
        if request.method == "GET":
            return httpx.Response(404)
        command = ExecutionCommand.model_validate_json(request.content)
        assert command.purpose == "CANCEL" and command.execution_id == body.execution_id
        result = ExecutionResult(
            tenant_id=TENANT,
            company_id=COMPANY,
            operation_id=body.operation_id,
            execution_id=body.execution_id,
            content_hash=body.content_hash,
            configuration_hash=body.configuration_hash,
            request_hash=body.request_hash,
            outcome="CANCELLED",
        )
        raw = canonical_json(result.model_dump(mode="json"))
        framed = service_request_bytes(
            method="POST", path=request.url.path, query="", body=request.content
        )
        return httpx.Response(
            200,
            content=raw,
            headers=signed_headers(
                secret,
                key,
                "voucher.execution.command.response",
                service_response_bytes(request_bytes=framed, response_body=raw),
                response=True,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(owner)) as http:
        assert await deliver(
            app.state.session_factory,
            ExecutionClient(http, "http://127.0.0.1", key, secret),
            TENANT,
            COMPANY,
            body.operation_id,
        )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            row = await db.get(m.VoucherOperation, body.operation_id)
            assert row.status == "CANCELLED"
            assert len(list(await db.scalars(select(m.VoucherPostingReference)))) == 0


async def test_reversal_can_be_recovered_and_cancelled(client, prefix, app):
    body = await prepare(client, prefix, app)
    reverse = body.model_copy(
        update={
            "purpose": "REVERSE",
            "reversal_of_execution_id": body.execution_id,
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "correction_reason": "Correct the source",
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                m.VoucherOperation(
                    id=reverse.operation_id,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    voucher_id=body.voucher_id,
                    revision_id=body.revision_id,
                    execution_id=reverse.execution_id,
                    purpose="REVERSE",
                    status="PENDING",
                    content_hash=reverse.content_hash,
                    configuration_hash=reverse.configuration_hash,
                    request_hash=reverse.request_hash,
                    command=reverse.model_dump(mode="json"),
                    created_by=USER,
                    updated_by=USER,
                )
            )
    recovered = await client.post(
        prefix + f"/voucher-operations/{reverse.operation_id}/recover",
        headers=headers(),
        json={"expected_version": 1},
    )
    assert recovered.status_code == 202, recovered.text
    cancelled = await client.post(
        prefix + f"/voucher-operations/{reverse.operation_id}/cancel",
        headers=headers(),
        json={"expected_version": 2},
    )
    assert cancelled.status_code == 202, cancelled.text


async def test_polling_worker_selects_pending_reversals(client, prefix, app, monkeypatch):
    import asyncio

    from billing_platform.service_auth import CompanyServiceScope
    from pydantic import SecretStr

    from vouchers.tasks import execution_worker as worker
    from vouchers.tasks.source_worker import Owner

    body = await prepare(client, prefix, app)
    reverse_id = uuid7()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.VoucherOperation, body.operation_id)
            db.add(
                m.VoucherOperation(
                    id=reverse_id,
                    tenant_id=TENANT,
                    company_id=COMPANY,
                    voucher_id=row.voucher_id,
                    revision_id=row.revision_id,
                    execution_id=uuid7(),
                    purpose="REVERSE",
                    status="PENDING",
                    content_hash=row.content_hash,
                    configuration_hash=row.configuration_hash,
                    request_hash="d" * 64,
                    created_by=USER,
                    updated_by=USER,
                )
            )
    visited = []

    async def delivered(factory, transport, tenant, company, identity):
        visited.append((tenant, company, identity))
        return True

    async def end_iteration(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "create_engine", lambda url: app.state.engine)
    monkeypatch.setattr(
        worker, "create_session_factory", lambda *args, **kwargs: app.state.session_factory
    )
    monkeypatch.setattr(worker, "deliver", delivered)
    monkeypatch.setattr(worker.asyncio, "sleep", end_iteration)
    settings = worker.Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        execution_owner=Owner(
            owner="accounting",
            origin="http://127.0.0.1",
            key_id="test.execution",
            secret=SecretStr(secrets.token_hex(32)),
            scopes=(CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY),),
        ),
    )
    with pytest.raises(asyncio.CancelledError):
        await worker.run(settings)
    assert visited == [(TENANT, COMPANY, body.operation_id), (TENANT, COMPANY, reverse_id)]
