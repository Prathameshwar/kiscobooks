"""Accounting-owned safe evidence; snapshots never retain personal or arbitrary values."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.audit_evidence import scalar
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from accounting.api.auth import Access
from accounting.events.audit_contract import audit_event
from accounting.financial_resources import FINANCIAL_RESOURCES
from accounting.models.masters import Record
from accounting.resources import RESOURCES, Resource

# Explicit vocabulary intersected with each resource's schema: no suffix-based PII guesses.
SAFE_FIELDS = frozenset(
    """
status kind nature country_code state_code base_currency currency currency_mode
head_id group_id parent_id party_id account_id payment_term_id commercial_type_id
fiscal_year_id fiscal_period_id journal_id reversal_of_id source_document_id
valid_from valid_to posting_date document_date start_date end_date due_date
amount amount_base base_amount net_amount gross_amount cumulative_amount
debit_base_amount credit_base_amount total_debit total_credit debit credit exchange_rate quantity
limit_amount overdue_tolerance overdue_days percentage rate rounding_limit
rounding_method inventory_affected sort_order template_version metadata_version
is_primary is_reserved is_revenue is_deemed_positive affects_gross_profit
nett_balances sub_ledger_behaviour used_for_calculation allocation_method
supply_kind code_system treatment itc_eligibility rcm_applicable assessable_inclusion
apportion_by rule_id
section_id deductee_type rate_percent no_pan_rate_percent single_transaction_threshold
aggregate_annual_threshold threshold_currency threshold_basis deductible pan_status
pan_identifier_id default_section_id amount_limit supersedes_id
""".split()
)

BANK_SAFE_FIELDS = frozenset(
    {
        "account_id",
        "currency",
        "revision",
        "amount",
        "cutoff_date",
        "status",
        "review_status",
        "mode",
        "match_window_days",
        "require_separate_reviewer",
        "statement_entry_id",
        "instrument_id",
        "session_id",
        "voucher_id",
        "reverses_id",
        "period_from",
        "period_to",
    }
)
_FIELDS = {
    spec.model: SAFE_FIELDS & spec.detail.model_fields.keys()
    for spec in (*RESOURCES, *FINANCIAL_RESOURCES)
}
_KEY = "accounting_audit_before"


@event.listens_for(Session, "before_flush")
def capture_before(session: Session, flush_context: Any, instances: Any) -> None:
    """Capture safe pre-flush values; domain commands remain the only emitters."""
    for row in session.new | session.dirty:
        fields = _FIELDS.get(type(row))
        if not fields:
            continue
        state = inspect(row)
        before = state.info.setdefault(_KEY, {})
        for name in fields:
            if name in before:
                continue
            history = state.attrs[name].history
            if row in session.new:
                before[name] = None
            elif history.deleted:
                before[name] = scalar(history.deleted[0])
            elif not history.has_changes() and name in state.dict:
                before[name] = scalar(state.dict[name])


@event.listens_for(Session, "after_soft_rollback")
def clear_rolled_back(session: Session, previous: Any) -> None:
    for row in session.identity_map.values():
        if type(row) in _FIELDS:
            state = inspect(row)
            assert state is not None
            state.info.pop(_KEY, None)


def changes(row: Record, fields: set[str], action: str) -> dict[str, Any]:
    state = inspect(row)
    before = state.info.pop(_KEY, {})
    allowed: set[str] | frozenset[str] = _FIELDS.get(type(row), set())
    result: dict[str, Any] = {}
    for key in sorted(fields):
        if key in allowed and (key in before or action == "create"):
            result[key] = {"from": before.get(key), "to": scalar(getattr(row, key))}
        else:
            result[key] = {"changed": True}
    # Currency is evidence of the unit, even when only the amount changed.
    if any(isinstance(getattr(row, key, None), Decimal) for key in fields & allowed):
        for key in ("currency", "base_currency"):
            if key in allowed and key not in result:
                value = scalar(getattr(row, key))
                result[key] = {"from": before.get(key, value), "to": value}
    return result


def access_event(
    db: AsyncSession,
    access: Access,
    spec: Resource,
    action: str,
    *,
    object_id: uuid.UUID | None = None,
    count: int | None = None,
) -> None:
    identity = object_id or uuid7()
    payload = audit_payload(
        action=audit_event(spec.name, action),
        category="access",
        entity_type="accounting." + spec.name,
        entity_id=identity,
        company_id=access.context.company_id,
        actor_user_id=access.actor.user_id,
    )
    payload["actor_type"] = "user"
    if count is not None:
        payload["context"] = {"count": count}
    emit(
        db,
        tenant_id=access.actor.tenant_id,
        aggregate_type="accounting." + spec.name,
        aggregate_id=identity,
        event_type=audit_event(spec.name, action),
        payload=payload,
    )
