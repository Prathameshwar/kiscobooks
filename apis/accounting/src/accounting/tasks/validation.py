"""Transaction-local checks, under the Accounting company lock."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, FeatureNotEnabledError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.rules import (
    PURPOSE_HEADS,
    PURPOSE_KINDS,
    TAX_DEFAULT_HEADS,
    TAX_MAPPINGS,
    allowed_head,
    overlapping,
    regime_permits,
    require_contained_interval,
    validate_schedule,
    validate_tax_head,
    validate_values,
)
from accounting.domain.withholding import FEATURES
from accounting.models import masters as m
from accounting.models.tax_replica import TaxRuleReplica
from accounting.resources import BY_NAME, RESOURCES, Resource


def registration_window(registration: dict[str, Any]) -> tuple[dt.date, dt.date | None]:
    """A signed Identity registration row's inclusive validity window."""
    try:
        start = dt.date.fromisoformat(registration["valid_from"])
        end = (
            dt.date.fromisoformat(registration["valid_to"])
            if registration.get("valid_to")
            else None
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationFailedError("company registration validity is unavailable") from exc
    return start, end


def regime_requirement(values: dict[str, Any]) -> str | None:
    """The regime test a GST profile or tax posting mapping imposes on its registration."""
    if values.get("purpose") in TAX_MAPPINGS:
        return TAX_MAPPINGS[values["purpose"]].regime
    if values.get("scheme") != "GST_IN":
        return None
    return {
        "INPUT_RECOVERABLE": "RECOVER",
        "INPUT_PENDING": "RECOVER",
        "OUTPUT_PAYABLE": "CHARGE",
    }.get(values.get("purpose", ""))


def company_registration(access: Access, values: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve and check the signed company registration a profile or mapping names.

    Regime is judged per registration row, over that row's window. Identity never edits a
    row's regime (a change closes the row and opens another with a new id), and every dated
    dependant must fit inside the row's window (``validate``), so a regime test on the row
    holds for every date the profile or mapping can be effective. A regular registration
    that is later replaced by composition therefore cannot carry an input-recovery mapping
    into the composition period: that period belongs to a different row, which fails here.
    """
    identifier = values.get("company_registration_id")
    if identifier is None:
        return None
    registration = next(
        (row for row in access.context.registrations if row["id"] == str(identifier)), None
    )
    if registration is None:
        raise ValidationFailedError("company registration is unavailable")
    expected = {"GST_IN": {"gst_in"}, "VAT": {"vat", "vat_gb", "vat_eu", "vat_ae", "vat_sa"}}.get(
        values.get("scheme", "")
    )
    if expected and registration["tax_system"] not in expected:
        raise ValidationFailedError("tax scheme differs from the company registration")
    requirement = regime_requirement(values)
    if requirement is not None:
        registration_window(registration)
        if not regime_permits(
            requirement, str(registration["tax_system"]), str(registration.get("regime"))
        ):
            raise ValidationFailedError(
                "input recovery requires a supported regular registration"
                if requirement == "RECOVER"
                else "the registration's regime may not charge output tax"
            )
    return registration


async def validate_account_profiles(
    db: AsyncSession,
    access: Access,
    account_id: uuid.UUID | None,
    kind: str,
    nature: str,
    *,
    activating: bool,
) -> None:
    tax = None
    bank = None
    if account_id is not None:
        tax = await db.scalar(
            select(m.AccountTaxProfile).where(
                m.AccountTaxProfile.company_id == access.context.company_id,
                m.AccountTaxProfile.account_id == account_id,
            )
        )
        bank = await db.scalar(
            select(m.AccountBankProfile).where(
                m.AccountBankProfile.company_id == access.context.company_id,
                m.AccountBankProfile.account_id == account_id,
            )
        )
    if (tax is not None and kind != "TAX") or (bank is not None and kind != "BANK"):
        raise ConflictError("account kind is retained by its existing profile")
    if tax is not None:
        validate_tax_head(tax.purpose, nature)
    if not activating:
        return
    if (kind == "TAX" and tax is None) or (kind == "BANK" and bank is None):
        raise ConflictError("account profile must be completed before activation")
    if tax is not None:
        values = {
            key: getattr(tax, key) for key in BY_NAME["account_tax_profile"].create.model_fields
        }
        validate_values("account_tax_profile", values)
        company_registration(access, values)
    if bank is not None and bank.company_bank_id not in access.context.bank_ids:
        raise ValidationFailedError("company bank is unavailable")


async def validate(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    values: dict[str, Any],
    *,
    object_id: uuid.UUID | None = None,
    activating: bool = False,
) -> None:
    validate_values(spec.name, values)
    from accounting.domain.reference import validate_reference

    validate_reference(
        values.get("country_code"),
        values.get("state_code"),
        [values.get("currency"), values.get("settlement_currency")],
    )
    company = access.context.company_id
    references: dict[str, Any] = {}
    for field, target in spec.references.items():
        if values.get(field) is None:
            continue
        row: Any = await company_object(
            db, BY_NAME[target].model, values[field], company_id=company
        )
        references[field] = row
        if BY_NAME[target].lifecycle == "dates":
            if spec.lifecycle == "dates":
                require_contained_interval(
                    values["valid_from"], values.get("valid_to"), row.valid_from, row.valid_to
                )
            elif activating:
                require_contained_interval(
                    utcnow().date(), utcnow().date(), row.valid_from, row.valid_to
                )
        if (
            (activating or spec.lifecycle == "dates")
            and hasattr(row, "status")
            and row.status != "ACTIVE"
        ):
            raise ConflictError("referenced master must be active")
        if (
            values.get("party_id") is not None
            and hasattr(row, "party_id")
            and row.party_id != values["party_id"]
        ):
            raise ValidationFailedError("related records must belong to the same party")
    registration = company_registration(access, values)
    if registration is not None and spec.lifecycle == "dates":
        start, end = registration_window(registration)
        require_contained_interval(values["valid_from"], values.get("valid_to"), start, end)
    if (
        values.get("company_bank_id") is not None
        and values["company_bank_id"] not in access.context.bank_ids
    ):
        raise ValidationFailedError("company bank is unavailable")
    if spec.name == "account":
        group = references["group_id"]
        head = await company_object(db, m.AccountHead, group.head_id, company_id=company)
        if not allowed_head(values["kind"], values.get("party_role"), head.nature):
            raise ValidationFailedError("account kind and group head are incompatible")
        foreign_fixed = (
            values["currency_mode"] == "FIXED"
            and values.get("currency") != access.context.base_currency
        )
        if (values["currency_mode"] == "MULTI" or foreign_fixed) and (
            "multi_currency" not in access.context.features
        ):
            raise ConflictError("multicurrency is not enabled for this company")
        if foreign_fixed and values["currency"] not in access.context.allowed_currencies:
            raise ConflictError("account currency is not enabled for this company")
        if values["kind"] == "PARTY":
            # A broker and an "other" party share the account role OTHER, so either role backs it.
            backing = (
                ("OTHER", "BROKER") if values["party_role"] == "OTHER" else (values["party_role"],)
            )
            roles = list(
                await db.scalars(
                    select(m.PartyRole).where(
                        m.PartyRole.company_id == company,
                        m.PartyRole.party_id == values["party_id"],
                        m.PartyRole.role.in_(backing),
                    )
                )
            )
            role = next(
                (row for row in roles if row.status == "ACTIVE"), roles[0] if roles else None
            )
            if role is None or (activating and role.status != "ACTIVE"):
                raise ConflictError("party role is unavailable")
            # One live account per party and account role (docs/party-ledger-mandatory-plan.md).
            # Only a new account, or a draft about to go live, is checked: an account that is
            # already live stays editable and retirable even where older data holds two.
            stored = (
                await db.scalar(select(m.Account.status).where(m.Account.id == object_id))
                if object_id is not None
                else None
            )
            if stored in (None, "DRAFT"):
                clash = select(m.Account.id).where(
                    m.Account.company_id == company,
                    m.Account.party_id == values["party_id"],
                    m.Account.party_role == values["party_role"],
                    m.Account.status != "INACTIVE",
                )
                if object_id is not None:
                    clash = clash.where(m.Account.id != object_id)
                if await db.scalar(clash.limit(1)) is not None:
                    raise ConflictError("this party already has an account for this role")
        await validate_account_profiles(
            db,
            access,
            object_id,
            values["kind"],
            head.nature,
            activating=activating,
        )
    if spec.name in {"account_bank_profile", "account_tax_profile"}:
        account = references["account_id"]
        expected = "BANK" if spec.name == "account_bank_profile" else "TAX"
        if account.kind != expected or account.used_at is not None or account.status != "DRAFT":
            raise ConflictError("profile requires an unused draft account of the matching kind")
        if expected == "TAX":
            group = await company_object(db, m.AccountGroup, account.group_id, company_id=company)
            head = await company_object(db, m.AccountHead, group.head_id, company_id=company)
            validate_tax_head(values["purpose"], head.nature)
    if spec.name == "party_commercial_type_membership":
        commercial = references["commercial_type_id"]
        if (
            await db.scalar(
                select(m.PartyRole.id).where(
                    m.PartyRole.company_id == company,
                    m.PartyRole.party_id == values["party_id"],
                    m.PartyRole.role == commercial.role,
                    m.PartyRole.status == "ACTIVE",
                )
            )
            is None
        ):
            raise ConflictError("commercial membership requires an active matching party role")
    if spec.name in {"party_credit_policy", "party_accounting_policy"}:
        if (
            await db.scalar(
                select(m.PartyRole.id).where(
                    m.PartyRole.company_id == company,
                    m.PartyRole.party_id == values["party_id"],
                    m.PartyRole.role == values["role"],
                    m.PartyRole.status == "ACTIVE",
                )
            )
            is None
        ):
            raise ConflictError("policy requires an active matching party role")
    if spec.name == "payment_term" and activating:
        lines = list(
            await db.scalars(
                select(m.PaymentTermLine)
                .where(
                    m.PaymentTermLine.company_id == company,
                    m.PaymentTermLine.payment_term_id == object_id,
                )
                .limit(25)
            )
        )
        validate_schedule([(line.sequence, line.percentage) for line in lines])
    if spec.name == "payment_term_line" and references["payment_term_id"].status != "DRAFT":
        raise ConflictError("instalments can only change while the payment term is draft")
    if (
        spec.name in {"party_registration_address", "party_address_use"}
        and values.get("registration_id") is not None
    ):
        address, registration = references["address_id"], references["registration_id"]
        if address.country_code != registration.country_code or (
            registration.scheme == "GST_IN"
            and (not registration.state_code or address.state_code != registration.state_code)
        ):
            raise ValidationFailedError("address jurisdiction differs from its registration")
    if spec.name == "party_address_use":
        duplicate = select(m.PartyAddressUse.id).where(
            m.PartyAddressUse.company_id == company,
            m.PartyAddressUse.address_id == values["address_id"],
            m.PartyAddressUse.purpose == values["purpose"],
            m.PartyAddressUse.registration_id == values.get("registration_id"),
        )
        if object_id is not None:
            duplicate = duplicate.where(m.PartyAddressUse.id != object_id)
        if await db.scalar(duplicate.limit(1)) is not None:
            raise ConflictError("address use already exists in this registration scope")
    if (
        spec.name in {"party_address_use", "party_contact_use"}
        and activating
        and values.get("is_default")
    ):
        model: Any = spec.model
        stmt = select(model.id).where(
            model.company_id == company,
            model.party_id == values["party_id"],
            model.purpose == values["purpose"],
            model.is_default.is_(True),
            model.status == "ACTIVE",
        )
        if spec.name == "party_address_use":
            stmt = stmt.where(model.registration_id == values.get("registration_id"))
        if object_id is not None:
            stmt = stmt.where(model.id != object_id)
        if await db.scalar(stmt.limit(1)) is not None:
            raise ConflictError("another active default exists for this purpose")
    if spec.name == "account_posting_mapping":
        account = references["account_id"]
        group = await company_object(db, m.AccountGroup, account.group_id, company_id=company)
        head = await company_object(db, m.AccountHead, group.head_id, company_id=company)
        purpose = values["purpose"]
        if head.nature not in PURPOSE_HEADS[purpose]:
            raise ValidationFailedError("posting purpose has an incompatible account head")
        expected_kind = PURPOSE_KINDS.get(purpose)
        if expected_kind is not None and account.kind != expected_kind:
            raise ValidationFailedError("posting purpose has an incompatible account kind")
        rule = TAX_MAPPINGS.get(purpose)
        if rule is not None:
            profile = await db.scalar(
                select(m.AccountTaxProfile).where(
                    m.AccountTaxProfile.company_id == company,
                    m.AccountTaxProfile.account_id == account.id,
                )
            )
            if (
                profile is None
                or profile.company_registration_id != values.get("company_registration_id")
                or profile.scheme != rule.scheme
                or profile.component != rule.component
                or profile.purpose != rule.profile_purpose
                or profile.duty_type not in rule.duty_types
            ):
                raise ValidationFailedError("posting tax mapping differs from its account profile")
            if rule.scheme == "GST_IN" and registration is None:
                raise ValidationFailedError("GST posting mappings require a company registration")
        currency = (
            account.currency if account.currency_mode == "FIXED" else access.context.base_currency
        )
        if account.currency_mode != "MULTI" and currency != values["currency"]:
            raise ValidationFailedError("posting mapping currency differs from the account")
    if spec.name in WITHHOLDING:
        await validate_withholding(db, access, spec, values, references, object_id)
    if spec.name == "account_tax_default":
        await validate_tax_default(db, values, references["account_id"], company)
    if spec.lifecycle == "dates":
        await check_intervals(db, spec, values, object_id, company)


async def validate_tax_default(
    db: AsyncSession, values: dict[str, Any], account: Any, company: uuid.UUID
) -> None:
    """An account GST default needs a GENERAL P&L or asset account and a matching rule."""
    group = await company_object(db, m.AccountGroup, account.group_id, company_id=company)
    head = await company_object(db, m.AccountHead, group.head_id, company_id=company)
    if account.kind != "GENERAL" or head.nature not in TAX_DEFAULT_HEADS:
        raise ValidationFailedError("tax defaults need a general income, expense or asset account")
    if values.get("rule_id") is None:
        return
    rule = await company_object(db, TaxRuleReplica, values["rule_id"], company_id=company)
    if not rule.is_active:
        raise ConflictError("referenced tax rule must be active")
    if rule.item_kind != values["supply_kind"] or rule.treatment != values["treatment"]:
        raise ValidationFailedError("tax rule differs from the default's supply kind or treatment")


WITHHOLDING = frozenset(
    {
        "withholding_section",
        "withholding_rate",
        "party_withholding_profile",
        "withholding_certificate",
    }
)


def require_withholding_feature(access: Access, kind: str) -> None:
    feature = FEATURES[kind]
    if feature not in access.context.features:
        raise FeatureNotEnabledError(f"{kind} is not enabled for this company", feature=feature)


async def validate_withholding(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    values: dict[str, Any],
    references: dict[str, Any],
    object_id: uuid.UUID | None,
) -> None:
    """Withholding masters: feature gate by kind, base-currency amounts, explicit supersession."""
    kind = values["kind"] if "kind" in values else references["section_id"].kind
    require_withholding_feature(access, kind)
    currency_field = "threshold_currency" if spec.name == "withholding_rate" else "currency"
    if values.get(currency_field) not in {None, access.context.base_currency}:
        raise ValidationFailedError("withholding amounts are in the company base currency")
    if spec.name == "party_withholding_profile":
        identifier = references.get("pan_identifier_id")
        if identifier is not None and identifier.scheme != "PAN":
            raise ValidationFailedError("PAN status must reference a PAN identifier")
        section = references.get("default_section_id")
        if section is not None and section.kind != kind:
            raise ValidationFailedError("default section differs from the profile kind")
    if spec.name == "withholding_rate" and values.get("supersedes_id") is not None:
        previous = await company_object(
            db, m.WithholdingRate, values["supersedes_id"], company_id=access.context.company_id
        )
        if (
            previous.id == object_id
            or previous.section_id != values["section_id"]
            or previous.deductee_type != values["deductee_type"]
            or previous.valid_to is None
            or previous.valid_to + dt.timedelta(days=1) != values["valid_from"]
        ):
            raise ConflictError("a superseding rate must start the day after its predecessor ends")
        successor = select(m.WithholdingRate.id).where(
            m.WithholdingRate.company_id == access.context.company_id,
            m.WithholdingRate.supersedes_id == previous.id,
        )
        if object_id is not None:
            successor = successor.where(m.WithholdingRate.id != object_id)
        if await db.scalar(successor.limit(1)) is not None:
            raise ConflictError("the predecessor rate is already superseded")


async def check_intervals(
    db: AsyncSession,
    spec: Resource,
    values: dict[str, Any],
    object_id: uuid.UUID | None,
    company: uuid.UUID,
) -> None:
    keys = {
        "party_tax_registration": ("party_id", "scheme", "registration_number"),
        "party_drug_licence": ("party_id", "address_id", "licence_form"),
        "party_identifier": ("party_id", "scheme"),
        "party_registration_address": ("registration_id", "address_id"),
        "party_commercial_type_membership": ("party_id", "commercial_type_id"),
        "party_accounting_policy": ("party_id", "role"),
        "party_credit_policy": ("party_id", "role"),
        "account_posting_mapping": ("purpose", "company_registration_id", "currency"),
        "account_tax_default": ("account_id", "direction"),
        "withholding_rate": ("section_id", "deductee_type"),
        "party_withholding_profile": ("party_id", "kind"),
        "withholding_certificate": ("party_id", "section_id"),
    }[spec.name]
    model: Any = spec.model
    if spec.name == "party_tax_registration" and values.get("scheme") == "GST_IN":
        if values.get("registration_type") in GST_STATUS_TYPES:
            await overlap(
                db,
                model,
                values,
                object_id,
                company,
                (model.party_id == values.get("party_id"))
                & (model.scheme == "GST_IN")
                & (model.state_code == values.get("state_code"))
                & model.registration_type.in_(GST_STATUS_TYPES),
            )
        if values.get("registration_number") is None:
            return
    conditions = [getattr(model, key) == values.get(key) for key in keys]
    await overlap(db, model, values, object_id, company, *conditions)


#: A GST party's status in one state: regular, composition or unregistered. At most one holds
#: on any date, so one party and state never have two overlapping regular registrations, and
#: never two unregistered rows (which carry no number to key on).
GST_STATUS_TYPES = ("REGULAR", "COMPOSITION", "UNREGISTERED")


async def overlap(
    db: AsyncSession,
    model: Any,
    values: dict[str, Any],
    object_id: uuid.UUID | None,
    company: uuid.UUID,
    *conditions: Any,
) -> None:
    stmt = select(model).where(model.company_id == company, *conditions)
    if object_id is not None:
        stmt = stmt.where(model.id != object_id)
    stmt = stmt.where(
        model.valid_from.is_(None) | (model.valid_from <= (values.get("valid_to") or dt.date.max))
    )
    rows = list(await db.scalars(stmt.limit(1001)))
    if len(rows) > 1000:
        raise ConflictError("interval history requires an archived history review")
    if any(
        overlapping(values["valid_from"], values.get("valid_to"), row.valid_from, row.valid_to)
        for row in rows
    ):
        raise ConflictError("effective interval overlaps an existing record")


async def guard_registration_links(
    db: AsyncSession, spec: Resource, row: m.Record, changed: set[str]
) -> None:
    if spec.name == "party_address" and changed & {
        "mailing_name",
        "line1",
        "line2",
        "locality",
        "city",
        "state_code",
        "country_code",
        "postal_code",
    }:
        reviewed = await db.scalar(
            select(m.PartyDrugLicence.id)
            .where(
                m.PartyDrugLicence.company_id == row.company_id,
                m.PartyDrugLicence.address_id == row.id,
            )
            .limit(1)
        )
        if reviewed is not None:
            raise ConflictError("reviewed drug licence retains this exact trading premises")
    if spec.name not in {"party_address", "party_tax_registration"} or not changed & {
        "country_code",
        "state_code",
        "scheme",
    }:
        return
    field = "address_id" if spec.name == "party_address" else "registration_id"
    for model in (m.PartyRegistrationAddress, m.PartyAddressUse):
        query = select(model.id).where(
            model.company_id == row.company_id,
            getattr(model, field) == row.id,
            model.registration_id.is_not(None),
        )
        if await db.scalar(query.limit(1)) is not None:
            raise ConflictError("jurisdiction is retained by existing registration associations")


async def guard_role_retirement(db: AsyncSession, row: Any) -> None:
    """Accounts and role-scoped policies name a role by value, not by identifier, so the
    generic reference walk in `guard_retirement` cannot see that they depend on it."""
    # A broker's account has the account role OTHER, shared with an "other" role of the party: the
    # account stays needed while another live role of the party still stands on it.
    account_role = "OTHER" if row.role in {"OTHER", "BROKER"} else row.role
    standing = select(m.PartyRole.id).where(
        m.PartyRole.company_id == row.company_id,
        m.PartyRole.party_id == row.party_id,
        m.PartyRole.id != row.id,
        m.PartyRole.status != "INACTIVE",
        m.PartyRole.role.in_(("OTHER", "BROKER") if account_role == "OTHER" else (account_role,)),
    )
    account = select(m.Account.id).where(
        m.Account.company_id == row.company_id,
        m.Account.party_id == row.party_id,
        m.Account.party_role == account_role,
        m.Account.status != "INACTIVE",
    )
    if await db.scalar(account.limit(1)) is not None and await db.scalar(standing.limit(1)) is None:
        raise ConflictError("dependent masters must be retired or replaced first")
    today = utcnow().date()
    membership = (
        select(m.PartyCommercialTypeMembership.id)
        .join(
            m.PartyCommercialType,
            m.PartyCommercialType.id == m.PartyCommercialTypeMembership.commercial_type_id,
        )
        .where(
            m.PartyCommercialTypeMembership.company_id == row.company_id,
            m.PartyCommercialType.company_id == row.company_id,
            m.PartyCommercialTypeMembership.party_id == row.party_id,
            m.PartyCommercialType.role == row.role,
            (m.PartyCommercialTypeMembership.valid_to.is_(None))
            | (m.PartyCommercialTypeMembership.valid_to >= today),
        )
    )
    if await db.scalar(membership.limit(1)) is not None:
        raise ConflictError("commercial memberships must end before retiring this role")
    policies: tuple[Any, ...] = (m.PartyAccountingPolicy, m.PartyCreditPolicy)
    for model in policies:
        stmt = select(model.id).where(
            model.company_id == row.company_id,
            model.party_id == row.party_id,
            model.role == row.role,
            (model.valid_to.is_(None)) | (model.valid_to >= today),
        )
        if await db.scalar(stmt.limit(1)) is not None:
            raise ConflictError("dependent masters must be retired or replaced first")


async def guard_retirement(db: AsyncSession, spec: Resource, row: m.Record) -> None:
    if spec.name == "party_role":
        await guard_role_retirement(db, row)
    for other in RESOURCES:
        if other.name in {
            "account_group_closure",
            "account_template_binding",
            "payment_term_line",
            "account_bank_profile",
            "account_tax_profile",
        }:
            continue
        for field, target in other.references.items():
            if target != spec.name:
                continue
            model: Any = other.model
            stmt = select(model.id).where(
                model.company_id == row.company_id, getattr(model, field) == row.id
            )
            if other.lifecycle == "status":
                stmt = stmt.where(model.status != "INACTIVE")
            if other.lifecycle == "dates":
                stmt = stmt.where((model.valid_to.is_(None)) | (model.valid_to >= utcnow().date()))
            if await db.scalar(stmt.limit(1)) is not None:
                raise ConflictError("dependent masters must be retired or replaced first")


async def guard_child_intervals(
    db: AsyncSession, spec: Resource, row: m.Record, values: dict[str, Any]
) -> None:
    """Parent changes must preserve all recorded and scheduled dependent intervals."""
    start = values["valid_from"] or dt.date.min
    end = values.get("valid_to") or dt.date.max
    for child in RESOURCES:
        for field, target in child.references.items():
            if target != spec.name:
                continue
            model: Any = child.model
            stmt = select(model.id).where(
                model.company_id == row.company_id, getattr(model, field) == row.id
            )
            if child.lifecycle == "dates":
                stmt = stmt.where(
                    (model.valid_from < start)
                    | (model.valid_to.is_(None) & (end < dt.date.max))
                    | (model.valid_to > end)
                )
            elif child.lifecycle == "status":
                if start <= utcnow().date() <= end:
                    continue
                stmt = stmt.where(model.status == "ACTIVE")
            else:
                continue
            if await db.scalar(stmt.limit(1)) is not None:
                raise ConflictError("registration validity would exclude dependent records")
