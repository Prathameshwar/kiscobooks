"""Bounded resumable bank encryption; caller holds the tenant mutation lock."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.models import CompanyBankAccount
from identity.services.audit import record
from identity.services.banks import cipher, decrypt_details, encrypt_details


async def rotate_batch(
    db: AsyncSession, current: Actor, settings: Settings, company_id: uuid.UUID, *, limit: int = 50
) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("bank batch must be between 1 and 100")
    cipher(settings, settings.bank_active_key_id)  # fail before selecting legacy plaintext
    rows = list(
        await db.scalars(
            select(CompanyBankAccount)
            .where(
                CompanyBankAccount.company_id == company_id,
                or_(
                    CompanyBankAccount.details_ciphertext.is_(None),
                    CompanyBankAccount.encryption_key_id.is_(None),
                    CompanyBankAccount.encryption_key_id != settings.bank_active_key_id,
                ),
            )
            .order_by(CompanyBankAccount.id)
            .limit(limit)
        )
    )
    for row in rows:
        values = (
            {"account_number": row.account_number, "iban": row.iban}
            if row.details_ciphertext is None
            else decrypt_details(row, settings)
        )
        encrypt_details(row, settings, values["account_number"], values["iban"])
        row.updated_by = current.user_id
        record(
            db,
            current,
            action="company.bank_encryption_rotated",
            entity="company_bank_account",
            entity_id=row.id,
            company_id=company_id,
        )
    await db.flush()
    return len(rows)
