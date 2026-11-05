"""Identity company customization through shared validators and transaction-local indexes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import (
    CustomDefinition,
    decode_default,
    scalar_value,
    validate_definitions,
    validate_values,
)
from billing_platform.db.reference_models import Currency
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.fields import registry
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.field_registry import COMPANY_ENTITY_TYPE
from identity.models import (
    Company,
    CompanyFeature,
    CustomFieldDefinition,
    CustomFieldSequence,
    CustomFieldValueIndex,
)
from identity.schemas.customization import DefinitionItem

ENTITY = "identity.company"


def contract(row: CustomFieldDefinition) -> CustomDefinition:
    return CustomDefinition.model_validate(
        {
            "key": row.key,
            "data_type": row.data_type,
            "is_active": row.is_active,
            "is_searchable": row.is_searchable,
            "is_immutable_after_create": row.is_immutable_after_create,
            "validation": row.validation or {},
            "choices": (row.options or {}).get("choices", []),
            "option_source_key": row.option_source_key,
            "depends_on_key": row.depends_on_key,
            "visibility": row.visibility,
            "default_value": decode_default(row.data_type, row.default_value),
            "sequence_config": row.sequence_config,
        }
    )


def definition_digest(row: CustomFieldDefinition) -> str:
    data = {
        key: getattr(row, key)
        for key in (
            "entity_type",
            "label",
            "help_text",
            "placeholder",
            "display_order",
            "display_group",
            "requires_feature",
        )
    }
    data.update(company_id=str(row.company_id), definition=contract(row).model_dump(mode="json"))
    return hashlib.sha256(canonical_json(data)).hexdigest()


def definition_item(row: CustomFieldDefinition) -> DefinitionItem:
    return DefinitionItem(
        id=row.id,
        entity_type=cast(
            Literal[
                "identity.company",
                "catalog.item",
                "catalog.product_family",
                "vouchers.voucher",
                "vouchers.voucher_item",
            ],
            row.entity_type,
        ),
        digest=definition_digest(row),
        requires_adoption=row.requires_adoption,
        company_id=None if row.company_id == SCOPE_ALL else row.company_id,
        label=row.label,
        help_text=row.help_text,
        placeholder=row.placeholder,
        display_order=row.display_order,
        display_group=row.display_group,
        requires_feature=row.requires_feature,
        definition=contract(row),
    )


async def definitions(
    db: AsyncSession, company_id: uuid.UUID, entity_type: str = ENTITY
) -> tuple[CustomFieldDefinition, ...]:
    rows = list(
        await db.scalars(
            select(CustomFieldDefinition)
            .where(
                CustomFieldDefinition.entity_type == entity_type,
                CustomFieldDefinition.company_id.in_([SCOPE_ALL, company_id]),
            )
            .limit(257)
        )
    )
    if len(rows) > 256:
        raise ValidationFailedError("custom definition count exceeds limit")
    resolved: dict[str, CustomFieldDefinition] = {}
    for row in sorted(rows, key=lambda r: r.company_id != SCOPE_ALL):
        resolved[row.key] = row
    if len(resolved) > 128:
        raise ValidationFailedError("custom definition count exceeds limit")
    return tuple(resolved.values())


async def validate_contract(
    db: AsyncSession, value: CustomDefinition, entity_type: str = ENTITY
) -> None:
    if (
        entity_type in {"vouchers.voucher", "vouchers.voucher_item"}
        and value.is_searchable
        and value.data_type in {"text", "select", "auto_number"}
        and value.validation.max_length > 200
    ):
        raise ValidationFailedError("voucher text search requires a maximum length of 200")
    if len(value.key) > 60:
        raise ValidationFailedError("custom key exceeds storage bound")
    if (
        entity_type == ENTITY
        and value.is_searchable
        and (
            value.data_type in {"multi_select", "currency_amount"}
            or (
                value.data_type in {"text", "select", "auto_number"}
                and value.validation.max_length > 255
            )
        )
    ):
        raise ValidationFailedError("search requires a bounded scalar of at most 255 characters")
    if (
        entity_type not in {"vouchers.voucher", "vouchers.voucher_item"}
        and value.sequence_config
        and value.sequence_config.reset == "fiscal_year"
    ):
        raise ValidationFailedError("fiscal numbering requires the Billing fiscal adapter")
    if value.default_value is not None:
        currencies = frozenset(await db.scalars(select(Currency.code)))
        try:
            checked = scalar_value(value, value.default_value, currencies=currencies)
            if value.data_type in {"select", "multi_select"}:
                selected = set(checked) if value.data_type == "multi_select" else {checked}
                if not selected <= {choice.value for choice in value.choices if choice.is_active}:
                    raise ValueError("default must select active options")
        except (ValueError, TypeError) as exc:
            raise ValidationFailedError("invalid custom default") from exc
        if len(json.dumps(value.default_value)) > 500:
            raise ValidationFailedError("default exceeds storage bound")


async def index_values(
    db: AsyncSession,
    row: Company,
    definitions_: tuple[CustomFieldDefinition, ...],
    values: dict[str, Any],
) -> None:
    active_ids = [d.id for d in definitions_ if d.is_active and d.is_searchable]
    await db.execute(
        delete(CustomFieldValueIndex).where(
            CustomFieldValueIndex.entity_type == ENTITY,
            CustomFieldValueIndex.entity_id == row.id,
            CustomFieldValueIndex.definition_id.not_in(active_ids),
        )
    )
    for definition in definitions_:
        if not definition.is_active or not definition.is_searchable:
            continue
        model = contract(definition)
        value = values.get(definition.key)
        key = (ENTITY, row.id, definition.id)
        indexed = await db.get(CustomFieldValueIndex, key)
        if indexed is None:
            indexed = CustomFieldValueIndex(
                tenant_id=row.tenant_id,
                entity_type=ENTITY,
                entity_id=row.id,
                definition_id=definition.id,
                company_id=row.id,
            )
            db.add(indexed)
        indexed.value_text = indexed.value_number = indexed.value_date = indexed.value_bool = None
        if value is not None:
            if model.data_type in {"integer", "decimal"}:
                indexed.value_number = Decimal(str(value))
            elif model.data_type == "boolean":
                indexed.value_bool = value
            elif model.data_type in {"date", "datetime"}:
                indexed.value_date = (
                    dt.datetime.fromisoformat(value).replace(tzinfo=dt.UTC)
                    if model.data_type == "date"
                    else dt.datetime.fromisoformat(value)
                )
            else:
                indexed.value_text = (
                    str(value) if model.validation.case_sensitive else str(value).casefold()
                )
                if len(indexed.value_text) > 255:
                    raise ValidationFailedError("custom search value exceeds its storage bound")
            if model.validation.unique_within != "none":
                # All company writes hold the tenant lock, serializing claims and release.
                # Compare the logical field across scoped definitions to prevent override bypass.
                ids = select(CustomFieldDefinition.id).where(
                    CustomFieldDefinition.entity_type == ENTITY,
                    CustomFieldDefinition.key == definition.key,
                    CustomFieldDefinition.is_active.is_(True),
                )
                query = select(CustomFieldValueIndex.entity_id).where(
                    CustomFieldValueIndex.definition_id.in_(ids),
                    CustomFieldValueIndex.entity_id != row.id,
                )
                for column in ["value_text", "value_number", "value_date", "value_bool"]:
                    query = query.where(
                        getattr(CustomFieldValueIndex, column) == getattr(indexed, column)
                    )
                if model.validation.unique_within == "company":
                    query = query.where(CustomFieldValueIndex.company_id == row.id)
                if await db.scalar(query.limit(1)) is not None:
                    raise ConflictError("custom field value is already assigned")
    await db.flush()


async def prepare_values(
    db: AsyncSession,
    row: Company,
    supplied: dict[str, Any],
    *,
    creating: bool,
    readable: frozenset[str],
    native_changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = await definitions(db, row.id)
    features = frozenset(
        await db.scalars(
            select(CompanyFeature.feature_key).where(
                CompanyFeature.company_id == row.id, CompanyFeature.is_enabled.is_(True)
            )
        )
    )
    for definition in rows:
        if (
            definition.requires_feature is not None
            and definition.requires_feature not in features
            and definition.key in supplied
        ):
            raise ValidationFailedError("custom field requires an enabled feature")
    contracts = tuple(contract(r) for r in rows)
    validate_definitions(
        contracts,
        native_fields=frozenset(registry.get(COMPANY_ENTITY_TYPE).fields),
        option_sources=frozenset(),
    )
    currencies = frozenset(await db.scalars(select(Currency.code)))
    native = {key: getattr(row, key) for key in registry.get(COMPANY_ENTITY_TYPE).fields}
    previous_native = dict(native)
    native.update(native_changes or {})
    previous = row.custom_fields or {}

    def no_options(key: str, parent: Any) -> frozenset[str]:
        raise ValidationFailedError("dynamic option source is not registered")

    values = validate_values(
        contracts,
        supplied,
        previous=previous,
        native_values=native,
        previous_native_values=previous_native,
        creating=creating,
        readable_condition_fields=readable,
        currencies=currencies,
        resolve_options=no_options,
    )
    for definition, model in zip(rows, contracts, strict=True):
        if not model.is_active or model.data_type != "auto_number" or definition.key in values:
            continue
        cfg = model.sequence_config
        assert cfg is not None
        calendar = utcnow().astimezone(ZoneInfo(row.timezone))
        cycle = (
            ""
            if cfg.reset == "never"
            else calendar.strftime("%Y" if cfg.reset == "calendar_year" else "%Y-%m")
        )
        sequence = await db.scalar(
            select(CustomFieldSequence)
            .where(
                CustomFieldSequence.definition_id == definition.id,
                CustomFieldSequence.company_id == SCOPE_ALL,
                CustomFieldSequence.cycle_key == cycle,
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = CustomFieldSequence(
                id=uuid7(),
                tenant_id=row.tenant_id,
                definition_id=definition.id,
                company_id=SCOPE_ALL,
                cycle_key=cycle,
                next_value=cfg.start,
            )
            db.add(sequence)
        if sequence.next_value >= 2**63 - 1:
            raise ConflictError("custom sequence exhausted")
        values[definition.key] = cfg.prefix + str(sequence.next_value).zfill(cfg.padding)
        sequence.next_value += 1
    # JSON is exact on the wire; scalar validators already canonicalize decimals and dates.
    await index_values(db, row, rows, values)
    return values
