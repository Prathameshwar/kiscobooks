"""Explicit RabbitMQ lanes; JSON-only tasks carry identities, never financial payloads."""

import uuid
from collections.abc import Callable

from celery import Celery
from kombu import Exchange, Queue

from reports.config import Settings
from reports.tasks.job_process import lane_seconds, run

TASK_NAME = "reports.execute_job"


def application(
    settings: Settings, *, executor: Callable[[str, str, str], None] | None = None
) -> Celery:
    if settings.job_broker_url is None:
        raise ValueError("Reports job broker must be configured")
    app = Celery("reports", broker=settings.job_broker_url.get_secret_value())
    namespace = settings.job_queue_namespace
    exchange = Exchange(namespace + ".jobs", type="direct", durable=True)
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
        worker_max_tasks_per_child=100,
        worker_max_memory_per_child=524288,
        task_soft_time_limit=55,
        task_time_limit=60,
        reports_lane_time_limits={
            lane.lower(): lane_seconds(settings, lane) for lane in ("SHORT", "BULK", "RENDER")
        },
        task_create_missing_queues=False,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"confirm_publish": True},
        broker_connection_timeout=5,
        task_publish_retry=False,
        timezone="UTC",
        enable_utc=True,
        task_default_queue=namespace + ".short",
        task_queues=tuple(
            Queue(
                namespace + "." + lane, exchange, routing_key=namespace + "." + lane, durable=True
            )
            for lane in ("short", "bulk", "render")
        ),
    )

    @app.task(name=TASK_NAME, ignore_result=True, bind=True)
    def run_job(task: object, tenant: str, company: str, identity: str) -> None:
        try:
            scope = (uuid.UUID(tenant), uuid.UUID(company), uuid.UUID(identity))
            if any(value.int == 0 for value in scope):
                raise ValueError("real report identities required")
            if executor is not None:
                executor(tenant, company, identity)
            else:
                from celery import Task

                if not isinstance(task, Task):
                    raise ValueError("report task context is unavailable")
                routing = (task.request.delivery_info or {}).get("routing_key")
                if routing is not None and routing not in {
                    namespace + "." + lane for lane in ("short", "bulk", "render")
                }:
                    raise ValueError("report task route is unavailable")
                lane = (
                    "SHORT"
                    if routing is None
                    else str(routing).removeprefix(namespace + ".").upper()
                )
                run(settings, scope, lane)
        except Exception as exc:
            # Broker logs must not include SQL parameters, secrets or report data.
            raise RuntimeError("report worker failed: " + type(exc).__name__) from None

    return app


def create_app() -> Celery:
    """Programmatic factory; use reports.tasks.job_dispatcher for the worker CLI."""
    return application(Settings.model_validate({}))
