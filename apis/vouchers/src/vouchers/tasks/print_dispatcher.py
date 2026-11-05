"""Confirmed Celery dispatch from the outbox, with bounded crash-recovery repair."""

import asyncio
import uuid
from collections.abc import Callable

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import OutgoingMessage, publish_batch
from billing_platform.messages import MessageEnvelope
from celery import Celery
from kombu import Exchange, Queue
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.config import PrintRuntime
from vouchers.models.printing import VoucherPrintJob
from vouchers.tasks.print_worker import DISPATCH_EVENT, dispatch, run, sandbox_enabled

QUEUE = "vouchers.purchase.print"
TASK = "vouchers.purchase.render"


def application(
    settings: PrintRuntime, *, executor: Callable[[str, str, str], None] | None = None
) -> Celery:
    if settings.print_broker_url is None:
        raise ValueError("Purchase print broker must be configured")
    app = Celery("vouchers-print", broker=settings.print_broker_url.get_secret_value())
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_acks_on_failure_or_timeout=False,
        worker_prefetch_multiplier=1,
        worker_enable_remote_control=False,
        worker_max_tasks_per_child=50,
        worker_max_memory_per_child=524288,
        task_create_missing_queues=False,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=5,
        broker_transport_options={"confirm_publish": True},
        task_publish_retry=False,
        task_default_queue=QUEUE,
        timezone="UTC",
        enable_utc=True,
        task_queues=(
            Queue(
                QUEUE, Exchange(QUEUE, type="direct", durable=True), routing_key=QUEUE, durable=True
            ),
        ),
        task_time_limit=settings.print_timeout_seconds + 20,
        task_soft_time_limit=settings.print_timeout_seconds + 15,
    )

    @app.task(name=TASK, ignore_result=True)
    def render_job(tenant: str, company: str, identity: str) -> None:
        try:
            for value in (tenant, company, identity):
                if uuid.UUID(value).int == 0:
                    raise ValueError("real print identities required")
            if executor:
                executor(tenant, company, identity)
            else:
                run(settings, tenant, company, identity)
        except Exception as error:
            raise RuntimeError("Purchase print worker failed: " + type(error).__name__) from None

    return app


async def publish(app: Celery, outgoing: OutgoingMessage) -> bool:
    envelope = MessageEnvelope.model_validate_json(outgoing.body)
    if (
        outgoing.routing_key != DISPATCH_EVENT
        or envelope.tenant_id is None
        or envelope.schema_version != 1
        or envelope.payload.get("version") != 1
    ):
        raise ValueError("invalid Purchase print dispatch")
    company, identity = (
        uuid.UUID(envelope.payload["company_id"]),
        uuid.UUID(envelope.payload["job_id"]),
    )
    await asyncio.to_thread(
        app.send_task,
        TASK,
        args=[str(envelope.tenant_id), str(company), str(identity)],
        task_id=str(outgoing.message_id),
        queue=QUEUE,
        routing_key=QUEUE,
        mandatory=True,
        retry=False,
        delivery_mode=2,
    )
    return True


async def repair(factory: async_sessionmaker[AsyncSession], settings: PrintRuntime) -> int:
    repaired = 0
    for scope in settings.print_scopes:
        with tenant_scope(scope.tenant_id):
            async with factory() as db, db.begin():
                jobs = list(
                    await db.scalars(
                        select(VoucherPrintJob)
                        .where(
                            VoucherPrintJob.company_id == scope.company_id,
                            or_(
                                VoucherPrintJob.status == "PENDING",
                                (VoucherPrintJob.status == "RUNNING")
                                & (VoucherPrintJob.lease_until <= utcnow()),
                            ),
                        )
                        .order_by(VoucherPrintJob.id)
                        .limit(20)
                        .with_for_update()
                    )
                )
                for job in jobs:
                    latest = await db.scalar(
                        select(Outbox)
                        .where(
                            Outbox.tenant_id == scope.tenant_id,
                            Outbox.aggregate_id == job.id,
                            Outbox.event_type == DISPATCH_EVENT,
                        )
                        .order_by(Outbox.id.desc())
                        .limit(1)
                    )
                    if latest is not None and (
                        latest.published_at is None
                        or (utcnow() - latest.occurred_at).total_seconds() < 30
                    ):
                        continue
                    dispatch(db, job)
                    repaired += 1
    return repaired


async def serve(settings: PrintRuntime) -> None:
    from billing_platform.polling import repeat

    app = application(settings)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)

    async def cycle() -> None:
        await repair(factory, settings)
        await publish_batch(
            factory,
            lambda message: publish(app, message),
            event_types=frozenset({DISPATCH_EVENT}),
            limit=20,
        )

    try:
        await repeat(cycle, interval=1)
    finally:
        app.close()
        await engine.dispose()


def announce_sandbox(settings: PrintRuntime) -> None:
    """Startup line for both the dispatcher and the worker: a disabled sandbox is never silent."""
    sandbox_enabled(settings)


def main() -> None:
    import argparse

    import dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--pool", choices=("solo", "prefork"), default="prefork")
    args = parser.parse_args()
    if args.env_file:
        dotenv.load_dotenv(args.env_file)
    settings = PrintRuntime.model_validate({})
    announce_sandbox(settings)
    if args.worker:
        application(settings).worker_main(
            [
                "worker",
                "--pool",
                args.pool,
                "--concurrency",
                "1",
                "--queues",
                QUEUE,
                "--loglevel",
                "WARNING",
                "--without-gossip",
                "--without-mingle",
            ]
        )
    else:
        asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
