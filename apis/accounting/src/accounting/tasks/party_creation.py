"""One transaction for a ready party, its role and its ledger account, and the role commands.

A party is never created without a role, and a role is never active without its account
(docs/party-ledger-mandatory-plan.md). Adding a role later and repairing older data go through
the same ledger planning as creation.
"""

import uuid
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from identity_posting import PostingClient
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.models.masters import Account, Party, PartyRole
from accounting.resources import BY_NAME
from accounting.schemas.party_creation import (
    PartyCreation,
    PartyLedgerRepair,
    PartyLedgerRepairItem,
    PartyLedgerRepairResult,
    PartyRoleActivation,
)
from accounting.tasks.access import authorize
from accounting.tasks.commands import (
    create_active,
    mutate_master,
    protected,
    require_metadata,
    setup_lock,
)
from accounting.tasks.master_codes import allocate_code
from accounting.tasks.party_ledger import (
    account_values,
    activate_role_with_ledger,
    create_party_ledger,
    party_account,
    plan_ledger,
)


async def create_party_with_details(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: PartyCreation,
    key: str,
    settings: Settings,
    posting_client: PostingClient | None = None,
) -> CommandResult[BaseModel]:
    retained: dict[str, Any] = {}
    if body.opening is not None and posting_client is None:
        from accounting.tasks.journal_posting import PostingDependencyError

        raise PostingDependencyError("Opening posting is unavailable; retry the same creation.")
    resources = ["party", "party_role", "account"]
    if body.address:
        resources.extend(("party_address", "party_address_use"))
    if body.contact:
        resources.extend(("party_contact", "party_contact_use"))
    if body.tax_registration:
        resources.append("party_tax_registration")

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await require_metadata(db, access)
        for name in resources:
            authorize(access, BY_NAME[name], "manage")
            authorize(access, BY_NAME[name], "read")
        if body.opening is not None:
            from accounting.tasks.master_opening import capture_access, replay_access

            capture_access(access)
            if receipt and receipt.get("opening_id"):
                await replay_access(db, access, uuid.UUID(receipt["opening_id"]))
        if receipt:
            for name, ids in receipt["records"].items():
                for object_id in ids:
                    row = await company_object(
                        db,
                        BY_NAME[name].model,
                        uuid.UUID(object_id),
                        company_id=access.context.company_id,
                    )
                    protected(row, BY_NAME[name], access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        records: dict[str, list[str]] = {}

        async def create(name: str, values: dict[str, Any]) -> uuid.UUID:
            spec = BY_NAME[name]
            try:
                incoming = spec.create.model_validate(values)
                if spec.lifecycle == "status":
                    row = await create_active(db, access, spec, incoming, settings)
                else:
                    row = await mutate_master(db, access, spec, "create", incoming, settings)
            except (ValidationFailedError, ConflictError) as exc:
                if isinstance(exc, ConflictError) and not exc.extra.get("fields"):
                    raise
                group = {
                    "party": "party",
                    "party_role": "party",
                    "account": "ledger",
                    "party_address": "address",
                    "party_address_use": "address",
                    "party_contact": "contact",
                    "party_contact_use": "contact",
                    "party_tax_registration": "tax_registration",
                }[name]
                fields = exc.extra.get("fields") or {"section": exc.message}
                raise type(exc)(
                    exc.message,
                    fields={f"{group}.{field}": message for field, message in fields.items()},
                ) from exc
            records.setdefault(name, []).append(str(row.id))
            # Use the same current protected projection for creation and replay.
            protected(row, spec, access)
            return row.id

        party_code = body.code or await allocate_code(db, access.context.company_id, "party")
        # Refuse a ledger that cannot work before creating anything, with every `ledger.*` reason.
        plan = await plan_ledger(
            db,
            access,
            role=body.role,
            party_code=party_code,
            party_name=body.name,
            ledger=body.ledger,
        )
        party_id = await create(
            "party",
            body.model_dump(
                exclude={"role", "address", "contact", "tax_registration", "ledger", "opening"}
            )
            | {"code": party_code},
        )
        # The role is active before its account, which the account rules require.
        await create("party_role", {"party_id": party_id, "role": body.role})
        account_id = await create(
            "account", account_values(plan, party_id=party_id, role=body.role)
        )
        opening_id = None
        if body.opening is not None:
            from accounting.tasks.master_opening import stage

            opening_id = await stage(db, access, account_id, body.opening)
        if body.address:
            address_id = await create(
                "party_address",
                {
                    **body.address.model_dump(),
                    "party_id": party_id,
                },
            )
            for purpose in ("BILLING", "SHIPPING"):
                await create(
                    "party_address_use",
                    {
                        "party_id": party_id,
                        "address_id": address_id,
                        "purpose": purpose,
                        "is_default": True,
                    },
                )
        if body.contact:
            contact_id = await create(
                "party_contact",
                {
                    **body.contact.model_dump(),
                    "party_id": party_id,
                },
            )
            await create(
                "party_contact_use",
                {
                    "party_id": party_id,
                    "contact_id": contact_id,
                    "purpose": "GENERAL",
                    "is_default": True,
                },
            )
        if body.tax_registration:
            await create(
                "party_tax_registration",
                {
                    **body.tax_registration.model_dump(),
                    "party_id": party_id,
                },
            )
        return CommandReceipt(
            201,
            {
                "id": str(party_id),
                "records": records,
                **({"opening_id": str(opening_id)} if opening_id else {}),
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        retained.update(receipt)
        row = await company_object(
            db,
            BY_NAME["party"].model,
            uuid.UUID(receipt["id"]),
            company_id=access.context.company_id,
        )
        return protected(row, BY_NAME["party"], access)

    try:
        result = await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                actor_id=access.actor.user_id,
                operation="accounting.party.create_with_details",
                key=key,
                request=body.model_dump(mode="json"),
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
        if retained.get("opening_id"):
            from accounting.tasks.master_opening_posting import complete

            await complete(factory, access, uuid.UUID(retained["opening_id"]), posting_client)
        return result
    except IntegrityError as exc:
        raise ConflictError("party identity or details conflict with existing data") from exc


async def activate_party_role(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    role_id: uuid.UUID,
    body: PartyRoleActivation,
    key: str,
    settings: Settings,
) -> CommandResult[BaseModel]:
    """Activate a party role together with its account, so no role is ever active without one."""
    spec = BY_NAME["party_role"]

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        for name in ("party_role", "account"):
            authorize(access, BY_NAME[name], "manage")
            authorize(access, BY_NAME[name], "read")
        await require_metadata(db, access)
        await company_object(db, spec.model, role_id, company_id=access.context.company_id)
        if receipt is not None:
            row = await company_object(
                db, spec.model, uuid.UUID(receipt["id"]), company_id=access.context.company_id
            )
            protected(row, spec, access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        row = await activate_role_with_ledger(
            db,
            access,
            settings,
            role_id=role_id,
            expected_version=body.expected_version,
            ledger=body.ledger,
        )
        return CommandReceipt(200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, spec.model, uuid.UUID(receipt["id"]), company_id=access.context.company_id
        )
        return protected(row, spec, access)

    try:
        return await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                actor_id=access.actor.user_id,
                operation="accounting.party_role.activate",
                key=key,
                request={"object_id": str(role_id), "body": body.model_dump(mode="json")},
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    except IntegrityError as exc:
        raise ConflictError("party role or ledger conflicts with existing data") from exc


def _reason(exc: ConflictError | ValidationFailedError) -> str:
    fields = exc.extra.get("fields")
    return "; ".join(str(text) for text in fields.values()) if fields else exc.message


async def repair_party_ledgers(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: PartyLedgerRepair,
    key: str,
    settings: Settings,
) -> CommandResult[BaseModel]:
    """Give every active party role without an account its account, one bounded batch at a time.

    Idempotent: a role that already has one is never touched, and a role that cannot be repaired
    here (an inactive party, a code another account already uses, no standard group) is reported
    rather than failing the batch. A party holding several accounts for one role is reported and
    left alone: choosing which to keep is a decision for the company, not for this command.
    """

    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        for name in ("party", "party_role", "account"):
            authorize(access, BY_NAME[name], "read")
        authorize(access, BY_NAME["account"], "manage")
        await require_metadata(db, access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await setup_lock(db, access)
        company = access.context.company_id
        account_role = case((PartyRole.role == "BROKER", "OTHER"), else_=PartyRole.role)
        has_account = (
            select(Account.id)
            .where(
                Account.company_id == PartyRole.company_id,
                Account.party_id == PartyRole.party_id,
                Account.party_role == account_role,
                Account.status != "INACTIVE",
            )
            .correlate(PartyRole)
            .exists()
        )
        batch = (
            select(PartyRole.id, PartyRole.party_id, PartyRole.role)
            .where(
                PartyRole.company_id == company,
                PartyRole.status == "ACTIVE",
                ~has_account,
                *([PartyRole.id > body.after] if body.after else []),
            )
            .order_by(PartyRole.id)
            .limit(body.limit + 1)
        )
        rows = list((await db.execute(batch)).all())
        more = len(rows) > body.limit
        created: list[PartyLedgerRepairItem] = []
        attention: list[PartyLedgerRepairItem] = []
        for _, party_id, role in rows[: body.limit]:
            # A broker and an "other" role of one party share an account: the first repair gives it.
            if await party_account(db, company, party_id, role) is not None:
                continue
            party = await db.scalar(
                select(Party).where(Party.company_id == company, Party.id == party_id)
            )
            if party is None or party.status != "ACTIVE":
                attention.append(
                    PartyLedgerRepairItem(
                        party_id=party_id, role=role, reason="the party is not active"
                    )
                )
                continue
            try:
                async with db.begin_nested():
                    account = await create_party_ledger(
                        db,
                        access,
                        settings,
                        party_id=party_id,
                        role=role,
                        party_code=party.code,
                        party_name=party.name,
                    )
            except (ConflictError, ValidationFailedError) as exc:
                attention.append(
                    PartyLedgerRepairItem(party_id=party_id, role=role, reason=_reason(exc))
                )
            else:
                created.append(
                    PartyLedgerRepairItem(party_id=party_id, role=role, account_id=account.id)
                )
        if not body.after:
            # Duplicates belong to the data, not to a page: reported once, on the first call.
            crowded = (
                select(Account.party_id, Account.party_role)
                .where(
                    Account.company_id == company,
                    Account.kind == "PARTY",
                    Account.status != "INACTIVE",
                )
                .group_by(Account.party_id, Account.party_role)
                .having(func.count(Account.id) > 1)
                .order_by(Account.party_id)
                .limit(200)
            )
            for party_id, role in (await db.execute(crowded)).all():
                ids = list(
                    await db.scalars(
                        select(Account.id)
                        .where(
                            Account.company_id == company,
                            Account.party_id == party_id,
                            Account.party_role == role,
                            Account.status != "INACTIVE",
                        )
                        .order_by(Account.id)
                    )
                )
                attention.append(
                    PartyLedgerRepairItem(
                        party_id=party_id,
                        role=role,
                        account_ids=ids,
                        reason="more than one account for this role: keep one, retire the rest",
                    )
                )
        result = PartyLedgerRepairResult(
            created=created,
            attention=attention,
            next_after=rows[body.limit - 1][0] if more else None,
        )
        return CommandReceipt(200, result.model_dump(mode="json"))

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return PartyLedgerRepairResult.model_validate(receipt)

    try:
        return await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                actor_id=access.actor.user_id,
                operation="accounting.party.ledger_repair",
                key=key,
                request=body.model_dump(mode="json"),
            ),
            authorize=check,
            mutate=mutate,
            render=render,
        )
    except IntegrityError as exc:
        raise ConflictError("party ledger repair conflicts with existing data") from exc
