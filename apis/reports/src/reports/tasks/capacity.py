"""Stable capacity failures can be explained without exposing internal exceptions."""

from billing_platform.errors import ConflictError


class CapacityExceededError(ConflictError):
    code = "report_capacity_exceeded"
