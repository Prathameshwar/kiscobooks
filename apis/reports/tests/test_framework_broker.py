import asyncio
import os
import threading
import uuid
from urllib.parse import urlsplit

import pytest
from billing_platform.delivery import publish_batch
from celery.contrib.testing.worker import start_worker
from conftest import COMPANY, TENANT
from pydantic import SecretStr
from test_framework_execution import accepted

from reports.tasks.celery_app import application
from reports.tasks.framework_jobs import JOB_EVENTS
from reports.tasks.job_dispatcher import publish


async def test_bulk_dispatch_budget_is_independent_of_short_and_render_lanes(app, monkeypatch):
    from billing_platform.db.types import utcnow
    from billing_platform.delivery import OutgoingMessage
    from billing_platform.messages import MessageEnvelope

    settings = app.state.settings.model_copy(
        update={
            "job_broker_url": SecretStr("amqp://localhost"),
            "export_timeout_seconds": 600,
        }
    )
    worker = application(settings)
    deliveries = []
    monkeypatch.setattr(worker, "send_task", lambda *args, **kwargs: deliveries.append(kwargs))
    try:
        for lane in ("short", "bulk", "render"):
            envelope = MessageEnvelope(
                message_id=uuid.uuid4(),
                tenant_id=TENANT,
                event_type="reports.job." + lane,
                schema_version=1,
                occurred_at=utcnow(),
                payload={"company_id": str(COMPANY), "job_id": str(uuid.uuid4()), "version": 1},
            )
            await publish(
                worker,
                settings.job_queue_namespace,
                OutgoingMessage(
                    envelope.message_id,
                    envelope.event_type,
                    envelope.model_dump_json().encode(),
                ),
            )
        assert [delivery["time_limit"] for delivery in deliveries] == [60, 660, 90]
        assert [delivery["soft_time_limit"] for delivery in deliveries] == [55, 655, 85]
    finally:
        worker.close()


@pytest.mark.rabbitmq
async def test_confirmed_outbox_reaches_the_isolated_celery_lane(app, client, prefix):
    broker = os.environ.get("REPORTS_TEST_BROKER_URL")
    if not broker:
        pytest.skip("requires local RabbitMQ")
    assert urlsplit(broker).hostname in {"127.0.0.1", "localhost", "::1"}
    _path, row = await accepted(app, client, prefix)
    namespace = "reports.test_" + uuid.uuid4().hex
    settings = app.state.settings.model_copy(
        update={
            "job_broker_url": SecretStr(broker),
            "job_queue_namespace": namespace,
        }
    )
    received = []
    ready = threading.Event()

    def execute(tenant, company, identity):
        received.append((tenant, company, identity))
        ready.set()

    worker = application(settings, executor=execute)
    assert worker.conf.task_acks_late and worker.conf.worker_prefetch_multiplier == 1
    try:
        with start_worker(
            worker,
            pool="solo",
            concurrency=1,
            perform_ping_check=False,
            queues=[namespace + ".short"],
            shutdown_timeout=15,
        ):
            result = await publish_batch(
                app.state.session_factory,
                lambda outgoing: publish(worker, namespace, outgoing),
                event_types=JOB_EVENTS,
            )
            assert result.confirmed == 1 and result.deferred == 0
            assert await asyncio.to_thread(ready.wait, 10)
            assert received == [(str(TENANT), str(COMPANY), row["id"])]
            again = await publish_batch(
                app.state.session_factory,
                lambda outgoing: publish(worker, namespace, outgoing),
                event_types=JOB_EVENTS,
            )
            assert again.confirmed == 0
    finally:
        with worker.connection_for_write() as connection:
            channel = connection.channel()
            for lane in ("short", "bulk", "render"):
                channel.queue_delete(namespace + "." + lane)
            channel.exchange_delete(namespace + ".jobs")
        worker.close()
