"""Stable opening conflict codes within the platform error envelope."""

from billing_platform.errors import ConflictError


class OpeningConflictError(ConflictError):
    def __init__(self, message: str) -> None:
        code, separator, explanation = message.partition(": ")
        if separator and code in {
            "OPENING_DATE_MISMATCH",
            "OPENING_ALREADY_RECORDED",
            "EXECUTION_UNCONFIRMED",
            "REVIEW_STALE",
            "OPENING_FINALIZED",
            "OPENING_NOT_FINALIZED",
            "CORRECTION_HAS_DEPENDENCIES",
            "PRODUCT_NOT_ACTIVE",
            "UNIT_CONVERSION_INVALID",
            "OPENING_COHORT_ORDER",
        }:
            self.code = code.lower()
            message = explanation
        super().__init__(message)
