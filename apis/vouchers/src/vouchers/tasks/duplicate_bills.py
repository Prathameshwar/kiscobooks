"""Find a supplier's bill number already recorded in the company, within one fiscal year.

Only the revision a voucher currently stands on counts, so an earlier revision's number never
matches. Two bills are the same supplier's when they share the supplier party named in the header
or the payable ledger the bill posts to (a Purchase need not name a header party at all). Each key
is walked on its own, most recent first, in keyset batches, and references are compared in Python
after normalisation, which no collation does. The walk reads at most ``CANDIDATE_CEILING`` rows
per key; reaching it with rows left over is reported as ``truncated`` rather than hidden, and
submit treats that as a possible duplicate.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.documents import fiscal_start
from vouchers.domain.duplicate_bill import (
    BATCH_SIZE,
    CANDIDATE_CEILING,
    LIVE_STATUSES,
    MATCH_LIMIT,
    DuplicateSupplierBillError,
    normalize_bill_reference,
)
from vouchers.models import core as m
from vouchers.models.invoice import VoucherInvoiceDetail
from vouchers.schemas.duplicate_bills import DuplicateBill
from vouchers.tasks.access import authorize, denied

#: Fields the lookup filters on, orders by or returns. A read-deny on any of them closes the
#: lookup, as a denied field may not be filtered or searched on either (api-conventions).
GUARDED_FIELDS = {"parties", "invoice", "document_date", "status", "kind", "id"}

type Candidates = Select[Any]


@dataclass(frozen=True)
class DuplicateScan:
    """Matching bills, and whether the walk stopped at its ceiling with rows left unread."""

    items: list[DuplicateBill] = field(default_factory=list)
    truncated: bool = False


def require_readable(current: Access) -> None:
    authorize(current, "read")
    if denied(current, "vouchers.voucher", GUARDED_FIELDS, "read"):
        raise PermissionDeniedError("duplicate supplier bill fields are not readable")


def readable(current: Access) -> bool:
    try:
        require_readable(current)
    except PermissionDeniedError:
        return False
    return True


def candidates(
    tenant: uuid.UUID, company: uuid.UUID, year: dt.date, exclude: uuid.UUID | None
) -> Candidates:
    """Live Purchase bills of the fiscal year at their current revision, supplier not yet chosen."""
    revision = m.VoucherRevision
    statement = (
        select(
            m.Voucher.id,
            m.Voucher.status,
            revision.document_date,
            VoucherInvoiceDetail.bill_reference,
            revision.revision_number,
        )
        .select_from(revision)
        .join(
            m.Voucher,
            and_(
                m.Voucher.tenant_id == revision.tenant_id,
                m.Voucher.company_id == revision.company_id,
                m.Voucher.id == revision.voucher_id,
                m.Voucher.current_revision == revision.revision_number,
            ),
        )
        .join(
            m.VoucherType,
            and_(
                m.VoucherType.tenant_id == m.Voucher.tenant_id,
                m.VoucherType.company_id == m.Voucher.company_id,
                m.VoucherType.id == m.Voucher.type_id,
            ),
        )
        .join(
            VoucherInvoiceDetail,
            and_(
                VoucherInvoiceDetail.tenant_id == revision.tenant_id,
                VoucherInvoiceDetail.company_id == revision.company_id,
                VoucherInvoiceDetail.revision_id == revision.id,
            ),
        )
        .where(
            revision.tenant_id == tenant,
            revision.company_id == company,
            m.VoucherType.kind == "PURCHASE",
            m.Voucher.status.in_(LIVE_STATUSES),
            revision.fiscal_start_date == year,
        )
        .distinct()
    )
    if exclude is not None:
        statement = statement.where(m.Voucher.id != exclude)
    return statement


def of_supplier(
    statement: Candidates, tenant: uuid.UUID, company: uuid.UUID, party_id: uuid.UUID
) -> Candidates:
    """Restrict to bills naming this party as SUPPLIER in the header (``ix_voucher_party_list``)."""
    return statement.join(
        m.VoucherParty,
        and_(
            m.VoucherParty.tenant_id == m.VoucherRevision.tenant_id,
            m.VoucherParty.company_id == m.VoucherRevision.company_id,
            m.VoucherParty.revision_id == m.VoucherRevision.id,
        ),
    ).where(
        m.VoucherParty.tenant_id == tenant,
        m.VoucherParty.company_id == company,
        m.VoucherParty.party_id == party_id,
        m.VoucherParty.role == "SUPPLIER",
    )


def of_ledger(statement: Candidates, ledger_id: uuid.UUID) -> Candidates:
    """Restrict to bills that post their payable to this ledger, whatever the header names."""
    return statement.where(VoucherInvoiceDetail.party_account_id == ledger_id)


async def walk(
    db: AsyncSession, statement: Candidates, wanted: str, limit: int
) -> tuple[list[DuplicateBill], bool]:
    """Keyset-walk one key's bills, newest first, comparing references until ``limit`` match.

    Returns the matches and whether the ceiling was reached with unread rows left. Batches are
    ordered ``(document_date, id)`` descending, the voucher id being the tie-break, so no row is
    skipped or read twice across a batch boundary.
    """
    revision = m.VoucherRevision
    ordered = statement.order_by(revision.document_date.desc(), m.Voucher.id.desc())
    found: list[DuplicateBill] = []
    read = 0
    last: Any = None
    while True:
        # One row past the ceiling tells "stopped exactly at the end" from "rows were left".
        size = min(BATCH_SIZE, CANDIDATE_CEILING - read + 1)
        page = ordered
        if last is not None:
            page = page.where(
                or_(
                    revision.document_date < last.document_date,
                    and_(revision.document_date == last.document_date, m.Voucher.id < last.id),
                )
            )
        rows = (await db.execute(page.limit(size))).all()
        for row in rows:
            if read >= CANDIDATE_CEILING:
                return found, True
            read += 1
            if normalize_bill_reference(row.bill_reference) != wanted:
                continue
            found.append(
                DuplicateBill(
                    id=row.id,
                    status=row.status,
                    document_date=row.document_date,
                    bill_reference=row.bill_reference,
                    revision_number=row.revision_number,
                )
            )
            if len(found) >= limit:
                return found, False
        if len(rows) < size:
            return found, False
        last = rows[-1]


async def find(
    db: AsyncSession,
    current: Access,
    *,
    party_ids: Sequence[uuid.UUID] = (),
    party_account_id: uuid.UUID | None = None,
    bill_reference: str,
    document_date: dt.date,
    exclude_voucher_id: uuid.UUID | None = None,
    limit: int = MATCH_LIMIT,
) -> DuplicateScan:
    """Purchase bills of this supplier or payable ledger and fiscal year with this number.

    A bill matches when it names one of ``party_ids`` as its SUPPLIER or posts to
    ``party_account_id``; a bill matching both is returned once.
    """
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("active company calendar context is required")
    wanted = normalize_bill_reference(bill_reference)
    if not wanted:
        return DuplicateScan()
    year = fiscal_start(
        document_date, finance.fiscal_year_start_month, finance.fiscal_year_start_day
    )
    tenant, company = current.actor.tenant_id, current.context.company_id
    base = candidates(tenant, company, year, exclude_voucher_id)
    keys = [of_supplier(base, tenant, company, party) for party in dict.fromkeys(party_ids)]
    if party_account_id is not None:
        keys.append(of_ledger(base, party_account_id))
    matches: dict[uuid.UUID, DuplicateBill] = {}
    truncated = False
    for statement in keys:
        rows, cut = await walk(db, statement, wanted, limit)
        truncated = truncated or cut
        for row in rows:
            matches.setdefault(row.id, row)
    newest = sorted(matches.values(), key=lambda r: (r.document_date, r.id), reverse=True)
    return DuplicateScan(newest[:limit], truncated)


def refusal(current: Access, scan: DuplicateScan, reference: str) -> DuplicateSupplierBillError:
    """The 409 for an unacknowledged duplicate or an incomplete check.

    The envelope has no payload for rows, so the matches ride in its ``fields`` map as flat
    ``matches.<n>.<field>`` entries, and the first one is named in the message. A caller without
    the right to read vouchers is told only that the number is already recorded. An incomplete
    check with no match names no voucher: it says only that it could not be completed.
    """
    shown = reference.strip()
    incomplete = (
        "the duplicate check was incomplete, so older bills of this supplier were not compared; "
        if scan.truncated
        else ""
    )
    if not scan.items:
        return DuplicateSupplierBillError(
            f"supplier bill {shown}: {incomplete}acknowledge to submit it anyway"
        )
    if not readable(current):
        return DuplicateSupplierBillError(
            f"supplier bill {shown} is already recorded for this supplier; "
            f"{incomplete}acknowledge the duplicate to submit it anyway"
        )
    first = scan.items[0]
    fields: dict[str, str] = {}
    for index, row in enumerate(scan.items):
        prefix = f"matches.{index}."
        fields[prefix + "id"] = str(row.id)
        fields[prefix + "status"] = row.status
        fields[prefix + "document_date"] = row.document_date.isoformat()
        fields[prefix + "bill_reference"] = row.bill_reference
        fields[prefix + "revision_number"] = str(row.revision_number)
    return DuplicateSupplierBillError(
        f"supplier bill {shown} is already recorded for this supplier "
        f"(voucher {first.id}, {first.status}); {incomplete}"
        "acknowledge the duplicate to submit it anyway",
        fields=fields,
    )
