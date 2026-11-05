"""Bounded typed predicates over a service's custom-value indexes.

Services supply their ORM models and a verified ready generation. The helper
never discovers tenant definitions, grants access, queries JSON, or joins members
into an owner's row set. Cursor binding must include the definition/generation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.sql.elements import ColumnElement

from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import CustomDefinition, ValidationRules, scalar_value
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.idempotency import canonical_json


class CustomPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^cf_[a-z][a-z0-9_]{0,59}$")
    operator: Literal["eq", "in", "gte", "lte", "has_any", "has_all", "is_set"]
    value: Any


@dataclass(frozen=True, slots=True)
class ReadyIndex:
    definition: CustomDefinition
    generation: int
    definition_digest: str


def definition_digest(definition: CustomDefinition) -> str:
    return hashlib.sha256(canonical_json(definition.model_dump(mode="json"))).hexdigest()


def custom_predicate(
    predicate: CustomPredicate,
    *,
    binding: ReadyIndex,
    scalar_model: Any,
    member_model: Any,
    owner_id: ColumnElement[Any],
    company_id: uuid.UUID,
    entity_type: str,
    readable: frozenset[str],
    currencies: frozenset[str],
) -> ColumnElement[bool]:
    """Build one EXISTS predicate; callers cap a request at 16 predicates.

    A generation token comes only from service-owned ready index state under the
    current metadata source. A partially built/stale generation must never be
    passed as ready. Exact hash matching also prevents accidental stale reuse.
    """
    definition = binding.definition
    if "custom_field:" + predicate.key not in readable:
        raise PermissionDeniedError("requested custom predicate is not readable")
    if predicate.key != definition.key or not definition.is_active or not definition.is_searchable:
        raise ValidationFailedError("custom field is not queryable")
    if (
        type(binding.generation) is not int
        or binding.generation < 1
        or binding.definition_digest != definition_digest(definition)
    ):
        raise ConflictError("custom index is not ready for this definition")
    tenant = require_current_tenant()
    if tenant == SCOPE_ALL or company_id == SCOPE_ALL:
        raise ValidationFailedError("custom predicate requires a real tenant and company")
    multi = definition.data_type == "multi_select"
    model = member_model if multi else scalar_model
    base = (
        model.tenant_id == tenant,
        model.company_id == company_id,
        model.entity_type == entity_type,
        model.entity_id == owner_id,
        model.field_key == definition.key,
        model.generation == binding.generation,
    )

    def exists(condition: ColumnElement[bool] | None = None) -> ColumnElement[bool]:
        query = select(model.id).where(*base)
        return (query if condition is None else query.where(condition)).exists()

    op = predicate.operator
    if op == "is_set":
        if type(predicate.value) is not bool:
            raise ValidationFailedError("is_set requires an exact boolean")
        return exists() if predicate.value else ~exists()
    if multi:
        if op not in {"has_any", "has_all"}:
            raise ValidationFailedError("multi-select requires membership operators")
        members = predicate.value
        if (
            not isinstance(members, list)
            or not 1 <= len(members) <= 100
            or any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in members)
            or len(set(members)) != len(members)
        ):
            raise ValidationFailedError("membership requires distinct bounded strings")
        if op == "has_any":
            return exists(model.member_value.in_(members))
        return and_(*(exists(model.member_value == member) for member in members))
    if op in {"has_any", "has_all"}:
        raise ValidationFailedError("scalar fields do not accept membership operators")
    if op in {"gte", "lte"} and definition.data_type not in {
        "integer",
        "decimal",
        "date",
        "datetime",
        "currency_amount",
    }:
        raise ValidationFailedError("range requires a numeric or date field")
    raw_values = predicate.value if op == "in" else [predicate.value]
    if not isinstance(raw_values, list) or not 1 <= len(raw_values) <= 100:
        raise ValidationFailedError("in requires one to one hundred values")
    conditions = []
    for raw in raw_values:
        try:
            # Predicates must still find retained historical values that no longer
            # satisfy today's min/max/pattern. Only storage type/size applies.
            query_definition = definition.model_copy(update={"validation": ValidationRules()})
            value = scalar_value(query_definition, raw, currencies=currencies)
        except (ValueError, TypeError, ValidationFailedError) as exc:
            raise ValidationFailedError("invalid custom predicate value") from exc
        kind = definition.data_type
        currency = None
        if kind in {"integer", "decimal"}:
            column, value = model.value_number, exact_decimal(value)
        elif kind == "currency_amount":
            column, currency, value = (
                model.value_number,
                value["currency"],
                exact_decimal(value["amount"]),
            )
        elif kind == "boolean":
            column = model.value_bool
        elif kind == "date":
            column, value = model.value_date, dt.date.fromisoformat(value)
        elif kind == "datetime":
            column, value = model.value_datetime, dt.datetime.fromisoformat(value)
        else:
            column = model.value_text
            value = unicodedata.normalize("NFKC", value).strip()
            if not definition.validation.case_sensitive:
                value = value.casefold()
            if len(value) > 512:
                raise ValidationFailedError("normalized predicate exceeds index bounds")
        condition = (
            column >= value if op == "gte" else column <= value if op == "lte" else column == value
        )
        if currency is not None:
            condition = and_(condition, model.currency == currency)
        conditions.append(condition)
    # An IN is still a single existence check, including currency/amount pairs.
    from sqlalchemy import or_

    return exists(or_(*conditions))
