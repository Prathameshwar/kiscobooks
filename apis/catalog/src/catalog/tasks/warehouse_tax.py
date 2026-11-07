"""Company-owned registration references from the signed gateway preflight context."""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from billing_platform.company_context import CompanyContext
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor

from catalog.models.warehouses import Warehouse
from catalog.tasks.identity_source import IdentitySourceUnavailableError

_context: ContextVar[CompanyContext | None] = ContextVar("warehouse_tax_context", default=None)


@contextmanager
def request_context(value: CompanyContext | None) -> Iterator[None]:
    token = _context.set(value)
    try:
        yield
    finally:
        _context.reset(token)


def validate_registration(row: Warehouse, actor: Actor, *, today: dt.date) -> None:
    if row.tax_registration_id is None:
        return
    context = _context.get()
    if context is None:
        raise IdentitySourceUnavailableError("Company tax-registration context is unavailable")
    context.assert_current(actor, row.company_id)
    registration = next(
        (
            entry
            for entry in context.registrations
            if entry.get("id") == str(row.tax_registration_id)
        ),
        None,
    )
    message = (
        "Choose an active tax registration belonging to this company and warehouse jurisdiction"
    )
    valid = registration is not None
    if registration is not None:
        start, end = registration.get("valid_from"), registration.get("valid_to")
        valid &= isinstance(start, str) and start <= today.isoformat()
        valid &= end is None or (isinstance(end, str) and today.isoformat() <= end)
        valid &= (
            row.country_code is not None and registration.get("country_code") == row.country_code
        )
        jurisdiction = registration.get("jurisdiction_code")
        valid &= (
            jurisdiction is None
            or jurisdiction == row.country_code
            or jurisdiction == row.state_code
        )
    if not valid:
        raise ValidationFailedError(message, fields={"tax_registration_id": message})
