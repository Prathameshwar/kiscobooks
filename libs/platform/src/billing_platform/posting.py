"""One local posting guard; owners supply a period read under their transaction lock.

This module performs no network I/O and owns no ledger policy. A consumer must resolve
exactly one period from its authoritative local store before calling the guard.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor


@dataclass(frozen=True, slots=True)
class PostingPeriod:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    start_date: dt.date
    end_date: dt.date
    status: str


def assert_postable(
    company_id: uuid.UUID,
    posting_date: dt.date,
    actor: Actor,
    *,
    context: CompanyContext,
    period: PostingPeriod | None,
    now: dt.datetime | None = None,
) -> PostingPeriod:
    context.assert_current(actor, company_id)
    target = ScopePath(company_id=company_id)
    finance = context.finance
    if finance is None:
        raise ConflictError("authoritative financial company context is required")
    if actor.impersonation_id is not None:
        raise PermissionDeniedError("support sessions cannot post")
    if not finance.company_active:
        raise ConflictError("company is not active")
    if posting_date < finance.books_begin_date:
        raise ValidationFailedError("posting date precedes books begin date")
    if period is None:
        raise ConflictError("posting date has no generated fiscal period")
    if period.tenant_id != actor.tenant_id or period.company_id != company_id:
        raise PermissionDeniedError("fiscal period has a different scope")
    if not period.start_date <= posting_date <= period.end_date:
        raise ConflictError("posting date is outside the resolved fiscal period")
    if period.status == "OPEN":
        actor.require_scope("period.post", target=target)
    elif period.status == "SOFT_CLOSED":
        actor.require_scope("period.post_adjustment", target=target)
    else:
        raise ConflictError("fiscal period does not permit posting")
    limit = finance.backdated_posting_limit_days
    instant = now or dt.datetime.now(dt.UTC)
    if instant.tzinfo is None:
        raise ValueError("posting guard requires an aware current instant")
    today = instant.astimezone(ZoneInfo(finance.timezone)).date()
    if (
        limit is not None
        and (today - posting_date).days > limit
        and not actor.allows_scope("period.post_adjustment", target=target)
    ):
        raise PermissionDeniedError("posting date exceeds the backdated posting limit")
    return period
