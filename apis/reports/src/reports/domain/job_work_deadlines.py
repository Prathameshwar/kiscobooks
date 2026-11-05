"""Review-only projection of owner-supplied job-work time-limit evidence.

The Accounting movement owner must resolve residual quantities and an effective-
dated statutory rule must supply the deadline. This module cannot issue invoices,
post tax, or infer that an absent movement means a return did not happen.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class JobWorkDeadlineEvidence:
    source_line_id: UUID
    original_challan_id: UUID
    policy_version_id: UUID
    material_category: Literal["INPUT", "CAPITAL_GOOD", "EXEMPT_TOOL"]
    origin_kind: Literal["PRINCIPAL_DISPATCH", "DIRECT_WORKER_RECEIPT"]
    origin_date: date
    as_of_date: date
    remaining_quantity: Decimal
    deadline: date | None
    final_clearance_date: date | None


@dataclass(frozen=True, slots=True)
class JobWorkDeadlineAssessment:
    source_line_id: UUID
    policy_version_id: UUID
    status: Literal["CLOSED", "EXEMPT", "WITHIN_LIMIT", "REVIEW_REQUIRED"]
    remaining_quantity: Decimal
    deadline: date | None


def assess(evidence: JobWorkDeadlineEvidence) -> JobWorkDeadlineAssessment:
    """Classify a complete owner residual; a late case only requests review."""
    if evidence.material_category not in {"INPUT", "CAPITAL_GOOD", "EXEMPT_TOOL"}:
        raise ValidationFailedError("unsupported job-work material category")
    if evidence.origin_kind not in {"PRINCIPAL_DISPATCH", "DIRECT_WORKER_RECEIPT"}:
        raise ValidationFailedError("unsupported job-work origin kind")
    if evidence.as_of_date < evidence.origin_date:
        raise ValidationFailedError("assessment cannot precede the movement origin")
    try:
        remaining = exact_decimal(evidence.remaining_quantity)
    except MoneyError as exc:
        raise ValidationFailedError("job-work residual must be exactly representable") from exc
    if remaining < 0:
        raise ValidationFailedError("job-work residual cannot be negative")
    if remaining == 0 and evidence.final_clearance_date is None:
        raise ValidationFailedError("cleared material requires final clearance date")
    if evidence.final_clearance_date is not None and not (
        evidence.origin_date <= evidence.final_clearance_date <= evidence.as_of_date
    ):
        raise ValidationFailedError("final clearance date must be within the observed interval")
    if remaining > 0 and evidence.final_clearance_date is not None:
        raise ValidationFailedError("unresolved material cannot have a final clearance date")
    if evidence.material_category == "EXEMPT_TOOL":
        if evidence.deadline is not None:
            raise ValidationFailedError("exempt tools must not receive a time-limit deadline")
        status: Literal["CLOSED", "EXEMPT", "WITHIN_LIMIT", "REVIEW_REQUIRED"] = (
            "CLOSED" if remaining == 0 else "EXEMPT"
        )
    else:
        if evidence.deadline is None or evidence.deadline <= evidence.origin_date:
            raise ValidationFailedError("a statutory deadline after origin is required")
        late_clearance = (
            evidence.final_clearance_date is not None
            and evidence.final_clearance_date > evidence.deadline
        )
        status = (
            "REVIEW_REQUIRED"
            if late_clearance or (remaining > 0 and evidence.as_of_date > evidence.deadline)
            else "CLOSED"
            if remaining == 0
            else "WITHIN_LIMIT"
        )
    return JobWorkDeadlineAssessment(
        evidence.source_line_id,
        evidence.policy_version_id,
        status,
        remaining,
        evidence.deadline,
    )
