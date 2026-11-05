"""Bind reviewed invoice distribution to dated posting mappings and tax profiles."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.models.masters import Account, AccountTaxProfile
from accounting.tasks.finance_records import require_fields
from accounting.tasks.voucher_tax import mapping_row

PROFILES = {
    "OUTPUT": "OUTPUT_PAYABLE",
    "PENDING": "INPUT_PENDING",
    "INPUT": "INPUT_RECOVERABLE",
    "RCM": "RCM_PAYABLE",
    "DEPOSIT": "DEPOSIT",
}


async def tax_account(
    db: AsyncSession,
    access: Access,
    account_id: uuid.UUID,
    *,
    purpose: str,
    code: str,
    registration_id: str,
    currency: str,
) -> tuple[Account, AccountTaxProfile]:
    account = await company_object(db, Account, account_id, company_id=access.context.company_id)
    require_fields(access, "account", {"kind", "status", "currency_mode", "currency"}, row=account)
    profile = await db.scalar(
        select(AccountTaxProfile).where(
            AccountTaxProfile.company_id == access.context.company_id,
            AccountTaxProfile.account_id == account.id,
        )
    )
    if profile is None:
        raise ValidationFailedError("tax posting account has no tax profile")
    require_fields(
        access,
        "account_tax_profile",
        {"scheme", "purpose", "component", "company_registration_id", "account_id"},
        row=profile,
    )
    if (
        account.kind != "TAX"
        or account.status != "ACTIVE"
        or (account.currency_mode == "FIXED" and account.currency != currency)
        or profile.scheme != "GST_IN"
        or profile.purpose != PROFILES[purpose]
        or profile.component != code
        or (
            profile.company_registration_id is not None
            and str(profile.company_registration_id) != registration_id
        )
    ):
        raise ValidationFailedError("dated tax posting mapping has an incompatible account")
    return account, profile


async def resolve(
    db: AsyncSession, access: Access, kind: str, proof: dict[str, Any]
) -> list[dict[str, Any]]:
    if not proof.get("components"):
        return []
    purposes = {"OUTPUT"} if kind in {"SALES", "CREDIT_NOTE"} else set()
    if kind in {"PURCHASE", "DEBIT_NOTE"}:
        if proof["credit_state"] == "PENDING_EVIDENCE":
            purposes.add("PENDING")
        if proof["reverse_charge"]:
            purposes.add("RCM")
    result = []
    for purpose in sorted(purposes):
        for code in sorted({row["code"] for row in proof["components"]}):
            key = purpose + "_" + code
            mapping = await mapping_row(
                db,
                access,
                key,
                proof["company_registration_id"],
                dt.date.fromisoformat(proof["tax_point"]["tax_point_date"]),
            )
            if mapping is None:
                result.append({"purpose": key, "ready": False})
                continue
            account, profile = await tax_account(
                db,
                access,
                mapping.account_id,
                purpose=purpose,
                code=code,
                registration_id=proof["company_registration_id"],
                currency=mapping.currency,
            )
            result.append(
                {
                    "purpose": key,
                    "ready": True,
                    "mapping_id": str(mapping.id),
                    "mapping_version": mapping.row_version,
                    "valid_from": mapping.valid_from.isoformat(),
                    "valid_to": mapping.valid_to.isoformat() if mapping.valid_to else None,
                    "company_registration_id": str(mapping.company_registration_id)
                    if mapping.company_registration_id
                    else None,
                    "account_id": str(account.id),
                    "account_version": account.row_version,
                    "profile_id": str(profile.id),
                    "profile_version": profile.row_version,
                }
            )
    return result
