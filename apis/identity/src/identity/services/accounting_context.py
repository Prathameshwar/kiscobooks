"""Accounting gateway context from authoritative Identity facts, never client input."""

from __future__ import annotations

import time
import uuid
from typing import Any

from billing_platform.authz import Scope, ScopePath
from billing_platform.company_context import CompanyContext, FinancialContext
from billing_platform.constants import SCOPE_ALL
from billing_platform.display import DisplayConfiguration
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.money import RoundingMode
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import (
    Company,
    CompanyBankAccount,
    CompanyCurrencyAllowance,
    CompanyFeature,
    CompanyTaxRegistration,
    FieldConfig,
    FieldPolicy,
    User,
)
from identity.services.display import resolve_display
from identity.services.posting import configuration, digest
from identity.models.company_gst_filing import CompanyGstFilingPreference
from identity.models.company_gst_outward import CompanyGstOutwardProfile


async def accounting_policies(
    db: AsyncSession, current: Actor, target: ScopePath, *, entity_prefix: str = "accounting."
) -> list[FieldPolicy]:
    """Use the same subject, role validity and scope resolution for delegation and transport."""
    from identity.services.field_subjects import policy_subjects

    groups, assignments = await policy_subjects(db, current)
    roles = {
        row.role_id for row in assignments if target.includes(Scope(row.scope_type, row.scope_id))
    }
    policies = list(
        await db.scalars(
            select(FieldPolicy)
            .where(
                FieldPolicy.entity_type.startswith(entity_prefix),
                FieldPolicy.is_active.is_(True),
                or_(
                    and_(
                        FieldPolicy.subject_type == "user",
                        FieldPolicy.subject_id == current.user_id,
                    ),
                    and_(
                        FieldPolicy.subject_type == "user_group", FieldPolicy.subject_id.in_(groups)
                    ),
                    and_(FieldPolicy.subject_type == "role", FieldPolicy.subject_id.in_(roles)),
                ),
            )
            .limit(1001)
        )
    )
    if len(policies) > 1000:
        raise ValidationFailedError("company policy count exceeds its bound")
    return [row for row in policies if target.includes(Scope(row.scope_type, row.scope_id))]


async def company_context(
    db: AsyncSession, current: Actor, company_id: uuid.UUID, *, entity_prefix: str = "accounting."
) -> CompanyContext:
    company = await db.get(Company, company_id)
    if company is None:
        raise NotFoundError("company not found")
    target = ScopePath(company_id=company_id)
    policies = await accounting_policies(db, current, target, entity_prefix=entity_prefix)
    if entity_prefix in {"vouchers.", "reports."}:
        policies += await accounting_policies(db, current, target, entity_prefix="accounting.")
    layouts = list(
        await db.scalars(
            select(FieldConfig)
            .where(
                FieldConfig.entity_type.startswith(entity_prefix),
                FieldConfig.company_id.in_([SCOPE_ALL, company_id]),
            )
            .limit(1001)
        )
    )
    banks = list(
        await db.scalars(
            select(CompanyBankAccount.id)
            .where(
                CompanyBankAccount.company_id == company_id, CompanyBankAccount.is_active.is_(True)
            )
            .limit(201)
        )
    )
    registrations = list(
        await db.scalars(
            select(CompanyTaxRegistration)
            .where(CompanyTaxRegistration.company_id == company_id)
            .limit(201)
        )
    )
    gst_outward_profiles = list(
        await db.scalars(
            select(CompanyGstOutwardProfile)
            .where(CompanyGstOutwardProfile.company_id == company_id)
            .limit(201)
        )
    )
    if len(gst_outward_profiles) > 200:
        raise ConflictError("GST outward reporting profiles exceed their supported context bound")
    gst_preferences = list(
        await db.scalars(
            select(CompanyGstFilingPreference)
            .where(CompanyGstFilingPreference.company_id == company_id)
            .limit(201)
        )
    )
    if len(gst_preferences) > 200:
        raise ValidationFailedError("GST filing history exceeds the transport bound")
    if len(policies) > 1000 or len(layouts) > 1000 or len(banks) > 200 or len(registrations) > 200:
        raise ValidationFailedError("company context exceeds the transport bound")
    features = frozenset(
        await db.scalars(
            select(CompanyFeature.feature_key).where(
                CompanyFeature.company_id == company_id, CompanyFeature.is_enabled.is_(True)
            )
        )
    )
    allowed_currency_rows = list(
        await db.scalars(
            select(CompanyCurrencyAllowance.currency_code)
            .where(
                CompanyCurrencyAllowance.company_id == company_id,
                CompanyCurrencyAllowance.is_active.is_(True),
            )
            .limit(65)
        )
    )
    if len(allowed_currency_rows) > 64:
        raise ValidationFailedError("company currency allowance exceeds the transport bound")
    allowed_currencies = frozenset(allowed_currency_rows)
    policy_values: list[dict[str, Any]] = []
    for row in policies:
        if target.includes(Scope(row.scope_type, row.scope_id)):
            policy_values.append(
                {
                    "entity_type": row.entity_type,
                    "field_key": row.field_key,
                    "access": row.access,
                    "effect": row.effect,
                    "scope_type": row.scope_type,
                    "scope_id": str(row.scope_id),
                    "condition": row.condition,
                }
            )
    layout_values = tuple(
        {
            "entity_type": row.entity_type,
            "field_key": row.field_key,
            "is_visible": row.is_visible,
            "is_required": row.is_required,
            "label_override": row.label_override,
            "display_order": row.display_order,
            "display_group": row.display_group,
        }
        for row in sorted(layouts, key=lambda row: (row.company_id != SCOPE_ALL, str(row.id)))
    )
    report_display = None
    if entity_prefix in {"reports.", "vouchers."}:
        display = resolve_display(company, await db.get(User, current.user_id))
        display.pop("show_amount_in_words")
        report_display = DisplayConfiguration(company_label=company.display_name, **display)
    return CompanyContext(
        issued_at=int(time.time()),
        tenant_id=current.tenant_id,
        company_id=company_id,
        user_id=current.user_id,
        base_currency=company.base_currency,
        report_display=report_display,
        policy_namespaces=frozenset({"vouchers", "accounting"})
        if entity_prefix == "vouchers."
        else frozenset({"reports", "accounting"})
        if entity_prefix == "reports."
        else frozenset({"accounting"}),
        finance=FinancialContext(
            configuration_hash=digest(await configuration(db, company)),
            company_active=company.status == "active",
            books_begin_date=company.books_begin_date,
            fiscal_year_start_month=company.fiscal_year_start_month,
            fiscal_year_start_day=company.fiscal_year_start_day,
            amount_precision=company.amount_precision,
            rounding_mode=RoundingMode(company.rounding_mode),
            default_payment_terms_days=company.default_payment_terms_days,
            credit_limit_default=company.credit_limit_default,
            cash_receipt_limit=company.cash_receipt_limit,
            backdated_posting_limit_days=company.backdated_posting_limit_days,
            timezone=company.timezone,
        ),
        features=features,
        allowed_currencies=allowed_currencies,
        bank_ids=frozenset(banks),
        registrations=tuple(
            {
                "id": str(row.id),
                "tax_system": row.tax_system,
                "regime": row.regime,
                "registration_class": row.registration_class,
                "jurisdiction_code": row.jurisdiction_code,
                "number": row.number,
                "legal_name": row.legal_name_on_registration or company.legal_name,
                "country_code": company.country_code,
                "filing_preferences": [
                    {
                        "id": str(preference.id),
                        "frequency": preference.frequency,
                        "valid_from": preference.valid_from.isoformat(),
                        "valid_to": preference.valid_to.isoformat()
                        if preference.valid_to
                        else None,
                    }
                    for preference in gst_preferences
                    if preference.registration_id == row.id
                ],
                "outward_profiles": [
                    {
                        "id": str(profile.id),
                        "annual_turnover": format(profile.annual_turnover, ".4f"),
                        "currency": profile.currency,
                        "rule_14a": profile.rule_14a,
                        "valid_from": profile.valid_from.isoformat(),
                        "valid_to": profile.valid_to.isoformat() if profile.valid_to else None,
                        "reference": profile.reference,
                        "evidence_hash": profile.evidence_hash,
                    }
                    for profile in gst_outward_profiles
                    if profile.registration_id == row.id
                ],
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            }
            for row in registrations
        ),
        policies=tuple(policy_values),
        layouts=layout_values,
    )
