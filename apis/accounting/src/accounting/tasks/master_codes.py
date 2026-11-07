"""Allocate identities under the caller's company setup lock, including retired rows."""

import secrets
import uuid
from typing import Literal

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models.masters import Account, Party


def candidate_code() -> str:
    return secrets.token_hex(4).upper()


async def allocate_code(
    db: AsyncSession, company_id: uuid.UUID, resource: Literal["account", "party"]
) -> str:
    for _ in range(20):
        code = candidate_code()
        models = (Party, Account) if resource == "party" else (Account,)
        occupied = False
        for model in models:
            if await db.scalar(
                select(model.id).where(model.company_id == company_id, model.code == code)
            ):
                occupied = True
                break
        if not occupied:
            return code
    raise ConflictError("A unique Code could not be generated. Try again.")


async def check_code_available(
    db: AsyncSession,
    company_id: uuid.UUID,
    resource: Literal["account", "party"],
    code: str,
    *,
    field: str = "code",
) -> None:
    model = Party if resource == "party" else Account
    if await db.scalar(select(model.id).where(model.company_id == company_id, model.code == code)):
        raise ConflictError(
            "Code is already in use", fields={field: "Choose a unique Code or leave it blank."}
        )
