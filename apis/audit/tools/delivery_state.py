"""Local audit inventory, contract preflight and explicit-ID exhausted-event recovery.

Run with Audit's interpreter. Private connections never appear in output or argv.
This operator tool reads infrastructure outboxes, never another owner's business tables.
"""

import argparse
import ast
import asyncio
import datetime as dt
import importlib.util
import json
import uuid
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

from billing_platform.db import create_engine, create_session_factory
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.messages import MessageEnvelope
from dotenv import dotenv_values
from sqlalchemy import func, select

from audit.domain.ingest import AuditEventPayload
from audit.domain.source_contract import validate_source

ROOT = Path(__file__).resolve().parents[3]


@cache
def literal_fields(path: Path, name: str) -> set[str]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value = node.value
            if isinstance(value, ast.Call) and value.args:
                argument = value.args[0]
                if (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Attribute)
                    and isinstance(argument.func.value, ast.Constant)
                ):
                    return set(str(argument.func.value.value).split())
                return set(ast.literal_eval(argument))
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            if isinstance(node.value, ast.Call) and node.value.args:
                value = node.value.args[0]
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "split"
                    and isinstance(value.func.value, ast.Constant)
                ):
                    return set(str(value.func.value.value).split())
                return set(ast.literal_eval(value))
    return set()


def evidence_valid(row: Outbox, issuer: str) -> None:
    """Review retained values against source-owned safe vocabularies before replay."""
    if issuer in {"catalog", "accounting"}:
        path = ROOT / "apis" / issuer / "contracts/audit-events.json"
        # Cache immutable contract metadata, never event payloads.
        if issuer not in _MATRICES:
            _MATRICES[issuer] = json.loads(path.read_text(encoding="utf-8"))
        allowed = set(_MATRICES[issuer].get(row.event_type, {}).get("safe_fields", []))
    elif issuer == "identity":
        # Copy cached metadata before adding route-specific exceptions.
        allowed = set(
            literal_fields(ROOT / "apis/identity/src/identity/api/audit.py", "_SAFE_FIELDS")
        )
        if row.event_type in {
            "voucher_source.discovery_read",
            "catalog_source.discovery_read",
            "report_source.discovery_read",
        }:
            allowed |= {"scope_count"}
        if row.event_type.startswith("platform."):
            allowed |= {
                "action",
                "attested",
                "needs_attention",
                "provider_active",
                "provider_verified",
                "count",
                "version",
                "command_id",
                "administrator_id",
                "assignment_id",
                "delivery",
                "code",
                "error_code",
            }
    elif issuer == "vouchers":
        allowed = {
            "counter_id",
            "user_id",
            "status",
            "state",
            "rows",
            "voucher_count",
            "created_count",
            "failed_count",
            "recipient_party_id",
            "channel",
            "message_id",
        }
    elif issuer == "notification":
        allowed = literal_fields(
            ROOT / "apis/notification/src/notification/audit.py", "_SAFE_VALUES"
        )
    elif issuer == "design":
        allowed = literal_fields(ROOT / "apis/design/src/design/events/evidence.py", "SAFE_FIELDS")
    else:
        allowed = set()
    changes = row.payload.get("changes") or {}
    if issuer == "notification" and isinstance(changes.get("fields"), list):
        changes = changes.get("values", {})
    for field, value in changes.items():
        marker = value == {"changed": True} or value == {"from": "[redacted]", "to": "[redacted]"}
        if field not in allowed and not marker:
            raise ValueError("retained field values need privacy review")


_MATRICES: dict[str, Any] = {}


def native_contracts() -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location(
        "audit_contracts", ROOT / "start/win/audit-contracts.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("native contract reader missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.contracts())


def payload_valid(row: Outbox, issuer: str) -> None:
    if row.tenant_id is None:
        raise ValueError("audit evidence requires a tenant reference")
    envelope = MessageEnvelope(
        message_id=row.message_id,
        tenant_id=row.tenant_id,
        event_type=row.event_type,
        schema_version=row.schema_version,
        occurred_at=row.occurred_at,
        trace_id=row.trace_id,
        payload=row.payload,
    )
    validate_source(envelope, issuer)
    AuditEventPayload.model_validate(envelope.payload)
    evidence_valid(row, issuer)


async def inventory(
    service: str,
    events: list[str],
    directory: Path,
    preflight: bool,
    selected: set[uuid.UUID],
    apply: bool,
) -> dict[str, Any]:
    owner = dotenv_values(directory / (service + ".env"), interpolate=False)
    publisher = (
        dotenv_values(directory / "audit-publisher.env", interpolate=False)
        if service == "audit"
        else owner
    )
    prefix = "AUDIT_PUBLISHER_" if service == "audit" else service.upper() + "_AUDIT_"
    audit = dotenv_values(directory / "audit.env", interpolate=False)
    sources = json.loads(audit.get("AUDIT_SOURCE_CREDENTIALS") or "{}")
    key_id = publisher.get(prefix + ("KEY_ID" if service == "audit" else "EVENT_KEY_ID"))
    source = sources.get(key_id, {})
    configured = bool(
        publisher.get(prefix + "BROKER_URL") == audit.get("AUDIT_BROKER_URL")
        and publisher.get(prefix + "BROKER_URL")
        and source.get("issuer") == service
        and source.get("secret") == publisher.get(prefix + "EVENT_SECRET")
        and source.get("broker_user") == publisher.get(prefix + "BROKER_USER")
        and set(source.get("event_types", [])) == set(events)
    )
    cutoff_value = publisher.get(prefix + "PUBLISH_AFTER")
    maximum_attempts = int(publisher.get(prefix + "MAXIMUM_ATTEMPTS") or 12)
    if not 1 <= maximum_attempts <= 32767:
        raise ValueError("invalid publisher attempt limit")
    cutoff = (
        dt.datetime.fromisoformat(cutoff_value.replace("Z", "+00:00")) if cutoff_value else None
    )
    engine = create_engine(str(owner[service.upper() + "_DATABASE_URL"]))
    factory = create_session_factory(engine)
    try:
        async with factory() as db, db.begin():
            pending = (Outbox.event_type.in_(events), Outbox.published_at.is_(None))
            eligible = (*pending, *((Outbox.occurred_at >= cutoff,) if cutoff else ()))
            held = (
                int(
                    await db.scalar(
                        select(func.count())
                        .select_from(Outbox)
                        .where(*pending, Outbox.occurred_at < cutoff)
                    )
                    or 0
                )
                if cutoff
                else 0
            )
            count = int(
                await db.scalar(select(func.count()).select_from(Outbox).where(*eligible)) or 0
            )
            exhausted = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Outbox)
                    .where(*eligible, Outbox.attempt_count >= maximum_attempts)
                )
                or 0
            )
            oldest = await db.scalar(select(func.min(Outbox.occurred_at)).where(*eligible))
            report: dict[str, Any] = {
                "service": service,
                "configured": configured,
                "pending": count,
                "historical_held": held,
                "exhausted": exhausted,
                "oldest_age_seconds": max(0, int((utcnow() - oldest).total_seconds()))
                if oldest
                else 0,
            }
            if preflight:
                invalid: Counter[str] = Counter()
                checked = 0
                # Fixed upper bound prevents ongoing traffic extending a scan indefinitely.
                boundary = await db.scalar(
                    select(Outbox.id).where(*eligible).order_by(Outbox.id.desc()).limit(1)
                )
                previous = None
                while boundary:
                    rows = list(
                        await db.scalars(
                            select(Outbox)
                            .where(
                                *eligible,
                                Outbox.id <= boundary,
                                *((Outbox.id > previous,) if previous else ()),
                            )
                            .order_by(Outbox.id)
                            .limit(250)
                        )
                    )
                    if not rows:
                        break
                    for row in rows:
                        checked += 1
                        try:
                            payload_valid(row, service)
                        except Exception as exc:
                            invalid[row.event_type + ":" + type(exc).__name__] += 1
                    previous = rows[-1].id
                report.update(checked=checked, invalid=dict(invalid))
            if selected:
                rows = list(
                    await db.scalars(
                        select(Outbox)
                        .where(
                            *eligible,
                            Outbox.message_id.in_(selected),
                        )
                        .with_for_update()
                    )
                )
                if len(rows) != len(selected) or not configured:
                    raise ValueError(
                        "recovery IDs must be eligible pending events with matching credentials"
                    )
                for row in rows:
                    payload_valid(row, service)
                report["reviewed_recovery"] = [
                    {"message_id": str(row.message_id), "event_type": row.event_type}
                    for row in rows
                ]
                if apply:
                    for row in rows:
                        row.attempt_count, row.last_error, row.available_at = 0, None, utcnow()
                    report["recovery_applied"] = True
            return report
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> None:
    contracts = native_contracts()
    selected = set(args.retry or [])
    if args.apply and not selected:
        raise ValueError("apply requires explicit reviewed message IDs")
    if selected and (
        args.service == "all" or len(selected) > 100 or len(selected) != len(args.retry)
    ):
        raise ValueError("select one service and at most 100 distinct message IDs")
    services = contracts if args.service == "all" else {args.service: contracts[args.service]}
    reports = []
    for service, events in services.items():
        try:
            reports.append(
                await inventory(
                    service, events, args.env_directory, args.preflight, selected, args.apply
                )
            )
        except Exception as exc:
            if selected:
                raise
            reports.append(
                {"service": service, "configured": False, "error_type": type(exc).__name__}
            )
    if args.broker:
        import aio_pika

        audit = dotenv_values(args.env_directory / "audit.env", interpolate=False)
        broker: dict[str, Any] = {"ready": False}
        try:
            async with await aio_pika.connect_robust(
                str(audit["AUDIT_BROKER_URL"]), timeout=5
            ) as connection:
                async with connection.channel() as channel:
                    name = audit.get("AUDIT_CONSUMER_QUEUE") or "audit.events.authenticated.v1"
                    queue = await channel.declare_queue(name, passive=True)
                    dead = await channel.declare_queue(name + ".dead", passive=True)
                    queued = int(queue.declaration_result.message_count or 0)
                    rejected = int(dead.declaration_result.message_count or 0)
                    consumers = int(queue.declaration_result.consumer_count or 0)
                    broker.update(
                        ready=consumers > 0 and rejected == 0 and queued < 500,
                        queued=queued,
                        dead_letters=rejected,
                        consumers=consumers,
                    )
        except Exception as exc:
            broker["error_type"] = type(exc).__name__
        reports.append({"service": "broker", "configured": broker["ready"], "broker": broker})
    print(json.dumps(reports, sort_keys=True))
    if any(
        not row.get("configured")
        or row.get("exhausted")
        or row.get("invalid")
        or row.get("oldest_age_seconds", 0) > 300
        for row in reports
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--service",
        choices=(
            "all",
            "identity",
            "audit",
            "catalog",
            "accounting",
            "vouchers",
            "reports",
            "notification",
            "design",
        ),
        default="all",
    )
    parser.add_argument("--env-directory", type=Path, default=ROOT / "start/win/env")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--broker", action="store_true", help="inspect existing queues without creating bindings"
    )
    parser.add_argument("--retry", type=uuid.UUID, action="append")
    parser.add_argument("--apply", action="store_true")
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as exc:
        raise SystemExit("Audit delivery check failed: " + type(exc).__name__) from None
