"""Verify Catalog computations once, then post only from local immutable evidence."""

import time
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import CommandResult, canonical_json
from billing_platform.service_auth import ServiceKey, verify_service_body
from billing_platform.statutory import covers
from billing_platform.tax import may_charge_tax, registration_class
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.domain.ledger import base_value
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.charges import ChargeAssessment, ChargePolicy, ChargeTaxSnapshot
from accounting.models.masters import Account, AccountPostingMapping, AccountTaxProfile
from accounting.models.subledger import OpenItem
from accounting.resources import BY_NAME
from accounting.schemas.charge_tax import (
    TAX_COMPUTATION,
    TaxComputation,
    TaxComputationV2,
    TaxEvidence,
)
from accounting.schemas.ledger import JournalLineCreate
from accounting.tasks.access import authorize, readable
from accounting.tasks.finance_records import create_row, require_fields
from accounting.tasks.financial_commands import (
    FinancialEffect,
    financial_command,
    financial_context,
)
from accounting.tasks.validation import registration_window

OPERATION = "catalog.accounting_tax.assessed"


def charging_registration(
    access: Access, value: TaxComputation | TaxComputationV2
) -> dict[str, Any] | None:
    """The company registration the statement is made under, valid on its posting date.

    Neither the charge nor its assessment records a registration, so the evidence must name
    it. The row comes from the signed Identity context and is checked by date, never by the
    company's current regime: a composition period is refused even if the company is regular
    today. Taxed evidence without a resolvable registration is refused.
    """
    identifier = getattr(value, "company_registration_id", None)
    if identifier is None:
        if value.components:
            raise ValidationFailedError(
                "taxed Catalog evidence must name the company registration (version two)"
            )
        return None
    registration = next(
        (row for row in access.context.registrations if row.get("id") == str(identifier)), None
    )
    if registration is None or registration.get("tax_system") != "gst_in":
        raise ValidationFailedError("company GST registration is unavailable")
    # Only a supplier-class registration charges output tax; an ISD or TDS-deductor GSTIN may
    # coexist in the same state (Phase 1) and is never the charging registration. Identity
    # sends the class; it must agree with the class the regime implies, failing closed.
    implied = registration_class("gst_in", str(registration.get("regime")))
    if registration.get("registration_class", implied) != implied or implied != "supplier":
        raise ValidationFailedError("company registration is not a supplier registration")
    start, end = registration_window(registration)
    if not covers(start, end, value.posting_date):
        raise ValidationFailedError("company registration is not valid on the posting date")
    if value.components and not may_charge_tax("gst_in", str(registration.get("regime"))):
        raise ValidationFailedError(
            "the company registration's regime may not charge tax on the posting date"
        )
    return registration


async def ingest(
    factory: async_sessionmaker[AsyncSession],
    access: Access,
    body: TaxEvidence,
    key: str,
    settings: Settings,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> FinancialEffect:
        require_fields(
            access,
            "charge_assessment",
            {"input_hash", "amount", "currency", "posting_date", "status"},
        )
        credential = settings.catalog_tax_credentials.get(body.key_id)
        if credential is None:
            raise PermissionDeniedError("Catalog tax issuer is not configured")
        if not any(
            scope.tenant_id == access.actor.tenant_id
            and scope.company_id == access.context.company_id
            for scope in credential.scopes
        ):
            raise PermissionDeniedError("Catalog tax credential does not cover this company")
        verify_service_body(
            {
                body.key_id: ServiceKey(
                    "catalog",
                    "accounting",
                    frozenset({OPERATION}),
                    credential.secret.get_secret_value().encode(),
                )
            },
            key_id=body.key_id,
            issuer="catalog",
            audience="accounting",
            operation=OPERATION,
            timestamp=str(body.timestamp),
            signature=body.signature,
            body=canonical_json(body.computation.model_dump(mode="json")),
            now=int(time.time()),
            maximum_age=300,
        )
        value = body.computation
        if (
            value.tenant_id != access.actor.tenant_id
            or value.company_id != access.context.company_id
        ):
            raise PermissionDeniedError("Catalog tax evidence belongs to another company")
        row = await company_object(
            db, ChargeAssessment, value.assessment_id, company_id=value.company_id
        )
        if (
            row.status != "DRAFT"
            or value.input_hash != row.input_hash
            or value.currency != row.currency
            or value.net_amount != row.amount
            or value.posting_date != row.posting_date
        ):
            raise ConflictError("Catalog tax evidence differs from the current charge assessment")
        codes = [component.code for component in value.components]
        if len(set(codes)) != len(codes) or set(codes) != set(body.accounts):
            raise ValidationFailedError(
                "every unique tax component requires one local account assignment"
            )
        if (
            value.net_amount + sum((line.amount for line in value.components), Decimal(0))
            != value.gross_amount
        ):
            raise ValidationFailedError("Catalog tax gross total does not reconcile")
        registration = charging_registration(access, value)
        for code, account_id in body.accounts.items():
            account = await company_object(db, Account, account_id, company_id=value.company_id)
            require_fields(access, "account", {"kind", "status", "currency_mode"}, row=account)
            if (
                account.kind != "TAX"
                or account.status != "ACTIVE"
                or account.currency_mode != "BASE"
            ):
                raise ValidationFailedError(
                    "tax components require active base-currency tax accounts"
                )
            profile = await db.scalar(
                select(AccountTaxProfile).where(
                    AccountTaxProfile.company_id == value.company_id,
                    AccountTaxProfile.account_id == account.id,
                )
            )
            require_fields(
                access,
                "account_tax_profile",
                {"scheme", "component", "purpose", "company_registration_id"},
                row=profile,
            )
            # GST profiles always name a registration (validate_duty), so there is no
            # company-wide output account a component could fall back to.
            if (
                registration is None
                or profile is None
                or profile.scheme != "GST_IN"
                or profile.component != code
                or profile.purpose != "OUTPUT_PAYABLE"
                or str(profile.company_registration_id) != registration["id"]
            ):
                raise ValidationFailedError(
                    "each component requires an output tax account of that component "
                    "under the charging registration"
                )
        existing = await db.scalar(
            select(ChargeTaxSnapshot).where(
                ChargeTaxSnapshot.company_id == value.company_id,
                (ChargeTaxSnapshot.assessment_id == row.id)
                | (ChargeTaxSnapshot.provider_id == value.provider_id),
            )
        )
        snapshot = {
            "computation": value.model_dump(mode="json"),
            "accounts": {key: str(value) for key, value in body.accounts.items()},
        }
        if existing:
            if existing.snapshot != snapshot:
                raise ConflictError("Catalog assessment identity was reused with different content")
            return FinancialEffect(existing)
        return FinancialEffect(
            await create_row(
                db,
                access,
                "charge_tax_snapshot",
                assessment_id=row.id,
                provider_id=value.provider_id,
                currency=value.currency,
                net_amount=value.net_amount,
                gross_amount=value.gross_amount,
                input_hash=value.input_hash,
                key_id=body.key_id,
                snapshot=snapshot,
            )
        )

    return await financial_command(
        factory,
        access,
        FINANCIAL_BY_NAME["charge_tax_snapshot"],
        "ingest",
        body,
        key,
        mutate,
        permission="accounting.charges.manage",
        status=201,
    )


async def journal_lines(
    db: AsyncSession, access: Access, row: ChargeAssessment, item: OpenItem, policy: ChargePolicy
) -> list[JournalLineCreate]:
    facts = financial_context(access)
    debit = item.role == "CUSTOMER"
    gross = row.amount
    computation = None
    assignments: dict[str, str] = {}
    if policy.tax_treatment == "EXTERNAL":
        require_fields(
            access,
            "charge_tax_snapshot",
            {"assessment_id", "input_hash", "currency", "net_amount", "gross_amount", "snapshot"},
        )
        evidence = await db.scalar(
            select(ChargeTaxSnapshot).where(
                ChargeTaxSnapshot.company_id == row.company_id,
                ChargeTaxSnapshot.assessment_id == row.id,
            )
        )
        if evidence is None or evidence.input_hash != row.input_hash:
            raise ConflictError("taxable charges require a verified Catalog tax assessment")
        computation = TAX_COMPUTATION.validate_python(evidence.snapshot["computation"])
        assignments = evidence.snapshot["accounts"]
        gross = computation.gross_amount

    def base(amount: Decimal) -> Decimal:
        return base_value(
            amount,
            row.currency,
            row.exchange_rate,
            access.context.base_currency,
            facts.amount_precision,
            facts.rounding_mode,
        )

    output = [
        JournalLineCreate(
            account_id=item.account_id,
            side="DEBIT" if debit else "CREDIT",
            currency=row.currency,
            amount=gross,
            exchange_rate=row.exchange_rate,
        ),
        JournalLineCreate(
            account_id=policy.offset_account_id,
            side="CREDIT" if debit else "DEBIT",
            currency=access.context.base_currency,
            amount=base(row.amount),
            exchange_rate=Decimal(1),
        ),
    ]
    if computation:
        output.extend(
            JournalLineCreate(
                account_id=uuid.UUID(assignments[line.code]),
                side="CREDIT" if debit else "DEBIT",
                currency=access.context.base_currency,
                amount=base(line.amount),
                exchange_rate=Decimal(1),
            )
            for line in computation.components
        )
    residual = base(gross) - sum((line.amount for line in output[1:]), Decimal(0))
    if residual:
        credit = (residual > 0) == debit
        purpose = "ROUNDING_GAIN" if credit else "ROUNDING_LOSS"
        spec = BY_NAME["account_posting_mapping"]
        authorize(access, spec, "read")
        if not {
            "purpose",
            "account_id",
            "currency",
            "valid_from",
            "valid_to",
            "company_registration_id",
        } <= readable(access, spec):
            raise PermissionDeniedError("rounding account mapping is not readable")
        mappings = list(
            await db.scalars(
                select(AccountPostingMapping)
                .where(
                    AccountPostingMapping.company_id == row.company_id,
                    AccountPostingMapping.purpose == purpose,
                    AccountPostingMapping.company_registration_id.is_(None),
                    AccountPostingMapping.currency == access.context.base_currency,
                    AccountPostingMapping.valid_from <= row.posting_date,
                    (AccountPostingMapping.valid_to.is_(None))
                    | (AccountPostingMapping.valid_to >= row.posting_date),
                )
                .limit(2)
            )
        )
        if len(mappings) != 1:
            raise ConflictError(
                "foreign tax conversion requires one effective rounding account mapping"
            )
        output.append(
            JournalLineCreate(
                account_id=mappings[0].account_id,
                side="CREDIT" if credit else "DEBIT",
                currency=access.context.base_currency,
                amount=abs(residual),
                exchange_rate=Decimal(1),
            )
        )
    return output
