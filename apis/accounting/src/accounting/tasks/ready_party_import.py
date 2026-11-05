"""Ready-to-use party imports compose ordinary, transaction-local lifecycle commands."""

from typing import Any, Literal

from billing_platform.bulk import BulkRecord, resolve_references
from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.resources import BY_NAME
from accounting.schemas.masters import ExpectedVersion, PartyCreate, PartyRoleCreate
from accounting.schemas.party_opening import OPENING_FIELDS, ReadyPartyCreate
from accounting.tasks.commands import mutate_master, setup_lock
from accounting.tasks.party_opening import stage

READY_PARTY_ROLES: dict[str, Literal["SUPPLIER", "CUSTOMER"]] = {
    "supplier": "SUPPLIER",
    "customer": "CUSTOMER",
}


async def create_ready_party(
    db: AsyncSession,
    access: Access,
    settings: Settings,
    record: BulkRecord,
    mode: str,
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The caller owns the aggregate savepoint, receipts, effects and final commit."""
    if (
        mode != "CREATE_ONLY"
        or record.action not in {"CREATE", "AUTO"}
        or record.target.model_dump(exclude_defaults=True)
        or record.clear_fields
    ):
        raise ConflictError("ready customer/supplier imports only create new identities")
    body = ReadyPartyCreate.model_validate(resolve_references(record.data, results))
    await setup_lock(db, access)
    party = await mutate_master(
        db,
        access,
        BY_NAME["party"],
        "create",
        PartyCreate.model_validate(body.model_dump(exclude=set(OPENING_FIELDS))),
        settings,
    )
    party = await mutate_master(
        db,
        access,
        BY_NAME["party"],
        "activate",
        ExpectedVersion(expected_version=party.row_version),
        settings,
        party.id,
    )
    role = await mutate_master(
        db,
        access,
        BY_NAME["party_role"],
        "create",
        PartyRoleCreate(party_id=party.id, role=READY_PARTY_ROLES[record.resource]),
        settings,
    )
    role = await mutate_master(
        db,
        access,
        BY_NAME["party_role"],
        "activate",
        ExpectedVersion(expected_version=role.row_version),
        settings,
        role.id,
    )
    await db.flush()
    # The ledger account is never optional. An opening balance is: when given it is held as one
    # line for the opening declaration against that account, and it never posts.
    opening = await stage(
        db, access, settings, party_id=party.id, role=READY_PARTY_ROLES[record.resource], body=body
    )
    return {"id": str(party.id), "party_id": str(party.id), "party_role_id": str(role.id)} | opening
