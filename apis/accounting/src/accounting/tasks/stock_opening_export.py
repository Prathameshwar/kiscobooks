"""Bounded manifest export; signed tickets supplement current field authority."""

import uuid

from billing_platform.authz import ScopePath
from billing_platform.bulk_files import csv_document
from billing_platform.db.access import company_object
from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import CursorCodec
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.stock_opening import StockOpeningControl
from accounting.schemas.stock_opening import OpeningManifest
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.stock_opening_control import active_claims, require_capture_read


async def authorized(db: AsyncSession, current: Access, identity: uuid.UUID) -> StockOpeningControl:
    require_capture_read(current)
    current.actor.require_scope(
        "accounting.export.read", target=ScopePath(company_id=current.context.company_id)
    )
    return await company_object(
        db, StockOpeningControl, identity, company_id=current.context.company_id, lock=True
    )


def codec(current: Access, row: StockOpeningControl, secret: bytes) -> CursorCodec:
    return CursorCodec(
        secret,
        ttl_seconds=300,
        context=canonical_json(
            {
                "resource": "opening-export",
                "tenant": str(current.actor.tenant_id),
                "company": str(current.context.company_id),
                "actor": str(current.actor.user_id),
                "control": str(row.id),
                "version": row.row_version,
                "manifest": row.manifest_hash,
                "authority": authority_fingerprint(current),
            }
        ).decode(),
    )


async def document(
    db: AsyncSession, current: Access, row: StockOpeningControl, token: str, secret: bytes
) -> bytes:
    if codec(current, row, secret).decode(token) != {"id": str(row.id)}:
        raise ValidationFailedError("invalid opening export ticket")
    manifest = OpeningManifest.model_validate(row.manifest)
    claimed = {claim.source_key for claim in await active_claims(db, row)}
    records = []
    for line in manifest.lines:
        capture = line.opening
        assert capture is not None
        records.append(
            [
                str(row.id),
                row.manifest_hash,
                row.status,
                capture.source_key,
                str(capture.source_key in claimed).lower(),
                str(line.item_id),
                str(line.warehouse_id),
                str(line.bin_id or ""),
                str(line.lot_id or ""),
                ";".join(str(unit) for unit in line.unit_ids),
                str(capture.entered_unit_id),
                str(capture.unit_revision_id),
                format(capture.entered_quantity, ".4f"),
                format(line.quantity, ".4f"),
                capture.cost_mode,
                format(capture.unit_cost, ".4f") if capture.unit_cost is not None else "",
                format(capture.priced_quantity, ".4f"),
                format(line.received_value, ".4f") if line.received_value is not None else "",
                row.currency,
                str(capture.history_known).lower(),
                capture.received_on.isoformat() if capture.received_on else "",
                str(capture.cohort_order),
                str(line.opening_journal_line_id or ""),
            ]
        )
    event = "accounting.stock_opening_control.export"
    emit(
        db,
        aggregate_type="accounting.stock_opening_control",
        aggregate_id=row.id,
        tenant_id=current.actor.tenant_id,
        event_type=event,
        payload=audit_payload(
            action=event,
            category="access",
            entity_type="accounting.stock_opening_control",
            entity_id=row.id,
            actor_user_id=current.actor.user_id,
            company_id=row.company_id,
        ),
    )
    return csv_document(
        [
            "control_id",
            "manifest_hash",
            "status",
            "source_key",
            "applied",
            "item_id",
            "warehouse_id",
            "bin_id",
            "lot_id",
            "unit_ids",
            "entered_unit_id",
            "unit_revision_id",
            "entered_quantity",
            "base_quantity",
            "cost_mode",
            "unit_cost",
            "priced_quantity",
            "carrying_value",
            "currency",
            "history_known",
            "received_on",
            "cohort_order",
            "opening_journal_line_id",
        ],
        records,
        marker="_stock_opening_manifest_version",
    )
