"""A party's ledger account: the standard group for its role, and its creation with the party.

Every party role has exactly one account (docs/party-ledger-mandatory-plan.md). The party
creation command, the party import, role activation and the repair all go through this module,
so they resolve the same group, create the same kind of account and refuse the same things.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.domain.rules import allowed_head
from accounting.models.masters import Account, AccountGroup, AccountHead, Party, PartyRole
from accounting.resources import BY_NAME
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.party_creation import PartyLedgerInput, no_choices
from accounting.tasks.access import authorize
from accounting.tasks.commands import create_active, mutate_master

# The account table has no BROKER role, so brokers and "other" parties share OTHER.
ACCOUNT_ROLE = {"CUSTOMER": "CUSTOMER", "SUPPLIER": "SUPPLIER", "BROKER": "OTHER", "OTHER": "OTHER"}
GROUP_FOR_ROLE = {
    "CUSTOMER": "group.DEBTORS",
    "SUPPLIER": "group.CREDITORS",
    "BROKER": "group.CREDITORS",
    "OTHER": "group.CREDITORS",
}


ROLE_SUFFIX = {"CUSTOMER": "CUST", "SUPPLIER": "SUPP", "BROKER": "OTHR", "OTHER": "OTHR"}
ROLE_LABEL = {"CUSTOMER": "Customer", "SUPPLIER": "Supplier", "BROKER": "Broker", "OTHER": "Other"}


@dataclass(frozen=True, slots=True)
class LedgerPlan:
    code: str
    name: str
    group_id: uuid.UUID
    currency_mode: str
    currency: str | None


def require_account_rights(access: Access) -> None:
    """Giving a role its account is account authority, whichever route got here first.

    Checked before anything is read, so a caller without it learns nothing about existing
    accounts or groups from the planning refusals.
    """
    for action in ("manage", "read"):
        authorize(access, BY_NAME["account"], action)


async def standard_group(db: AsyncSession, company_id: uuid.UUID, role: str) -> AccountGroup | None:
    """The company's active Sundry Debtors/Creditors group for the role; system keys are unique."""
    group: AccountGroup | None = await db.scalar(
        select(AccountGroup).where(
            AccountGroup.company_id == company_id,
            AccountGroup.system_key == GROUP_FOR_ROLE[role],
            AccountGroup.status == "ACTIVE",
        )
    )
    return group


async def party_account(
    db: AsyncSession, company_id: uuid.UUID, party_id: uuid.UUID, role: str
) -> Account | None:
    """The party's live (draft or active) account for the role's account role, if it has one."""
    account: Account | None = await db.scalar(
        select(Account)
        .where(
            Account.company_id == company_id,
            Account.party_id == party_id,
            Account.party_role == ACCOUNT_ROLE[role],
            Account.status != "INACTIVE",
        )
        .order_by(Account.status, Account.id)
        .limit(1)
    )
    return account


async def plan_ledger(
    db: AsyncSession,
    access: Access,
    *,
    role: str,
    party_code: str,
    party_name: str,
    ledger: PartyLedgerInput,
    party_id: uuid.UUID | None = None,
) -> LedgerPlan:
    """Resolve the ledger's defaults and refuse what cannot work, before anything is created.

    Every refusal names its `ledger.<field>`, and all of them are reported together. Pass
    `party_id` for a party that already exists: if it holds another account, a default code
    that is taken is made distinct by role instead of being refused.
    """
    company = access.context.company_id
    errors: dict[str, str] = {}
    if role not in ACCOUNT_ROLE:
        errors["ledger.role"] = "a party needs the customer, supplier, broker or other role"
    if ledger.currency_mode == "FIXED" and ledger.currency is None:
        errors["ledger.currency"] = "a fixed-currency ledger needs a currency"
    elif ledger.currency_mode != "FIXED" and ledger.currency is not None:
        errors["ledger.currency"] = "only a fixed-currency ledger takes a currency"
    group_id: uuid.UUID | None = None
    if role in ACCOUNT_ROLE:
        if ledger.group_id is None:
            group = await standard_group(db, company, role)
            if group is None:
                errors["ledger.group_id"] = (
                    "the standard debtors/creditors group is not available; choose a group"
                )
            else:
                group_id = group.id
        else:
            chosen = await db.scalar(
                select(AccountGroup).where(
                    AccountGroup.company_id == company, AccountGroup.id == ledger.group_id
                )
            )
            head = (
                None
                if chosen is None
                else await db.scalar(
                    select(AccountHead).where(
                        AccountHead.company_id == company, AccountHead.id == chosen.head_id
                    )
                )
            )
            if chosen is None or head is None:
                errors["ledger.group_id"] = "account group not found"
            elif chosen.status != "ACTIVE":
                errors["ledger.group_id"] = "account group is not active"
            elif not allowed_head("PARTY", ACCOUNT_ROLE[role], head.nature):
                errors["ledger.group_id"] = "account group is not under a head this ledger can use"
            else:
                group_id = chosen.id
    code = ledger.code or party_code
    name = ledger.name or party_name
    taken = await db.scalar(
        select(Account.id).where(Account.company_id == company, Account.code == code)
    )
    if (
        taken
        and ledger.code is None
        and party_id is not None
        and await db.scalar(
            select(Account.id)
            .where(
                Account.company_id == company,
                Account.party_id == party_id,
                Account.status != "INACTIVE",
            )
            .limit(1)
        )
    ):
        # A party taking a further role already holds an account under its own code, so the
        # newcomer is told apart by role rather than refused: "ABC" and "ABC-SUPP".
        suffix = "-" + ROLE_SUFFIX[role] if role in ROLE_SUFFIX else "-2"
        code = party_code[: 40 - len(suffix)] + suffix
        if ledger.name is None:
            name = f"{party_name} ({ROLE_LABEL.get(role, role.title())})"[:160]
        taken = await db.scalar(
            select(Account.id).where(Account.company_id == company, Account.code == code)
        )
    if taken:
        errors["ledger.code"] = "a ledger account already uses this code"
    if errors or group_id is None:
        raise ValidationFailedError("ledger is not valid", fields=errors)
    return LedgerPlan(code, name, group_id, ledger.currency_mode, ledger.currency)


def account_values(plan: LedgerPlan, *, party_id: uuid.UUID, role: str) -> dict[str, Any]:
    """The party's ledger as an `account` create: a PARTY account of this party in this role."""
    return {
        "code": plan.code,
        "name": plan.name,
        "group_id": plan.group_id,
        "kind": "PARTY",
        "party_id": party_id,
        "party_role": ACCOUNT_ROLE[role],
        "currency_mode": plan.currency_mode,
        "currency": plan.currency,
    }


async def create_party_ledger(
    db: AsyncSession,
    access: Access,
    settings: Settings,
    *,
    party_id: uuid.UUID,
    role: str,
    party_code: str,
    party_name: str,
    ledger: PartyLedgerInput | None = None,
) -> Account:
    """Create and activate the party's account for the role inside the caller's transaction.

    The party's role must already be active (the account rules require it). A party that
    already has a live account for the role gets no second one: that is refused by the
    account rules, so a caller wanting "ensure" checks `party_account` first.
    """
    require_account_rights(access)
    plan = await plan_ledger(
        db,
        access,
        role=role,
        party_code=party_code,
        party_name=party_name,
        ledger=ledger or no_choices(),
        party_id=party_id,
    )
    account = await create_active(
        db,
        access,
        BY_NAME["account"],
        BY_NAME["account"].create.model_validate(
            account_values(plan, party_id=party_id, role=role)
        ),
        settings,
    )
    assert isinstance(account, Account)
    return account


async def activate_role_with_ledger(
    db: AsyncSession,
    access: Access,
    settings: Settings,
    *,
    role_id: uuid.UUID,
    expected_version: int,
    ledger: PartyLedgerInput | None = None,
) -> PartyRole:
    """Activate a party role and give it its account in the same transaction.

    A role is never active without its account: an account the party already holds for the
    role's account role is reused (a broker and an "other" role share one), a draft one is
    activated, and otherwise the planned one is created. Any refusal rolls the activation back.
    """
    require_account_rights(access)
    company = access.context.company_id
    role: PartyRole = await company_object(db, PartyRole, role_id, company_id=company)
    party: Party = await company_object(db, Party, role.party_id, company_id=company)
    existing = await party_account(db, company, role.party_id, role.role)
    plan = (
        None
        if existing is not None
        else await plan_ledger(
            db,
            access,
            role=role.role,
            party_code=party.code,
            party_name=party.name,
            ledger=ledger or no_choices(),
            party_id=role.party_id,
        )
    )
    activated = await mutate_master(
        db,
        access,
        BY_NAME["party_role"],
        "activate",
        ExpectedVersion(expected_version=expected_version),
        settings,
        role_id,
    )
    if plan is not None:
        await create_active(
            db,
            access,
            BY_NAME["account"],
            BY_NAME["account"].create.model_validate(
                account_values(plan, party_id=role.party_id, role=role.role)
            ),
            settings,
        )
    elif existing is not None and existing.status == "DRAFT":
        await mutate_master(
            db,
            access,
            BY_NAME["account"],
            "activate",
            ExpectedVersion(expected_version=existing.row_version),
            settings,
            existing.id,
        )
    assert isinstance(activated, PartyRole)
    return activated
