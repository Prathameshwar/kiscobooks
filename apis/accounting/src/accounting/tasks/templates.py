"""Previewable atomic chart installation with stable system keys and no overwrites."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.domain.master_metadata import template_group_defaults
from accounting.domain.rules import regime_permits
from accounting.models import masters as m
from accounting.resources import BY_NAME
from accounting.schemas.setup import (
    TemplateChange,
    TemplatePreview,
    TemplateResult,
    TemplateSelection,
)
from accounting.seeds.default_accounts import DefaultAccounts
from accounting.seeds.templates import BUSINESS, CORE, GROUPS, HIGH_PRIORITY, STOCK, VERSION
from accounting.tasks.access import authorize, readable, writable
from accounting.tasks.commands import (
    audit,
    rebuild_hierarchy,
    require_metadata,
    setup_lock,
    update_setup,
    values_of,
)
from accounting.tasks.group_metadata import normalize_group
from accounting.tasks.validation import registration_window, validate

LOG = logging.getLogger(__name__)


#: Each template group keeps its place in the full chart, whichever part of it is installed.
GROUP_ORDER = {row[0]: ordinal for ordinal, row in enumerate(GROUPS, 1)}
#: The cash account and the groups it sits in: Cash-in-hand, under Current Assets.
CASH_GROUPS = ("CURRENT_ASSETS", "CASH")


def content(
    selection: TemplateSelection,
    *,
    stock: bool = False,
    cash: bool = False,
    defaults: DefaultAccounts | None = None,
) -> tuple[str, list[tuple[str, str, str, str | None]], list[tuple[str, str, str, str]], str]:
    groups = list(GROUPS)
    accounts = list(CORE) + list(BUSINESS if selection.business_accounts else ())
    key = "business" if selection.business_accounts else "core"
    if cash:
        # Only initialization installs this, for a chart that has no cash account at all.
        groups = [row for row in GROUPS if row[0] in CASH_GROUPS]
        accounts = [row for row in CORE if row[0] == "CASH_MAIN"]
        key = "cash"
    elif stock:
        # Only the books bootstrap installs these; the selection API is unchanged.
        accounts += list(STOCK)
        key += ".stock"
    if selection.gst_registration_id:
        # All 128 bits, encoded in 26 characters: even OUTPUT_UTGST fits the 40-char code.
        suffix = base64.b32encode(selection.gst_registration_id.bytes).decode().rstrip("=")
        key += "." + selection.gst_registration_id.hex + "." + str(selection.local_component)
        groups.append(("TAX_RECOVERABLE", "Tax Recoverables", "ASSET", "CURRENT_ASSETS"))
        for direction, group in [("INPUT", "TAX_RECOVERABLE"), ("OUTPUT", "TAX_PAYABLE")]:
            for component in ("CGST", selection.local_component, "IGST"):
                accounts.append(
                    (
                        f"{direction}_{component}_{suffix}",
                        f"{direction.title()} {component}",
                        group,
                        "TAX",
                    )
                )
    if defaults is not None:
        key, groups, accounts = defaults.key, defaults.groups(), defaults.accounts
    digest = hashlib.sha256(
        canonical_json(
            {
                "groups": [list(row) for row in groups],
                "accounts": [list(row) for row in accounts],
                "version": VERSION,
                **(
                    {
                        "profiles": {
                            code: {
                                name: str(value) if value is not None else None
                                for name, value in profile.items()
                            }
                            for code, profile in defaults.profiles.items()
                        }
                    }
                    if defaults is not None
                    else {}
                ),
                "group_metadata": [
                    template_group_defaults(row[0], GROUP_ORDER.get(row[0], i))
                    for i, row in enumerate(groups, 1)
                ],
            }
        )
    ).hexdigest()
    return key, groups, accounts, digest


def authorize_selection(access: Access, selection: TemplateSelection, *, write: bool) -> None:
    action = "manage" if write else "read"
    for name in ("accounting_setup", "account_group", "account"):
        authorize(access, BY_NAME[name], action)
    if selection.gst_registration_id:
        authorize(access, BY_NAME["account_tax_profile"], action)
        registration = next(
            (
                row
                for row in access.context.registrations
                if row["id"] == str(selection.gst_registration_id)
            ),
            None,
        )
        if registration is None or registration["tax_system"] != "gst_in":
            raise ValidationFailedError(
                "GST template requires an available regular GST registration"
            )
        # The template creates input-recovery and output-payable profiles on this one row.
        # Its regime holds for its whole window (Identity closes a row rather than changing
        # its regime), so the row must recover input and charge output, and must not already
        # have ended: a closed registration's window can no longer receive new accounts.
        _, end = registration_window(registration)
        regime = str(registration.get("regime"))
        if (
            not regime_permits("RECOVER", "gst_in", regime)
            or not regime_permits("CHARGE", "gst_in", regime)
            or (end is not None and end < utcnow().date())
        ):
            raise ValidationFailedError(
                "GST template requires an available regular GST registration"
            )
    if not write:
        # Preview/replay aggregate classifications across rows. Apply conditional denies
        # conservatively, as list/export do, before returning changes or conflicts.
        required = {
            "account_head": {"nature"},
            "account_group": {
                "code",
                "system_key",
                "head_id",
                "parent_id",
                "status",
                "affects_gross_profit",
                "is_primary",
            },
            "account": {"code", "system_key", "group_id", "kind", "status", "used_at"},
            "account_template_installation": {"template_key", "template_version", "content_hash"},
        }
        if selection.gst_registration_id:
            required["account_tax_profile"] = {
                "account_id",
                "company_registration_id",
                "scheme",
                "component",
                "purpose",
                "duty_type",
            }
        for name, fields in required.items():
            spec = BY_NAME[name]
            authorize(access, spec, "read")
            if not fields <= readable(access, spec):
                raise PermissionDeniedError("template classification fields are not readable")


async def preview(
    db: AsyncSession, access: Access, selection: TemplateSelection
) -> TemplatePreview:
    authorize_selection(access, selection, write=False)
    key, groups, accounts, digest = content(selection)
    existing = await db.scalar(
        select(m.AccountTemplateInstallation).where(
            m.AccountTemplateInstallation.company_id == access.context.company_id,
            m.AccountTemplateInstallation.template_key == key,
            m.AccountTemplateInstallation.template_version == VERSION,
        )
    )
    changes, conflicts = await plan(db, access, selection, groups, accounts, check_read=True)
    return TemplatePreview(
        template_key=key,
        version=VERSION,
        content_hash=digest,
        groups=[row[1] for row in groups],
        accounts=[row[1] for row in accounts],
        installed=existing is not None,
        changes=changes,
        conflicts=conflicts,
    )


async def bootstrap_conflicts(
    db: AsyncSession,
    access: Access,
    selection: TemplateSelection,
    *,
    stock: bool = False,
    cash: bool = False,
    defaults: DefaultAccounts | None = None,
) -> list[str]:
    """Why a fixed bootstrap install would be refused, found before anything is written."""
    _, groups, accounts, _ = content(selection, stock=stock, cash=cash, defaults=defaults)
    return (
        await plan(db, access, selection, groups, accounts, check_read=False, defaults=defaults)
    )[1]


async def plan(
    db: AsyncSession,
    access: Access,
    selection: TemplateSelection,
    groups: list[tuple[str, str, str, str | None]],
    accounts: list[tuple[str, str, str, str]],
    *,
    check_read: bool,
    defaults: DefaultAccounts | None = None,
) -> tuple[list[TemplateChange], list[str]]:
    """The changes a template install would make and the conflicts that would refuse it."""
    changes: list[TemplateChange] = []
    conflicts: list[str] = []
    stored = {
        row.system_key: row
        for row in await db.scalars(
            select(m.AccountGroup).where(
                m.AccountGroup.company_id == access.context.company_id,
                m.AccountGroup.system_key.is_not(None),
            )
        )
    }
    for code, _, nature, parent in groups:
        row = stored.get("group." + code)
        if row is None:
            collision = await db.scalar(
                select(m.AccountGroup.id).where(
                    m.AccountGroup.company_id == access.context.company_id,
                    m.AccountGroup.code == code,
                )
            )
            if collision is not None:
                conflicts.append(f"group {code}: code is already owned by another master")
            else:
                changes.append(TemplateChange(resource="account_group", code=code, action="create"))
            continue
        if check_read:
            readable(access, BY_NAME["account_group"], values_of(row, BY_NAME["account_group"]))
        try:
            updates = await group_upgrade(
                db, access, row, nature, stored.get("group." + parent) if parent else None
            )
        except ConflictError:
            conflicts.append(
                f"group {code}: existing classification or financial use prevents upgrade"
            )
        else:
            if updates:
                changes.append(
                    TemplateChange(
                        resource="account_group", code=code, action="update", fields=sorted(updates)
                    )
                )
    for code, _, group, kind in accounts:
        try:
            account = await resolve_account(
                db, access, selection, code, stored.get("group." + group), kind, defaults=defaults
            )
        except ConflictError:
            conflicts.append(f"account {code}: existing identity or classification conflicts")
        else:
            if account is None:
                changes.append(TemplateChange(resource="account", code=code, action="create"))
    return changes, conflicts


def tax_profile(
    selection: TemplateSelection,
    code: str,
    defaults: DefaultAccounts | None,
) -> dict[str, Any]:
    if defaults is not None:
        return defaults.profiles[code]
    direction, component, _ = code.split("_", 2)
    return {
        "company_registration_id": selection.gst_registration_id,
        "scheme": "GST_IN",
        "duty_type": "GST",
        "component": component,
        "purpose": "INPUT_RECOVERABLE" if direction == "INPUT" else "OUTPUT_PAYABLE",
    }


async def resolve_account(
    db: AsyncSession,
    access: Access,
    selection: TemplateSelection,
    code: str,
    group: m.AccountGroup | None,
    kind: str,
    *,
    defaults: DefaultAccounts | None = None,
) -> m.Account | None:
    """Preview and install use the same compatibility and legacy identity resolution."""
    company = access.context.company_id

    async def compatible(row: m.Account) -> bool:
        if group is None or row.group_id != group.id or row.kind != kind or row.status != "ACTIVE":
            return False
        if kind != "TAX":
            return True
        expected = tax_profile(selection, code, defaults)
        profile = await db.scalar(
            select(m.AccountTaxProfile).where(
                m.AccountTaxProfile.company_id == company, m.AccountTaxProfile.account_id == row.id
            )
        )
        return profile is not None and all(
            getattr(profile, name) == value
            or (name == "duty_type" and value == "GST" and profile.duty_type == "OTHER")
            for name, value in expected.items()
        )

    row = await db.scalar(
        select(m.Account).where(
            m.Account.company_id == company, m.Account.system_key == "account." + code
        )
    )
    if row is not None:
        if not await compatible(row):
            raise ConflictError("existing template account classification differs")
        return row
    registration_id = (
        tax_profile(selection, code, defaults).get("company_registration_id")
        if kind == "TAX"
        else None
    )
    if (
        kind == "TAX"
        and registration_id is not None
        and tax_profile(selection, code, defaults)["scheme"] == "GST_IN"
    ):
        direction, component, _ = code.split("_", 2)
        legacy_key = f"account.{direction}_{component}_{registration_id.hex[:12].upper()}"
        legacy = await db.scalar(
            select(m.Account).where(
                m.Account.company_id == company, m.Account.system_key == legacy_key
            )
        )
        # A collided v1 identity remains with its original registration and historical bindings.
        if legacy is not None and await compatible(legacy):
            return legacy
    collision = await db.scalar(
        select(m.Account.id).where(m.Account.company_id == company, m.Account.code == code)
    )
    if collision is not None:
        raise ConflictError("template account code is already owned by another master")
    return None


async def group_upgrade(
    db: AsyncSession,
    access: Access,
    row: m.AccountGroup,
    nature: str,
    parent: m.AccountGroup | None,
) -> dict[str, Any]:
    """The v3 Reserves correction is the only permitted structural seed upgrade."""
    head = await db.scalar(
        select(m.AccountHead).where(
            m.AccountHead.company_id == row.company_id, m.AccountHead.id == row.head_id
        )
    )
    if head is None or head.nature != nature or row.status != "ACTIVE":
        raise ConflictError("existing template group classification differs")
    expected_parent = parent.id if parent else None
    if row.parent_id == expected_parent:
        return {}
    if row.system_key != "group.RESERVES" or row.parent_id is not None or parent is None:
        raise ConflictError("existing template hierarchy differs")
    descendants = select(m.AccountGroupClosure.descendant_id).where(
        m.AccountGroupClosure.company_id == row.company_id,
        m.AccountGroupClosure.ancestor_id == row.id,
    )
    used = await db.scalar(
        select(m.Account.id)
        .where(
            m.Account.company_id == row.company_id,
            m.Account.group_id.in_(descendants),
            m.Account.used_at.is_not(None),
        )
        .limit(1)
    )
    if used is not None:
        raise ConflictError("financially used group hierarchy cannot be upgraded")
    before = values_of(row, BY_NAME["account_group"])
    after = await normalize_group(
        db, access, before | {"parent_id": expected_parent}, system_key=row.system_key
    )
    changed = writable(access, BY_NAME["account_group"], before, after)
    return {key: after[key] for key in changed}


async def seed_initial_chart(db: AsyncSession, access: Access) -> None:
    """Fixed defaults only, under initialize's authorization and existing company lock.

    An empty company initialized before this feature may catch up. An installed or
    authored chart receives only missing Cash and the fixed high-priority defaults
    approved on 2026-11-03/04, including opening offset and clearing. Existing identities
    and authored classifications remain
    protected; broader additions/upgrades use the preview/install command.
    """
    company = access.context.company_id
    for model in (m.AccountTemplateInstallation, m.AccountGroup, m.Account):
        if await db.scalar(select(model.id).where(model.company_id == company).limit(1)):
            await ensure_cash(db, access)
            pack = DefaultAccounts("defaults.business-high", list(HIGH_PRIORITY))
            keys = set(
                await db.scalars(
                    select(m.Account.system_key).where(
                        m.Account.company_id == company,
                        m.Account.system_key.in_(["account." + row[0] for row in HIGH_PRIORITY]),
                    )
                )
            )
            if len(keys) != len(HIGH_PRIORITY):
                selection = TemplateSelection(business_accounts=False)
                if await bootstrap_conflicts(db, access, selection, defaults=pack):
                    raise ConflictError(
                        "company default accounts conflict with existing masters; review setup"
                    )
                await install_content(db, access, selection, defaults=pack)
            return
    await install_content(db, access, TemplateSelection(business_accounts=True))


async def ensure_cash(db: AsyncSession, access: Access) -> None:
    """Every company can take cash: add Cash (and Cash-in-hand, Current Assets) if none exists.

    The groups and account are the template's own, by system key; a code already owned by
    another master leaves the chart as it is, for an administrator, rather than failing setup.
    """
    if await db.scalar(
        select(m.Account.id)
        .where(m.Account.company_id == access.context.company_id, m.Account.kind == "CASH")
        .limit(1)
    ):
        return
    selection = TemplateSelection(business_accounts=False)
    if await bootstrap_conflicts(db, access, selection, cash=True):
        LOG.info("The company's chart has no cash account and its template codes are taken")
        return
    await install_content(db, access, selection, cash=True)


async def install_content(
    db: AsyncSession,
    access: Access,
    selection: TemplateSelection,
    *,
    stock: bool = False,
    cash: bool = False,
    defaults: DefaultAccounts | None = None,
) -> CommandReceipt:
    """Transaction-local chart writer, shared by authorized setup and template commands.

    Callers authorize first; field policies, validation, company locking and audit remain
    enforced here. The initialization caller supplies only the fixed business selection,
    and the books bootstrap only the fixed standard stock accounts.
    """
    template, groups, accounts, digest = content(
        selection, stock=stock, cash=cash, defaults=defaults
    )
    setup = await setup_lock(db, access)
    company = access.context.company_id
    existing = await db.scalar(
        select(m.AccountTemplateInstallation).where(
            m.AccountTemplateInstallation.company_id == company,
            m.AccountTemplateInstallation.template_key == template,
            m.AccountTemplateInstallation.template_version == VERSION,
        )
    )
    if existing:
        if existing.content_hash != digest:
            raise ConflictError("installed template digest differs")
        return CommandReceipt(
            200,
            {
                "installation_id": str(existing.id),
                "groups_created": 0,
                "accounts_created": 0,
                "groups_updated": 0,
            },
        )
    installation = m.AccountTemplateInstallation(
        id=uuid7(),
        tenant_id=access.actor.tenant_id,
        company_id=company,
        template_key=template,
        template_version=VERSION,
        content_hash=digest,
        row_version=1,
        created_by=access.actor.user_id,
        updated_by=access.actor.user_id,
    )
    writable(
        access,
        BY_NAME["account_template_installation"],
        {},
        {
            "template_key": template,
            "template_version": VERSION,
            "content_hash": digest,
        },
    )
    db.add(installation)
    await db.flush()
    heads = {
        row.code: row
        for row in await db.scalars(
            select(m.AccountHead).where(m.AccountHead.company_id == company)
        )
    }
    if set(heads) != {"ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"}:
        raise ConflictError("company heads require repair")
    group_map = {
        row.system_key: row
        for row in await db.scalars(
            select(m.AccountGroup).where(
                m.AccountGroup.company_id == company, m.AccountGroup.system_key.is_not(None)
            )
        )
    }
    counts = {"groups_created": 0, "accounts_created": 0, "groups_updated": 0}

    def bind(row: m.Record, kind: str, system_key: str) -> None:
        writable(
            access,
            BY_NAME["account_template_binding"],
            {},
            {
                "installation_id": installation.id,
                "object_type": kind,
                "object_id": row.id,
                "system_key": system_key,
            },
        )
        db.add(
            m.AccountTemplateBinding(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=company,
                installation_id=installation.id,
                object_type=kind,
                object_id=row.id,
                system_key=system_key,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
            )
        )

    for position, (code, label, nature, parent) in enumerate(groups, 1):
        ordinal = GROUP_ORDER.get(code, position)
        system_key = "group." + code
        row: Any = group_map.get(system_key)
        if row is None:
            values = {
                "code": code,
                "name": label,
                "head_id": heads[nature].id,
                "parent_id": group_map["group." + parent].id if parent else None,
            }
            values.update(template_group_defaults(code, ordinal))
            if parent is not None and code != "STOCK":
                values["affects_gross_profit"] = None
            values = await normalize_group(db, access, values, system_key=system_key)
            changed = writable(
                access,
                BY_NAME["account_group"],
                {},
                values | {"status": "ACTIVE", "system_key": system_key},
            )
            row = m.AccountGroup(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=company,
                **values,
                status="ACTIVE",
                system_key=system_key,
                row_version=1,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
            )
            db.add(row)
            await db.flush()
            audit(db, access, BY_NAME["account_group"], row, "create", changed)
            group_map[system_key] = row
            counts["groups_created"] += 1
        else:
            updates = await group_upgrade(
                db, access, row, nature, group_map.get("group." + parent) if parent else None
            )
            if updates:
                for field, value in updates.items():
                    setattr(row, field, value)
                row.row_version += 1
                row.updated_by = access.actor.user_id
                await db.flush()
                audit(db, access, BY_NAME["account_group"], row, "update", set(updates))
                counts["groups_updated"] += 1
        bind(row, "GROUP", system_key)
    await rebuild_hierarchy(db, company)
    for code, label, group, kind in accounts:
        system_key = "account." + code
        row = await resolve_account(
            db, access, selection, code, group_map["group." + group], kind, defaults=defaults
        )
        if row is None:
            values = (
                BY_NAME["account"]
                .create.model_validate(
                    {
                        "code": code,
                        "name": label,
                        "group_id": group_map["group." + group].id,
                        "kind": kind,
                    }
                )
                .model_dump()
            )
            changed = writable(
                access,
                BY_NAME["account"],
                {},
                values | {"status": "ACTIVE", "system_key": system_key},
            )
            await validate(db, access, BY_NAME["account"], values)
            row = m.Account(
                id=uuid7(),
                tenant_id=access.actor.tenant_id,
                company_id=company,
                **values,
                status="DRAFT",
                system_key=system_key,
                row_version=1,
                created_by=access.actor.user_id,
                updated_by=access.actor.user_id,
            )
            db.add(row)
            await db.flush()
            if kind == "TAX":
                tax_values = {"account_id": row.id, **tax_profile(selection, code, defaults)}
                tax_changed = writable(access, BY_NAME["account_tax_profile"], {}, tax_values)
                await validate(db, access, BY_NAME["account_tax_profile"], tax_values)
                tax = m.AccountTaxProfile(
                    id=uuid7(),
                    tenant_id=access.actor.tenant_id,
                    company_id=company,
                    **tax_values,
                    row_version=1,
                    created_by=access.actor.user_id,
                    updated_by=access.actor.user_id,
                )
                db.add(tax)
                await db.flush()
                audit(db, access, BY_NAME["account_tax_profile"], tax, "create", tax_changed)
            await validate(
                db, access, BY_NAME["account"], values, object_id=row.id, activating=True
            )
            row.status = "ACTIVE"
            audit(db, access, BY_NAME["account"], row, "create", changed | {"status"})
            counts["accounts_created"] += 1
        bind(row, "ACCOUNT", system_key)
    await update_setup(db, access, setup, {"template_version": VERSION})
    audit(
        db,
        access,
        BY_NAME["account_template_installation"],
        installation,
        "create",
        {"template_key", "template_version", "content_hash"},
    )
    return CommandReceipt(200, {"installation_id": str(installation.id), **counts})


async def install(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    selection: TemplateSelection,
    key: str,
) -> CommandResult[BaseModel]:
    async def check(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        authorize_selection(access, selection, write=True)
        authorize_selection(access, selection, write=False)
        await require_metadata(db, access)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        return await install_content(db, access, selection)

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return TemplateResult.model_validate(receipt)

    try:
        return await execute_idempotent(
            factory,
            CommandIdentity(
                tenant_id=access.actor.tenant_id,
                company_id=access.context.company_id,
                actor_id=access.actor.user_id,
                operation="accounting.setup.install",
                key=key,
                request=selection.model_dump(mode="json"),
            ),
            authorize=check,
            mutate=mutate,
            render=render,
            timeout_seconds=30,
        )
    except IntegrityError as exc:
        raise ConflictError(
            "template conflicts with an existing company master; no changes were installed"
        ) from exc
