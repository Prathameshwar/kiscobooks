"""B40 review-only cases based on complete owner residuals and dated policy."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from reports.domain.job_work_deadlines import JobWorkDeadlineEvidence, assess


def evidence() -> JobWorkDeadlineEvidence:
    return JobWorkDeadlineEvidence(
        uuid7(),
        uuid7(),
        uuid7(),
        "INPUT",
        "PRINCIPAL_DISPATCH",
        date(2024, 4, 1),
        date(2025, 4, 1),
        Decimal("3.0000"),
        date(2025, 4, 1),
        None,
    )


def test_deadline_is_inclusive_then_residual_is_review_only():
    original = evidence()
    assert assess(original).status == "WITHIN_LIMIT"
    late = assess(replace(original, as_of_date=date(2025, 4, 2)))
    assert late.status == "REVIEW_REQUIRED"
    assert late.source_line_id == original.source_line_id
    assert late.policy_version_id == original.policy_version_id
    assert late.remaining_quantity == Decimal("3.0000")
    closed = replace(
        original,
        as_of_date=date(2025, 4, 2),
        remaining_quantity=Decimal(0),
        final_clearance_date=date(2025, 4, 1),
    )
    assert assess(closed).status == "CLOSED"
    late_clearance = replace(closed, final_clearance_date=date(2025, 4, 2))
    assert assess(late_clearance).status == "REVIEW_REQUIRED"


def test_direct_worker_origin_and_exempt_tools_are_explicit():
    original = evidence()
    assert assess(replace(original, origin_kind="DIRECT_WORKER_RECEIPT")).status == "WITHIN_LIMIT"
    exempt = replace(
        original, material_category="EXEMPT_TOOL", deadline=None, as_of_date=date(2030, 1, 1)
    )
    assert assess(exempt).status == "EXEMPT"


def test_missing_policy_deadline_and_invalid_residual_refuse_a_case():
    original = evidence()
    with pytest.raises(ValidationFailedError, match="deadline"):
        assess(replace(original, deadline=None))
    with pytest.raises(ValidationFailedError, match="negative"):
        assess(replace(original, remaining_quantity=Decimal("-1")))
    with pytest.raises(ValidationFailedError, match="exactly representable"):
        assess(replace(original, remaining_quantity=Decimal("1.00001")))
    with pytest.raises(ValidationFailedError, match="precede"):
        assess(replace(original, as_of_date=date(2024, 3, 31)))
    with pytest.raises(ValidationFailedError, match="final clearance date"):
        assess(replace(original, remaining_quantity=Decimal(0)))
