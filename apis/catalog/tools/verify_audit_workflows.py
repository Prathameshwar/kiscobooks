"""Native Catalog workflows -> confirmed RabbitMQ -> independently migrated Audit schema.

Uses only the explicit loopback test MySQL and bill_identity_test broker vhost. The existing
Catalog verifier provisions and removes its own schema and upgrades all migrations.
No application schema changes are made by this work.
"""

import asyncio
import inspect
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
import httpx
import pytest
from billing_platform.broker import (
    BrokerSource,
    ConfirmedPublisher,
    confirmed_channel,
    declare_consumer_queue,
)
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.delivery import publish_batch
from billing_platform.ids import uuid7
from billing_platform.service_auth import ServiceKey
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url

from catalog.config import Settings
from catalog.events.audit_contract import AUDIT_EVENTS
from catalog.main import create_app
from catalog.models import Outbox
from tests.conftest import ACTOR_SECRET, stable_product_source_clock
from tests.test_bulk_transports import test_transport_templates_and_signed_private_reports
from tests.test_pricing_publication import test_fixed_price_publication_retains_history
from tests.test_products import test_simple_product_roundtrip
from tests.test_tax_workflows import test_tax_publication_is_dated_atomic_and_replayable
from tools.mysql_smoke import ROOT, run_verifier, schema


async def verify(url: str) -> dict[str, object]:
    sys.path.insert(0, str(ROOT / "apis/audit/src"))
    # Resolved off the path inserted above, never as a dependency: Catalog depending on the Audit
    # package would make the two services deploy together, which is exactly what this end-to-end
    # check exists to avoid needing. mypy cannot see a runtime path insert.
    from audit.models import AuditEvent  # type: ignore[import-not-found]
    from audit.tasks.consume import receive_audit  # type: ignore[import-not-found]
    from audit.tasks.verify import verify_tenant_chain  # type: ignore[import-not-found]

    server = os.environ["CATALOG_TEST_MYSQL_SERVER_URL"]
    broker_url = os.environ["IDENTITY_TEST_BROKER_URL"]
    broker_user = os.environ["IDENTITY_TEST_BROKER_USER"]
    parsed_broker = make_url(broker_url.replace("amqp://", "mysql://", 1))
    if (
        parsed_broker.host not in {"localhost", "127.0.0.1"}
        or parsed_broker.database != "bill_identity_test"
    ):
        raise ValueError("isolated local test broker required")
    database = "catalog_test_" + uuid.uuid4().hex
    audit_url = make_url(server).set(database=database).render_as_string(hide_password=False)
    await schema(server, database, create=True)
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    engine = create_engine(audit_url)
    factory = create_session_factory(engine)
    import secrets

    key = ServiceKey("catalog", "audit", AUDIT_EVENTS, secrets.token_bytes(32))
    exchange_name = "catalog-audit-workflows-" + uuid.uuid4().hex
    results = {}
    try:
        migrated = await asyncio.to_thread(
            subprocess.run,
            [
                str(ROOT / "apis/audit/.venv/Scripts/python.exe"),
                "-m",
                "alembic",
                "-c",
                str(ROOT / "dbs/audit/alembic.ini"),
                "upgrade",
                "head",
            ],
            cwd=ROOT / "dbs/audit",
            env=dict(os.environ, AUDIT_DATABASE_URL=audit_url),
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert migrated.returncode == 0, migrated.stderr[-2000:]
        async with confirmed_channel(broker_url) as channel:
            exchange = await channel.declare_exchange(
                exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await declare_consumer_queue(
                channel,
                exchange_name=exchange_name,
                queue_name=exchange_name,
                dead_letter_exchange=exchange_name + ".dlx",
                routes=tuple(sorted(AUDIT_EVENTS)),
                single_active_consumer=True,
            )
            try:
                publisher = ConfirmedPublisher(
                    exchange, key_id="proof", key=key, broker_user=broker_user
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://catalog.test",
                ) as client:
                    workflows: list[tuple[str, Callable[..., Awaitable[None]], dict[str, Any]]] = [
                        ("product_goods", test_simple_product_roundtrip, {"kind": "GOODS"}),
                        ("product_service", test_simple_product_roundtrip, {"kind": "SERVICE"}),
                        ("pricing", test_fixed_price_publication_retains_history, {}),
                        ("tax", test_tax_publication_is_dated_atomic_and_replayable, {}),
                        (
                            "bulk_csv",
                            test_transport_templates_and_signed_private_reports,
                            {"kind": "CSV"},
                        ),
                        (
                            "bulk_xlsx",
                            test_transport_templates_and_signed_private_reports,
                            {"kind": "XLSX"},
                        ),
                    ]
                    for name, workflow, kwargs in workflows:
                        tenant = uuid7()
                        # One workflow represents one authorization interval, even on slow hosts.
                        # Real expiry is covered separately, including the gateway proof.
                        with pytest.MonkeyPatch.context() as clock:
                            inspect.unwrap(stable_product_source_clock)(clock)
                            await workflow(client, app.state.session_factory, tenant, **kwargs)
                        with tenant_scope(tenant):
                            async with app.state.session_factory() as db:
                                pending = list(
                                    await db.scalars(
                                        select(Outbox).where(
                                            Outbox.tenant_id == tenant,
                                            Outbox.event_type.in_(AUDIT_EVENTS),
                                        )
                                    )
                                )
                        assert pending
                        expected = {event.message_id for event in pending}
                        published = 0
                        while published < len(expected):
                            batch = await publish_batch(
                                app.state.session_factory, publisher, event_types=AUDIT_EVENTS
                            )
                            assert batch.confirmed > 0 and batch.deferred == 0, (
                                name,
                                published,
                                len(expected),
                                batch,
                            )
                            published += batch.confirmed
                        for _ in expected:
                            delivery = await queue.get(timeout=10)
                            await receive_audit(
                                factory,
                                delivery,
                                sources={"proof": BrokerSource(key, broker_user)},
                                consumer_name=exchange_name,
                            )
                        with tenant_scope(tenant):
                            async with factory() as db:
                                events = list(await db.scalars(select(AuditEvent)))
                                assert {event.message_id for event in events} == expected
                                assert await verify_tenant_chain(db, tenant, page_size=1) == []
                                assert all(
                                    event.source_service == "catalog" and event.company_id
                                    for event in events
                                )
                                if name.startswith("bulk"):
                                    assert any(
                                        event.action == "catalog.bulk_job.export"
                                        and event.category == "access"
                                        for event in events
                                    )
                        results[name] = len(events)
                        print(
                            f"Native {name}: {len(events)} events; IDs and chain passed",
                            flush=True,
                        )
            finally:
                await channel.queue_delete(exchange_name, if_unused=False, if_empty=False)
                await channel.queue_delete(exchange_name + ".dead", if_unused=False, if_empty=False)
                await channel.exchange_delete(exchange_name, if_unused=False)
                await channel.exchange_delete(exchange_name + ".dlx", if_unused=False)
        artifact = ROOT / ".test_artifacts/catalog-audit-workflows"
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return {"events": results, "chain_breaks": 0}
    finally:
        await app.state.engine.dispose()
        await engine.dispose()
        await schema(server, database, create=False)


if __name__ == "__main__":
    # Existing revision 0131 deliberately forbids downgrade; this proof changes no schema.
    run_verifier(verify, roundtrip=False)
