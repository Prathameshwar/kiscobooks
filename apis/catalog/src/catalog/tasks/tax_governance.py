"""Atomic, reviewed tax changes and retained future withdrawal evidence."""

import datetime as dt
import hashlib
import hmac
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.pagination import CursorCodec

from catalog.models.pricing import PricingRow
from catalog.models.tax import (
    CatalogTaxBinding,
    CatalogTaxScope,
    TaxClassification,
    TaxRate,
    TaxRule,
)
from catalog.models.tax_governance import TaxHistoryAction, TaxRelease
from catalog.schemas import tax_governance as s
from catalog.schemas.tax import BindingInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, business_date, row
from catalog.tasks.tax_commands import TaxWork, create_classification, publish_binding, publish_rate
from catalog.tasks.tax_history import live_rows, require_live, rows, withdrawn
from catalog.tasks.tax_integrity import impact_for, validate_changes

MODELS: dict[str, type[Any]] = {
    entry.__tablename__: entry for entry in (TaxClassification, TaxRate, CatalogTaxBinding)
}
KEYS = {
    TaxClassification: ("code_system", "code"),
    TaxRate: ("series_id",),
    CatalogTaxBinding: ("scope_id", "direction", "bundle", "item_kind"),
}


def digest(body: s.ReleaseInput) -> str:
    return hashlib.sha256(
        canonical_json(body.model_dump(mode="json", exclude={"preview_token", "impact_review_id"}))
    ).hexdigest()


def codec(access: ConfigurationAccess, secret: bytes) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.tax-release.v1", hashlib.sha256),
        context=f"tax-release:{access.actor.tenant_id}:{access.company}:{access.actor.user_id}",
        ttl_seconds=900,
    )


async def reviewed_values(access: ConfigurationAccess, body: s.ReleaseInput) -> dict[str, Any]:
    today = business_date((await access.context(TaxRule)).company.timezone)
    return {"digest": digest(body), "business_date": str(today)}


async def withdraw(
    work: PricingWork, body: s.WithdrawalInput, object_id: uuid.UUID | None
) -> PricingRow:
    assert isinstance(work, TaxWork)
    await work.publication(body)
    model = MODELS[body.resource]
    target = await row(work.access, model, body.target_id)
    await TaxWork.authorize_reference(work.access, target, write=True)
    await require_live(work.access, target)
    today = business_date((await work.access.context(model)).company.timezone)
    if target.valid_from <= today:
        raise ConflictError("only strictly future tax definitions can be withdrawn")
    if target.row_version != body.expected_version:
        raise ConflictError("withdrawal target changed; review again")
    actions = await rows(work.access, TaxHistoryAction, resource=body.resource, target_id=target.id)
    successors = await rows(
        work.access, TaxHistoryAction, resource=body.resource, previous_id=target.id
    )
    excluded = await withdrawn(
        work.access,
        resource=body.resource,
        target_id=frozenset(entry.target_id for entry in successors),
    )
    if any(
        entry.resource == body.resource
        and entry.previous_id == target.id
        and (entry.resource, entry.target_id) not in excluded
        for entry in successors
    ):
        raise ConflictError("withdraw live successor definitions before their predecessor")
    evidence = next(
        (
            entry
            for entry in actions
            if entry.resource == body.resource
            and entry.target_id == target.id
            and entry.action == "SUPERSEDE"
        ),
        None,
    )
    if body.restore_predecessor and evidence is not None:
        previous = await row(work.access, model, evidence.previous_id)
        await require_live(work.access, previous)
        if previous.valid_to != target.valid_from - dt.timedelta(days=1):
            raise ConflictError("predecessor interval changed after publication")
        peers = await live_rows(
            work.access, model, **{key: getattr(target, key) for key in KEYS[model]}
        )
        if any(
            entry.id not in {previous.id, target.id}
            and all(getattr(entry, key) == getattr(target, key) for key in KEYS[model])
            and (entry.valid_to is None or entry.valid_to >= previous.valid_from)
            and entry.valid_from <= (evidence.previous_valid_to or dt.date.max)
            for entry in peers
        ):
            raise ConflictError("restoring the predecessor would overlap another publication")
        await work.update(previous, previous.row_version, valid_to=evidence.previous_valid_to)
    elif body.restore_predecessor and not any(
        entry.resource == body.resource
        and entry.target_id == target.id
        and entry.action == "PUBLISH"
        for entry in actions
    ):
        raise ConflictError(
            "legacy publication lacks restoration evidence; provide an explicit replacement"
        )
    work.touched[model, target.id] = target
    # The version bump is the target's only change; it audits as `withdraw`, not `update`, and
    # the action row below records why.
    await work.update(target, body.expected_version, "withdraw")
    return await work.new(
        TaxHistoryAction,
        resource=body.resource,
        target_id=target.id,
        action="WITHDRAW",
        previous_id=None,
        previous_valid_to=None,
        release_id=work.release_id,
        reason=body.reason,
        business_date=today,
    )


async def apply_changes(work: TaxWork, body: s.ReleaseInput) -> TaxRelease:
    await work.publication(body)
    release = await work.new(
        TaxRelease,
        "publish",
        change_reason=body.change_reason,
        business_date=business_date((await work.access.context(TaxRule)).company.timezone),
        input_digest=digest(body),
        change_count=len(body.changes),
    )
    work.release_id, work.change_reason = release.id, body.change_reason
    created: dict[str, PricingRow] = {}
    for change in body.changes:
        if isinstance(change, s.ClassificationChange):
            value = await create_classification(work, change.definition, None)
        elif isinstance(change, s.RateChange):
            value = await publish_rate(work, change.definition, None)
        elif isinstance(change, s.WithdrawalChange):
            value = await withdraw(work, change.definition, None)
        else:
            definition = change.definition.model_dump()
            reference = change.definition.classification_id
            if isinstance(reference, s.NewClassification):
                target = created.get(reference.key)
                if not isinstance(target, TaxClassification):
                    raise ConflictError(
                        "classification reference must name an earlier classification change"
                    )
                definition["classification_id"] = target.id
            value = await publish_binding(work, BindingInput.model_validate(definition), None)
        created[change.key] = value
    return release


async def preview(
    access: ConfigurationAccess, body: s.ReleaseInput, secret: bytes
) -> s.ReleasePreview:
    access.actor.require_scope("tax_rule.publish", target=ScopePath(company_id=access.company))
    await access.context(TaxRelease, "tax_rule.manage")
    state = await policy_state(access.db, access.actor, access.company, lock=True)
    assert state is not None
    work = TaxWork(access, state)
    savepoint = await access.db.begin_nested()
    try:
        await apply_changes(work, body)
        impact = await validate_changes(work)
        result = s.ReleasePreview(
            policy_generation=state.generation,
            source_version=(await access.context(TaxRule)).source_version,
            preview_token=codec(access, secret).encode(await reviewed_values(access, body)),
            **impact.model_dump(),
        )
    finally:
        await savepoint.rollback()
        access.tax_rows.clear()
    return result


async def publish(work: PricingWork, body: s.ReleaseCommit, secret: bytes) -> PricingRow:
    assert isinstance(work, TaxWork)
    if body.impact_review_id is not None:
        from catalog.tasks.tax_impact_reviews import verify

        work.impact_review = await verify(work, body)
    else:
        assert body.preview_token is not None
        if codec(work.access, secret).decode(body.preview_token) != await reviewed_values(
            work.access, body
        ):
            raise ConflictError("tax release input or business date changed; preview again")
    return await apply_changes(work, body)


async def impact(access: ConfigurationAccess, body: s.ImpactQuery) -> s.TaxImpact:
    models: dict[str, type[Any]] = {
        **MODELS,
        "tax_rule": TaxRule,
        "catalog_tax_scope": CatalogTaxScope,
    }
    model = models[body.resource]
    target = await row(access, model, body.target_id)
    await TaxWork.authorize_reference(access, target)
    scopes = (
        {target.id}
        if isinstance(target, CatalogTaxScope)
        else {
            entry.scope_id
            for entry in await live_rows(
                access,
                CatalogTaxBinding,
                since=body.as_of,
                **{
                    "classification_id"
                    if isinstance(target, TaxClassification)
                    else "rule_id": target.id
                },
            )
            if (
                entry.classification_id == target.id
                if isinstance(target, TaxClassification)
                else entry.rule_id == target.id
            )
        }
    )
    return await impact_for(access, scopes, body.as_of, enforce=False)
