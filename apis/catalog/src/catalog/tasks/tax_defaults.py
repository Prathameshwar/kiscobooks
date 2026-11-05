"""Bounded automatic provisioning from a committed, officially sourced pack.

The source worker is a trusted company-enrollment provisioner, not an impersonated
user. It accepts no authored tax values. User commands additionally enforce native
field permissions. Existing identities and dated history are never rewritten.
"""

import uuid
from importlib.resources import files
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.tax import CONTEXTS, validate_components
from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category
from catalog.events.evidence import audit_change, changes
from catalog.models import tax as m
from catalog.models.projections import CompanyProjection
from catalog.models.tax_governance import TaxHistoryAction, TaxRuleApplicability
from catalog.schemas import tax as s
from catalog.schemas.tax_defaults import TaxDefaultsResult, TaxStarterPack
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.pricing_foundation import values
from catalog.tasks.projections import require_identity_context
from catalog.tasks.tax_default_labels import rename_legacy_defaults
from catalog.tasks.tax_publication import stage


def starter_pack() -> TaxStarterPack:
    return TaxStarterPack.model_validate_json(
        files("catalog.seeds").joinpath("tax_defaults_v2.json").read_text(encoding="utf-8")
    )


async def ensure_tax_defaults(
    db: AsyncSession, company: uuid.UUID, *, actor: Actor | None = None
) -> TaxDefaultsResult:
    tenant = require_current_tenant()
    if actor is not None and actor.tenant_id != tenant:
        raise ConflictError("tax defaults authority differs from the company tenant")
    checkpoint = await require_identity_context(db, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None:
        raise ConflictError("verified company settings are unavailable")
    pack = starter_pack()
    result = TaxDefaultsResult.model_validate(
        {"company_id": company, "pack_version": pack.version, "status": "NOT_APPLICABLE"}
    )
    # GST is selected by the company's tax system; no fictitious `gst` feature flag.
    if (
        profile.country_code != "IN"
        or profile.default_tax_system != "gst_in"
        or profile.status != "active"
    ):
        return result
    state = await company_policy_state(db, tenant, company, lock=True)
    assert state is not None
    if state.generation >= 2**63 - 1:
        raise ConflictError("company tax generation is exhausted")
    access = ConfigurationAccess(db, actor, company) if actor else None
    day = max(pack.effective_from, business_date(profile.timezone))
    publications: list[tuple[Any, str]] = await rename_legacy_defaults(
        db, company, pack.version, actor=actor
    )
    changed = bool(publications)

    async def create(model: type[Any], audit_action: str = "create", /, **incoming: Any) -> Any:
        nonlocal changed
        row = model(
            id=uuid7(),
            tenant_id=tenant,
            company_id=company,
            row_version=1,
            created_by=actor.user_id if actor else None,
            updated_by=actor.user_id if actor else None,
            **incoming,
        )
        entity = "catalog." + model.__tablename__
        field_names = frozenset(incoming)
        if access:
            context = await access.context(model)
            context.assert_writable(field_names, before={}, after=incoming)
        if actor:
            audit_change(
                db,
                actor,
                company,
                entity,
                row.id,
                audit_action,
                field_names,
                before={},
                after=incoming,
            )
        else:
            event = audit_event(entity, audit_action)
            payload = audit_payload(
                action=event,
                category=category(entity, audit_action),
                entity_type=entity,
                entity_id=row.id,
                actor_user_id=None,
                company_id=company,
                changes=changes(entity, field_names, after=incoming, creating=True),
                reason=pack.version,
            )
            payload.update(actor_type="system", source_service="catalog")
            emit(
                db,
                aggregate_type=entity,
                aggregate_id=row.id,
                event_type=event,
                tenant_id=tenant,
                payload=payload,
            )
        db.add(row)
        await db.flush()
        changed = True
        if model in (m.TaxClassification, m.TaxRule, m.TaxRate):
            publications.append((row, "PUBLISH"))
        return row

    async def history(row: Any) -> None:
        await create(
            TaxHistoryAction,
            resource=row.__tablename__,
            target_id=row.id,
            action="PUBLISH",
            previous_id=None,
            previous_valid_to=None,
            release_id=None,
            reason=pack.version,
            business_date=day,
        )

    categories: dict[str, Any] = {
        row.code: row
        for row in await db.scalars(
            select(m.TaxCategory)
            .where(
                m.TaxCategory.company_id == company,
                m.TaxCategory.code.in_([entry.code for entry in pack.categories]),
            )
            .limit(21)
        )
    }
    existing_classifications = set(
        await db.execute(
            select(
                m.TaxClassification.code_system,
                m.TaxClassification.code,
            )
            .where(
                m.TaxClassification.company_id == company,
                m.TaxClassification.code.in_([entry.code for entry in pack.classifications]),
            )
            .distinct()
            .limit(129)
        )
    )
    existing_rules = set(
        await db.scalars(
            select(m.TaxRule.code)
            .where(
                m.TaxRule.company_id == company,
                m.TaxRule.code.in_([entry.code for entry in pack.rules]),
            )
            .limit(65)
        )
    )
    for definition in pack.categories:
        row = categories.get(definition.code)
        if row is None:
            row = await create(m.TaxCategory, **definition.model_dump(), is_active=True)
            result.categories_created += 1
        else:
            result.preserved_records += 1
        categories[definition.code] = row
    for classification in pack.classifications:
        if (classification.code_system, classification.code) in existing_classifications:
            result.preserved_records += 1
            continue
        classification_body = s.ClassificationInput.model_validate(
            dict(
                **classification.model_dump(exclude={"source", "match_kind"}),
                **pack.sources[classification.source].evidence(),
                valid_from=day,
                expected_generation=state.generation,
                expected_source_version=checkpoint.source_version,
            )
        )
        row = await create(m.TaxClassification, "publish", **values(classification_body))
        await history(row)
        result.classifications_created += 1
    for definition in pack.rules:
        if definition.code in existing_rules:
            # Preserve the entire existing rule graph, including withdrawn/future rates.
            result.preserved_records += 1
            continue
        selected = categories[definition.category]
        if not selected.is_active:
            result.notices.append(
                f"{definition.code}: its category is inactive; preserved for review."
            )
            continue
        evidence = pack.sources[definition.source].evidence()
        rule_body = s.RuleInput.model_validate(
            dict(
                **definition.model_dump(exclude={"source", "percentage", "category"}),
                tax_category_id=selected.id,
                **evidence,
            )
        )
        rule = await create(
            m.TaxRule, **rule_body.model_dump(exclude={"classifications"}), is_active=True
        )
        for match in rule_body.classifications:
            await create(TaxRuleApplicability, rule_id=rule.id, **match.model_dump())
        result.rules_created += 1
        if definition.treatment in {"EXEMPT", "NON_GST"}:
            continue
        for applicability, components in CONTEXTS.items():
            series = await create(m.TaxRateSeries, rule_id=rule.id, applicability=applicability)
            percentage = definition.percentage / len(components)
            parts = [
                s.ComponentInput.model_validate(
                    {
                        "component_key": component,
                        "component": component,
                        "kind": "PERCENT",
                        "percentage": format(percentage, "f"),
                        "rounding_mode": "HALF_UP",
                        "position": index,
                    }
                )
                for index, component in enumerate(sorted(components))
            ]
            validate_components(applicability, definition.treatment, parts)
            rate = await create(
                m.TaxRate,
                "publish",
                series_id=series.id,
                valid_from=day,
                valid_to=None,
                supersedes_id=None,
                **evidence,
            )
            for part in parts:
                await create(m.TaxRateComponent, "publish", rate_id=rate.id, **part.model_dump())
            await history(rate)
            result.rates_created += 1
    if changed:
        state.generation += 1
        await db.flush()
        await stage(db, state.generation, publications)
    result.status = "NEEDS_REVIEW" if result.notices else "READY"
    return result


async def bootstrap_tax_defaults(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    key: str,
) -> CommandResult[TaxDefaultsResult]:
    pack = starter_pack()

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        target = ScopePath(company_id=company)
        for permission in ("tax_rule.read", "tax_rule.manage", "tax_rule.publish"):
            actor.require_scope(permission, target=target)
        await ConfigurationAccess(db, actor, company).context(m.TaxRule, "tax_rule.manage")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        result = await ensure_tax_defaults(db, company, actor=actor)
        if result.status == "NEEDS_REVIEW":
            raise ConflictError(" ".join(result.notices))
        return CommandReceipt(200, result.model_dump(mode="json"))

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> TaxDefaultsResult:
        return TaxDefaultsResult.model_validate(receipt)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            tenant_id=actor.tenant_id,
            company_id=company,
            actor_id=actor.user_id,
            operation="catalog.tax.defaults." + pack.version.lower(),
            key=key,
            request={},
        ),
        authorize=authorize,
        mutate=mutate,
        render=render,
    )
