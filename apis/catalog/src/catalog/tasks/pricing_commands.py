"""Company-locked pricing commands with current field authority, receipts and audit."""

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import (
    PRICING_MODELS,
    ItemPrice,
    ItemPriceDraft,
    ItemPriceSeries,
    PricePlan,
    PricingRow,
)
from catalog.models.products import Item, ProductFamily
from catalog.schemas.pricing import CommandOutput, DatedInput, PublicationInput
from catalog.tasks.classification import audit_change
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import MANAGE_PERMISSIONS, FieldWriteChecks, load_field_context
from catalog.tasks.policy_state import policy_state

RowT = TypeVar("RowT", bound=Base)


def business_date(timezone: str) -> dt.date:
    return utcnow().astimezone(ZoneInfo(timezone)).date()


async def protected(access: ConfigurationAccess, model: type[Any]) -> None:
    context = await access.context(model)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("pricing requires readable dependency fields")


async def row(access: ConfigurationAccess, model: type[RowT], object_id: uuid.UUID) -> RowT:
    await protected(access, model)
    value = await company_object(access.db, model, object_id, company_id=access.company)
    await access.require(value)
    return value


async def product(access: ConfigurationAccess, item_id: uuid.UUID) -> tuple[Item, ProductFamily]:
    item = await row(access, Item, item_id)
    family = await row(access, ProductFamily, item.family_id)
    return item, family


async def purpose_access(access: ConfigurationAccess, value: Any, *, write: bool = False) -> None:
    if isinstance(value, PricePlan):
        plan = value
    elif isinstance(value, ItemPriceSeries):
        plan = await row(access, PricePlan, value.plan_id)
    elif isinstance(value, ItemPriceDraft | ItemPrice):
        series = await row(access, ItemPriceSeries, value.series_id)
        plan = await row(access, PricePlan, series.plan_id)
    elif hasattr(value, "price_id") and (value.price_id or value.draft_id):
        parent = await row(
            access,
            ItemPrice if value.price_id else ItemPriceDraft,
            value.price_id or value.draft_id,
        )
        await purpose_access(access, parent, write=write)
        return
    else:
        return
    if plan.purpose == "PURCHASE":
        access.actor.require_scope(
            "purchase_price.read", target=ScopePath(company_id=access.company)
        )
        if write:
            access.actor.require_scope(
                "purchase_price.manage", target=ScopePath(company_id=access.company)
            )


async def effective(
    access: ConfigurationAccess, model: type[RowT], as_of: dt.date, **filters: Any
) -> RowT | None:
    await protected(access, model)
    dated: Any = model
    rows = list(
        await access.db.scalars(
            select(model)
            .where(
                dated.company_id == access.company,
                *(getattr(model, key) == value for key, value in filters.items()),
                dated.valid_from <= as_of,
                or_(dated.valid_to.is_(None), dated.valid_to >= as_of),
            )
            .limit(2)
        )
    )
    if len(rows) > 1:
        raise ConflictError("ambiguous effective pricing history")
    if rows:
        await access.require(rows[0])
        return rows[0]
    return None


class PricingWork:
    #: Whose field context answers the expectation check. Pricing's own plan by default; a
    #: command surface reached by an administrator who holds no ``price_plan.read`` names its
    #: own entity instead, and the check keeps meaning exactly what it means here — the
    #: generation is the company's and ``source_version`` is the Identity checkpoint.
    entity_model: type[PricingRow] = PricePlan
    #: What a stale-preview refusal calls the policy the caller previewed.
    policy_subject: str = "pricing policy"

    @staticmethod
    async def authorize_reference(
        access: ConfigurationAccess, value: Any, *, write: bool = False
    ) -> None:
        await purpose_access(access, value, write=write)

    async def validate(self) -> None:
        """Optional aggregate validation inside the same command transaction."""

    async def published(self) -> None:
        """Optional hook after the generation bump, inside the same command transaction.

        A work type that feeds a replica emits its outbox events here, so the published
        ``source_version`` is the bumped generation and a rollback discards both together.
        """

    def __init__(self, access: ConfigurationAccess, state: CatalogPolicyState) -> None:
        self.access, self.state = access, state
        self.db, self.actor, self.company = access.db, access.actor, access.company
        self.changed: dict[str, set[str]] = {}

    async def record(self, value: Any, before: Mapping[str, Any], action: str = "create") -> None:
        self.actor.require_scope(
            MANAGE_PERMISSIONS["catalog." + value.__tablename__],
            target=ScopePath(company_id=self.company),
        )
        context = await self.access.context(type(value))
        after = await self.access.values(value)
        if hasattr(value, "custom_fields"):
            after.update(
                {"custom_field:" + key: entry for key, entry in (value.custom_fields or {}).items()}
            )
        fields = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        context.assert_writable(
            fields,
            before=before,
            after=after,
            checked=self.access.checks.setdefault(context.native.entity_type, FieldWriteChecks()),
        )
        if fields:
            self.changed.setdefault(context.native.entity_type, set()).update(fields)
            audit_change(
                self.db,
                self.actor,
                self.company,
                context.native.entity_type,
                value.id,
                action,
                fields,
                before=before,
                after=after,
            )
        self.db.add(value)
        await self.db.flush()

    async def new(self, model: type[RowT], audit_action: str = "create", /, **values: Any) -> RowT:
        # Named `audit_action`, not `action`: two Catalog tables have an `action` column of their
        # own, and a parameter sharing that name would swallow the column's value silently.
        # Positional-only for the same reason from the other side: callers legitimately unpack a
        # narrow mapping of columns into `**values`, and a named parameter here would demand that
        # every such mapping's value type also satisfy this one.
        # A row whose audited fact is the reviewed delivery rather than the row's appearance
        # says so — `catalog_policy_release` registers only `publish` in the audit contract.
        value = model(
            id=uuid7(),
            tenant_id=self.actor.tenant_id,
            company_id=self.company,
            row_version=1,
            created_by=self.actor.user_id,
            updated_by=self.actor.user_id,
            **values,
        )
        await self.record(value, {}, audit_action)
        return value

    async def update(
        self, value: Any, expected_version: int, audit_action: str = "update", /, **values: Any
    ) -> None:
        await self.access.require(value)
        if value.row_version != expected_version or value.row_version >= 2**31 - 1:
            raise ConflictError("pricing version changed or exhausted")
        before = await self.access.values(value)
        if hasattr(value, "custom_fields"):
            before.update(
                {"custom_field:" + key: entry for key, entry in (value.custom_fields or {}).items()}
            )
        for key, entry in values.items():
            setattr(value, key, entry)
        value.row_version += 1
        value.updated_at, value.updated_by = utcnow(), self.actor.user_id
        await self.record(value, before, audit_action)

    async def publication(self, body: PublicationInput) -> None:
        context = await self.access.context(self.entity_model)
        if (
            body.expected_generation != self.state.generation
            or body.expected_source_version != context.source_version
        ):
            raise ConflictError(f"{self.policy_subject} or Identity source changed; preview again")

    async def history(self, model: type[Any], body: DatedInput, filters: dict[str, Any]) -> None:
        await self.publication(body)
        company = (await self.access.context(model)).company
        if body.valid_from < business_date(company.timezone):
            raise ConflictError("new pricing history cannot rewrite past dates")
        await protected(self.access, model)
        overlaps = list(
            await self.db.scalars(
                select(model)
                .where(
                    model.company_id == self.company,
                    *(getattr(model, key) == value for key, value in filters.items()),
                    or_(model.valid_to.is_(None), model.valid_to >= body.valid_from),
                    model.valid_from <= (body.valid_to or dt.date.max),
                )
                .limit(2)
            )
        )
        previous = None
        if body.supersedes_id is not None:
            previous = await row(self.access, model, body.supersedes_id)
            if any(getattr(previous, key) != value for key, value in filters.items()):
                raise PermissionDeniedError("replacement belongs to a different price history")
            if previous.valid_from >= body.valid_from or (
                previous.valid_to is not None and previous.valid_to < body.valid_from
            ):
                raise ConflictError("replacement must shorten an applicable predecessor")
        if any(previous is None or entry.id != previous.id for entry in overlaps):
            raise ConflictError("pricing history overlaps an existing revision")
        if previous is not None:
            assert body.expected_previous_version is not None
            await self.update(
                previous,
                body.expected_previous_version,
                valid_to=body.valid_from - dt.timedelta(days=1),
            )


Handler = Callable[[PricingWork, Any, uuid.UUID | None], Awaitable[PricingRow]]


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    model: type[PricingRow],
    body: Any,
    key: str,
    handler: Handler,
    *,
    object_id: uuid.UUID | None = None,
    action: str = "create",
    models: tuple[type[PricingRow], ...] = PRICING_MODELS,
    work_type: type[PricingWork] = PricingWork,
    publish_permission: str = "price_plan.publish",
    timeout_seconds: int | None = None,
) -> CommandResult[CommandOutput]:
    entity = "catalog." + model.__tablename__
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        entity + "." + action,
        key,
        {
            "id": str(object_id) if object_id else None,
            "body": body.model_dump(
                mode="json",
                exclude={"accept_defaults"}
                if getattr(body, "accept_defaults", None) is None
                else set(),
            ),
        },
    )
    state: CatalogPolicyState | None = None
    checks: dict[str, FieldWriteChecks] = {}
    access: ConfigurationAccess | None = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal state, access
        access = ConfigurationAccess(db, actor, company)
        access.checks = checks
        await access.context(model, MANAGE_PERMISSIONS[entity])
        if action == "publish" or isinstance(body, PublicationInput):
            actor.require_scope(publish_permission, target=ScopePath(company_id=company))
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for name, fields in receipt["changed"].items():
                context = await load_field_context(
                    db, actor, company, name, permission=MANAGE_PERMISSIONS[name]
                )
                if name in checks:
                    checks[name].recheck(context)
                else:
                    assert_fields_writable(
                        frozenset(fields),
                        rules=context.rules(),
                        target=ScopePath(company_id=company),
                    )
            result_model = next(m for m in models if m.__tablename__ == receipt["model"])
            value = await row(access, result_model, uuid.UUID(receipt["id"]))
            await work_type.authorize_reference(access, value, write=True)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert access is not None and state is not None
        if state.generation >= 2**63 - 1:
            raise ConflictError("company pricing generation exhausted")
        work = work_type(access, state)
        value = await handler(work, body, object_id)
        await work.validate()
        await work_type.authorize_reference(access, value, write=True)
        if work.changed:
            state.generation += 1
            await work.published()
        await db.flush()
        return CommandReceipt(
            201 if action in {"create", "publish"} else 200,
            {
                "id": str(value.id),
                "model": value.__tablename__,
                "changed": {name: sorted(fields) for name, fields in work.changed.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> CommandOutput:
        assert access is not None and state is not None
        result_model = next(m for m in models if m.__tablename__ == receipt["model"])
        value = await row(access, result_model, uuid.UUID(receipt["id"]))
        await work_type.authorize_reference(access, value)
        context = await access.context(result_model)
        return CommandOutput(
            id=value.id,
            row_version=value.row_version,
            policy_generation=state.generation,
            source_version=context.source_version,
        )

    try:
        if timeout_seconds is None:
            return await execute_idempotent(
                factory, identity, authorize=authorize, mutate=mutate, render=render
            )
        return await execute_idempotent(
            factory,
            identity,
            authorize=authorize,
            mutate=mutate,
            render=render,
            timeout_seconds=timeout_seconds,
        )
    except IntegrityError as exc:
        raise ConflictError("pricing definition conflicts or its references changed") from exc
