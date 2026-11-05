"""Local typed metadata, claims, sequences and indexes; definitions remain Identity-owned."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import CustomDefinition, canonical_claim, validate_values
from billing_platform.db.claims import insert_candidate
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.custom_values import search_text
from vouchers.domain.documents import fiscal_start
from vouchers.models import core as m
from vouchers.tasks.access import denied, writable
from vouchers.tasks.common import values

ENTITIES = frozenset({"vouchers.voucher", "vouchers.voucher_item"})
SOURCES = {"voucher_types": "voucher_type", "items": "item", "parties": "party"}


async def definitions(
    db: AsyncSession, current: Access, entity: str
) -> tuple[CustomDefinition, ...]:
    rows = list(
        await db.scalars(
            select(m.VoucherDefinitionProjection)
            .where(
                m.VoucherDefinitionProjection.company_id == current.context.company_id,
                m.VoucherDefinitionProjection.entity_type == entity,
            )
            .order_by(m.VoucherDefinitionProjection.field_key)
            .limit(129)
        )
    )
    if len(rows) > 128:
        raise ConflictError("definition bound exceeded")
    for row in rows:
        row.used_at = utcnow()
    return tuple(CustomDefinition.model_validate(row.definition) for row in rows)


async def normalize(
    db: AsyncSession,
    current: Access,
    entity: str,
    entity_id: uuid.UUID,
    supplied: dict[str, Any],
    previous: dict[str, Any],
    native: dict[str, Any],
    *,
    allowed: frozenset[str] | None,
    day: dt.date,
    creating: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    defs = tuple(
        d for d in await definitions(db, current, entity) if allowed is None or d.key in allowed
    )
    dynamic = {}
    for definition in defs:
        if definition.option_source_key:
            source = SOURCES.get(definition.option_source_key)
            if source is None:
                raise ValidationFailedError("unregistered dynamic option source")
            if source == "voucher_type":
                options = list(
                    await db.scalars(
                        select(m.VoucherType.id)
                        .where(
                            m.VoucherType.company_id == current.context.company_id,
                            m.VoucherType.status == "ACTIVE",
                        )
                        .limit(1001)
                    )
                )
            else:
                options = list(
                    await db.scalars(
                        select(m.VoucherMasterEvidence.source_id)
                        .where(
                            m.VoucherMasterEvidence.company_id == current.context.company_id,
                            m.VoucherMasterEvidence.entity_type == source,
                            m.VoucherMasterEvidence.status == "ACTIVE",
                        )
                        .limit(1001)
                    )
                )
            if len(options) > 1000:
                raise ConflictError("dynamic option source exceeds supported bound")
            dynamic[definition.option_source_key] = frozenset(str(option) for option in options)
    custom_keys = {definition.key for definition in defs}
    readable = set(native) | custom_keys
    previous_values = native | previous
    fields = readable | {"custom_fields"}
    blocked = denied(current, entity, fields, "read", previous_values) | denied(
        current, entity, fields, "read", previous_values | supplied
    )
    readable -= blocked
    if "custom_fields" in blocked:
        readable -= custom_keys
    result = validate_values(
        defs,
        supplied,
        previous=previous,
        native_values=native,
        previous_native_values=native,
        creating=creating,
        readable_condition_fields=frozenset(readable),
        currencies=frozenset({current.context.base_currency}),
        resolve_options=lambda key, parent: dynamic[key],
    )
    for definition in defs:
        seq = definition.sequence_config
        if seq is None or not definition.is_active or result.get(definition.key) is not None:
            continue
        finance = current.context.finance
        cycle = (
            "never"
            if seq.reset == "never"
            else str(day.year)
            if seq.reset == "calendar_year"
            else day.strftime("%Y-%m")
            if seq.reset == "month"
            else str(
                fiscal_start(day, finance.fiscal_year_start_month, finance.fiscal_year_start_day)
            )
            if finance
            else None
        )
        if cycle is None:
            raise ConflictError("company calendar is required for fiscal auxiliary numbering")
        query = (
            select(m.VoucherCustomSequence)
            .where(
                m.VoucherCustomSequence.company_id == current.context.company_id,
                m.VoucherCustomSequence.entity_type == entity,
                m.VoucherCustomSequence.field_key == definition.key,
                m.VoucherCustomSequence.cycle_key == cycle,
            )
            .with_for_update()
        )
        row = await db.scalar(query)
        if row is None:
            row = m.VoucherCustomSequence(
                **values(current),
                entity_type=entity,
                field_key=definition.key,
                cycle_key=cycle,
                next_value=seq.start,
            )
            db.add(row)
            await db.flush()
        if row.next_value >= 2**63 - 1:
            raise ConflictError("auxiliary sequence exhausted")
        result[definition.key] = seq.prefix + str(row.next_value).zfill(seq.padding)
        row.next_value += 1
    writable(current, entity, previous, result)
    writable(current, entity, {"custom_fields": previous}, {"custom_fields": result})
    for definition in defs:
        claim = canonical_claim(definition, result.get(definition.key))
        if claim is None:
            continue
        hashed, content = claim
        scope = (
            SCOPE_ALL
            if definition.validation.unique_within == "tenant"
            else current.context.company_id
        )
        claim_query = (
            select(m.VoucherCustomClaim)
            .where(
                m.VoucherCustomClaim.scope_company_id == scope,
                m.VoucherCustomClaim.entity_type == entity,
                m.VoucherCustomClaim.field_key == definition.key,
                m.VoucherCustomClaim.value_hash == hashed.hex(),
            )
            .with_for_update()
        )
        claim_row = await db.scalar(claim_query)
        if claim_row is None:
            await insert_candidate(
                db,
                m.VoucherCustomClaim,
                values(current)
                | {
                    "scope_company_id": scope,
                    "entity_type": entity,
                    "entity_id": entity_id,
                    "field_key": definition.key,
                    "value_hash": hashed.hex(),
                    "canonical_value": content.decode(),
                    "row_version": 1,
                },
            )
            claim_row = await db.scalar(claim_query)
        if (
            claim_row is None
            or claim_row.entity_id != entity_id
            or claim_row.company_id != current.context.company_id
            or claim_row.canonical_value != content.decode()
        ):
            raise ConflictError("custom field value is already assigned")
    # Release superseded claims only after all desired claims have been acquired.
    for claim_row in await db.scalars(
        select(m.VoucherCustomClaim).where(
            m.VoucherCustomClaim.company_id == current.context.company_id,
            m.VoucherCustomClaim.entity_type == entity,
            m.VoucherCustomClaim.entity_id == entity_id,
        )
    ):
        previous_definition = next(
            (d for d in defs if d.key == claim_row.field_key and d.is_active), None
        )
        if previous_definition:
            claim = canonical_claim(previous_definition, result.get(claim_row.field_key))
            if claim is None or claim[0].hex() != claim_row.value_hash:
                await db.delete(claim_row)
    return result, [d.model_dump(mode="json") for d in defs]


async def indexes(
    db: AsyncSession,
    current: Access,
    entity: str,
    entity_id: uuid.UUID,
    voucher_id: uuid.UUID,
    revision_id: uuid.UUID,
    definitions_wire: list[dict[str, Any]],
    data: dict[str, Any],
) -> None:
    for row in await db.scalars(
        select(m.VoucherCustomIndex).where(
            m.VoucherCustomIndex.company_id == current.context.company_id,
            m.VoucherCustomIndex.entity_type == entity,
            m.VoucherCustomIndex.entity_id == entity_id,
        )
    ):
        await db.delete(row)
    await db.flush()
    for wire in definitions_wire:
        definition = CustomDefinition.model_validate(wire)
        value = data.get(definition.key)
        if not definition.is_searchable or value is None:
            continue
        for number, member in enumerate(
            value if definition.data_type == "multi_select" else [value]
        ):
            item = values(current) | {
                "entity_type": entity,
                "entity_id": entity_id,
                "voucher_id": voucher_id,
                "revision_id": revision_id,
                "field_key": definition.key,
                "member_number": number,
            }
            if definition.data_type in {"integer", "decimal", "currency_amount"}:
                item["value_number"] = Decimal(
                    str(member["amount"] if isinstance(member, dict) else member)
                )
                if isinstance(member, dict):
                    item["currency"] = member["currency"]
            elif definition.data_type == "boolean":
                item["value_bool"] = member
            elif definition.data_type == "date":
                item["value_date"] = dt.date.fromisoformat(member)
            elif definition.data_type == "datetime":
                item["value_datetime_at"] = dt.datetime.fromisoformat(member.replace("Z", "+00:00"))
            else:
                text_value = search_text(
                    str(member), case_sensitive=definition.validation.case_sensitive
                )
                if len(text_value) > 200:
                    raise ValidationFailedError("searchable custom value exceeds index bound")
                item["value_text"] = text_value
            db.add(m.VoucherCustomIndex(**item))
