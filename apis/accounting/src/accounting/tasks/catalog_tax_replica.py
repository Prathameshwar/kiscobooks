"""Apply Catalog GST publications to the read-only Accounting replica (tax-accounting Phase 5).

``consume_once`` has already recorded the inbox key in this transaction, so a redelivered
message never reaches these functions. Generation ordering then makes late and duplicate
publications no-ops. Invalid or history-rewriting payloads raise ``ValidationFailedError``
and go to the dead-letter queue; nothing here is audited, because the change is Catalog's
and Catalog audits it — each row keeps the ``source_message_id`` that last changed it.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from billing_platform.errors import ValidationFailedError
from billing_platform.messages import MessageEnvelope
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.domain.tax_replica import (
    MUTABLE_FIELDS,
    decide,
    immutable_changes,
    next_action,
    same_components,
)
from accounting.models.tax_replica import (
    ReplicaRow,
    TaxClassificationReplica,
    TaxRateComponentReplica,
    TaxRateReplica,
    TaxRuleReplica,
)
from accounting.schemas.catalog_tax_events import (
    PAYLOADS,
    Change,
    ClassificationChanged,
    RateChanged,
    RuleChanged,
)

CONSUMER = "accounting.catalog_tax.v1"
COMPONENT_FIELDS = (
    "id",
    "component_key",
    "component",
    "kind",
    "percentage",
    "amount",
    "currency",
    "unit_id",
    "basis_quantity",
    "rounding_mode",
    "position",
)


def parse(envelope: MessageEnvelope) -> Change:
    """The authenticated envelope's typed payload, bound to the envelope's tenant."""
    model = PAYLOADS.get(envelope.event_type)
    if model is None or envelope.schema_version != 1:
        raise ValidationFailedError("unsupported Catalog tax event contract")
    try:
        change = model.model_validate(envelope.payload)
    except ValidationError as exc:
        raise ValidationFailedError("Catalog tax event payload is invalid") from exc
    if change.tenant_id != envelope.tenant_id:
        raise ValidationFailedError("source payload and authenticated envelope scopes differ")
    return change


async def handle_catalog_tax(db: AsyncSession, envelope: MessageEnvelope) -> None:
    change = parse(envelope)
    if isinstance(change, ClassificationChanged):
        values = change.classification.model_dump()
        await apply_row(
            db, TaxClassificationReplica, change, values, envelope.message_id, "classification"
        )
    elif isinstance(change, RuleChanged):
        values = change.rule.model_dump()
        await apply_row(db, TaxRuleReplica, change, values, envelope.message_id, "rule")
    elif isinstance(change, RateChanged):
        await apply_rate(db, change, envelope.message_id)


async def apply_row(
    db: AsyncSession,
    model: type[ReplicaRow],
    change: Change,
    values: dict[str, Any],
    message_id: uuid.UUID,
    entity: str,
) -> str:
    """Insert, advance or ignore one replica row; returns the decision taken."""
    row = await db.scalar(select(model).where(model.id == values["id"]).with_for_update())
    if row is not None and row.company_id != change.company_id:
        raise ValidationFailedError("Catalog tax object moved between companies")
    decision = decide(None if row is None else row.source_version, change.source_version)
    dated = hasattr(model, "source_action")
    if decision == "insert":
        extra = {"source_action": change.action} if dated else {}
        db.add(
            model(
                **values,
                **extra,
                tenant_id=change.tenant_id,
                company_id=change.company_id,
                source_version=change.source_version,
                source_message_id=message_id,
            )
        )
    elif decision == "update":
        assert row is not None
        current = {key: getattr(row, key) for key in values}
        if immutable_changes(current, values, MUTABLE_FIELDS[entity]):
            raise ValidationFailedError("Catalog tax publication rewrites immutable history")
        for key in MUTABLE_FIELDS[entity]:
            setattr(row, key, values[key])
        if dated:
            # Classification and rate replicas only; rules use ``is_active`` instead.
            dated_row = cast(TaxClassificationReplica | TaxRateReplica, row)
            dated_row.source_action = next_action(dated_row.source_action, change.action)
        row.source_version = change.source_version
        row.source_message_id = message_id
    await db.flush()
    return decision


async def apply_rate(db: AsyncSession, change: RateChanged, message_id: uuid.UUID) -> str:
    values = change.rate.model_dump(exclude={"components"})
    components = [component.model_dump() for component in change.rate.components]
    existing = await db.scalar(
        select(TaxRateReplica.source_version).where(TaxRateReplica.id == values["id"])
    )
    if existing is not None and decide(existing, change.source_version) == "update":
        stored = await db.scalars(
            select(TaxRateComponentReplica).where(TaxRateComponentReplica.rate_id == values["id"])
        )
        current = [{key: getattr(row, key) for key in COMPONENT_FIELDS} for row in stored]
        if not same_components(current, components):
            raise ValidationFailedError("Catalog tax rate components are immutable")
    decision = await apply_row(db, TaxRateReplica, change, values, message_id, "rate")
    if decision == "insert":
        for component in components:
            db.add(
                TaxRateComponentReplica(
                    **component,
                    rate_id=values["id"],
                    tenant_id=change.tenant_id,
                    company_id=change.company_id,
                    source_version=change.source_version,
                    source_message_id=message_id,
                )
            )
        await db.flush()
    return decision


__all__ = ["CONSUMER", "apply_rate", "apply_row", "handle_catalog_tax", "parse"]
