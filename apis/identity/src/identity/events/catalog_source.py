"""Transactionally publish approved Identity facts for Catalog, never audit deltas.

Identity request/worker sessions explicitly enable capture. Every captured writer
locks the tenant generation before its native flush; snapshot readers acquire the
same lock before reading native records. No network call occurs in a transaction.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.claims import candidate_statement
from billing_platform.db.platform_models import Outbox
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import ClauseElement, Table, event, inspect, select, update
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.util import find_tables

from identity import models
from identity.models.catalog_source import CatalogSourceGeneration

CONTRACT = "identity.catalog_context.v2"
CAPTURE_KEY = "identity_catalog_capture"


@dataclass(frozen=True)
class SourceSpec:
    model: Any
    fields: tuple[str, ...]
    scope: str  # company_identity, company, definition, policy, assignment, tenant


SOURCE_SPECS = {
    "company": SourceSpec(
        models.Company,
        (
            "code",
            "display_name",
            "status",
            "country_code",
            "state_code",
            "base_currency",
            "reporting_currency",
            "fiscal_year_start_month",
            "fiscal_year_start_day",
            "amount_precision",
            "quantity_precision",
            "rounding_mode",
            "default_tax_system",
            "timezone",
            "first_posted_at",
        ),
        "company_identity",
    ),
    "feature": SourceSpec(
        models.CompanyFeature,
        (
            "company_id",
            "feature_key",
            "is_enabled",
            "locked_at",
        ),
        "company",
    ),
    "currency_allowance": SourceSpec(
        models.CompanyCurrencyAllowance,
        ("company_id", "currency_code", "is_active"),
        "company",
    ),
    "custom_definition": SourceSpec(
        models.CustomFieldDefinition,
        (
            "company_id",
            "entity_type",
            "key",
            "label",
            "help_text",
            "placeholder",
            "data_type",
            "display_order",
            "display_group",
            "is_active",
            "is_searchable",
            "is_immutable_after_create",
            "requires_adoption",
            "requires_feature",
            "validation",
            "options",
            "option_source_key",
            "depends_on_key",
            "visibility",
            "sequence_config",
            "default_value",
        ),
        "definition",
    ),
    "field_config": SourceSpec(
        models.FieldConfig,
        (
            "company_id",
            "entity_type",
            "field_source",
            "field_key",
            "definition_id",
            "is_visible",
            "is_required",
            "display_order",
            "display_group",
            "label_override",
            "help_text_override",
            "default_value",
        ),
        "definition",
    ),
    "field_policy": SourceSpec(
        models.FieldPolicy,
        (
            "subject_type",
            "subject_id",
            "entity_type",
            "field_key",
            "access",
            "effect",
            "scope_type",
            "scope_id",
            "condition",
            "is_active",
        ),
        "policy",
    ),
    "role_assignment": SourceSpec(
        models.RoleAssignment,
        (
            "subject_type",
            "subject_id",
            "role_id",
            "scope_type",
            "scope_id",
            "is_active",
            "valid_from",
            "valid_to",
        ),
        "assignment",
    ),
    "group_member": SourceSpec(models.UserGroupMember, ("user_group_id", "user_id"), "tenant"),
    "user": SourceSpec(models.User, ("status",), "tenant"),
    "group": SourceSpec(models.UserGroup, ("is_active",), "tenant"),
    "role": SourceSpec(models.Role, ("is_active",), "tenant"),
}
_BY_MODEL = {spec.model: (kind, spec) for kind, spec in SOURCE_SPECS.items()}


def _wire(value: Any) -> Any:
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _wire(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_wire(child) for child in value]
    return value


def record_for(kind: str, row: Any, *, deleted: bool = False) -> SnapshotRecord:
    spec = SOURCE_SPECS[kind]
    return SnapshotRecord(
        kind=kind,
        id=row.id,
        deleted=deleted,
        data={} if deleted else {key: _wire(getattr(row, key)) for key in spec.fields},
    )


def lock_generation(session: Session, tenant_id: uuid.UUID) -> int:
    current = lock_current_generation(session, tenant_id)
    if current >= 2**63 - 1:
        raise ConflictError("Identity source generation is exhausted")
    table = cast(Table, CatalogSourceGeneration.__table__)
    session.connection().execute(
        update(table).where(table.c.tenant_id == tenant_id).values(version=current + 1)
    )
    return current + 1


def lock_current_generation(session: Session, tenant_id: uuid.UUID) -> int:
    if tenant_id != require_current_tenant() or tenant_id == SCOPE_ALL:
        raise ValidationFailedError("source generation requires the current real tenant")
    connection = session.connection()
    # Fixed internal single-row claim; all SQL is parameterized by verified tenant.
    connection.execute(
        candidate_statement(
            connection.dialect.name, CatalogSourceGeneration, {"tenant_id": tenant_id, "version": 1}
        )
    )
    table = cast(Table, CatalogSourceGeneration.__table__)
    current = connection.execute(
        select(table.c.version).where(table.c.tenant_id == tenant_id).with_for_update()
    ).scalar_one()
    return int(current)


@event.listens_for(Session, "before_flush")
def capture_changes(session: Session, context: Any, instances: Any) -> None:
    if not session.info.get(CAPTURE_KEY):
        return
    pending = []
    authority_changes = 0
    for row in session.new | session.dirty | session.deleted:
        entry = _BY_MODEL.get(type(row))
        if entry is None:
            if type(row) is not models.RolePermission or row.tenant_id == SCOPE_ALL:
                continue
            state = inspect(row)
            if row.tenant_id != require_current_tenant() or (
                state.persistent
                and any(state.attrs[name].history.has_changes() for name in ("id", "tenant_id"))
            ):
                raise ValidationFailedError("Identity permission source ownership is immutable")
            if row not in session.dirty or session.is_modified(row, include_collections=False):
                authority_changes += 1
            continue
        state = inspect(row)
        if state.persistent and any(
            state.attrs[name].history.has_changes() for name in ("id", "tenant_id")
        ):
            raise ValidationFailedError("Identity source ownership is immutable")
        # Shared roles are immutable to tenant routes; seeds have their own explicit
        # source bootstrap. New complete snapshots always advance a fresh generation.
        if row.tenant_id == SCOPE_ALL:
            continue
        if hasattr(row, "entity_type") and not row.entity_type.startswith("catalog."):
            # Company.entity_type describes its legal form, not a field owner.
            if entry[0] in {"custom_definition", "field_config", "field_policy"}:
                previous = state.attrs.entity_type.history.deleted
                if not any(value.startswith("catalog.") for value in previous):
                    continue
                # A source leaving this owner's namespace removes its former fact.
                if row.tenant_id != require_current_tenant():
                    raise ValidationFailedError("Identity source writer crossed tenant scope")
                pending.append((entry[0], row, True))
                continue
        if row.tenant_id != require_current_tenant():
            raise ValidationFailedError("Identity source writer crossed tenant scope")
        if row in session.dirty and not session.is_modified(row, include_collections=False):
            continue
        pending.append((entry[0], row, row in session.deleted))
    if not pending and not authority_changes:
        return
    if len(pending) + authority_changes > 1000:
        raise ValidationFailedError("Identity atomic source change exceeds record bound")
    version = lock_generation(session, require_current_tenant())
    session.info["identity_catalog_pending"] = (version, pending)


@event.listens_for(Session, "after_flush_postexec")
def publish_changes(session: Session, context: Any) -> None:
    batch = session.info.pop("identity_catalog_pending", None)
    if batch is None:
        return
    version, pending = batch
    records = [
        record_for(kind, row, deleted=deleted).model_dump(mode="json")
        for kind, row, deleted in pending
    ]
    records.sort(key=lambda row: (row["kind"], row["id"]))
    session.add(source_outbox(require_current_tenant(), version, records))


def source_outbox(tenant: uuid.UUID, version: int, records: list[dict[str, Any]]) -> Outbox:
    now = utcnow()
    payload = {
        "contract": CONTRACT,
        "tenant_id": str(tenant),
        "source_version": version,
        "previous_version": version - 1,
        "records": records,
        "generated_at": now.isoformat(),
    }
    try:
        canonical_json(payload, maximum_bytes=512 * 1024)
    except ValueError as exc:
        raise ValidationFailedError("Identity source change exceeds safe transport bounds") from exc
    return Outbox(
        id=uuid7(),
        message_id=uuid7(),
        tenant_id=tenant,
        aggregate_type="identity.catalog_context",
        aggregate_id=tenant,
        event_type="identity.catalog_context.changed",
        schema_version=1,
        payload=payload,
        occurred_at=now,
        available_at=now,
        attempt_count=0,
    )


@event.listens_for(Session, "after_soft_rollback")
def discard_pending(session: Session, previous_transaction: Any) -> None:
    session.info.pop("identity_catalog_pending", None)


@event.listens_for(Session, "do_orm_execute")
def reject_uncaptured_source_writes(state: ORMExecuteState) -> None:
    if not state.session.info.get(CAPTURE_KEY):
        return
    if isinstance(state.statement, TextClause):
        raise ValidationFailedError("Identity request SQL must preserve source capture")
    if state.is_select:
        return
    source_tables = {spec.model.__tablename__ for spec in SOURCE_SPECS.values()} | {
        "role_permission"
    }
    if any(
        table.name in source_tables for table in find_tables(cast(ClauseElement, state.statement))
    ):
        raise ValidationFailedError("Identity source mutations require tracked ORM writes")
