"""Minimal independent source records for projection invariants.

Real cross-service compatibility is separately tested over HTTP with Identity.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.snapshots import (
    SnapshotManifest,
    SnapshotRecord,
    manifest_digest,
    paginate_records,
)

from catalog.schemas.identity_source import CONTRACT, FACTS, IdentityChange
from catalog.tasks.identity_source import VerifiedSnapshot


def company_record(company: uuid.UUID, **changes: Any) -> SnapshotRecord:
    return SnapshotRecord(
        kind="company",
        id=company,
        data={
            "code": "MAIN",
            "display_name": "Test company",
            "status": "active",
            "country_code": "IN",
            "state_code": "MH",
            "base_currency": "INR",
            "reporting_currency": None,
            "fiscal_year_start_month": 4,
            "fiscal_year_start_day": 1,
            "amount_precision": 2,
            "quantity_precision": 4,
            "rounding_mode": "half_up",
            "default_tax_system": "gst",
            "timezone": "Asia/Kolkata",
            "first_posted_at": None,
            **changes,
        },
    )


def all_facts(company: uuid.UUID, user: uuid.UUID) -> tuple[SnapshotRecord, ...]:
    group, role, definition = uuid7(), uuid7(), uuid7()
    return (
        company_record(company),
        SnapshotRecord(
            kind="feature",
            id=uuid7(),
            data={
                "company_id": str(company),
                "feature_key": "inventory",
                "is_enabled": True,
                "locked_at": None,
            },
        ),
        SnapshotRecord(
            kind="currency_allowance",
            id=uuid7(),
            data={
                "company_id": str(company),
                "currency_code": "USD",
                "is_active": True,
            },
        ),
        SnapshotRecord(
            kind="custom_definition",
            id=definition,
            data={
                "company_id": str(SCOPE_ALL),
                "entity_type": "catalog.item",
                "key": "cf_note",
                "label": "Note",
                "help_text": None,
                "placeholder": None,
                "data_type": "text",
                "display_order": 0,
                "display_group": None,
                "is_active": True,
                "is_searchable": False,
                "is_immutable_after_create": False,
                "requires_feature": None,
                "validation": None,
                "options": None,
                "option_source_key": None,
                "depends_on_key": None,
                "visibility": None,
                "sequence_config": None,
                "default_value": None,
            },
        ),
        SnapshotRecord(
            kind="field_config",
            id=uuid7(),
            data={
                "company_id": str(SCOPE_ALL),
                "entity_type": "catalog.item",
                "field_source": "custom",
                "field_key": "cf_note",
                "definition_id": str(definition),
                "is_visible": True,
                "is_required": False,
                "display_order": None,
                "display_group": None,
                "label_override": None,
                "help_text_override": None,
                "default_value": None,
            },
        ),
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                "subject_type": "role",
                "subject_id": str(role),
                "entity_type": "catalog.unit_of_measure",
                "field_key": "name",
                "access": "write",
                "effect": "deny",
                "scope_type": "tenant",
                "scope_id": str(SCOPE_ALL),
                "condition": None,
                "is_active": True,
            },
        ),
        SnapshotRecord(
            kind="role_assignment",
            id=uuid7(),
            data={
                "subject_type": "user_group",
                "subject_id": str(group),
                "role_id": str(role),
                "scope_type": "tenant",
                "scope_id": str(SCOPE_ALL),
                "is_active": True,
                "valid_from": "2020-01-01",
                "valid_to": None,
            },
        ),
        SnapshotRecord(
            kind="group_member",
            id=uuid7(),
            data={"user_group_id": str(group), "user_id": str(user)},
        ),
        SnapshotRecord(kind="user", id=user, data={"status": "active"}),
        SnapshotRecord(kind="group", id=group, data={"is_active": True}),
        SnapshotRecord(kind="role", id=role, data={"is_active": True}),
    )


def snapshot(
    tenant: uuid.UUID,
    company: uuid.UUID,
    records: tuple[SnapshotRecord, ...] | None = None,
    *,
    version: int = 2,
) -> VerifiedSnapshot:
    rows = records if records is not None else (company_record(company),)
    snapshot_id = uuid7()
    pages = paginate_records(snapshot_id, rows)
    digests = tuple(page.digest() for page in pages)
    now = utcnow()
    manifest = SnapshotManifest(
        contract=CONTRACT,
        snapshot_id=snapshot_id,
        tenant_id=tenant,
        company_id=company,
        source_version=version,
        generated_at=now,
        expires_at=now + dt.timedelta(seconds=60),
        record_count=len(rows),
        page_sha256=digests,
        content_sha256=manifest_digest(digests),
        stream_counts={kind: sum(row.kind == kind for row in rows) for kind in FACTS},
    )
    return VerifiedSnapshot(manifest, rows)


def change(
    tenant: uuid.UUID, version: int, records: tuple[SnapshotRecord, ...] = ()
) -> IdentityChange:
    return IdentityChange(
        contract=CONTRACT,
        tenant_id=tenant,
        source_version=version,
        previous_version=version - 1,
        generated_at=utcnow(),
        records=records,
    )
