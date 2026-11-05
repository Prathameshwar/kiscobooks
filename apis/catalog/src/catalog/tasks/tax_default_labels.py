"""Rename only exact, unedited old starter labels without changing their tax meaning."""

import uuid
from importlib.resources import files
from typing import Any

from billing_platform.gateway import Actor
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import audit_change, changes
from catalog.models.tax import TaxRate, TaxRateSeries, TaxRule
from catalog.models.tax_governance import TaxRuleApplicability
from catalog.schemas.tax_defaults import TaxStarterPack
from catalog.tasks.configuration_access import ConfigurationAccess


async def rename_legacy_defaults(
    db: AsyncSession, company: uuid.UUID, version: str, *, actor: Actor | None
) -> list[tuple[Any, str]]:
    legacy = TaxStarterPack.model_validate_json(
        files("catalog.seeds").joinpath("tax_defaults_v1.json").read_text(encoding="utf-8")
    )
    definitions = {entry.code: entry for entry in legacy.rules}
    rows = list(
        await db.scalars(
            select(TaxRule)
            .where(
                TaxRule.company_id == company,
                TaxRule.code.in_(definitions),
                TaxRule.row_version == 1,
            )
            .limit(65)
        )
    )
    if not rows:
        return []
    ids = [row.id for row in rows]
    matches: dict[uuid.UUID, set[tuple[str, str, str]]] = {}
    for match in await db.scalars(
        select(TaxRuleApplicability)
        .where(TaxRuleApplicability.company_id == company, TaxRuleApplicability.rule_id.in_(ids))
        .limit(1153)
    ):
        matches.setdefault(match.rule_id, set()).add(
            (match.code_system, match.code, match.match_kind)
        )
    rates: dict[uuid.UUID, list[TaxRate]] = {}
    rate_rows = list(
        await db.execute(
            select(TaxRateSeries.rule_id, TaxRate)
            .join(TaxRate, TaxRate.series_id == TaxRateSeries.id)
            .where(
                TaxRateSeries.company_id == company,
                TaxRate.company_id == company,
                TaxRateSeries.tenant_id == TaxRate.tenant_id,
                TaxRateSeries.rule_id.in_(ids),
            )
            .limit(1153)
        )
    )
    if len(rate_rows) >= 1153:
        # A truncated history cannot prove that a definition is still untouched.
        return []
    for rule_id, rate in rate_rows:
        rates.setdefault(rule_id, []).append(rate)
    result: list[tuple[Any, str]] = []
    for row in rows:
        definition = definitions[row.code]
        expected_matches = {
            (entry.code_system, entry.code, entry.match_kind)
            for entry in definition.classifications
        }
        if matches.get(row.id, set()) != expected_matches:
            continue
        schedule = rates.get(row.id, [])
        if len(schedule) != 3 or any(
            rate.row_version != 1 or rate.valid_to is not None for rate in schedule
        ):
            continue
        # Ordinary edits increment the row version. Also compare the complete
        # authored identity/evidence so a colliding user code is never sufficient.
        expected = {
            "name": definition.name,
            "item_kind": definition.item_kind,
            "treatment": definition.treatment,
            "tax_system": "gst_in",
            "jurisdiction": "IN",
            "classification_scope": "SPECIFIC",
            "is_active": True,
            **legacy.sources[definition.source].evidence(),
        }
        if row.custom_fields or any(getattr(row, key) != value for key, value in expected.items()):
            continue
        codes = ", ".join(entry.code for entry in definition.classifications)
        system = definition.classifications[0].code_system
        percentage = format(definition.percentage.normalize(), "f")
        name = f"GST {percentage}% - {system} {codes}"
        before, after = {"name": row.name}, {"name": name}
        entity = "catalog.tax_rule"
        fields = frozenset({"name"})
        if actor:
            context = await ConfigurationAccess(db, actor, company).context(TaxRule)
            context.assert_writable(fields, before=before, after=after)
            audit_change(
                db, actor, company, entity, row.id, "update", fields, before=before, after=after
            )
        else:
            event = audit_event(entity, "update")
            payload = audit_payload(
                action=event,
                category=category(entity, "update"),
                entity_type=entity,
                entity_id=row.id,
                actor_user_id=None,
                company_id=company,
                changes=changes(entity, fields, before=before, after=after),
                reason=version,
            )
            payload.update(actor_type="system", source_service="catalog")
            emit(
                db,
                aggregate_type=entity,
                aggregate_id=row.id,
                event_type=event,
                tenant_id=row.tenant_id,
                payload=payload,
            )
        row.name = name
        row.row_version += 1
        row.updated_by = actor.user_id if actor else None
        result.append((row, "UPDATE"))
    return result
