"""Cheque-book/leaf rule checks; no financial posting or print side effect."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from billing_platform.errors import ConflictError, ValidationFailedError


@dataclass(frozen=True, slots=True)
class ChequeBookRange:
    tenant_id: UUID
    company_id: UUID
    bank_account_id: UUID
    first_leaf: int
    last_leaf: int


LeafState = Literal[
    "AVAILABLE", "RESERVED", "ISSUED", "PRESENTED", "CLEARED", "DISHONOURED", "VOID"
]


def validate_book_range(candidate: ChequeBookRange, existing: tuple[ChequeBookRange, ...]) -> None:
    """Preflight only; native unique/range locking is required at commit."""
    if (
        type(candidate.first_leaf) is not int
        or type(candidate.last_leaf) is not int
        or candidate.first_leaf <= 0
        or candidate.last_leaf < candidate.first_leaf
    ):
        raise ValidationFailedError("invalid cheque-book leaf range")
    if candidate.last_leaf - candidate.first_leaf >= 100_000:
        raise ValidationFailedError("cheque-book leaf range exceeds the supported size")
    for prior in existing:
        if (
            prior.tenant_id == candidate.tenant_id
            and prior.company_id == candidate.company_id
            and prior.bank_account_id == candidate.bank_account_id
            and candidate.first_leaf <= prior.last_leaf
            and prior.first_leaf <= candidate.last_leaf
        ):
            raise ConflictError("cheque-book leaf ranges overlap")


def next_leaf_state(current: LeafState, action: LeafState) -> LeafState:
    allowed: dict[LeafState, frozenset[LeafState]] = {
        "AVAILABLE": frozenset({"RESERVED", "VOID"}),
        "RESERVED": frozenset({"ISSUED", "AVAILABLE", "VOID"}),
        "ISSUED": frozenset({"PRESENTED", "VOID"}),
        "PRESENTED": frozenset({"CLEARED", "DISHONOURED"}),
        "DISHONOURED": frozenset({"PRESENTED", "VOID"}),
        "CLEARED": frozenset(),
        "VOID": frozenset(),
    }
    if action not in allowed.get(current, frozenset()):
        raise ConflictError("cheque leaf transition is not allowed")
    return action
