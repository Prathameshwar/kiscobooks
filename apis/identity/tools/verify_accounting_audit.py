"""Disposable native Accounting -> RabbitMQ -> Audit -> gateway -> console proof.

Run from apis/identity with PYTHONPATH including this project and Accounting/Audit src.
Requires explicit loopback MySQL, isolated RabbitMQ URL/user, nginx and optional browser
Python paths in AUDIT_TEST_* environment variables. Never uses deployed schemas/queues.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import time
import uuid
from pathlib import Path

import aio_pika
import httpx
import uvicorn
from accounting.config import Settings as AccountingSettings
from accounting.events.audit_contract import AUDIT_EVENTS
from accounting.main import create_app as accounting_app
from audit.config import Settings as AuditSettings
from audit.main import create_app as audit_app
from audit.models import AuditEvent
from audit.tasks.consume import receive_audit
from audit.tasks.partitions import provision_ahead
from audit.tasks.verify import verify_tenant_chain
from billing_platform.broker import (
    BrokerSource,
    ConfirmedPublisher,
    confirmed_channel,
    declare_consumer_queue,
)
from billing_platform.db import Base, create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.dead_letters import recover_dead_letters
from billing_platform.delivery import publish_batch
from billing_platform.oidc import AccessTokenVerifier, OidcConfig
from billing_platform.outbox_ops import inventory, retry_selected
from billing_platform.publisher import PublisherConfig
from billing_platform.service_auth import ServiceKey, sign_service_body
from joserfc import jwt
from joserfc.jwk import RSAKey
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from identity.config import Settings as IdentitySettings
from identity.main import create_app as identity_app
from tests.factories import (
    build_field_policy,
    build_membership,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    seed_two_companies,
)

ROOT = Path(__file__).resolve().parents[3]
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def execute(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    # All executables and arguments are local, fixed by this operator-owned test.
    return subprocess.run(args, capture_output=True, text=True, creationflags=FLAGS, **kwargs)  # noqa: S603


async def delivery(queue):
    # basic.get is a poll: its RPC timeout does not wait for asynchronous dead-letter routing.
    async with asyncio.timeout(10):
        while True:
            message = await queue.get(fail=False)
            if message is not None:
                return message
            await asyncio.sleep(0.05)


async def provision(server: str, names: list[str], create: bool) -> None:
    engine = create_async_engine(server, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            for name in names:
                if not re.fullmatch(r"audit_proof_[0-9a-f]{24}_(accounting|catalog|audit)", name):
                    raise ValueError("invalid disposable schema")
                await connection.execute(
                    text(
                        f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        if create
                        else f"DROP DATABASE IF EXISTS `{name}`"
                    )
                )
    finally:
        await engine.dispose()


async def grant_runtime(
    server: str, schema: str, user: str, password: str, *, create: bool
) -> None:
    if not re.fullmatch(r"audit_proof_[0-9a-f]{24}_audit", schema) or not re.fullmatch(
        r"ap_[0-9a-f]{24}", user
    ):
        raise ValueError("invalid disposable grant target")
    engine = create_async_engine(server, poolclass=NullPool)
    try:
        async with engine.connect() as db:
            if create:
                await db.execute(
                    text(f"CREATE USER '{user}'@'localhost' IDENTIFIED BY :password"),
                    {"password": password},
                )
                for table, grants in [
                    ("audit_event", "SELECT, INSERT"),
                    ("outbox", "SELECT, INSERT, UPDATE"),
                    ("processed_message", "SELECT, INSERT"),
                ]:
                    await db.execute(
                        text(
                            f"GRANT {grants} ON \u0060{schema}\u0060.\u0060{table}\u0060 "
                            f"TO '{user}'@'localhost'"
                        )
                    )
            else:
                await db.execute(text(f"DROP USER IF EXISTS '{user}'@'localhost'"))
    finally:
        await engine.dispose()


async def proof(urls: list[str], runtime: Path, runtime_url: str) -> None:
    service = os.environ.get("AUDIT_PROOF_SERVICE", "accounting")
    catalog_mode = service == "catalog"
    expected_events = 4 if catalog_mode else 9
    entity = "catalog.unit_of_measure" if catalog_mode else "accounting.party"
    evidence_field = "quantity_increment" if catalog_mode else "country_code"
    old_value, new_value = ("1.0000", "2.0000") if catalog_mode else ("IN", "US")
    secret = secrets.token_hex(32)
    identity = identity_app(
        IdentitySettings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(secret),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
            public_auth_url="https://auth.test",
        )
    )
    if catalog_mode:
        from types import SimpleNamespace

        producer_engine = create_engine(urls[0])
        producer = SimpleNamespace(
            state=SimpleNamespace(
                engine=producer_engine, session_factory=create_session_factory(producer_engine)
            )
        )
        events = frozenset(
            json.loads((ROOT / "apis/catalog/contracts/audit-events.json").read_text())
        )
    else:
        producer = accounting_app(
            AccountingSettings(database_url=urls[0], actor_signing_secret=SecretStr(secret))
        )
        events = AUDIT_EVENTS
    audit = audit_app(
        AuditSettings(
            database_url=runtime_url,
            actor_signing_secret=SecretStr(secret),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        )
    )
    apps = [identity, producer, audit]
    servers, tasks, processes = [], [], []
    ports = [port() for _ in range(5)]
    gateway_port, console_port = ports[3:]
    tenant, other, user = [uuid.uuid4() for _ in range(3)]
    broker_url, broker_user = (
        os.environ["IDENTITY_TEST_BROKER_URL"],
        os.environ["IDENTITY_TEST_BROKER_USER"],
    )
    broker = make_url(broker_url.replace("amqp://", "mysql://", 1))
    if broker.host not in {"localhost", "127.0.0.1"} or broker.database != "bill_identity_test":
        raise ValueError("native proof requires the isolated local test broker")
    exchange_name = "audit-proof-" + uuid.uuid4().hex
    key = ServiceKey(service, "audit", events, secrets.token_bytes(32))
    export_key = ServiceKey(
        "audit", "audit", frozenset({"audit.exported"}), secrets.token_bytes(32)
    )
    sources = {
        "proof": BrokerSource(key, broker_user),
        "export": BrokerSource(export_key, broker_user),
    }
    signing = RSAKey.generate_key(2048, {"kid": "proof"})
    provider = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"keys": [signing.as_dict(private=False)]})
        )
    )
    identity.state.token_verifier = AccessTokenVerifier(
        OidcConfig(
            "https://audit-proof.test/",
            "web",
            "https://audit-proof.test/jwks",
            max_token_seconds=900,
        ),
        provider,
    )
    now = int(time.time())
    token = jwt.encode(
        {"alg": "RS256", "kid": "proof"},
        {
            "iss": "https://audit-proof.test/",
            "aud": "web",
            "sub": "audit-proof",
            "iat": now,
            "exp": now + 900,
            "scope": "openid billing.api",
        },
        signing,
    )
    headers = {"Authorization": "Bearer " + token}
    nginx_args: list[str] = []
    try:
        async with identity.state.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with identity.state.session_factory() as db:
            company, foreign = await seed_two_companies(db, tenant, other)
            with tenant_scope(tenant):
                role = build_role(tenant_id=tenant, key="audit_proof")
                db.add_all(
                    [
                        role,
                        build_user(
                            tenant_id=tenant,
                            user_id=user,
                            authentik_sub="audit-proof",
                            default_company_id=company,
                        ),
                    ]
                )
                await db.flush()
                permissions = [
                    "company.read",
                    "user.read",
                    "audit.read",
                    "audit.export",
                    "activity.read",
                    "accounting.setup.manage",
                    "accounting.setup.read",
                    "accounting.party.manage",
                    "accounting.party.read",
                    "accounting.export.read",
                ]
                if catalog_mode:
                    from billing_platform.permissions import CATALOG_PERMISSIONS

                    permissions.extend(sorted(CATALOG_PERMISSIONS))
                db.add_all(
                    [
                        build_role_permission(tenant_id=tenant, role_id=role.id, permission_key=p)
                        for p in permissions
                    ]
                )
                db.add_all(
                    [
                        build_role_assignment(tenant_id=tenant, role_id=role.id, subject_id=user),
                        build_membership(tenant_id=tenant, user_id=user, company_id=company),
                    ]
                )
                await db.commit()
        maintenance = create_async_engine(urls[1], poolclass=NullPool)
        try:
            async with maintenance.begin() as connection:
                created = await provision_ahead(connection, today=utcnow().date(), ahead=6)
                assert await provision_ahead(connection, today=utcnow().date(), ahead=6) == []
        finally:
            await maintenance.dispose()
        async with audit.state.engine.connect() as connection:
            for statement in (
                "UPDATE audit_event SET sequence=sequence WHERE 1=0",
                "DELETE FROM audit_event WHERE 1=0",
            ):
                try:
                    await connection.execute(text(statement))
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("runtime grant permits mutation of audit evidence")
        print("Native schemas, partitions and append-only runtime grants passed", flush=True)
        for app, chosen in zip(apps, ports, strict=False):
            if catalog_mode and app is producer:
                # Catalog and Identity own different mappings of similarly named tables.
                # Run Catalog in its own interpreter, as deployed, instead of sharing metadata.
                with (runtime / "catalog.log").open("w") as log:
                    processes.append(
                        subprocess.Popen(  # noqa: S603 - owned local interpreter and arguments
                            [
                                str(ROOT / "apis/catalog/.venv/Scripts/python.exe"),
                                "-m",
                                "uvicorn",
                                "catalog.main:create_app",
                                "--factory",
                                "--host",
                                "127.0.0.1",
                                "--port",
                                str(chosen),
                                "--log-level",
                                "error",
                                "--no-access-log",
                            ],
                            cwd=ROOT / "apis/catalog",
                            creationflags=FLAGS,
                            stdout=log,
                            stderr=log,
                            env=dict(
                                os.environ,
                                PYTHONPATH=".",
                                CATALOG_DATABASE_URL=urls[0],
                                CATALOG_ACTOR_SIGNING_SECRET=secret,
                            ),
                        )
                    )
                continue
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=chosen,
                    log_level="error",
                    access_log=False,
                    lifespan="off",
                )
            )
            servers.append(server)
            tasks.append(asyncio.create_task(server.serve()))
        async with httpx.AsyncClient(timeout=20) as http:
            for _ in range(100):
                if all(s.started for s in servers):
                    break
                await asyncio.sleep(0.1)
            for folder in ("logs", "temp", "conf.d"):
                (runtime / folder).mkdir(exist_ok=True)
            (runtime / "conf.d/proxy.include").write_text(
                (ROOT / "start/win/conf/proxy.include").read_text()
            )
            config = (ROOT / "start/win/conf/bill.conf").read_text()
            for old, new in [
                (8090, gateway_port),
                (8001, ports[0]),
                (8003 if catalog_mode else 8011, ports[1]),
                (8002, ports[2]),
            ]:
                config = (
                    config.replace(f"127.0.0.1:{old}", f"127.0.0.1:{new}")
                    if old != 8090
                    else config.replace("listen       8090", f"listen       127.0.0.1:{new}")
                )
            (runtime / "bill.conf").write_text(config)
            (runtime / "nginx.conf").write_text(
                "worker_processes 1; pid logs/nginx.pid; error_log logs/error.log;\n"
                "events { worker_connections 128; }\nhttp { access_log off; include bill.conf; }\n"
            )
            nginx_args = [
                os.environ["AUDIT_TEST_NGINX_BINARY"],
                "-p",
                str(runtime) + os.sep,
                "-c",
                "nginx.conf",
            ]
            checked = await asyncio.to_thread(execute, [*nginx_args, "-t"])
            assert checked.returncode == 0, checked.stderr
            processes.append(subprocess.Popen(nginx_args, creationflags=FLAGS))  # noqa: S603
            gateway = f"http://127.0.0.1:{gateway_port}"
            for _ in range(50):
                try:
                    if (await http.get(gateway + "/nginx-health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)

            async def request(
                method: str,
                path: str,
                body: dict[str, object] | None = None,
                expected: int = 200,
                extra: dict[str, str] | None = None,
            ) -> httpx.Response:
                result = await http.request(
                    method, gateway + path, headers=headers | (extra or {}), json=body
                )
                assert result.status_code == expected, (
                    path,
                    result.status_code,
                    result.text[:1000],
                )
                return result

            # Raw request_uri can be encoded even though nginx routes a normalized path.
            from identity.models import Company

            with tenant_scope(tenant):
                async with identity.state.session_factory() as db, db.begin():
                    protected = await db.get(Company, company)
                    protected.requires_step_up = True
            company_text = str(company)
            encoded_company = "%" + format(ord(company_text[0]), "02x") + company_text[1:]
            for guarded_path in (
                f"/{service}/v1/companies/{encoded_company}/units",
                f"/{service}/v1/comp%61nies/{company}/units",
                f"/{service}/v1/companies/unused/%2e%2e/{company}/units",
                f"/%61udit/v1/audit-events?company_id={company}",
                f"//audit/v1/audit-events?company_id={company}",
            ):
                await request("GET", guarded_path, expected=403)
            with tenant_scope(tenant):
                async with identity.state.session_factory() as db, db.begin():
                    protected = await db.get(Company, company)
                    protected.requires_step_up = False

            if catalog_mode:
                from verify_catalog_audit import prepare

                for _ in range(100):
                    try:
                        if (
                            await http.get(f"http://127.0.0.1:{ports[1]}/health/live")
                        ).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                denied_catalog = await http.get(
                    gateway + f"/catalog/v1/companies/{company}/units",
                    headers={"X-Actor-Context": "forged", "X-Actor-Signature": "0" * 64},
                )
                assert denied_catalog.status_code == 401
                canary = await prepare(urls[0], tenant, company, user, request)
            else:
                base = f"/accounting/v1/companies/{company}"
                idem = {"Idempotency-Key": str(uuid.uuid4())}
                await request("POST", base + "/accounting-setup/initialize", {}, extra=idem)
                await request("POST", base + "/accounting-setup/initialize", {}, extra=idem)
                row = (
                    await request(
                        "POST",
                        base + "/parties",
                        {
                            "code": "PROOF",
                            "name": "Private person",
                            "legal_name": "Private person",
                            "country_code": "IN",
                        },
                        201,
                        {"Idempotency-Key": str(uuid.uuid4())},
                    )
                ).json()
                updated = await request(
                    "PATCH",
                    base + "/parties/" + row["id"],
                    {"country_code": "US", "expected_version": row["row_version"]},
                    extra={"Idempotency-Key": str(uuid.uuid4()), "X-Trace-Id": "a" * 32},
                )
                assert updated.json()["country_code"] == "US"
                await request("GET", base + "/exports/parties")

                async def canary():
                    await request("GET", base + "/exports/parties")

            async with producer.state.session_factory() as db:
                pending = list(await db.scalars(select(Outbox)))
                assert len(pending) == expected_events, len(pending)
                assert all("Private person" not in json.dumps(e.payload) for e in pending)
                original_ids = {e.message_id for e in pending}
            # Accounting commits while Audit is offline. Nothing is ingested until delivery.
            async with audit.state.session_factory() as db:
                with tenant_scope(tenant):
                    assert not list(await db.scalars(select(AuditEvent)))
            async with confirmed_channel(broker_url) as channel:
                exchange = await channel.declare_exchange(
                    exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
                publisher = ConfirmedPublisher(
                    exchange, key_id="proof", key=key, broker_user=broker_user
                )
                failed = await publish_batch(
                    producer.state.session_factory,
                    publisher,
                    event_types=key.operations,
                    maximum_attempts=1,
                )
                assert failed.confirmed == 0 and failed.deferred == expected_events
                inv = await inventory(
                    producer.state.session_factory, key.operations, maximum_attempts=1
                )
                assert inv["exhausted"] == expected_events, inv
                queue = await declare_consumer_queue(
                    channel,
                    exchange_name=exchange_name,
                    queue_name=exchange_name,
                    dead_letter_exchange=exchange_name + ".dlx",
                    routes=tuple(sorted(key.operations | export_key.operations)),
                    single_active_consumer=True,
                )
                try:
                    await retry_selected(
                        producer.state.session_factory,
                        key.operations,
                        list(original_ids),
                        apply=False,
                    )
                    await retry_selected(
                        producer.state.session_factory,
                        key.operations,
                        list(original_ids),
                        apply=True,
                    )

                    async def interrupted_publish(outgoing):
                        assert await publisher(outgoing)
                        # Cancel after native broker confirmation, before committing the outbox.
                        raise asyncio.CancelledError

                    try:
                        await publish_batch(
                            producer.state.session_factory,
                            interrupted_publish,
                            event_types=key.operations,
                            limit=1,
                        )
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("publication cancellation did not escape")
                    sent = await publish_batch(
                        producer.state.session_factory, publisher, event_types=key.operations
                    )
                    assert sent.confirmed == expected_events
                    # Put one authentic event through DLX and the recovery command.
                    first = await delivery(queue)
                    assert first is not None
                    first_id = uuid.UUID(first.message_id)
                    # Retiring the original key rejects even an authentic old delivery.
                    rotated_key = ServiceKey(
                        service, "audit", key.operations, secrets.token_bytes(32)
                    )
                    rotated_sources = {"rotated": BrokerSource(rotated_key, broker_user)}
                    await receive_audit(
                        audit.state.session_factory,
                        first,
                        sources=rotated_sources,
                        consumer_name=exchange_name,
                    )
                    recover_config = PublisherConfig(
                        database_url=urls[0],
                        broker_url=broker_url,
                        broker_user=broker_user,
                        key_id="proof",
                        key=key,
                        exchange=exchange_name,
                    )
                    report = await recover_dead_letters(
                        recover_config, exchange_name + ".dead", [first_id]
                    )
                    assert len(report) == 1 and not report[0]["applied"]
                    report = await recover_dead_letters(
                        recover_config, exchange_name + ".dead", [first_id], apply=True
                    )
                    assert report[0]["applied"]
                    # A real MySQL authentication outage cannot acknowledge a queued event.
                    denied_url = (
                        make_url(runtime_url)
                        .set(password=secrets.token_hex(32))
                        .render_as_string(hide_password=False)
                    )
                    denied_engine = create_engine(denied_url)
                    try:
                        async with confirmed_channel(broker_url) as failing_channel:
                            failing_queue = await failing_channel.get_queue(exchange_name)
                            failed_message = await delivery(failing_queue)
                            try:
                                await receive_audit(
                                    create_session_factory(denied_engine),
                                    failed_message,
                                    sources=sources,
                                    consumer_name=exchange_name,
                                )
                            except DBAPIError:
                                assert not failed_message.processed
                            else:
                                raise AssertionError("unavailable database acknowledged a message")
                            # Closing the channel requeues the delivery, as the supervisor does.
                    finally:
                        await denied_engine.dispose()
                    for _ in range(expected_events + 1):
                        message = await delivery(queue)
                        assert message is not None
                        await receive_audit(
                            audit.state.session_factory,
                            message,
                            sources=sources,
                            consumer_name=exchange_name,
                        )
                    # Redelivery after commit cannot append another row.
                    await exchange.publish(
                        aio_pika.Message(
                            body=message.body,
                            content_type="application/json",
                            headers=dict(message.headers)
                            | {
                                "key_id": "rotated",
                                "signed_at": "1",
                                "signature": sign_service_body(
                                    rotated_key,
                                    key_id="rotated",
                                    operation=message.type,
                                    timestamp=1,
                                    body=message.body,
                                ),
                            },
                            user_id=broker_user,
                            message_id=message.message_id,
                            type=message.type,
                        ),
                        routing_key=message.type,
                    )
                    duplicate = await delivery(queue)
                    assert duplicate is not None
                    await receive_audit(
                        audit.state.session_factory,
                        duplicate,
                        sources=sources | rotated_sources,
                        consumer_name=exchange_name,
                    )
                    rotation_dead = await channel.get_queue(exchange_name + ".dead")
                    assert await rotation_dead.get(fail=False) is None
                    # Authenticated permanent defects must not trap the single writer in reconnect.
                    for invalid_field, invalid_value in (
                        ("reason", "x" * 501),
                        ("context", {"value": float("inf")}),
                    ):
                        bad_body = json.loads(message.body)
                        bad_id = str(uuid.uuid4())
                        bad_body["message_id"] = bad_id
                        bad_body["payload"][invalid_field] = invalid_value
                        encoded_bad = json.dumps(bad_body).encode()
                        await exchange.publish(
                            aio_pika.Message(
                                body=encoded_bad,
                                content_type="application/json",
                                message_id=bad_id,
                                type=message.type,
                                user_id=broker_user,
                                headers=dict(message.headers)
                                | {
                                    "key_id": "proof",
                                    "signed_at": "1",
                                    "signature": sign_service_body(
                                        key,
                                        key_id="proof",
                                        operation=message.type,
                                        timestamp=1,
                                        body=encoded_bad,
                                    ),
                                },
                            ),
                            routing_key=message.type,
                            mandatory=True,
                        )
                        rejected_message = await delivery(queue)
                        assert rejected_message is not None
                        await receive_audit(
                            audit.state.session_factory,
                            rejected_message,
                            sources=sources,
                            consumer_name=exchange_name,
                        )
                        rejected_original = await delivery(rotation_dead)
                        assert (
                            rejected_original is not None and rejected_original.message_id == bad_id
                        )
                        await rejected_original.ack()
                    # Scoped reads, export ingestion and the worker canary must still pass.
                    with tenant_scope(tenant):
                        async with audit.state.session_factory() as db:
                            rows = list(await db.scalars(select(AuditEvent)))
                            assert (
                                len(rows) == expected_events
                                and {r.message_id for r in rows} == original_ids
                            )
                            assert await verify_tenant_chain(db, tenant) == []
                            parameters = {
                                "tenant": tenant.bytes,
                                "company": company.bytes,
                                "id": rows[0].id.bytes,
                                "occurred": rows[0].occurred_at.replace(tzinfo=None),
                            }
                            plans = {}
                            queries = {
                                "detail": (
                                    "SELECT id FROM audit_event WHERE tenant_id=:tenant "
                                    "AND occurred_at=:occurred AND id=:id"
                                ),
                                "company_list": (
                                    "SELECT id,occurred_at,action FROM audit_event "
                                    "WHERE tenant_id=:tenant AND company_id=:company "
                                    "AND occurred_at>=:occurred "
                                    "ORDER BY occurred_at DESC,id DESC LIMIT 51"
                                ),
                            }
                            for label, sql in queries.items():
                                plan = (
                                    (
                                        await db.execute(
                                            text("EXPLAIN FORMAT=TRADITIONAL " + sql), parameters
                                        )
                                    )
                                    .mappings()
                                    .all()
                                )
                                assert all(row["partitions"] for row in plan)
                                assert any(row["key"] or row["possible_keys"] for row in plan)
                                plans[label] = [dict(row) for row in plan]
                            assert len(plans["detail"][0]["partitions"].split(",")) == 1
                            (runtime / "query-plans.json").write_text(
                                json.dumps(plans, indent=2, default=str), encoding="utf-8"
                            )
                    trail = (
                        "/audit/v1/audit-events?company_id="
                        + str(company)
                        + "&entity_type="
                        + entity
                    )
                    listing = (await request("GET", trail)).json()
                    item = next(r for r in listing["items"] if r["action"] == entity + ".update")
                    detail_path = f'/audit/v1/audit-events/{item["id"]}'
                    query = {"company_id": str(company), "occurred_at": item["occurred_at"]}
                    detail = await http.get(gateway + detail_path, params=query, headers=headers)
                    assert detail.status_code == 200, detail.text
                    assert detail.json()["changes"][evidence_field] == {
                        "from": old_value,
                        "to": new_value,
                    }
                    assert detail.json()["trace_id"] == "a" * 32
                    forged = await http.get(
                        gateway + trail,
                        headers={"X-Actor-Context": "forged", "X-Actor-Signature": "0" * 64},
                    )
                    assert forged.status_code == 401
                    wrong = await http.get(
                        gateway + detail_path,
                        params=query | {"company_id": str(foreign)},
                        headers=headers,
                    )
                    assert wrong.status_code in (403, 404)
                    # Policies are resolved fresh at Identity, without rewriting stored hashes.
                    with tenant_scope(tenant):
                        async with identity.state.session_factory() as db, db.begin():
                            policy = build_field_policy(
                                tenant_id=tenant,
                                entity_type=entity,
                                field_key=evidence_field,
                                subject_type="user",
                                subject_id=user,
                                access="read",
                            )
                            db.add(policy)
                    denied = await http.get(gateway + detail_path, params=query, headers=headers)
                    assert evidence_field not in denied.json()["changes"]
                    exported = (
                        await request(
                            "POST", "/audit/v1/audit-events/export?company_id=" + str(company)
                        )
                    ).json()
                    assert exported["count"] == expected_events and all(
                        evidence_field not in (r["changes"] or {}) for r in exported["events"]
                    )
                    with tenant_scope(tenant):
                        async with identity.state.session_factory() as db, db.begin():
                            current_policy = await db.get(type(policy), policy.id)
                            current_policy.is_active = False
                    print("Native delivery, recovery, scope and policy passed", flush=True)
                    # Browser uses a real encrypted NextAuth session and this exact gateway.
                    await browser(
                        runtime, ports[0], gateway, console_port, token, company, processes
                    )
                    export_publisher = ConfirmedPublisher(
                        exchange, key_id="export", key=export_key, broker_user=broker_user
                    )
                    exported_count = await publish_batch(
                        audit.state.session_factory,
                        export_publisher,
                        event_types=export_key.operations,
                    )
                    assert exported_count.confirmed >= 1
                    for _ in range(exported_count.confirmed):
                        exported_message = await delivery(queue)
                        await receive_audit(
                            audit.state.session_factory,
                            exported_message,
                            sources=sources,
                            consumer_name=exchange_name,
                        )
                    with tenant_scope(tenant):
                        async with audit.state.session_factory() as db:
                            assert await verify_tenant_chain(db, tenant) == []
                    from verify_audit_workers import verify_workers

                    async def worker_canary():
                        await canary()
                        for _ in range(30):
                            with tenant_scope(tenant):
                                async with audit.state.session_factory() as db:
                                    delivered = list(await db.scalars(select(AuditEvent)))
                                    if (
                                        len(delivered)
                                        == expected_events + 1 + exported_count.confirmed
                                    ):
                                        assert await verify_tenant_chain(db, tenant) == []
                                        return
                            await asyncio.sleep(1)
                        raise AssertionError("worker canary was not ingested")

                    await verify_workers(
                        ROOT,
                        runtime,
                        {
                            service + ".env": {
                                service.upper() + "_DATABASE_URL": urls[0],
                                service.upper() + "_AUDIT_BROKER_URL": broker_url,
                                service.upper() + "_AUDIT_BROKER_USER": broker_user,
                                service.upper() + "_AUDIT_EVENT_SECRET": key.secret.hex(),
                                service.upper() + "_AUDIT_EXCHANGE": exchange_name,
                                service.upper() + "_AUDIT_EVENT_KEY_ID": "proof",
                            },
                            **(
                                {
                                    "accounting.env": {
                                        "ACCOUNTING_DATABASE_URL": urls[2],
                                        "ACCOUNTING_AUDIT_BROKER_URL": broker_url,
                                        "ACCOUNTING_AUDIT_BROKER_USER": broker_user,
                                        "ACCOUNTING_AUDIT_EVENT_SECRET": secrets.token_hex(32),
                                        "ACCOUNTING_AUDIT_EXCHANGE": exchange_name,
                                    }
                                }
                                if catalog_mode
                                else {}
                            ),
                            "audit.env": {
                                "AUDIT_DATABASE_URL": runtime_url,
                                "AUDIT_ACTOR_SIGNING_SECRET": secret,
                                "AUDIT_CURSOR_SIGNING_SECRET": secret,
                                "AUDIT_BROKER_URL": broker_url,
                                "AUDIT_CONSUMER_EXCHANGE": exchange_name,
                                "AUDIT_CONSUMER_QUEUE": exchange_name,
                                "AUDIT_CONSUMER_DEAD_LETTER_EXCHANGE": exchange_name + ".dlx",
                                "AUDIT_CONSUMER_NAME": exchange_name,
                                "AUDIT_SOURCE_CREDENTIALS": {
                                    "proof": {
                                        "issuer": service,
                                        "broker_user": broker_user,
                                        "secret": key.secret.hex(),
                                        "event_types": sorted(key.operations),
                                    },
                                    "audit.current": {
                                        "issuer": "audit",
                                        "broker_user": broker_user,
                                        "secret": export_key.secret.hex(),
                                        "event_types": ["audit.exported"],
                                    },
                                },
                            },
                            "audit-publisher.env": {
                                "AUDIT_PUBLISHER_DATABASE_URL": runtime_url,
                                "AUDIT_PUBLISHER_BROKER_URL": broker_url,
                                "AUDIT_PUBLISHER_BROKER_USER": broker_user,
                                "AUDIT_PUBLISHER_EVENT_SECRET": export_key.secret.hex(),
                                "AUDIT_PUBLISHER_EXCHANGE": exchange_name,
                            },
                        },
                        worker_canary,
                    )
                    # Verify duplicate-sequence detection using native PK ordering, then roll back.
                    with tenant_scope(tenant):
                        async with audit.state.session_factory() as db:
                            original = await db.scalar(
                                select(AuditEvent).order_by(AuditEvent.sequence).limit(1)
                            )
                            assert original is not None
                            copy = {
                                column.key: getattr(original, column.key)
                                for column in AuditEvent.__table__.columns
                            }
                            copy["id"] = uuid.uuid4()
                            db.add(AuditEvent(**copy))
                            await db.flush()
                            breaks = await verify_tenant_chain(db, tenant, page_size=1)
                            assert any("sequence" in item.reason for item in breaks)
                            await db.rollback()
                            assert await verify_tenant_chain(db, tenant, page_size=1) == []
                    proof_data = {
                        "invalid_payload_dead_letters": 2,
                        "duplicate_sequence_detection": "passed",
                        service + "_events": expected_events,
                        "worker_canary": 1,
                        "duplicate_rows": 0,
                        "exhausted_recovered": expected_events,
                        "dead_letter_recovered": 1,
                        "audit_export_events": exported_count.confirmed,
                        "chain_breaks": 0,
                        "confirmed_before_outbox_commit_cancel": "passed",
                        "native_database_failure_redelivery": "passed",
                        "key_rotation_retirement_and_delayed_signature": "passed",
                        "query_plans": "passed",
                        "partition_months_created": created,
                        "scope_and_live_policy": "passed",
                        "browser": "passed",
                        "encoded_gateway_scope": "passed",
                    }
                    (runtime / "result.json").write_text(json.dumps(proof_data, indent=2))
                    print(json.dumps(proof_data), flush=True)
                finally:
                    await queue.delete(if_unused=False, if_empty=False)
                    dead = await channel.get_queue(exchange_name + ".dead")
                    await dead.delete(if_unused=False, if_empty=False)
                    dlx = await channel.get_exchange(exchange_name + ".dlx")
                    await dlx.delete(if_unused=False)
                    await exchange.delete(if_unused=False)
    finally:
        if nginx_args:
            await asyncio.to_thread(execute, [*nginx_args, "-s", "quit"])
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    await asyncio.to_thread(
                        execute, ["taskkill", "/PID", str(process.pid), "/T", "/F"]
                    )
                else:
                    process.terminate()
                await asyncio.to_thread(process.wait, 15)
        for server in servers:
            server.should_exit = True
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for app in apps:
            await app.state.engine.dispose()
        await provider.aclose()
        await identity.state.oidc_http.aclose()


async def browser(
    runtime: Path,
    identity_port: int,
    gateway: str,
    chosen: int,
    access_token: str,
    company: uuid.UUID,
    processes: list[subprocess.Popen[bytes]],
) -> None:
    origin = f"http://127.0.0.1:{chosen}"
    env = dict(
        os.environ,
        AUTH_URL=origin,
        IDENTITY_URL=f"http://127.0.0.1:{identity_port}",
        AUDIT_GATEWAY_URL=gateway,
        NEXTAUTH_SECRET=secrets.token_hex(32),
        AUDIT_PROOF_TOKEN=access_token,
    )
    console = ROOT / "mfes/apps/console"
    encoded = await asyncio.to_thread(
        execute,
        [
            "node",
            "--input-type=module",
            "-e",
            "import {encode} from 'next-auth/jwt'; process.stdout.write(await encode({"
            "secret:process.env.NEXTAUTH_SECRET, token:{accessToken:process.env.AUDIT_PROOF_TOKEN,"
            "accessTokenExpires:Date.now()+3600000}, maxAge:3600}));",
        ],
        cwd=console,
        env=env,
    )
    assert encoded.returncode == 0, encoded.stderr
    env["AUDIT_PROOF_COOKIE"] = encoded.stdout
    env["AUDIT_PROOF_ORIGIN"] = origin
    env["AUDIT_PROOF_COMPANY"] = str(company)
    env["AUDIT_PROOF_SERVICE"] = os.environ.get("AUDIT_PROOF_SERVICE", "accounting")
    env["AUDIT_PROOF_ARTIFACTS"] = str(runtime)
    with (runtime / "console.log").open("w") as log:
        process = subprocess.Popen(  # noqa: S603 -- owned local console executable
            [
                __import__("shutil").which("node") or "node",
                str(console / "node_modules/next/dist/bin/next"),
                "dev",
                "-p",
                str(chosen),
                "--hostname",
                "127.0.0.1",
            ],
            cwd=console,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=FLAGS,
        )
        processes.append(process)
        async with httpx.AsyncClient(timeout=3) as http:
            for _ in range(120):
                try:
                    if (await http.get(origin + "/favicon.svg")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None:
                    raise AssertionError("console failed; inspect sanitized local console.log")
                await asyncio.sleep(0.5)
        result = await asyncio.to_thread(
            execute,
            [
                os.environ["AUDIT_TEST_BROWSER_PYTHON"],
                str(Path(__file__).with_name("verify_audit_browser.py")),
            ],
            env=env,
            timeout=300,
        )
        assert result.returncode == 0, result.stderr[-3500:]


def main() -> None:
    server = os.environ["AUDIT_TEST_MYSQL_SERVER_URL"]
    parsed = make_url(server)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.database:
        raise ValueError("explicit loopback server without a schema is required")
    nonce = uuid.uuid4().hex[:24]
    service = os.environ.get("AUDIT_PROOF_SERVICE", "accounting")
    if service not in {"catalog", "accounting"}:
        raise ValueError("unsupported proof service")
    services = (service, "audit", "accounting") if service == "catalog" else (service, "audit")
    names = [f"audit_proof_{nonce}_{name}" for name in services]
    urls = [parsed.set(database=name).render_as_string(hide_password=False) for name in names]
    runtime = ROOT / ".test_artifacts" / ("audit-proof-" + nonce)
    runtime.mkdir(parents=True)
    asyncio.run(provision(server, names, True))
    try:
        for service, url in zip(services, urls, strict=True):
            result = execute(
                [
                    str(ROOT / "apis" / service / ".venv/Scripts/python.exe"),
                    "-m",
                    "alembic",
                    "-c",
                    str(ROOT / "dbs" / service / "alembic.ini"),
                    "upgrade",
                    "head",
                ],
                cwd=ROOT / "dbs" / service,
                env=dict(os.environ, **{service.upper() + "_DATABASE_URL": url}),
            )
            assert result.returncode == 0, result.stderr[-2000:]
        grant_user, password = "ap_" + nonce, secrets.token_hex(32)
        asyncio.run(grant_runtime(server, names[1], grant_user, password, create=True))
        runtime_url = (
            make_url(urls[1])
            .set(username=grant_user, password=password)
            .render_as_string(hide_password=False)
        )
        try:
            asyncio.run(proof(urls, runtime, runtime_url))
        finally:
            asyncio.run(grant_runtime(server, names[1], grant_user, password, create=False))
        print("Native proof artifacts:", runtime)
    finally:
        asyncio.run(provision(server, names, False))


if __name__ == "__main__":
    main()
