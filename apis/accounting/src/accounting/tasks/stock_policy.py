"""Explicit dated company accounts; no stock account is inferred from a label."""

import datetime as dt
import logging
import uuid
from typing import Any

from billing_platform.audit_evidence import scalar
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.outbox import audit_payload, emit
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from accounting.api.auth import Access
from accounting.models.ledger import Journal, JournalLine
from accounting.models.masters import Account, AccountGroup, AccountHead
from accounting.models.stock import StockAccountPolicy, StockExecutionPlan, StockPosting
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.schemas.stock import StockAccountPolicyCreate
from accounting.seeds.templates import STOCK
from accounting.stock_resources import STOCK_POLICY
from accounting.tasks.access import authorize, writable
from accounting.tasks.commands import protected, setup_lock
from accounting.tasks.voucher_money_effects import audit, values

ACCOUNT_NATURES = {
    "inventory_account_id": "ASSET",
    "receipt_clearing_account_id": "LIABILITY",
    "dispatch_clearing_account_id": "ASSET",
    "opening_offset_account_id": "EQUITY",
    "variance_account_id": "EXPENSE",
}
CONTROLS = {"expected_generation", "correct_unused_id"}
LOG = logging.getLogger(__name__)


async def validate_accounts(
    db: AsyncSession, current: Access, mapping: dict[str, uuid.UUID]
) -> None:
    if len(set(mapping.values())) != len(ACCOUNT_NATURES):
        raise ValidationFailedError(
            "inventory, clearing, opening and variance accounts must be distinct"
        )
    for field, nature in ACCOUNT_NATURES.items():
        account = await company_object(
            db, Account, mapping[field], company_id=current.context.company_id
        )
        group = await company_object(
            db, AccountGroup, account.group_id, company_id=current.context.company_id
        )
        head = await company_object(
            db, AccountHead, group.head_id, company_id=current.context.company_id
        )
        if (
            account.status != "ACTIVE"
            or group.status != "ACTIVE"
            or account.kind != "GENERAL"
            or head.nature != nature
            or (
                account.currency_mode == "FIXED"
                and account.currency != current.context.base_currency
            )
        ):
            raise ValidationFailedError(
                "stock mappings require active general accounts with the indicated account nature",
                fields={field: f"Select an active {nature.lower()} general account."},
            )


async def effective(db: AsyncSession, current: Access, day: dt.date) -> StockAccountPolicy:
    policies = list(
        await db.scalars(
            select(StockAccountPolicy)
            .where(
                StockAccountPolicy.company_id == current.context.company_id,
                StockAccountPolicy.valid_from <= day,
                (StockAccountPolicy.valid_to.is_(None)) | (StockAccountPolicy.valid_to >= day),
            )
            .limit(2)
            .with_for_update()
        )
    )
    if len(policies) != 1:
        raise ConflictError("configure the company's stock accounts for this posting date first")
    policy = policies[0]
    retained_account = await db.scalar(
        select(StockAccountPolicy.inventory_account_id)
        .join(StockPosting, StockPosting.account_policy_id == StockAccountPolicy.id)
        .where(StockPosting.company_id == current.context.company_id)
        .limit(1)
    )
    if retained_account is not None and retained_account != policy.inventory_account_id:
        raise ConflictError(
            "inventory account changes require a controlled stock value reclassification"
        )
    await validate_accounts(db, current, {key: getattr(policy, key) for key in ACCOUNT_NATURES})
    return policy


async def correctable_policy(db: AsyncSession, company: uuid.UUID) -> uuid.UUID | None:
    latest = await db.scalar(
        select(StockAccountPolicy)
        .where(StockAccountPolicy.company_id == company)
        .order_by(StockAccountPolicy.valid_from.desc())
        .limit(1)
    )
    if latest is None:
        return None
    used = await db.scalar(
        select(StockPosting.id)
        .where(StockPosting.company_id == company, StockPosting.account_policy_id == latest.id)
        .limit(1)
    )
    pending = await db.scalar(
        select(StockExecutionPlan.id)
        .join(VoucherMoneyIntent, VoucherMoneyIntent.id == StockExecutionPlan.intent_id)
        .where(
            StockExecutionPlan.company_id == company,
            VoucherMoneyIntent.company_id == company,
            VoucherMoneyIntent.status == "PREPARED",
        )
        .limit(1)
    )
    return latest.id if used is None and pending is None else None


#: The standard accounts' template codes, by the policy field each one fills.
STANDARD_ACCOUNTS = dict(zip(ACCOUNT_NATURES, (row[0] for row in STOCK), strict=True))


async def provision_standard(
    db: AsyncSession, current: Access, valid_from: dt.date
) -> StockAccountPolicy | None:
    """The standard stock accounts and their policy for a company with inventory (2026-11-03).

    Run by the books bootstrap inside its transaction. It creates the five accounts under their
    fixed system keys and maps them from the books begin date; it never adopts an account by
    its name and never changes a company that already has stock accounts. A template code
    already owned by another master leaves the books set up without them, for an
    administrator to map, rather than failing the company's setup.
    """
    from accounting.schemas.setup import TemplateSelection
    from accounting.tasks.templates import bootstrap_conflicts, install_content

    company = current.context.company_id
    if "inventory" not in current.context.features or await db.scalar(
        select(StockAccountPolicy.id).where(StockAccountPolicy.company_id == company).limit(1)
    ):
        return None
    selection = TemplateSelection(business_accounts=False)
    if await bootstrap_conflicts(db, current, selection, stock=True):
        LOG.info("Standard stock accounts were not set up; their template codes are taken")
        return None
    await install_content(db, current, selection, stock=True)
    # The last account is activated in memory; the checks below read the stored rows.
    await db.flush()
    mapping = {}
    for field, code in STANDARD_ACCOUNTS.items():
        account = await db.scalar(
            select(Account.id).where(
                Account.company_id == company, Account.system_key == "account." + code
            )
        )
        if account is None:
            raise ConflictError("standard stock account is unavailable")
        mapping[field] = account
    await validate_accounts(db, current, mapping)
    authored: dict[str, Any] = {
        "valid_from": valid_from,
        **mapping,
        "reason": "Standard stock accounts set up with the company's books",
    }
    writable(current, STOCK_POLICY, {}, authored)
    row = StockAccountPolicy(**values(current), **authored)
    db.add(row)
    await db.flush()
    audit(db, current, row.id, "stock_account_policy", "publish")
    return row


async def publish(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    body: StockAccountPolicyCreate,
    key: str,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        authorize(current, STOCK_POLICY, "read")
        authorize(current, STOCK_POLICY, "manage")
        writable(current, STOCK_POLICY, {}, body.model_dump(exclude=CONTROLS))
        if receipt and receipt.get("closed_id"):
            previous = await company_object(
                db,
                StockAccountPolicy,
                uuid.UUID(receipt["closed_id"]),
                company_id=current.context.company_id,
            )
            writable(current, STOCK_POLICY, {}, {"valid_to": previous.valid_to})
        if current.actor.impersonation_id:
            from billing_platform.errors import PermissionDeniedError

            raise PermissionDeniedError("support sessions are read only")

    async def mutate(db: AsyncSession) -> CommandReceipt:
        setup = await setup_lock(db, current)
        if setup.generation != body.expected_generation + 1:
            raise ConflictError(
                "company Accounting setup changed; reload before publishing stock accounts"
            )
        authored = body.model_dump(exclude=CONTROLS)
        writable(current, STOCK_POLICY, {}, authored)
        await validate_accounts(
            db, current, {field: getattr(body, field) for field in ACCOUNT_NATURES}
        )
        original = aliased(Journal)
        stock_journal = (
            select(StockPosting.id)
            .where(
                StockPosting.company_id == current.context.company_id,
                StockPosting.journal_id == Journal.id,
            )
            .exists()
        )
        opening_reversal = (
            select(original.id)
            .where(
                original.company_id == current.context.company_id,
                original.id == Journal.reversal_of_id,
                original.kind == "OPENING",
                Journal.kind == "REVERSAL",
            )
            .exists()
        )
        manual_history = await db.scalar(
            select(JournalLine.id)
            .join(Journal, JournalLine.journal_id == Journal.id)
            .where(
                JournalLine.company_id == current.context.company_id,
                Journal.company_id == current.context.company_id,
                JournalLine.account_id == body.inventory_account_id,
                Journal.status == "POSTED",
                Journal.kind != "OPENING",
                ~stock_journal,
                ~opening_reversal,
            )
            .limit(1)
        )
        if manual_history:
            raise ConflictError(
                "this inventory account has manual posted history; reconcile and reclassify "
                "that history before configuring native stock"
            )
        latest = await db.scalar(
            select(StockPosting)
            .where(
                StockPosting.company_id == current.context.company_id,
            )
            .order_by(StockPosting.posting_date.desc(), StockPosting.id.desc())
            .limit(1)
        )
        if latest and body.valid_from <= latest.posting_date:
            raise ConflictError(
                "new stock mappings cannot rewrite a date already used by posted stock"
            )
        if latest and latest.account_policy_id:
            retained = await company_object(
                db,
                StockAccountPolicy,
                latest.account_policy_id,
                company_id=current.context.company_id,
            )
            if retained.inventory_account_id != body.inventory_account_id:
                raise ConflictError(
                    "inventory account changes require a controlled stock value reclassification"
                )
        previous = await db.scalar(
            select(StockAccountPolicy)
            .where(
                StockAccountPolicy.company_id == current.context.company_id,
            )
            .order_by(StockAccountPolicy.valid_from.desc())
            .limit(1)
            .with_for_update()
        )
        if body.correct_unused_id is not None:
            if previous is None or previous.id != body.correct_unused_id:
                raise ConflictError("only the latest unused stock mapping can be corrected")
            used = await db.scalar(
                select(StockPosting.id)
                .where(
                    StockPosting.company_id == current.context.company_id,
                    StockPosting.account_policy_id == previous.id,
                )
                .limit(1)
            )
            pending = await db.scalar(
                select(StockExecutionPlan.id)
                .join(VoucherMoneyIntent, VoucherMoneyIntent.id == StockExecutionPlan.intent_id)
                .where(
                    StockExecutionPlan.company_id == current.context.company_id,
                    VoucherMoneyIntent.company_id == current.context.company_id,
                    VoucherMoneyIntent.status == "PREPARED",
                )
                .limit(1)
            )
            predecessor = await db.scalar(
                select(StockAccountPolicy.id)
                .where(
                    StockAccountPolicy.company_id == current.context.company_id,
                    StockAccountPolicy.id != previous.id,
                    StockAccountPolicy.valid_from >= body.valid_from,
                )
                .limit(1)
            )
            # A successor may be corrected without changing its predecessor's window.
            if (
                used
                or pending
                or predecessor
                or (
                    previous.valid_from != body.valid_from
                    and await db.scalar(
                        select(StockAccountPolicy.id)
                        .where(
                            StockAccountPolicy.company_id == current.context.company_id,
                            StockAccountPolicy.id != previous.id,
                        )
                        .limit(1)
                    )
                )
            ):
                raise ConflictError(
                    "used or prepared stock mappings and established date windows "
                    "cannot be rewritten"
                )
            before = {field: getattr(previous, field) for field in authored}
            writable(current, STOCK_POLICY, before, authored)
            for field, value in authored.items():
                setattr(previous, field, value)
            previous.row_version += 1
            previous.updated_by = current.actor.user_id
            event = "accounting.stock_account_policy.correct"
            emit(
                db,
                aggregate_type="accounting.stock_account_policy",
                aggregate_id=previous.id,
                tenant_id=current.actor.tenant_id,
                event_type=event,
                payload=audit_payload(
                    action=event,
                    category="money",
                    entity_type="accounting.stock_account_policy",
                    entity_id=previous.id,
                    actor_user_id=current.actor.user_id,
                    company_id=current.context.company_id,
                    changes={
                        field: {"from": scalar(value), "to": scalar(authored[field])}
                        for field, value in before.items()
                        if field != "reason" and value != authored[field]
                    },
                ),
            )
            return CommandReceipt(200, {"id": str(previous.id)})
        if previous:
            if previous.valid_from >= body.valid_from:
                raise ConflictError(
                    "publish a successor after the latest stock mapping's effective date"
                )
            if latest and previous.inventory_account_id != body.inventory_account_id:
                raise ConflictError(
                    "inventory account changes require a controlled stock value reclassification"
                )
            before = {
                field: getattr(previous, field)
                for field in STOCK_POLICY.detail.model_fields
                if hasattr(previous, field)
            }
            changed = {"valid_to": body.valid_from - dt.timedelta(days=1)}
            writable(current, STOCK_POLICY, before, before | changed)
            previous.valid_to = changed["valid_to"]
            previous.row_version += 1
            previous.updated_by = current.actor.user_id
            audit(db, current, previous.id, "stock_account_policy", "close")
        row = StockAccountPolicy(**values(current), **authored)
        db.add(row)
        await db.flush()
        audit(db, current, row.id, "stock_account_policy", "publish")
        return CommandReceipt(
            201, {"id": str(row.id), **({"closed_id": str(previous.id)} if previous else {})}
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        row = await company_object(
            db, StockAccountPolicy, uuid.UUID(receipt["id"]), company_id=current.context.company_id
        )
        return protected(row, STOCK_POLICY, current)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "accounting.stock_account_policy.publish",
            key,
            body.model_dump(mode="json"),
        ),
        authorize=check,
        mutate=mutate,
        render=render,
    )
