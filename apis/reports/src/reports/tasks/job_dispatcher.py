"""Confirmed outbox dispatch and repair of queued/expired work after crashes or outages."""

import asyncio
import datetime as dt
import uuid

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import OutgoingMessage, publish_batch
from billing_platform.messages import MessageEnvelope
from celery import Celery
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.models.framework import ReportJob
from reports.tasks import framework_jobs as jobs
from reports.tasks.celery_app import TASK_NAME, application


async def publish(app: Celery, namespace: str, outgoing: OutgoingMessage) -> bool:
    if outgoing.routing_key not in jobs.JOB_EVENTS:
        raise ValueError("unknown report job route")
    envelope = MessageEnvelope.model_validate_json(outgoing.body)
    payload = envelope.payload
    if envelope.tenant_id is None or envelope.schema_version != 1 or payload.get("version") != 1:
        raise ValueError("invalid report dispatch contract")
    company, identity = uuid.UUID(payload["company_id"]), uuid.UUID(payload["job_id"])
    lane = outgoing.routing_key.rsplit(".", 1)[1]
    queue = namespace + "." + lane
    hard_limit = int(app.conf.reports_lane_time_limits[lane])

    def send() -> None:
        app.send_task(
            TASK_NAME,
            args=[str(envelope.tenant_id), str(company), str(identity)],
            task_id=str(outgoing.message_id),
            queue=queue,
            routing_key=queue,
            mandatory=True,
            retry=False,
            delivery_mode=2,
            time_limit=hard_limit,
            soft_time_limit=hard_limit - 5,
        )

    await asyncio.to_thread(send)
    return True  # RabbitMQ publisher confirmation is enabled; failures raise above.


async def repair(factory: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    from reports.tasks.enrollment import retained_scopes

    scopes = await retained_scopes(settings)
    repaired = 0
    for tenant, company in sorted(scopes):
        with tenant_scope(tenant):
            async with factory() as db, db.begin():
                await jobs.quota_lock(db)
                now = utcnow()
                pending = list(
                    await db.scalars(
                        select(ReportJob)
                        .where(
                            ReportJob.company_id == company,
                            ReportJob.available_at <= now,
                            or_(
                                ReportJob.status == "QUEUED",
                                (ReportJob.status == "RUNNING") & (ReportJob.lease_until <= now),
                                (ReportJob.status == "FAILED")
                                & (ReportJob.attempt < 3)
                                & (ReportJob.failure_code == "DEPENDENCY_UNAVAILABLE"),
                            ),
                        )
                        .order_by(ReportJob.id)
                        .limit(20)
                        .with_for_update()
                    )
                )
                for job in pending:
                    if job.status == "FAILED":
                        try:
                            await jobs.retry(db, company, job.id)
                            repaired += 1
                        except jobs.QuotaExceededError:
                            pass  # Try again after an admission slot becomes available.
                        continue
                    # Outbox is platform infrastructure; explicitly scope this lookup too.
                    latest = await db.scalar(
                        select(Outbox)
                        .where(
                            Outbox.tenant_id == tenant,
                            Outbox.aggregate_id == job.id,
                            Outbox.event_type.in_(jobs.JOB_EVENTS),
                        )
                        .order_by(Outbox.id.desc())
                        .limit(1)
                    )
                    if latest is not None and (
                        latest.published_at is None
                        or latest.occurred_at > now - dt.timedelta(seconds=15)
                    ):
                        continue
                    jobs.dispatch(db, job)
                    repaired += 1
    return repaired


async def run(settings: Settings) -> None:
    from billing_platform.polling import repeat

    app = application(settings)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)

    async def cycle() -> None:
        await repair(factory, settings)
        await publish_batch(
            factory,
            lambda message: publish(app, settings.job_queue_namespace, message),
            event_types=jobs.JOB_EVENTS,
            limit=20,
        )

    try:
        await repeat(cycle, interval=1)
    finally:
        app.close()
        await engine.dispose()


def main() -> None:
    import argparse

    import dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--worker", choices=("short", "bulk", "render"))
    parser.add_argument("--pool", choices=("solo", "prefork"), default="prefork")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    if args.env_file:
        dotenv.load_dotenv(args.env_file)
    if not 1 <= args.concurrency <= 8:
        raise SystemExit("concurrency must be between 1 and 8")
    settings = Settings.model_validate({})
    if args.worker:
        app = application(settings)
        app.worker_main(
            [
                "worker",
                "--pool",
                args.pool,
                "--concurrency",
                str(args.concurrency),
                "--queues",
                settings.job_queue_namespace + "." + args.worker,
                "--loglevel",
                "WARNING",
                "--without-gossip",
                "--without-mingle",
            ]
        )
    else:
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
