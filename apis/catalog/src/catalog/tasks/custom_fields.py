"""Transactional custom-field state adapters; caller owns domain/audit transaction."""

from __future__ import annotations

import datetime as dt
import hmac
import re
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import (
    MAX_DEFINITIONS,
    CustomDefinition,
    canonical_claim,
    scalar_value,
)
from billing_platform.db.claims import insert_candidate
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.exact import exact_decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.field_registry import CUSTOM_ENABLED_ENTITIES
from catalog.domain.sources import SourceUnavailableError
from catalog.models.custom_fields import (
    CustomFieldSequence,
    CustomFieldUniqueClaim,
    CustomFieldValueIndex,
    CustomFieldValueMember,
)


def validate_scope(company_id: uuid.UUID, entity_type: str) -> uuid.UUID:
    tenant = require_current_tenant()
    if tenant == SCOPE_ALL or company_id == SCOPE_ALL or entity_type not in CUSTOM_ENABLED_ENTITIES:
        raise ValidationFailedError("invalid custom-field scope")
    return tenant


async def reserve_claims(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    definitions: tuple[CustomDefinition, ...],
    values: Mapping[str, object],
) -> None:
    """Reserve before releasing old values. Hash collisions never count as equality.

    Stable company/entity/key scopes prevent company overrides from evading tenant
    uniqueness. All effects roll back with the caller's entity write on conflict.
    """
    tenant = validate_scope(company_id, entity_type)
    if entity_id == SCOPE_ALL:
        raise ValidationFailedError("custom owner identity required")
    from catalog.tasks.field_adoption import claim_definitions

    definitions = await claim_definitions(db, entity_type, definitions)
    desired: list[tuple[uuid.UUID, str, bytes, bytes]] = []
    for definition in definitions:
        if not definition.is_active:
            continue
        value = values.get(definition.key)
        if value is not None and definition.validation.unique_within != "none":
            currencies = (
                frozenset({value["currency"]})
                if isinstance(value, dict) and isinstance(value.get("currency"), str)
                else frozenset()
            )
            try:
                value = scalar_value(definition, value, currencies=currencies)
            except (ValueError, TypeError, ValidationFailedError) as exc:
                raise ConflictError(
                    "custom uniqueness requires a compatible value contract"
                ) from exc
        claim = canonical_claim(definition, value)
        if claim is None:
            continue
        digest, content = claim
        if len(content) > 4096:
            raise ValidationFailedError("custom uniqueness value exceeds its bound")
        scope = SCOPE_ALL if definition.validation.unique_within == "tenant" else company_id
        desired.append((scope, definition.key, digest, content))
    desired.sort(key=lambda item: (item[0].int, item[1], item[2]))
    for scope, key, digest, content in desired:
        stmt = (
            select(CustomFieldUniqueClaim)
            .where(
                CustomFieldUniqueClaim.scope_company_id == scope,
                CustomFieldUniqueClaim.entity_type == entity_type,
                CustomFieldUniqueClaim.field_key == key,
                CustomFieldUniqueClaim.value_hash == digest,
            )
            .with_for_update()
        )
        existing = await db.scalar(stmt)
        if existing is None:
            await insert_candidate(
                db,
                CustomFieldUniqueClaim,
                {
                    "tenant_id": tenant,
                    "company_id": company_id,
                    "scope_company_id": scope,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field_key": key,
                    "value_hash": digest,
                    "canonical_value": content,
                },
            )
            existing = await db.scalar(stmt)
            if existing is None:
                raise ConflictError("custom uniqueness claim is unavailable")
        if not hmac.compare_digest(existing.canonical_value, content):
            raise ConflictError("custom uniqueness hash collision; operator review required")
        if existing.entity_id != entity_id or existing.company_id != company_id:
            raise ConflictError("custom field value is already assigned")
    # Inactive definitions retain historical claims. An explicit reviewed change
    # of uniqueness scope must migrate claims; this adapter never erases them.
    active_keys = {
        d.key for d in definitions if d.is_active and d.validation.unique_within != "none"
    }
    keep = {(scope, key, digest) for scope, key, digest, _ in desired}
    owned = list(
        await db.scalars(
            select(CustomFieldUniqueClaim)
            .where(
                CustomFieldUniqueClaim.company_id == company_id,
                CustomFieldUniqueClaim.entity_type == entity_type,
                CustomFieldUniqueClaim.entity_id == entity_id,
            )
            .with_for_update()
        )
    )
    expected_scopes = {
        d.key: SCOPE_ALL if d.validation.unique_within == "tenant" else company_id
        for d in definitions
        if d.key in active_keys
    }
    for row in owned:
        if (
            row.field_key in expected_scopes
            and row.scope_company_id != expected_scopes[row.field_key]
        ):
            raise ConflictError("custom uniqueness scope change requires reviewed migration")
        if (
            row.field_key in active_keys
            and (row.scope_company_id, row.field_key, row.value_hash) not in keep
        ):
            await db.delete(row)
    await db.flush()


async def allocate_sequence(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_type: str,
    field_key: str,
    cycle_key: str,
    prefix: str,
    padding: int,
    start: int,
) -> str:
    """Allocate under a row lock; use only an already verified reset-cycle identity.

    Calendar keys must be derived from verified company time by the caller.
    Fiscal identities are rejected until an authoritative fiscal adapter exists.
    This primitive neither discovers fiscal periods nor promises gaplessness.
    """
    tenant = validate_scope(company_id, entity_type)
    if not re.fullmatch(r"cf_[a-z][a-z0-9_]{0,59}", field_key) or len(cycle_key) > 40:
        raise ValidationFailedError("invalid sequence key")
    if len(cycle_key) == 36:
        raise SourceUnavailableError("fiscal custom numbering source is unavailable")
    if cycle_key and not re.fullmatch(r"[1-9][0-9]{3}(?:-(?:0[1-9]|1[0-2]))?", cycle_key):
        raise ValidationFailedError("invalid calendar sequence cycle")
    if (
        type(padding) is not int
        or not 1 <= padding <= 20
        or type(start) is not int
        or not 1 <= start < 2**63 - 1
    ):
        raise ValidationFailedError("invalid sequence numeric settings")
    if len(prefix) > 64 or any(ord(c) < 32 for c in prefix):
        raise ValidationFailedError("invalid sequence prefix")
    stmt = (
        select(CustomFieldSequence)
        .where(
            CustomFieldSequence.company_id == company_id,
            CustomFieldSequence.entity_type == entity_type,
            CustomFieldSequence.field_key == field_key,
            CustomFieldSequence.cycle_key == cycle_key,
        )
        .with_for_update()
    )
    row = await db.scalar(stmt)
    if row is None:
        await insert_candidate(
            db,
            CustomFieldSequence,
            {
                "tenant_id": tenant,
                "company_id": company_id,
                "entity_type": entity_type,
                "field_key": field_key,
                "cycle_key": cycle_key,
                "next_value": start,
            },
        )
        row = await db.scalar(stmt)
    if row is None or row.next_value >= 2**63 - 1:
        raise ConflictError("custom sequence is exhausted or unavailable")
    value = row.next_value
    row.next_value += 1
    await db.flush()
    return prefix + str(value).zfill(padding)


async def replace_indexes(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    definitions: tuple[CustomDefinition, ...],
    values: Mapping[str, Any],
    generations: Mapping[str, tuple[int, ...]],
) -> None:
    """Replace bounded active/building generations in the caller's owner transaction.

    Caller locks/authorizes the owner and reads generation state before invoking.
    Old historical generations remain intact; queries require a ready generation.
    Member filters use EXISTS against the member table, never a multiplying join.
    """
    tenant = validate_scope(company_id, entity_type)
    if entity_id == SCOPE_ALL or len(definitions) > MAX_DEFINITIONS:
        raise ValidationFailedError("invalid custom index owner or definition count")
    desired: list[CustomFieldValueIndex | CustomFieldValueMember] = []
    targets: list[tuple[str, tuple[int, ...]]] = []
    for definition in definitions:
        if not definition.is_active or not definition.is_searchable:
            continue
        version_set = generations.get(definition.key, ())
        if (
            not 1 <= len(version_set) <= 2
            or len(set(version_set)) != len(version_set)
            or any(type(generation) is not int or generation < 1 for generation in version_set)
        ):
            raise ConflictError("custom index generation is unavailable")
        targets.append((definition.key, version_set))
        value = values.get(definition.key)
        if value is None:
            continue
        for generation in version_set:
            base = {
                "tenant_id": tenant,
                "company_id": company_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_key": definition.key,
                "generation": generation,
            }
            kind = definition.data_type
            if kind == "multi_select":
                desired.extend(
                    CustomFieldValueMember(**base, member_value=member) for member in value
                )
            else:
                typed: dict[str, Any] = {}
                if kind in {"integer", "decimal"}:
                    typed["value_number"] = exact_decimal(value)
                elif kind == "currency_amount":
                    typed = {
                        "value_number": exact_decimal(value["amount"]),
                        "currency": value["currency"],
                    }
                elif kind == "boolean":
                    typed["value_bool"] = value
                elif kind == "date":
                    typed["value_date"] = dt.date.fromisoformat(value)
                elif kind == "datetime":
                    typed["value_datetime"] = dt.datetime.fromisoformat(value)
                else:
                    normalized = unicodedata.normalize("NFKC", value).strip()
                    typed["value_text"] = (
                        normalized
                        if definition.validation.case_sensitive
                        else normalized.casefold()
                    )
                    if len(typed["value_text"]) > 512:
                        raise ValidationFailedError("normalized custom text exceeds index bounds")
                desired.append(CustomFieldValueIndex(**base, **typed))
        if len(desired) > 1024:
            raise ValidationFailedError("custom index expansion exceeds the per-record bound")
    for key, version_set in targets:
        for model in (CustomFieldValueIndex, CustomFieldValueMember):
            existing = list(
                await db.scalars(
                    select(model).where(
                        model.company_id == company_id,
                        model.entity_type == entity_type,
                        model.entity_id == entity_id,
                        model.field_key == key,
                        model.generation.in_(version_set),
                    )
                )
            )
            for row in existing:
                await db.delete(row)
    await db.flush()
    db.add_all(desired)
    await db.flush()
