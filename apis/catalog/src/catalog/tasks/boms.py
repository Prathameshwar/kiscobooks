"""Company-locked, audited and replay-safe native BOM aggregate commands."""

import hashlib
import json
import uuid
from typing import Any, Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, FeatureNotEnabledError, PermissionDeniedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.evidence import audit_change
from catalog.models.boms import Bom, BomAssignment, BomComponent, BomDraft, BomOutput, BomRevision
from catalog.schemas.boms import (
    AssignmentDetail,
    BomDraftDetail,
    BomDraftInput,
    BomDraftUpdate,
    BomRevisionDetail,
    ComponentInput,
    OutputInput,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.aggregate_work import AggregateWork
from catalog.tasks.bom_dependencies import goods, line_dependency, route_dependency
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.policy_state import policy_state

Definition = BomDraft | BomRevision
Child = BomComponent | BomOutput
SCALARS = tuple(key for key in BomDraftInput.model_fields if key not in {"components", "outputs"})
DETAILS: dict[type[Any], type[BaseModel]] = {
    BomDraft: BomDraftDetail,
    BomRevision: BomRevisionDetail,
    BomAssignment: AssignmentDetail,
}


def require_feature(context: FieldContext) -> None:
    for required in ("inventory", "bom_definitions"):
        if required not in context.features:
            raise FeatureNotEnabledError(
                "BOM definitions require enabled company capabilities", feature=required
            )


async def children(db: AsyncSession, row: Definition, model: type[Any]) -> list[Any]:
    parent = "draft_id" if isinstance(row, BomDraft) else "revision_id"
    maximum = 1000 if model is BomComponent else 100
    result = list(
        await db.scalars(
            select(model)
            .where(
                model.company_id == row.company_id,
                getattr(model, parent) == row.id,
            )
            .order_by(model.sequence)
            .limit(maximum + 1)
        )
    )
    expected = row.component_count if model is BomComponent else row.output_count
    if (
        len(result) != expected
        or len(result) > maximum
        or tuple(child.sequence for child in result) != tuple(range(1, len(result) + 1))
    ):
        raise ConflictError("BOM child collection is incomplete; reload before continuing")
    return result


async def definition_input(access: ConfigurationAccess, row: Definition) -> BomDraftInput:
    await access.require(row)
    values: dict[str, Any] = {key: getattr(row, key) for key in SCALARS}
    for key, model, schema in (
        ("components", BomComponent, ComponentInput),
        ("outputs", BomOutput, OutputInput),
    ):
        context = await access.context(model)
        if set(schema.model_fields) - context.readable():
            raise PermissionDeniedError(
                "BOM calculation requires complete readable line definitions"
            )
        values[key] = []
        for child in await children(access.db, row, model):
            await access.require(child)
            values[key].append({field: getattr(child, field) for field in schema.model_fields})
    return BomDraftInput.model_validate(values)


async def read_definition(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    model: type[Any],
) -> BaseModel:
    context = await load_field_context(db, actor, company, "catalog." + model.__tablename__)
    if "bom_id" not in context.readable():
        raise PermissionDeniedError("BOM revision access requires readable parent membership")
    row = await company_object(db, model, object_id, company_id=company)
    if row.bom_id != bom_id:
        raise PermissionDeniedError("BOM definition belongs to another parent")
    state = await policy_state(db, actor, company)
    return project(row, context, state.generation if state else 1)


def project(row: Any, context: FieldContext, generation: int) -> BaseModel:
    values = {key: getattr(row, key) for key in context.native.fields}
    readable = context.readable(values)
    schema = DETAILS[type(row)]
    return schema.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "policy_generation": generation,
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in schema.model_fields
            },
        }
    )


class BomWork(AggregateWork):
    async def replace_children(self, row: BomDraft, body: BomDraftInput) -> None:
        # Check every proposed field before any reference can disclose existence.
        for key, model in (("components", BomComponent), ("outputs", BomOutput)):
            for value in getattr(body, key):
                after = {**value.model_dump(), "draft_id": row.id, "revision_id": None}
                await self.authorize_values(model, {}, after, all_fields=True)
        for value in (*body.components, *body.outputs):
            await goods(self.access, value.item_id)
            if value.unit_revision_id is not None:
                await line_dependency(self.access, value, body.definition_date)
        await route_dependency(self.access, body)
        for key, model in (("components", BomComponent), ("outputs", BomOutput)):
            existing = await children(self.db, row, model)
            old = {value.line_key: value for value in existing}
            proposed_keys = {value.line_key for value in getattr(body, key)}
            for value in existing:
                before = await self.access.values(value)
                await self.authorize_values(model, before, {})
                self.changed.setdefault("catalog." + model.__tablename__, set()).update(before)
                if value.line_key not in proposed_keys:
                    audit_change(
                        self.db,
                        self.actor,
                        self.company,
                        "catalog." + model.__tablename__,
                        value.id,
                        "update",
                        frozenset(before),
                        before=before,
                        after={},
                    )
                await self.db.delete(value)
            await self.db.flush()
            for value in getattr(body, key):
                previous = old.get(value.line_key)
                common = self.common()
                if previous is not None:
                    common.update(
                        id=previous.id,
                        created_at=previous.created_at,
                        created_by=previous.created_by,
                    )
                child = model(**common, draft_id=row.id, revision_id=None, **value.model_dump())
                self.db.add(child)
                await self.record(
                    child,
                    await self.access.values(previous) if previous is not None else {},
                    "update" if previous is not None else "create",
                )
        row.component_count, row.output_count = len(body.components), len(body.outputs)

    async def publish(self, row: BomDraft, generation: int) -> BomRevision:
        body = await definition_input(self.access, row)
        if not body.outputs or sum(output.role == "PRIMARY" for output in body.outputs) != 1:
            raise ConflictError("publication requires exactly one primary output")
        for model in (BomComponent, BomOutput):
            for child in await children(self.db, row, model):
                values = await self.access.values(child)
                await self.authorize_values(model, values, values, all_fields=True)
        evidence: list[dict[str, Any]] = []
        for line in (*body.components, *body.outputs):
            dependency = await line_dependency(self.access, line, body.definition_date)
            quantity = (
                line.quantity
                if isinstance(line, ComponentInput)
                else cast(OutputInput, line).nominal_quantity
            )
            dependency.validate(quantity)
            evidence.append({"line_key": str(line.line_key), **dependency.evidence})
        manifest = {
            "schema": 1,
            "source_version": (await self.access.context(BomDraft)).source_version,
            "definition": body.model_dump(mode="json"),
            "dependencies": evidence,
            "route": await route_dependency(self.access, body),
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        number = await self.db.scalar(
            select(func.max(BomRevision.revision)).where(
                BomRevision.company_id == self.company,
                BomRevision.bom_id == row.bom_id,
            )
        )
        if number is not None and number >= 2**31 - 1:
            raise ConflictError("BOM revision numbering is exhausted")
        revision = BomRevision(
            **self.common(),
            bom_id=row.bom_id,
            draft_id=row.id,
            revision=(number or 0) + 1,
            row_version=1,
            status="PUBLISHED",
            published_at=utcnow(),
            policy_generation=generation,
            source_version=manifest["source_version"],
            content_sha256=hashlib.sha256(encoded).hexdigest(),
            dependency_manifest=manifest,
            component_count=row.component_count,
            output_count=row.output_count,
            **{key: getattr(body, key) for key in SCALARS},
        )
        await self.record(revision, {}, "publish", all_fields=True)
        self.db.add(revision)
        await self.db.flush([revision])
        for key, model in (("components", BomComponent), ("outputs", BomOutput)):
            for line in getattr(body, key):
                child = model(
                    **self.common(), draft_id=None, revision_id=revision.id, **line.model_dump()
                )
                await self.record(child, {}, "publish", all_fields=True)
                self.db.add(child)
        row.status, row.published_revision_id = "PUBLISHED", revision.id
        return revision


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    bom_id: uuid.UUID,
    body: BomDraftInput | BomDraftUpdate | ExpectedVersion,
    key: str,
    action: Literal["create", "update", "publish", "retire"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    model: type[Any] = BomRevision if action == "retire" else BomDraft
    permission = "bom.publish" if action in {"publish", "retire"} else "bom.manage"
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "bom." + action,
        key,
        {
            "bom_id": str(bom_id),
            "object_id": str(object_id) if object_id else None,
            "body": body.model_dump(mode="json"),
        },
    )
    work: BomWork | None = None
    state: Any = None
    checks: dict[str, FieldWriteChecks] = {}

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal work, state
        work = BomWork(db, actor, company, permission)
        work.checks = checks
        context = await work.context(model)
        if action != "retire":
            require_feature(context)
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for entity, keys in receipt["changed"].items():
                current = await load_field_context(
                    db, actor, company, entity, permission=permission
                )
                if entity in checks:
                    checks[entity].recheck(current)
                else:
                    assert_fields_writable(
                        frozenset(keys), rules=current.rules(), target=ScopePath(company_id=company)
                    )
            await read_definition(db, actor, company, bom_id, uuid.UUID(receipt["id"]), model)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert work is not None and state is not None
        parent = await company_object(db, Bom, bom_id, company_id=company)
        await work.access.require(parent)
        if action != "retire" and not parent.is_active:
            raise ConflictError("BOM is inactive")
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation is exhausted")
        if action == "create":
            assert isinstance(body, BomDraftInput)
            number = await db.scalar(
                select(func.max(BomDraft.draft_number)).where(
                    BomDraft.company_id == company,
                    BomDraft.bom_id == bom_id,
                )
            )
            if number is not None and number >= 2**31 - 1:
                raise ConflictError("BOM draft numbering is exhausted")
            row = BomDraft(
                **work.common(),
                bom_id=bom_id,
                draft_number=(number or 0) + 1,
                status="DRAFT",
                published_revision_id=None,
                row_version=1,
                component_count=0,
                output_count=0,
                **{key: getattr(body, key) for key in SCALARS},
            )
            before: dict[str, Any] = {}
            await work.authorize_values(BomDraft, before, await work.access.values(row))
            db.add(row)
            await db.flush([row])
            await work.replace_children(row, body)
        else:
            assert object_id is not None and isinstance(body, ExpectedVersion)
            row = await company_object(db, model, object_id, company_id=company, lock=True)
            if row.bom_id != bom_id:
                raise PermissionDeniedError("BOM definition belongs to another parent")
            if row.row_version != body.expected_version:
                raise ConflictError("BOM version changed; reload before continuing")
            if row.row_version >= 2**31 - 1:
                raise ConflictError("BOM version is exhausted")
            before = await work.access.values(row)
            if action == "retire":
                if row.status != "PUBLISHED":
                    raise ConflictError("only a published BOM can be retired")
                row.status = "RETIRED"
            else:
                if row.status != "DRAFT":
                    raise ConflictError("published BOM drafts are immutable")
                if action == "update":
                    assert isinstance(row, BomDraft) and isinstance(body, BomDraftUpdate)
                    await work.authorize_values(
                        BomDraft, before, {**before, **{key: getattr(body, key) for key in SCALARS}}
                    )
                    await work.replace_children(row, body)
                    for key in SCALARS:
                        setattr(row, key, getattr(body, key))
                else:
                    assert isinstance(row, BomDraft)
                    await work.publish(row, state.generation + 1)
            row.row_version += 1
            row.updated_at, row.updated_by = utcnow(), actor.user_id
        await work.record(row, before, action)
        state.generation += 1
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {
                "id": str(row.id),
                "changed": {name: sorted(fields) for name, fields in work.changed.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return await read_definition(db, actor, company, bom_id, uuid.UUID(receipt["id"]), model)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "BOM references or revision conflict with existing definitions"
        ) from exc
