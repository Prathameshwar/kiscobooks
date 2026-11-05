"""Voucher-owned send decisions; Notification owns actual delivery."""

from __future__ import annotations

import uuid

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.schemas.configuration import NotificationConfiguration, Policy
from vouchers.tasks.access import authorize, denied
from vouchers.tasks.common import audit, expected, get
from vouchers.tasks.documents import revision_for

EXTERNAL_ROLES = frozenset({"CUSTOMER", "SUPPLIER", "CONSIGNEE", "PRINCIPAL", "WORKER"})
INVOICING = frozenset({"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"})
PAYMENTS = frozenset({"PAYMENT", "RECEIPT"})
DELIVERY = frozenset(
    {
        "DELIVERY_NOTE",
        "RECEIPT_NOTE",
        "MATERIAL_IN",
        "MATERIAL_OUT",
        "REJECTIONS_IN",
        "REJECTIONS_OUT",
    }
)
SHAREABLE = (
    INVOICING
    | PAYMENTS
    | DELIVERY
    | {
        "SALES_ORDER",
        "PURCHASE_ORDER",
        "JOB_WORK_IN_ORDER",
        "JOB_WORK_OUT_ORDER",
    }
)


def recipient_purpose(kind: str) -> str:
    if kind in INVOICING:
        return "INVOICING"
    if kind in PAYMENTS:
        return "PAYMENTS"
    if kind in DELIVERY:
        return "DELIVERY"
    if kind in SHAREABLE:
        return "GENERAL"
    raise ValidationFailedError("this voucher kind has no external recipient")


def _configuration(revision: m.VoucherRevision) -> NotificationConfiguration | None:
    policy = Policy.model_validate(revision.configuration_evidence["policy"])
    return policy.notification


async def _eligible_parties(db: AsyncSession, revision: m.VoucherRevision) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(m.VoucherParty).where(
            m.VoucherParty.company_id == revision.company_id,
            m.VoucherParty.revision_id == revision.id,
            m.VoucherParty.role.in_(EXTERNAL_ROLES),
        )
    )
    return sorted({row.party_id for row in rows}, key=str)


async def _number(db: AsyncSession, revision: m.VoucherRevision) -> str:
    value = await db.scalar(
        select(m.VoucherNumberAssignment.display_number).where(
            m.VoucherNumberAssignment.company_id == revision.company_id,
            m.VoucherNumberAssignment.revision_id == revision.id,
        )
    )
    return value or ""


async def emit_send(
    db: AsyncSession,
    *,
    voucher: m.Voucher,
    revision: m.VoucherRevision,
    party_id: uuid.UUID,
    channels: list[str],
    source_event_key: str,
) -> uuid.UUID:
    kind = revision.configuration_evidence["kind"]
    purpose = recipient_purpose(kind)
    if voucher.status not in {"ISSUED", "ACCEPTED", "POSTED"}:
        raise ConflictError("only a final, shareable voucher can be sent")
    number = await _number(db, revision)
    event_key = f"voucher.{kind.lower()}.{voucher.status.lower()}"
    row = emit(
        db,
        aggregate_type="vouchers.voucher",
        aggregate_id=voucher.id,
        event_type="notification.send",
        tenant_id=voucher.tenant_id,
        payload={
            "company_id": str(voucher.company_id),
            "source_service": "vouchers",
            "source_event_key": source_event_key,
            "source_version": voucher.row_version,
            "event_key": event_key,
            "category": "transactional",
            "aggregate_type": "voucher",
            "aggregate_id": str(voucher.id),
            "subject_type": "party_" + purpose.lower(),
            "subject_id": str(party_id),
            "channels": channels,
            "locale": "en-IN",
            "correlation_id": str(voucher.id),
            "causation_id": str(revision.id),
            "variables": {
                "voucher_id": str(voucher.id),
                "voucher_kind": kind,
                "voucher_number": number,
                "voucher_status": voucher.status,
                "document_date": revision.document_date.isoformat(),
                "currency": revision.currency,
                "due_date": revision.credit_terms_date.isoformat()
                if revision.credit_terms_date
                else "",
                "party_id": str(party_id),
            },
        },
    )
    return row.message_id


async def share(
    db: AsyncSession,
    current: Access,
    voucher_id: uuid.UUID,
    expected_version: int,
    party_id: uuid.UUID,
    channel: str,
) -> uuid.UUID:
    authorize(current, "read")
    required = {
        "id",
        "revision_id",
        "type_revision_id",
        "document_date",
        "currency",
        "mode",
        "parties",
    }
    if denied(current, "vouchers.voucher", required, "read"):
        raise PermissionDeniedError("voucher fields required for sharing are not readable")
    voucher = await get(db, current, m.Voucher, voucher_id, lock=True)
    expected(voucher, expected_version)
    revision = await revision_for(db, current, voucher)
    config = _configuration(revision)
    if (
        config is None
        or not config.enabled
        or not config.manual_share_allowed
        or channel not in config.channels
    ):
        raise ConflictError("voucher sharing is not enabled for this channel")
    if revision.configuration_evidence["kind"] not in SHAREABLE:
        raise ConflictError("voucher kind is not externally shareable")
    if party_id not in await _eligible_parties(db, revision):
        raise ValidationFailedError("recipient party is not on this voucher revision")
    message_id = await emit_send(
        db,
        voucher=voucher,
        revision=revision,
        party_id=party_id,
        channels=[channel],
        source_event_key="vouchers.voucher.share",
    )
    audit(
        db,
        current,
        "voucher",
        voucher.id,
        "share",
        changes={
            "recipient_party_id": str(party_id),
            "channel": channel,
            "message_id": str(message_id),
        },
    )
    return message_id


async def automatic(
    db: AsyncSession,
    voucher: m.Voucher,
    revision: m.VoucherRevision,
) -> None:
    config = _configuration(revision)
    if (
        config is None
        or not config.enabled
        or voucher.status not in config.automatic_events
        or revision.configuration_evidence["kind"] not in SHAREABLE
    ):
        return
    parties = await _eligible_parties(db, revision)
    if len(parties) != 1:
        # An ambiguous/absent recipient must not prevent an already authorized posting.
        emit(
            db,
            aggregate_type="vouchers.voucher",
            aggregate_id=voucher.id,
            event_type="vouchers.voucher.notification_skipped",
            tenant_id=voucher.tenant_id,
            payload=audit_payload(
                action="vouchers.voucher.notification_skipped",
                category="system",
                entity_type="vouchers.voucher",
                entity_id=voucher.id,
                actor_user_id=None,
                company_id=voucher.company_id,
                reason="recipient_not_unique",
            )
            | {"actor_type": "system"},
        )
        return
    await emit_send(
        db,
        voucher=voucher,
        revision=revision,
        party_id=parties[0],
        channels=sorted(config.channels),
        source_event_key=f"vouchers.voucher.{voucher.status.lower()}",
    )


def emit_terminal_state(db: AsyncSession, voucher: m.Voucher) -> None:
    if voucher.status not in {"CANCELLED", "DECLINED", "EXPIRED", "REVERSED"}:
        return
    emit(
        db,
        aggregate_type="vouchers.voucher",
        aggregate_id=voucher.id,
        event_type="vouchers.voucher.notification_state",
        tenant_id=voucher.tenant_id,
        payload={
            "company_id": str(voucher.company_id),
            "voucher_id": str(voucher.id),
            "source_version": voucher.row_version,
            "status": voucher.status,
        },
    )
