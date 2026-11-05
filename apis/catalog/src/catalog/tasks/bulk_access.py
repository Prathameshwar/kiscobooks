"""Scoped job access and private review evidence, with current field authorization."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from pydantic import BaseModel
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.field_registry import registry
from catalog.models.bulk import BulkJob
from catalog.tasks.field_context import READ_PERMISSIONS, FieldContext, load_field_context


def resource_entity(resource: str) -> str:
    """Transport alias retains the native item's authorization and evidence."""
    return "catalog.item" if resource == "simple_product" else "catalog." + resource


def wire(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: wire(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [wire(child) for child in value]
    return value


def native(row: Any) -> dict[str, Any]:
    fields = registry.get("catalog." + row.__tablename__).fields
    values = {key: getattr(row, key) for key in fields}
    values.update(
        {
            "custom_field:" + key: value
            for key, value in (getattr(row, "custom_fields", None) or {}).items()
        }
    )
    return {key: wire(value) for key, value in values.items()}


async def require_bulk(
    db: AsyncSession, actor: Actor, company: uuid.UUID, permission: str = "catalog.bulk.read"
) -> FieldContext:
    actor.require_scope(permission, target=ScopePath(company_id=company))
    return await load_field_context(db, actor, company, "catalog.bulk_job")


async def scoped_job(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    job_id: uuid.UUID,
    *,
    lock: bool = False,
    live: bool = False,
) -> BulkJob:
    await require_bulk(db, actor, company)
    job = await company_object(db, BulkJob, job_id, company_id=company, lock=lock)
    if job.actor_user_id != actor.user_id:
        raise PermissionDeniedError("bulk job belongs to another actor")
    if live and job.expires_at <= utcnow():
        raise ConflictError("bulk review expired; create a new job for uncommitted work")
    return job


class Evidence:
    """Retain only Catalog dependencies read by ordinary command handlers.

    The company generation fences domain changes including inserts/absences. Row
    versions add explicit identity pins; values allow conditional read rules to be
    checked again before any saved preview is returned.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.session = db.sync_session
        self.rows: dict[tuple[str, uuid.UUID], Any] = {}
        self.before: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
        self.created: set[tuple[str, uuid.UUID]] = set()
        self.byte_count = 0

    def capture(self, session: Any, row: Any) -> None:
        table = getattr(row, "__tablename__", "")
        entity = "catalog." + table
        if entity not in READ_PERMISSIONS or table.startswith("bulk_"):
            return
        key = table, row.id
        if key not in self.rows:
            if len(self.rows) >= 10000:
                raise ConflictError("bulk dependency set exceeds the review bound")
            captured = {
                "resource": table,
                "id": str(row.id),
                "version": getattr(row, "row_version", None),
                "values": native(row),
            }
            try:
                self.byte_count += len(canonical_json(captured, maximum_bytes=256 * 1024))
            except ValueError as exc:
                raise ConflictError(
                    "bulk dependency evidence exceeds the review byte bound"
                ) from exc
            if self.byte_count > 256 * 1024:
                raise ConflictError("bulk dependency evidence exceeds the review byte bound")
            self.rows[key], self.before[key] = row, captured

    def new(self, session: Any, row: Any) -> None:
        self.capture(session, row)
        key = getattr(row, "__tablename__", ""), getattr(row, "id", None)
        if key in self.rows:
            self.created.add(key)

    def __enter__(self) -> "Evidence":
        for row in list(self.session.identity_map.values()):
            self.capture(self.session, row)
        event.listen(self.session, "loaded_as_persistent", self.capture)
        event.listen(self.session, "pending_to_persistent", self.new)
        return self

    def __exit__(self, *args: Any) -> None:
        event.remove(self.session, "loaded_as_persistent", self.capture)
        event.remove(self.session, "pending_to_persistent", self.new)

    def pins(self) -> list[dict[str, Any]]:
        return [value for key, value in self.before.items() if key not in self.created]

    def named_created(self) -> dict[str, str]:
        grouped: dict[str, list[str]] = {}
        for table, key in self.created:
            grouped.setdefault(table, []).append(str(key))
        return {table: ids[0] for table, ids in grouped.items() if len(ids) == 1}

    def changes(self) -> list[dict[str, Any]]:
        changes = []
        for key, row in self.rows.items():
            before = None if key in self.created else self.before[key]["values"]
            after = None if row in self.session.deleted else native(row)
            if before != after:
                changes.append({"resource": key[0], "before": before, "after": after})
        return changes


async def readable_evidence(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    evidence: list[dict[str, Any]],
    *,
    contexts: dict[str, FieldContext] | None = None,
) -> None:
    contexts = {} if contexts is None else contexts
    for pin in evidence:
        resource = pin["resource"]
        if resource not in contexts:
            contexts[resource] = await load_field_context(
                db, actor, company, resource_entity(resource)
            )
        values = pin["values"]
        if not values.keys() <= contexts[resource].readable(values):
            raise PermissionDeniedError(
                "bulk review contains fields the actor cannot currently read"
            )


async def verify_pins(
    db: AsyncSession, actor: Actor, company: uuid.UUID, pins: list[dict[str, Any]]
) -> None:
    await readable_evidence(db, actor, company, pins)
    models = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}
    for pin in sorted(pins, key=lambda value: (value["resource"], value["id"])):
        row = await company_object(
            db, models[pin["resource"]], uuid.UUID(pin["id"]), company_id=company, lock=True
        )
        if (pin["version"] is not None and row.row_version != pin["version"]) or (
            pin["version"] is None and native(row) != pin["values"]
        ):
            raise ConflictError("a reviewed dependency changed; validate the job again")
