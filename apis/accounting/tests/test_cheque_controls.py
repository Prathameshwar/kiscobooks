"""B44 cheque master preflight and append-only leaf transition rules."""

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7

from accounting.domain.cheque_controls import ChequeBookRange, next_leaf_state, validate_book_range


def test_overlapping_ranges_for_same_company_and_account_are_refused():
    tenant, company, account = uuid7(), uuid7(), uuid7()
    old = ChequeBookRange(tenant, company, account, 100, 199)
    with pytest.raises(ConflictError, match="overlap"):
        validate_book_range(ChequeBookRange(tenant, company, account, 199, 250), (old,))
    validate_book_range(ChequeBookRange(tenant, company, account, 200, 250), (old,))
    validate_book_range(ChequeBookRange(tenant, uuid7(), account, 150, 250), (old,))
    validate_book_range(ChequeBookRange(tenant, company, uuid7(), 150, 250), (old,))
    validate_book_range(ChequeBookRange(uuid7(), company, account, 150, 250), (old,))


def test_invalid_range_and_voided_leaf_reuse_are_refused():
    with pytest.raises(ValidationFailedError, match="range"):
        validate_book_range(ChequeBookRange(uuid7(), uuid7(), uuid7(), 0, 3), ())
    with pytest.raises(ValidationFailedError, match="range"):
        validate_book_range(ChequeBookRange(uuid7(), uuid7(), uuid7(), True, 3), ())
    assert next_leaf_state("AVAILABLE", "RESERVED") == "RESERVED"
    assert next_leaf_state("RESERVED", "ISSUED") == "ISSUED"
    assert next_leaf_state("ISSUED", "VOID") == "VOID"
    with pytest.raises(ConflictError, match="transition"):
        next_leaf_state("VOID", "AVAILABLE")
    with pytest.raises(ConflictError, match="transition"):
        next_leaf_state("CLEARED", "ISSUED")


def test_book_range_cannot_exceed_one_hundred_thousand_inclusive_leaves():
    with pytest.raises(ValidationFailedError, match="supported size"):
        validate_book_range(ChequeBookRange(uuid7(), uuid7(), uuid7(), 1, 100_001), ())
