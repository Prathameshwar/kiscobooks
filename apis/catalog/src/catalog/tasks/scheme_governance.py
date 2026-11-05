"""Company-serialized impact review for cardinality, requiredness and retirement."""

import uuid
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.categories import boundaries, cardinality
from catalog.models.classification import CategoryScheme, ItemCategory
from catalog.models.product_definitions import FamilyCategory
from catalog.models.products import ProductFamily
from catalog.schemas import scheme_governance as s
from catalog.schemas.classification import SchemeDetail
from catalog.tasks.category_membership import references, rows
from catalog.tasks.category_review import codec, stamp
from catalog.tasks.classification import SCHEME, audit_change, protected_detail
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state


async def impact(
    access: ConfigurationAccess, scheme: CategoryScheme, body: s.SchemeTransition
) -> tuple[list[Any], list[str], int, int, int]:
    context = await access.context(CategoryScheme)
    today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
    children = await rows(access, ItemCategory, ItemCategory.scheme_id == scheme.id)
    memberships = await rows(
        access,
        FamilyCategory,
        FamilyCategory.scheme_id == scheme.id,
        or_(FamilyCategory.valid_to.is_(None), FamilyCategory.valid_to >= today),
    )
    evidence = [scheme, *children, *memberships]
    blockers = []
    member_ids = {entry.category_id for entry in memberships}
    if any(not row.is_active for row in children if row.id in member_ids):
        blockers.append("inactive_member_category")
    if not body.is_active:
        if body.is_required:
            blockers.append("inactive_scheme_cannot_be_required")
        if any(row.is_active for row in children):
            blockers.append("active_categories")
        if memberships:
            blockers.append("current_or_scheduled_memberships")
    evidence.extend(await references(access, memberships, active=False))
    families = (
        await rows(access, ProductFamily, ProductFamily.status == "ACTIVE")
        if body.is_required
        else []
    )
    evidence.extend(families)
    family_ids = {row.family_id for row in memberships} | {row.id for row in families}
    if len(family_ids) > 512:
        raise ConflictError("scheme transition exceeds the family impact review limit")
    # Sweep each family's boundaries; adjacent dated sets do not overlap.
    checks = 0
    for family_id in family_ids:
        history = [row for row in memberships if row.family_id == family_id]
        for point in boundaries(((row.valid_from, row.valid_to) for row in history), today):
            checks += max(len(history), 1)
            if checks > 100000:
                raise ConflictError("scheme transition exceeds its interval review budget")
            current = [
                row
                for row in history
                if row.valid_from <= point and (row.valid_to is None or row.valid_to >= point)
            ]
            try:
                cardinality(body.membership_mode, (row.is_primary for row in current))
            except ConflictError:
                blockers.append("membership_cardinality")
            if body.is_required and family_id in {row.id for row in families} and not current:
                blockers.append("active_family_missing_required_scheme")
    return evidence, sorted(set(blockers)), len(children), len(memberships), len(family_ids)


async def preview(
    access: ConfigurationAccess, scheme_id: uuid.UUID, body: s.SchemeTransition, secret: bytes
) -> s.SchemeTransitionPreview:
    access.actor.require_scope("category_scheme.read", target=ScopePath(company_id=access.company))
    await access.context(CategoryScheme, "category_scheme.manage")
    scheme = await access.scoped(CategoryScheme, scheme_id)
    await access.require(scheme)
    if scheme.row_version != body.expected_version:
        raise ConflictError("scheme changed; reload before reviewing")
    values = body.model_dump(exclude={"expected_version", "preview_token"})
    context = await access.context(CategoryScheme)
    before = await access.values(scheme)
    context.assert_writable(
        frozenset(key for key, value in values.items() if before[key] != value),
        before=before,
        after={**before, **values},
    )
    evidence, blockers, categories, memberships, families = await impact(access, scheme, body)
    proof = await stamp(
        access, CategoryScheme, body.model_dump(mode="json", exclude={"preview_token"}), evidence
    )
    return s.SchemeTransitionPreview(
        scheme_id=scheme_id,
        expected_version=body.expected_version,
        category_count=categories,
        membership_count=memberships,
        affected_family_count=families,
        eligible=not blockers,
        blockers=blockers,
        policy_generation=proof["generation"],
        source_version=proof["source"],
        preview_token=codec(access, secret, str(scheme_id)).encode(proof),
    )


async def transition(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    scheme_id: uuid.UUID,
    body: s.SchemeTransitionCommit,
    key: str,
    secret: bytes,
) -> CommandResult[SchemeDetail]:
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.category_scheme.transition",
        key,
        {"id": str(scheme_id), "body": body.model_dump(mode="json")},
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        actor.require_scope("category_scheme.read", target=ScopePath(company_id=company))
        access = ConfigurationAccess(db, actor, company)
        context = await access.context(CategoryScheme, "category_scheme.manage")
        scheme = await access.scoped(CategoryScheme, scheme_id)
        await access.require(scheme)
        await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for model in (
                ItemCategory,
                FamilyCategory,
                *([ProductFamily] if body.is_required else []),
            ):
                dependency_context = await access.context(model)
                if set(dependency_context.native.fields) - dependency_context.readable():
                    raise PermissionDeniedError("scheme review dependency fields are protected")
            before = await access.values(scheme)
            context.assert_writable(
                frozenset(receipt["changed"]),
                before=before,
                after={**before, **body.model_dump(exclude={"preview_token", "expected_version"})},
            )
            # Recheck retained dependency identities rather than only today's membership set.
            models = {
                model.__tablename__: model
                for model in (CategoryScheme, ItemCategory, FamilyCategory, ProductFamily)
            }
            for entity, object_id in receipt["dependencies"]:
                value = await access.scoped(models[entity], uuid.UUID(object_id))
                await access.require(value)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        access = ConfigurationAccess(db, actor, company)
        fresh = await preview(access, scheme_id, body, secret)
        proof = codec(access, secret, str(scheme_id))
        if proof.decode(body.preview_token) != proof.decode(fresh.preview_token):
            raise ConflictError("scheme impact changed; review again")
        if not fresh.eligible:
            raise ConflictError("scheme transition has unresolved membership dependencies")
        scheme = await access.scoped(CategoryScheme, scheme_id)
        evidence, _, _, _, _ = await impact(access, scheme, body)
        state = await policy_state(db, actor, company, lock=True)
        assert state is not None
        if scheme.row_version >= 2**31 - 1 or state.generation >= 2**63 - 1:
            raise ConflictError("scheme or company version exhausted")
        before = await access.values(scheme)
        for field in ("membership_mode", "is_required", "is_active"):
            setattr(scheme, field, getattr(body, field))
        scheme.row_version += 1
        scheme.updated_at, scheme.updated_by = utcnow(), actor.user_id
        scheme.deactivated_at = None if scheme.is_active else utcnow()
        scheme.deactivated_by = None if scheme.is_active else actor.user_id
        changed = await access.write(scheme, before)
        audit_change(
            db,
            actor,
            company,
            "catalog.category_scheme",
            scheme.id,
            "update",
            changed,
            before=before,
            after=await access.values(scheme),
        )
        state.generation += 1
        await db.flush()
        return CommandReceipt(
            200,
            {
                "changed": sorted(changed),
                "dependencies": [
                    list(key)
                    for key in sorted({(row.__tablename__, str(row.id)) for row in evidence})
                ],
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> SchemeDetail:
        access = ConfigurationAccess(db, actor, company)
        scheme = await access.scoped(CategoryScheme, scheme_id)
        state = await policy_state(db, actor, company, lock=False)
        assert state is not None
        value = protected_detail(
            scheme, await access.context(CategoryScheme), SCHEME, state.generation
        )
        return SchemeDetail.model_validate(value.model_dump(exclude_unset=True))

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render
    )
