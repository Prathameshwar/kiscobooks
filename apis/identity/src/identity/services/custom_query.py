"""Typed exact custom-company filters use the dual-written index and effective definition."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import scalar_value
from billing_platform.db.reference_models import Currency
from billing_platform.errors import ValidationFailedError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from identity.models import Company, CustomFieldDefinition, CustomFieldValueIndex
from identity.services.customization import ENTITY, contract


async def company_custom_filter(db: AsyncSession, key: str, raw: str) -> ColumnElement[bool]:
    rows = list(
        await db.scalars(
            select(CustomFieldDefinition)
            .where(CustomFieldDefinition.entity_type == ENTITY, CustomFieldDefinition.key == key)
            .limit(201)
        )
    )
    if not rows or len(rows) > 200 or any(not r.is_searchable for r in rows if r.is_active):
        raise ValidationFailedError("custom filter is unavailable or exceeds its definition bound")
    currencies = frozenset(await db.scalars(select(Currency.code)))
    conditions = []
    for row in rows:
        if not row.is_active:
            continue
        model = contract(row)
        value = raw
        if model.data_type in {"integer", "boolean"}:
            try:
                value = json.loads(raw)
            except ValueError as exc:
                raise ValidationFailedError("invalid custom filter value") from exc
        try:
            value = scalar_value(model, value, currencies=currencies)
        except ValueError as exc:
            raise ValidationFailedError("invalid custom filter value") from exc
        if model.data_type in {"integer", "decimal"}:
            predicate = CustomFieldValueIndex.value_number == Decimal(str(value))
        elif model.data_type == "boolean":
            predicate = CustomFieldValueIndex.value_bool == value
        elif model.data_type in {"date", "datetime"}:
            date = dt.datetime.fromisoformat(value)
            predicate = CustomFieldValueIndex.value_date == (
                date.replace(tzinfo=dt.UTC) if model.data_type == "date" else date
            )
        else:
            predicate = CustomFieldValueIndex.value_text == (
                value if model.validation.case_sensitive else value.casefold()
            )
        effective = Company.id == row.company_id
        if row.company_id == SCOPE_ALL:
            override = aliased(CustomFieldDefinition)
            effective = ~exists(
                select(override.id).where(
                    override.company_id == Company.id,
                    override.key == key,
                    override.entity_type == ENTITY,
                )
            )
        conditions.append(
            and_(
                effective,
                exists(
                    select(CustomFieldValueIndex.entity_id).where(
                        CustomFieldValueIndex.entity_type == ENTITY,
                        CustomFieldValueIndex.entity_id == Company.id,
                        CustomFieldValueIndex.definition_id == row.id,
                        predicate,
                    )
                ),
            )
        )
    return or_(*conditions) if conditions else Company.id.is_(None)
