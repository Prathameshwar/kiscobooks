"""Atomic configuration draft editing and immutable dated publication."""

import uuid
from collections.abc import Mapping
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import (
    FilterColumn,
    ListQuery,
    Page,
    SortColumn,
    apply_filters,
    fetch_page,
    resolve_sort,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Currency
from catalog.models.classification import CatalogPolicyState
from catalog.models.configuration import (
    ConfigurationRow,
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductConfigurationScope,
)
from catalog.schemas.configuration import (
    CompanyDraftInput,
    ConfigurationComparison,
    ConfigurationPreview,
    DraftInput,
    DraftListItem,
    DraftPatch,
    EffectiveQuery,
    PublishInput,
    RevisionListItem,
    RevisionQuery,
    ScopeCreate,
    ScopeListItem,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.configuration_access import CHILDREN, ConfigurationAccess
from catalog.tasks.configuration_editing import merge_draft
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.field_context import FieldWriteChecks
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state

ConfigKind = Literal["scope", "draft", "revision"]
MODELS = {
    "scope": ProductConfigurationScope,
    "draft": ProductConfigurationDraft,
    "revision": ProductConfigurationRevision,
}
LISTS: dict[str, type[BaseModel]] = {
    "scope": ScopeListItem,
    "draft": DraftListItem,
    "revision": RevisionListItem,
}


async def validate(access: ConfigurationAccess, body: DraftInput) -> None:
    if body.options.variants_mode == "REQUIRED" or body.options.variants_default is True:
        from catalog.tasks.product_mode import require_advanced

        await require_advanced(access.db, access.company)
    scope = await access.scoped(ProductConfigurationScope, body.scope_id)
    await access.company_scope(scope)
    await access.profile_references(body.profiles)
    for numeric in body.numeric_defaults:
        if numeric.currency is not None and await access.db.get(Currency, numeric.currency) is None:
            raise ValidationFailedError("numeric default currency is not a supported reference")
    context = await access.context(ProductConfigurationScope)
    if (
        body.pricing.additional_currencies_mode == "ENABLED"
        and "multi_currency" not in context.features
    ):
        raise ConflictError("additional pricing currencies require enabled multi_currency")
    if body.pricing.sale_level_count is not None and body.pricing.sale_level_count > 1:
        if "multi_price_levels" not in context.features:
            raise ConflictError("additional sale levels require an available company capability")
    if (
        body.pricing.multiple_price_levels_mode == "ENABLED"
        and "multi_price_levels" not in context.features
    ):
        raise ConflictError("multiple selling-price levels require enabled multi_price_levels")


async def effective_queries(access: ConfigurationAccess, body: DraftInput) -> list[EffectiveQuery]:
    """Preview the company configuration for both supported product kinds."""
    scope = await access.scoped(ProductConfigurationScope, body.scope_id)
    await access.company_scope(scope)
    # The Company draft replaces its complete layer. Strict profile pairs make
    # VALUE the only mode with an ID, so the declared default type can be checked
    # directly without an extra generic resolution for each product kind.
    return [
        EffectiveQuery(
            as_of=body.effective_from,
            kind="GOODS",
            product_type_revision_id=body.profiles.goods_type_revision_id,
        ),
        EffectiveQuery(
            as_of=body.effective_from,
            kind="SERVICE",
            product_type_revision_id=body.profiles.service_type_revision_id,
        ),
    ]


async def validate_effective(access: ConfigurationAccess, body: DraftInput) -> None:
    for query in await effective_queries(access, body):
        await resolve(access.db, access.actor, access.company, query, draft=body)


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, kind: ConfigKind, object_id: uuid.UUID
) -> BaseModel:
    access = ConfigurationAccess(db, actor, company)
    row = await access.scoped(MODELS[kind], object_id)
    scope = (
        row
        if isinstance(row, ProductConfigurationScope)
        else await access.scoped(
            ProductConfigurationScope,
            cast(ProductConfigurationDraft | ProductConfigurationRevision, row).scope_id,
        )
    )
    await access.scope_owner(scope)
    state = await policy_state(db, actor, company)
    return await access.detail(row, state.generation if state else 1)


async def preview(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID
) -> ConfigurationPreview:
    access = ConfigurationAccess(db, actor, company)
    row = await access.scoped(ProductConfigurationDraft, object_id)
    body = await access.input(row)
    if row.status != "DRAFT":
        raise ConflictError("published drafts cannot be previewed for publication")
    await validate(access, body)
    comparisons = []
    for query in await effective_queries(access, body):
        after = await resolve(db, actor, company, query, draft=body)
        conflicts = []
        try:
            before = await resolve(db, actor, company, query)
        except (ConflictError, ValidationFailedError) as exc:
            # A valid repair must remain previewable when current defaults conflict.
            # Authorization failures still propagate; never fall back around a read deny.
            before = None
            conflicts.append(exc.message)
        changed: list[str] = []
        if before is not None:
            for section in ("options", "profiles", "pricing"):
                old = getattr(before, section).model_dump()
                new = getattr(after, section).model_dump()
                changed.extend(section + "." + key for key in old if old[key] != new[key])
            if before.numeric_defaults != after.numeric_defaults:
                changed.append("numeric_defaults")
        comparisons.append(
            ConfigurationComparison(
                kind=query.kind,
                before=before,
                before_conflicts=conflicts,
                after=after,
                changed_fields=sorted(changed),
            )
        )
    state = await policy_state(db, actor, company)
    context = await access.context(ProductConfigurationDraft)
    return ConfigurationPreview(
        draft_id=row.id,
        draft_version=row.row_version,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        effective_from=row.effective_from,
        validated=True,
        comparisons=comparisons,
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: ScopeCreate | CompanyDraftInput | DraftPatch | PublishInput,
    key: str,
    *,
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    creating_scope = isinstance(body, ScopeCreate)
    creating_draft = isinstance(body, CompanyDraftInput)
    publishing = isinstance(body, PublishInput)
    model = ProductConfigurationScope if creating_scope else ProductConfigurationDraft
    action = "publish" if publishing else "create" if creating_scope or creating_draft else "update"
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog." + model.__tablename__ + "." + action,
        key,
        {
            "body": body.model_dump(mode="json", exclude_unset=True),
            "id": str(object_id) if object_id else None,
        },
    )
    accesses: list[ConfigurationAccess] = []
    checks: dict[str, FieldWriteChecks] = {}
    state: CatalogPolicyState | None = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal state
        actor.require_scope("product_configuration.read", target=ScopePath(company_id=company))
        access = ConfigurationAccess(db, actor, company)
        access.checks = checks
        accesses.append(access)
        await access.context(
            model, "product_configuration.publish" if publishing else "product_configuration.manage"
        )
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for entity, fields in receipt["changed"].items():
                from catalog.models.configuration import CONFIGURATION_MODELS

                owner = next(
                    m for m in CONFIGURATION_MODELS if "catalog." + m.__tablename__ == entity
                )
                context = await access.context(owner)
                if entity in checks:
                    checks[entity].recheck(context)
                else:
                    assert_fields_writable(
                        frozenset(fields),
                        rules=context.rules(),
                        target=ScopePath(company_id=company),
                    )
            result = await access.scoped(MODELS[receipt["kind"]], uuid.UUID(receipt["id"]))
            scope = (
                result
                if isinstance(result, ProductConfigurationScope)
                else await access.scoped(
                    ProductConfigurationScope,
                    cast(ProductConfigurationDraft | ProductConfigurationRevision, result).scope_id,
                )
            )
            await access.scope_owner(scope)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert state is not None
        access = accesses[-1]
        result: ConfigurationRow
        pending_children: list[ConfigurationRow] = []
        changes: dict[str, set[str]] = {}
        common = {
            "tenant_id": actor.tenant_id,
            "company_id": company,
            "created_by": actor.user_id,
            "updated_by": actor.user_id,
        }

        async def record(row: ConfigurationRow, before: Mapping[str, Any]) -> None:
            fields = await access.write(row, before)
            entity = "catalog." + row.__tablename__
            changes.setdefault(entity, set()).update(fields)

        async def children(
            row: ProductConfigurationDraft | ProductConfigurationRevision,
            incoming: DraftInput,
            replacing: bool = False,
        ) -> None:
            owner_field = (
                "draft_id" if isinstance(row, ProductConfigurationDraft) else "revision_id"
            )
            for field, child_model, _ in CHILDREN:
                previous: dict[str, Any] = {}
                if replacing:
                    existing = list(
                        await db.scalars(
                            select(child_model)
                            .where(
                                child_model.company_id == company, child_model.draft_id == row.id
                            )
                            .limit(8)
                        )
                    )
                    for child in existing:
                        await access.require(child)
                        native = await access.values(child)
                        previous[getattr(child, "dimension", "single")] = (child, native)
                values = getattr(incoming, field)
                entries = values if isinstance(values, list) else [values]
                kept = set()
                for entry in entries:
                    identity_key = getattr(entry, "dimension", "single")
                    kept.add(identity_key)
                    before = previous.get(identity_key)
                    if before is None:
                        child = child_model(
                            id=uuid7(),
                            **common,
                            draft_id=None,
                            revision_id=None,
                            **entry.model_dump(),
                        )
                        setattr(child, owner_field, row.id)
                        await record(child, {})
                        pending_children.append(child)
                    else:
                        child, native = before
                        for key, value in entry.model_dump().items():
                            setattr(child, key, value)
                        await record(child, native)
                        child.updated_at, child.updated_by = utcnow(), actor.user_id
                for identity_key, (child, native) in previous.items():
                    if identity_key not in kept:
                        context = await access.context(child_model)
                        context.assert_writable(frozenset(native), before=native, after={})
                        changes.setdefault(context.native.entity_type, set()).update(native)
                        await db.delete(child)

        async def create_company_scope() -> ProductConfigurationScope:
            scope = ProductConfigurationScope(
                id=uuid7(),
                **common,
                scope_kind="COMPANY",
                owner_id=company,
                row_version=1,
                latest_revision=0,
            )
            await record(scope, {})
            await access.company_scope(scope)
            db.add(scope)
            await db.flush([scope])
            return scope

        if isinstance(body, ScopeCreate):
            scope = await create_company_scope()
            result, kind = scope, "scope"
        else:
            if isinstance(body, CompanyDraftInput):
                if isinstance(body, DraftInput):
                    incoming = body
                else:
                    company_scope = await db.scalar(
                        select(ProductConfigurationScope).where(
                            ProductConfigurationScope.company_id == company,
                            ProductConfigurationScope.scope_kind == "COMPANY",
                            ProductConfigurationScope.owner_id == company,
                        )
                    )
                    if company_scope is None:
                        company_scope = await create_company_scope()
                        audit_change(
                            db,
                            actor,
                            company,
                            "catalog.product_configuration_scope",
                            company_scope.id,
                            "create",
                            frozenset({"configuration"}),
                        )
                    await access.company_scope(company_scope)
                    incoming = DraftInput(scope_id=company_scope.id, **body.model_dump())
                row = ProductConfigurationDraft(
                    id=uuid7(),
                    **common,
                    scope_id=incoming.scope_id,
                    status="DRAFT",
                    row_version=1,
                    effective_from=body.effective_from,
                    change_reason=body.change_reason,
                )
                await record(row, {})
                # Preflight all child field writes before resolving any supplied reference.
                await children(row, incoming)
                await validate(access, incoming)
                db.add(row)
                await db.flush([row])
            else:
                assert object_id is not None
                row = await access.scoped(ProductConfigurationDraft, object_id)
                await access.require(row)
                await access.company_scope(
                    await access.scoped(ProductConfigurationScope, row.scope_id)
                )
                if row.status != "DRAFT" or row.row_version != body.expected_version:
                    raise ConflictError("configuration draft changed or is already published")
                if row.row_version >= 2**31 - 1:
                    raise ConflictError("configuration draft version exhausted")
                before = await access.values(row)
                incoming = await access.input(row)
                if isinstance(body, DraftPatch):
                    incoming = merge_draft(incoming, body)
                    row.effective_from, row.change_reason = (
                        incoming.effective_from,
                        incoming.change_reason,
                    )
                    row.row_version += 1
                    row.updated_at, row.updated_by = utcnow(), actor.user_id
                    await record(row, before)
                    await children(row, incoming, replacing=True)
                    await validate(access, incoming)
                else:
                    context = await access.context(ProductConfigurationDraft)
                    if (
                        body.expected_generation != state.generation
                        or body.expected_source_version != context.source_version
                    ):
                        raise ConflictError("configuration preview is stale; preview again")
                    if (
                        row.effective_from
                        < utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
                    ):
                        raise ConflictError(
                            "configuration publication cannot rewrite past defaults"
                        )
                    await validate(access, incoming)
                    scope = await access.scoped(ProductConfigurationScope, row.scope_id)
                    await validate_effective(access, incoming)
                    await access.scope_owner(scope)
                    last = await db.scalar(
                        select(func.max(ProductConfigurationRevision.effective_from)).where(
                            ProductConfigurationRevision.company_id == company,
                            ProductConfigurationRevision.scope_id == scope.id,
                        )
                    )
                    if last is not None and row.effective_from <= last:
                        raise ConflictError(
                            "configuration revisions must advance the effective date"
                        )
                    if max(scope.latest_revision, scope.row_version) >= 2**31 - 1:
                        raise ConflictError("configuration scope version exhausted")
                    old_scope = await access.values(scope)
                    scope.latest_revision += 1
                    scope.row_version += 1
                    scope.updated_at, scope.updated_by = utcnow(), actor.user_id
                    await record(scope, old_scope)
                    row.status, row.row_version = "PUBLISHED", row.row_version + 1
                    row.updated_at, row.updated_by = utcnow(), actor.user_id
                    await record(row, before)
                    revision = ProductConfigurationRevision(
                        id=uuid7(),
                        **common,
                        scope_id=scope.id,
                        source_draft_id=row.id,
                        revision=scope.latest_revision,
                        effective_from=row.effective_from,
                        change_reason=row.change_reason,
                        published_at=utcnow(),
                    )
                    await record(revision, {})
                    await children(revision, incoming)
                    db.add(revision)
                    await db.flush([revision])
                    result, kind = revision, "revision"
            if not publishing:
                result, kind = row, "draft"
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation exhausted")
        state.generation += 1
        db.add_all(pending_children)
        await db.flush()
        audit_change(
            db,
            actor,
            company,
            "catalog." + model.__tablename__,
            row.id if publishing else result.id,
            action,
            frozenset({"configuration"}),
        )
        return CommandReceipt(
            201 if creating_scope or creating_draft or publishing else 200,
            {
                "id": str(result.id),
                "kind": kind,
                "changed": {entity: sorted(fields) for entity, fields in changes.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert state is not None
        access = accesses[-1]
        row = await access.scoped(MODELS[receipt["kind"]], uuid.UUID(receipt["id"]))
        return await access.detail(row, state.generation)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError("configuration identity conflicts or dependency changed") from exc


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    kind: ConfigKind,
    query: ListQuery,
    secret: bytes,
    scope_id: uuid.UUID | None = None,
) -> Page[BaseModel]:
    access = ConfigurationAccess(db, actor, company)
    model, schema = MODELS[kind], LISTS[kind]
    context = await access.context(model)
    if scope_id is not None:
        scope = await access.scoped(ProductConfigurationScope, scope_id)
        await access.scope_owner(scope)
    readable = context.readable() | {"id"}
    keys = set(schema.model_fields) & readable
    stmt = select(*(getattr(model, field) for field in keys)).where(model.company_id == company)
    if kind == "scope":
        stmt = stmt.where(ProductConfigurationScope.scope_kind == "COMPANY")
    if scope_id is not None:
        if "scope_id" not in readable:
            raise PermissionDeniedError("configuration scope membership is protected")
        assert issubclass(model, ProductConfigurationDraft | ProductConfigurationRevision)
        history_model = cast(type[ProductConfigurationDraft | ProductConfigurationRevision], model)
        stmt = stmt.where(history_model.scope_id == scope_id)
    if isinstance(query, RevisionQuery) and query.effective_on is not None:
        if "effective_from" not in readable:
            raise PermissionDeniedError("configuration effective date is protected")
        stmt = stmt.where(ProductConfigurationRevision.effective_from <= query.effective_on)
    filters = {
        key: value
        for key, value in query.model_dump(exclude_none=True).items()
        if key in context.native.fields
    }
    stmt = apply_filters(
        stmt,
        filters,
        filters={key: FilterColumn(key, getattr(model, key)) for key in filters},
        readable=readable,
    )
    if query.q is not None:
        raise ValidationFailedError("configuration lists do not support text search")
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=readable,
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog." + model.__tablename__ + ":" + str(scope_id),
        context,
        query,
    )

    def project(values: Mapping[str, Any]) -> BaseModel:
        return schema.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
