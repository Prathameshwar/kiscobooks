"""Expose shared native entry controls through the service error envelope."""

import datetime as dt

from billing_platform.errors import ValidationFailedError
from voucher_execution.money import MoneyInput, MoneyPolicy, validate_entry_controls


def validate_money(
    body: MoneyInput, policy: MoneyPolicy, *, kind: str, profile: str, posting_date: dt.date | None
) -> None:
    try:
        validate_entry_controls(body, policy, kind=kind, profile=profile, posting_date=posting_date)
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
