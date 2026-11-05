"""Bank encryption binds ciphertext to tenant, company and row; keys support rotation."""

from __future__ import annotations

import base64
import json
import secrets

from billing_platform.crypto import AesGcmCipher
from billing_platform.errors import PlatformError
from cryptography.exceptions import InvalidTag

from identity.config import Settings
from identity.models import CompanyBankAccount


class EncryptionUnavailableError(PlatformError):
    code = "ENCRYPTION_UNAVAILABLE"
    status_code = 503


def cipher(settings: Settings, key_id: str | None) -> AesGcmCipher:
    configured = settings.bank_encryption_keys.get(key_id or "")
    if configured is None:
        raise EncryptionUnavailableError("bank encryption is unavailable")
    try:
        return AesGcmCipher(base64.b64decode(configured.get_secret_value(), validate=True))
    except ValueError as exc:
        raise EncryptionUnavailableError("bank encryption is unavailable") from exc


def aad(row: CompanyBankAccount) -> bytes:
    return f"identity.bank.v1:{row.tenant_id}:{row.company_id}:{row.id}".encode()


def encrypt_details(
    row: CompanyBankAccount, settings: Settings, account_number: str | None, iban: str | None
) -> None:
    active = cipher(settings, settings.bank_active_key_id)
    row.details_ciphertext = active.encrypt(
        json.dumps({"account_number": account_number, "iban": iban}).encode(),
        nonce=secrets.token_bytes(12),
        associated_data=aad(row),
    )
    row.encryption_key_id = settings.bank_active_key_id
    row.account_last4 = account_number[-4:] if account_number else None
    row.iban_last4 = iban[-4:] if iban else None
    row.account_number = row.iban = None


def decrypt_details(row: CompanyBankAccount, settings: Settings) -> dict[str, str | None]:
    if row.details_ciphertext is None:
        # Legacy accounts are masked until the explicit backfill has secured them.
        raise EncryptionUnavailableError("bank account requires encryption migration")
    try:
        value = json.loads(
            cipher(settings, row.encryption_key_id).decrypt(
                row.details_ciphertext, associated_data=aad(row)
            )
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"account_number", "iban"}
            or any(v is not None and not isinstance(v, str) for v in value.values())
        ):
            raise ValueError("invalid encrypted details")
        return {"account_number": value["account_number"], "iban": value["iban"]}
    except (ValueError, InvalidTag) as exc:
        raise EncryptionUnavailableError("bank details are unavailable") from exc
