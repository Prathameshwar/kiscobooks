"""One current revision per document; correlated filters never multiply counts."""

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import CursorCodec
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.schemas.day_book import DayBookPage, DayBookQuery
from vouchers.tasks.access import authorize, fingerprint


async def query(
    db: AsyncSession, current: Access, body: DayBookQuery, secret: bytes
) -> DayBookPage:
    authorize(current, "read")

    current.actor.require_scope(
        "report.read", target=ScopePath(company_id=current.context.company_id)
    )

    # A complete activity summary cannot expose values/counts over read-denied fields.

    if any(
        policy.get("access") == "read" and policy.get("effect") == "deny"
        for policy in current.context.policies
    ):
        raise PermissionDeniedError("Day Book requires readable contributing document fields")

    tenant, company = current.context.tenant_id, current.context.company_id

    voucher, revision, kind, assignment = (
        m.Voucher,
        m.VoucherRevision,
        m.VoucherType,
        m.VoucherNumberAssignment,
    )

    number = func.coalesce(assignment.display_number, "")

    statement = (
        select(
            voucher.id,
            revision.id.label("revision_id"),
            revision.document_date.label("date"),
            number.label("number"),
            kind.kind,
            kind.id.label("type_id"),
            kind.code.label("type_code"),
            kind.name.label("type_name"),
            kind.profile,
            voucher.status,
            revision.narration,
            revision.currency,
        )
        .join(
            revision,
            and_(
                revision.tenant_id == tenant,
                revision.company_id == company,
                revision.voucher_id == voucher.id,
                revision.revision_number == voucher.current_revision,
            ),
        )
        .join(
            kind,
            and_(kind.tenant_id == tenant, kind.company_id == company, kind.id == voucher.type_id),
        )
        .outerjoin(
            assignment,
            and_(
                assignment.tenant_id == tenant,
                assignment.company_id == company,
                assignment.revision_id == revision.id,
            ),
        )
        .where(
            voucher.tenant_id == tenant,
            voucher.company_id == company,
            revision.document_date >= body.date_from,
            revision.document_date <= body.date_to,
        )
    )

    if body.kinds:
        statement = statement.where(kind.kind.in_(body.kinds))

    for field, value in (
        (voucher.type_id, body.type_id),
        (voucher.status, body.status),
        (revision.currency, body.currency),
    ):
        if value is not None:
            statement = statement.where(field == value)

    if body.party_id:
        statement = statement.where(
            select(m.VoucherParty.id)
            .where(
                m.VoucherParty.tenant_id == tenant,
                m.VoucherParty.company_id == company,
                m.VoucherParty.revision_id == revision.id,
                m.VoucherParty.party_id == body.party_id,
            )
            .exists()
        )

    if body.q.strip():
        text = body.q.strip()

        statement = statement.where(
            or_(
                number.contains(text, autoescape=True),
                revision.narration.contains(text, autoescape=True),
                kind.name.contains(text, autoescape=True),
            )
        )

    clauses = []

    for condition in body.conditions:
        column = {"number": number, "narration": revision.narration, "kind": kind.kind}[
            condition.field
        ]

        clause = (
            column == condition.value
            if condition.operator == "equals"
            else column.contains(condition.value, autoescape=True)
        )

        clauses.append(~clause if condition.operator == "not_contains" else clause)

    if clauses:
        statement = statement.where(and_(*clauses) if body.match == "ALL" else or_(*clauses))

    summary = None

    if body.include_summary:
        counts = (
            await db.execute(
                statement.with_only_columns(
                    voucher.status,
                    kind.kind,
                    func.count(voucher.id),
                    maintain_column_froms=True,
                ).group_by(voucher.status, kind.kind)
            )
        ).all()

        statuses: dict[str, int] = defaultdict(int)

        kinds: dict[str, int] = defaultdict(int)

        for status, code, count in counts:
            statuses[status] += count

            kinds[code] += count

        summary = {
            "voucher_count": sum(statuses.values()),
            "by_status": dict(statuses),
            "by_kind": dict(kinds),
        }

    codec = CursorCodec(
        secret,
        context="day-book:"
        + fingerprint(current)
        + ":"
        + body.model_dump_json(exclude={"cursor", "include_summary"}),
    )

    order_column = number if body.sort == "number" else revision.document_date

    descending = body.sort == "-date"

    if body.cursor:
        try:
            position = codec.decode(body.cursor)

            last_id = uuid.UUID(position["id"])

            last = (
                position["value"]
                if body.sort == "number"
                else dt.date.fromisoformat(position["value"])
            )

        except (KeyError, ValueError, TypeError) as exc:
            raise ValidationFailedError("invalid Day Book cursor") from exc

        statement = statement.where(
            or_(
                order_column < last if descending else order_column > last,
                and_(
                    order_column == last,
                    voucher.id < last_id if descending else voucher.id > last_id,
                ),
            )
        )

    rows = (
        (
            await db.execute(
                statement.order_by(
                    order_column.desc() if descending else order_column,
                    voucher.id.desc() if descending else voucher.id,
                ).limit(body.limit + 1)
            )
        )
        .mappings()
        .all()
    )

    selected = rows[: body.limit]

    more = len(rows) > body.limit

    cursor = None

    if more:
        tail = selected[-1]

        cursor = codec.encode(
            {
                "id": str(tail["id"]),
                "value": tail["number"] if body.sort == "number" else tail["date"].isoformat(),
            }
        )

    names: dict[uuid.UUID, list[str]] = defaultdict(list)

    try:
        current.actor.require_scope("accounting.party.read", target=ScopePath(company_id=company))

        parties_readable = True

    except PermissionDeniedError:
        parties_readable = False

    if selected and parties_readable:
        # One bounded batch for the visible page; no N+1 reads or list fan-out.

        labels = (
            await db.execute(
                select(
                    m.VoucherParty.revision_id, m.VoucherMasterEvidence.facts["name"].as_string()
                )
                .join(
                    m.VoucherMasterEvidence,
                    and_(
                        m.VoucherMasterEvidence.tenant_id == tenant,
                        m.VoucherMasterEvidence.company_id == company,
                        m.VoucherMasterEvidence.owner == "accounting",
                        m.VoucherMasterEvidence.entity_type == "party",
                        m.VoucherMasterEvidence.source_id == m.VoucherParty.party_id,
                    ),
                )
                .where(
                    m.VoucherParty.tenant_id == tenant,
                    m.VoucherParty.company_id == company,
                    m.VoucherParty.revision_id.in_([row["revision_id"] for row in selected]),
                )
                .order_by(m.VoucherParty.role, m.VoucherParty.id)
            )
        ).all()

        for revision_id, name in labels:
            if isinstance(name, str) and name not in names[revision_id]:
                names[revision_id].append(name)

    items: list[dict[str, Any]] = [
        dict(row)
        | {"voucher_id": row["id"], "particulars": ", ".join(names[row["revision_id"]]) or "—"}
        for row in selected
    ]

    return DayBookPage.model_validate(
        {
            "items": items,
            "summary": summary,
            "page": {"limit": body.limit, "next_cursor": cursor, "has_more": more},
            "observed_at": dt.datetime.now(dt.UTC),
        }
    )
