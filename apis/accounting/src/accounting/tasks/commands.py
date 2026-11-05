"""Idempotent native master commands with one company lock and atomic audit evidence."""

from __future__ import annotations

import secrets
import uuid
from typing import Any, cast

from billing_platform.authz import ScopePath
from billing_platform.crypto import AesGcmCipher
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.db.claims import insert_candidate
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from identity_posting import PostingClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.domain.master_metadata import METADATA_VERSION, PRESENTATION
from accounting.domain.rules import GroupNode, guard_effective_edit, hierarchy
from accounting.events.audit_contract import SENSITIVE_READS, audit_event
from accounting.events.evidence import access_event, changes
from accounting.models import masters as m
from accounting.models.workflows import MasterRevision
from accounting.resources import BY_NAME, Resource
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.group_metadata import guard_group_change, normalize_group
from accounting.tasks.validation import (
    guard_child_intervals,
    guard_registration_links,
    guard_retirement,
    validate,
)

READ_ONLY = frozenset(
    {
        "account_head",
        "account_group_closure",
        "accounting_setup",
        "account_template_installation",
        "account_template_binding",
    }
)


async def require_metadata(db: AsyncSession, access: Access) -> None:
    version = await db.scalar(
        select(m.AccountingSetup.metadata_version).where(
            m.AccountingSetup.company_id == access.context.company_id
        )
    )
    if version is not None and version != METADATA_VERSION:
        raise ConflictError("company master metadata requires backfill before use")


async def setup_lock(db: AsyncSession, access: Access) -> m.AccountingSetup:
    row = await db.scalar(
        select(m.AccountingSetup)
        .where(m.AccountingSetup.company_id == access.context.company_id)
        .with_for_update()
    )
    if row is None:
        raise ConflictError("initialize Accounting for this company first")
    if row.metadata_version != METADATA_VERSION:
        raise ConflictError("company master metadata requires backfill before use")
    if row.base_currency != access.context.base_currency:
        if (
            await db.scalar(
                select(m.Account.id)
                .where(m.Account.company_id == row.company_id, m.Account.used_at.is_not(None))
                .limit(1)
            )
            is not None
        ):
            raise ConflictError("company currency differs from financially used accounts")
        await update_setup(db, access, row, {"base_currency": access.context.base_currency})
    row.generation += 1
    return row


async def update_setup(
    db: AsyncSession, access: Access, row: m.AccountingSetup, values: dict[str, Any]
) -> None:
    """Implicit setup changes have the same field policy and audit contract as master edits."""
    spec = BY_NAME["accounting_setup"]
    before = values_of(row, spec)
    changed = writable(access, spec, before, before | values)
    if changed:
        for key in changed:
            setattr(row, key, values[key])
        row.row_version += 1
        row.updated_by = access.actor.user_id
        await db.flush()
        audit(db, access, spec, row, "update", changed)


def values_of(row: m.Record, spec: Resource) -> dict[str, Any]:
    return {key: getattr(row, key) for key in spec.detail.model_fields if hasattr(row, key)}


def protected(row: m.Record, spec: Resource, access: Access) -> BaseModel:
    values = values_of(row, spec)
    allowed = readable(access, spec, values)
    return spec.detail.model_validate(
        {key: value for key, value in values.items() if key in allowed}
    )


def audit(
    db: AsyncSession, access: Access, spec: Resource, row: m.Record, action: str, changed: set[str]
) -> None:
    db.add(
        MasterRevision(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=row.company_id,
            entity_type=spec.name,
            object_id=row.id,
            action=action,
            object_version=row.row_version,
            changed_fields=sorted(changed),
            created_by=access.actor.user_id,
            updated_by=access.actor.user_id,
        )
    )
    emit(
        db,
        aggregate_type="accounting." + spec.name,
        aggregate_id=row.id,
        event_type=audit_event(spec.name, action),
        tenant_id=access.actor.tenant_id,
        payload=audit_payload(
            action=audit_event(spec.name, action),
            category="money" if spec.lifecycle == "command" else "admin",
            entity_type="accounting." + spec.name,
            entity_id=row.id,
            actor_user_id=access.actor.user_id,
            company_id=row.company_id,
            changes=changes(row, changed, action),
        )
        | {"actor_type": "user"},
    )


def protected_read(db: AsyncSession, row: m.Record, spec: Resource, access: Access) -> BaseModel:
    result = protected(row, spec, access)
    if spec.name in SENSITIVE_READS:
        access_event(db, access, spec, "read", object_id=row.id)
    return result


async def rebuild_hierarchy(db: AsyncSession, company: uuid.UUID) -> None:
    groups = list(
        await db.scalars(
            select(m.AccountGroup).where(m.AccountGroup.company_id == company).limit(10001)
        )
    )
    if len(groups) > 10000:
        raise ConflictError("hierarchy exceeds the supported group capacity")
    paths = hierarchy([GroupNode(row.id, row.parent_id, row.head_id) for row in groups])
    # Every mutation is tenant-bound, company-bound and protected by setup_lock.
    from billing_platform.db import unfiltered
    from billing_platform.db.tenant_context import require_current_tenant

    tenant_id = require_current_tenant()
    # Derived rows only: both explicit boundaries remain on this reviewed bulk delete.
    with unfiltered():
        await db.execute(
            delete(m.AccountGroupClosure).where(
                m.AccountGroupClosure.tenant_id == tenant_id,
                m.AccountGroupClosure.company_id == company,
            )
        )
    tenant = groups[0].tenant_id if groups else None
    for ancestor, descendant, depth in paths:
        db.add(
            m.AccountGroupClosure(
                id=uuid7(),
                tenant_id=tenant,
                company_id=company,
                ancestor_id=ancestor,
                descendant_id=descendant,
                depth=depth,
            )
        )
    await db.flush()


def cipher(settings: Settings) -> AesGcmCipher:
    if settings.encryption_key is None:
        raise ConflictError("beneficiary encryption is not configured")
    return AesGcmCipher(bytes.fromhex(settings.encryption_key.get_secret_value()))


def associated_data(access: Access, object_id: uuid.UUID) -> bytes:
    scope = f"{access.actor.tenant_id}:{access.context.company_id}:{object_id}"
    return f"accounting.bank.v1:{scope}".encode()


async def mutate_master(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    action: str,
    body: BaseModel,
    settings: Settings,
    object_id: uuid.UUID | None = None,
) -> m.Record:
    authorize(access, spec, "manage")
    if spec.name in READ_ONLY:
        raise ConflictError("this resource is maintained through Accounting setup")
    if spec.name == "account_posting_mapping":
        access.actor.require_scope(
            "accounting.mapping.publish", target=ScopePath(company_id=access.context.company_id)
        )
    row: Any = (
        None
        if object_id is None
        else await company_object(
            db, spec.model, object_id, company_id=access.context.company_id, lock=True
        )
    )
    incoming = body.model_dump(exclude_unset=True)
    if row is not None:
        if incoming.pop("expected_version", None) != row.row_version:
            raise ConflictError("master version changed; refresh before editing")
        if action == "create":
            raise ValidationFailedError("create cannot target an existing master")
    elif action != "create":
        raise ValidationFailedError("an existing master is required")
    before = (
        {}
        if row is None
        else {key: getattr(row, key) for key in spec.create.model_fields if hasattr(row, key)}
    )
    if row is not None and spec.name == "party_bank_account":
        before["account_number"] = (
            cipher(settings)
            .decrypt(row.account_number_ciphertext, associated_data=associated_data(access, row.id))
            .decode()
        )
    if action in {"activate", "deactivate"}:
        if spec.lifecycle != "status" or row is None:
            raise ConflictError("this resource uses effective dates instead of activation")
        if row.status == ("ACTIVE" if action == "activate" else "INACTIVE"):
            raise ConflictError("master already has the requested status")
        if row.status == "INACTIVE" and action == "activate":
            raise ConflictError("retired identities cannot be reactivated")
        if action == "deactivate":
            if getattr(row, "system_key", None):
                raise ConflictError("system masters cannot be retired")
            await guard_retirement(db, spec, row)
        merged = before
    else:
        merged = before | incoming
    try:
        parsed = spec.create.model_validate(merged)
    except ValidationError as exc:
        raise ValidationFailedError("master values are invalid") from exc
    values = parsed.model_dump()
    if spec.name == "party_drug_licence":
        if row is None:
            if values["closure_reason"] is not None:
                raise ValidationFailedError("new drug licence cannot carry a closure reason")
            values["reviewed_at"] = utcnow()
            values["reviewed_by"] = access.actor.user_id
        elif (
            row.valid_to is not None
            or values["valid_to"] is None
            or values["closure_reason"] is None
        ):
            raise ConflictError("drug licence may only be closed once")
    if spec.name == "account_group":
        values = await normalize_group(
            db, access, values, system_key=getattr(row, "system_key", None)
        )
    policy_before = (values_of(row, spec) | before) if row is not None else {}
    policy_after = policy_before | values
    if spec.lifecycle == "status":
        policy_after["status"] = (
            "ACTIVE"
            if action == "activate"
            else "INACTIVE"
            if action == "deactivate"
            else row.status
            if row is not None
            else "DRAFT"
        )
    changed = writable(access, spec, policy_before, policy_after)
    semantics = changed - {"status"}
    if row is not None:
        if changed & spec.immutable:
            raise ConflictError("master identity cannot be changed")
        await guard_registration_links(db, spec, row, changed)
        if spec.lifecycle == "dates":
            guard_effective_edit(
                row.valid_from, row.valid_to, changed, values.get("valid_to"), today=utcnow().date()
            )
            if changed & {"valid_from", "valid_to"}:
                await guard_child_intervals(db, spec, row, values)
        if spec.name == "account" and row.used_at is not None and semantics - PRESENTATION:
            raise ConflictError("financially used account semantics are immutable")
        if (
            spec.name == "account"
            and row.status == "ACTIVE"
            and changed
            & {
                "group_id",
                "kind",
                "currency_mode",
                "currency",
                "party_role",
                "posting_policy",
                "inventory_affected",
                "rounding_method",
                "rounding_limit",
            }
        ):
            raise ConflictError("active account semantics are immutable")
        if getattr(row, "system_key", None) and semantics - PRESENTATION:
            raise ConflictError("system master classification is protected")
        if spec.name == "account_group":
            await guard_group_change(db, row, values, changed)
    await validate(
        db,
        access,
        spec,
        values,
        object_id=object_id,
        activating=policy_after.get("status") == "ACTIVE",
    )
    if row is None:
        row = spec.model(
            id=uuid7(),
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            row_version=1,
            created_by=access.actor.user_id,
        )
        if spec.lifecycle == "status":
            row.status = "DRAFT"
        db.add(row)
    else:
        row.row_version += 1
    if spec.name == "party_bank_account":
        number = values.pop("account_number")
        if "account_number" in changed:
            row.account_number_ciphertext = cipher(settings).encrypt(
                number.encode(),
                nonce=secrets.token_bytes(12),
                associated_data=associated_data(access, row.id),
            )
            row.account_number_last4 = number[-4:]
    for key, value in values.items():
        setattr(row, key, value)
    if action in {"activate", "deactivate"}:
        row.status = policy_after["status"]
    row.updated_by = access.actor.user_id
    await db.flush()
    if spec.name == "account_group":
        await rebuild_hierarchy(db, row.company_id)
    audit(db, access, spec, row, action, changed)
    if spec.name in {"party_contact", "party_contact_use"}:
        from accounting.tasks.party_contact_notifications import emit_party_snapshot

        await emit_party_snapshot(db, access, row.party_id)
    return cast(m.Record, row)


async def create_active(
    db: AsyncSession, access: Access, spec: Resource, body: BaseModel, settings: Settings
) -> m.Record:
    """Create a status-lifecycle master and activate it inside the caller's transaction.

    The two steps are the create and activate mutations themselves, so validation, refusals and
    audit events are exactly theirs; the caller's transaction is what makes them one effect.
    """
    row = await mutate_master(db, access, spec, "create", body, settings)
    return await mutate_master(
        db,
        access,
        spec,
        "activate",
        ExpectedVersion(expected_version=row.row_version),
        settings,
        row.id,
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    spec: Resource,
    action: str,
    body: BaseModel,
    key: str,
    settings: Settings,
    object_id: uuid.UUID | None = None,
    posting_client: PostingClient | None = None,
) -> CommandResult[BaseModel]:
    from accounting.schemas.master_opening import AccountCreation
    from accounting.schemas.masters import AccountCreate

    opening = body.opening if isinstance(body, AccountCreation) else None
    profiles = {
        name: value
        for name in ("bank_profile", "tax_profile")
        if isinstance(body, AccountCreation) and (value := getattr(body, name)) is not None
    }
    retained: dict[str, Any] = {}
    if opening is not None and posting_client is None:
        from accounting.tasks.journal_posting import PostingDependencyError

        raise PostingDependencyError("Opening posting is unavailable; retry the same creation.")
    native_body = (
        AccountCreate.model_validate(
            body.model_dump(exclude={"opening", "bank_profile", "tax_profile"}, exclude_unset=True)
        )
        if isinstance(body, AccountCreation)
        else body
    )

    async def authorize_command(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        authorize(access, spec, "manage")
        authorize(access, spec, "read")
        await require_metadata(db, access)
        for name in profiles:
            authorize(access, BY_NAME["account_" + name], "manage")
            authorize(access, BY_NAME["account_" + name], "read")
            writable(access, BY_NAME["account_" + name], {}, profiles[name].model_dump())
        if opening is not None:
            from accounting.tasks.master_opening import capture_access, replay_access

            capture_access(access)
            if receipt and receipt.get("opening_id"):
                await replay_access(db, access, uuid.UUID(receipt["opening_id"]))
        if object_id is not None:
            await company_object(db, spec.model, object_id, company_id=access.context.company_id)
        if receipt is not None:
            row = await company_object(
                db, spec.model, uuid.UUID(receipt["id"]), company_id=access.context.company_id
            )
            # Replays must not disclose fields no longer readable.
            protected(row, spec, access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        if profiles:
            row = await mutate_master(db, access, spec, "create", native_body, settings)
            for name, profile in profiles.items():
                profile_spec = BY_NAME["account_" + name]
                try:
                    await mutate_master(
                        db,
                        access,
                        profile_spec,
                        "create",
                        profile_spec.create.model_validate(
                            profile.model_dump() | {"account_id": row.id}
                        ),
                        settings,
                    )
                except ValidationFailedError as exc:
                    fields = exc.extra.get("fields") or {"section": exc.message}
                    raise ValidationFailedError(
                        exc.message,
                        fields={
                            "opening.profile." + field: message for field, message in fields.items()
                        },
                    ) from exc
            if opening is not None or action == "create_active":
                row = await mutate_master(
                    db,
                    access,
                    spec,
                    "activate",
                    ExpectedVersion(expected_version=row.row_version),
                    settings,
                    row.id,
                )
        elif action == "create_active" or (action == "create" and opening is not None):
            row = await create_active(db, access, spec, native_body, settings)
        else:
            row = await mutate_master(db, access, spec, action, native_body, settings, object_id)
        opening_id = None
        if opening is not None:
            from accounting.tasks.master_opening import stage

            opening_id = await stage(db, access, row.id, opening)
        return CommandReceipt(
            201 if action in {"create", "create_active"} else 200,
            {"id": str(row.id), **({"opening_id": str(opening_id)} if opening_id else {})},
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        retained.update(receipt)
        row = await company_object(
            db, spec.model, uuid.UUID(receipt["id"]), company_id=access.context.company_id
        )
        return protected(row, spec, access)

    try:
        result = await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                actor_id=access.actor.user_id,
                operation=f"accounting.{spec.name}.{action}",
                key=key,
                request={
                    "object_id": str(object_id) if object_id else None,
                    "body": body.model_dump(mode="json", exclude_unset=True),
                },
            ),
            authorize=authorize_command,
            mutate=mutate,
            render=render,
        )
        if retained.get("opening_id"):
            from accounting.tasks.master_opening_posting import complete

            await complete(factory, access, uuid.UUID(retained["opening_id"]), posting_client)
            with tenant_scope(access.actor.tenant_id):
                async with factory() as db:
                    result = CommandResult(
                        result.status, await render(db, retained), result.replayed
                    )
        return result
    except IntegrityError as exc:
        raise ConflictError("master identity or references conflict with existing data") from exc


async def initialize(
    factory: async_sessionmaker[AsyncSession], access: Access, key: str
) -> CommandResult[BaseModel]:
    spec = BY_NAME["accounting_setup"]

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        target = ScopePath(company_id=access.context.company_id)
        if all(
            access.actor.allows_scope(key, target=target)
            for key in ("accounting.setup.manage", "accounting.setup.read")
        ):
            authorize(access, spec, "manage")
            authorize(access, spec, "read")
        else:
            # Bounded bootstrap provisions the fixed starter chart, without granting
            # arbitrary template installation, master CRUD or posting authority.
            from accounting.tasks.financial_commands import financial_context, require_any

            financial_context(access)
            access.actor.require_scope("accounting.finance.read", target=target)
            require_any(access, ("accounting.finance.initialize", "accounting.finance.manage"))
        await require_metadata(db, access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        candidate = uuid7()
        await insert_candidate(
            db,
            m.AccountingSetup,
            {
                "id": candidate,
                "tenant_id": access.actor.tenant_id,
                "company_id": access.context.company_id,
                "base_currency": access.context.base_currency,
                "generation": 1,
                "metadata_version": METADATA_VERSION,
                "row_version": 1,
            },
        )
        row = await db.scalar(
            select(m.AccountingSetup)
            .where(m.AccountingSetup.company_id == access.context.company_id)
            .with_for_update()
        )
        if row is None:
            raise ConflictError("company setup is unavailable")
        if row.metadata_version != METADATA_VERSION:
            raise ConflictError("company master metadata requires backfill before use")
        if row.id == candidate:
            changed = writable(access, spec, {}, values_of(row, spec))
            audit(db, access, spec, row, "create", changed)
            for code, label in [
                ("ASSET", "Assets"),
                ("LIABILITY", "Liabilities"),
                ("EQUITY", "Equity"),
                ("INCOME", "Income"),
                ("EXPENSE", "Expenses"),
            ]:
                head = m.AccountHead(
                    id=uuid7(),
                    tenant_id=access.actor.tenant_id,
                    company_id=row.company_id,
                    code=code,
                    name=label,
                    nature=code,
                    row_version=1,
                    created_by=access.actor.user_id,
                    updated_by=access.actor.user_id,
                )
                db.add(head)
                await db.flush()
                head_spec = BY_NAME["account_head"]
                head_changed = writable(access, head_spec, {}, values_of(head, head_spec))
                audit(db, access, head_spec, head, "create", head_changed)
        # Deferred import: the template writer shares this module's transaction helpers.
        from accounting.tasks.templates import seed_initial_chart

        await seed_initial_chart(db, access)
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, m.AccountingSetup, uuid.UUID(receipt["id"]), company_id=access.context.company_id
        )
        return protected(row, spec, access)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            tenant_id=access.actor.tenant_id,
            company_id=access.context.company_id,
            actor_id=access.actor.user_id,
            operation="accounting.setup.initialize",
            key=key,
            request={},
        ),
        authorize=check,
        mutate=mutate,
        render=render,
        timeout_seconds=30,
    )
