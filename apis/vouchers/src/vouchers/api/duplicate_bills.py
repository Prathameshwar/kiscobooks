"""Read-only duplicate supplier-bill lookup; no state, money or audit mutation."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access, access
from vouchers.api.common import ERRORS, session, unique_query
from vouchers.schemas.duplicate_bills import DuplicateBillList, DuplicateBillQuery
from vouchers.tasks.duplicate_bills import find, require_readable

router = APIRouter(
    prefix="/v1/companies/{company_id}", responses=ERRORS, dependencies=[Depends(unique_query)]
)


@router.get("/vouchers/duplicate-bills", response_model=DuplicateBillList)
async def duplicate_bills(
    company_id: uuid.UUID,
    query: Annotated[DuplicateBillQuery, Query()],
    response: Response,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> DuplicateBillList:
    """Other live Purchase bills from this supplier with this bill number, in the fiscal year.

    Give the supplier ``party_id``, the payable ledger ``party_account_id``, or both; a bill
    matches on either. Matching ignores case, runs of whitespace, dash variants, invisible
    characters and punctuation around the number. A cancelled, rejected or reversed bill is not a
    match, and neither is the voucher named in ``exclude_voucher_id``. At most five rows;
    ``truncated`` is true when the search stopped at its ceiling before reading every bill.
    """
    require_readable(current)
    response.headers["Cache-Control"] = "no-store"
    scan = await find(
        db,
        current,
        party_ids=() if query.party_id is None else (query.party_id,),
        party_account_id=query.party_account_id,
        bill_reference=query.bill_reference,
        document_date=query.document_date,
        exclude_voucher_id=query.exclude_voucher_id,
    )
    return DuplicateBillList(items=scan.items, truncated=scan.truncated)
