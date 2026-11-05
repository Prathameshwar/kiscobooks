"""Physical identity normalization and prepared-lot validation, never balance arithmetic."""

import datetime as dt

from billing_platform.errors import ValidationFailedError
from voucher_execution.identifiers import normalized as normalized
from voucher_execution.identifiers import validate_identifier_inputs

from accounting.schemas.stock_tracking import IdentifierInput, TrackingSource


def validate_dates(
    source: TrackingSource, manufactured: dt.date | None, expires: dt.date | None
) -> None:
    if source.manufacture_date_required and manufactured is None:
        raise ValidationFailedError(
            "manufacture date is required",
            fields={"manufactured_on": "Required by the published inventory profile."},
        )
    if source.expiry_required and expires is None:
        raise ValidationFailedError(
            "expiry date is required",
            fields={"expires_on": "Required by the published inventory profile."},
        )
    if manufactured and expires and expires < manufactured:
        raise ValidationFailedError(
            "expiry date precedes manufacture date",
            fields={"expires_on": "Must be on or after manufacture."},
        )
    if manufactured and source.shelf_life_days is not None and expires:
        if (expires - manufactured).days > source.shelf_life_days:
            raise ValidationFailedError(
                "expiry exceeds the configured shelf life",
                fields={"expires_on": "Review the published shelf-life limit."},
            )


def validate_identifiers(
    source: TrackingSource, values: list[IdentifierInput]
) -> list[tuple[IdentifierInput, str, str]]:
    requirements = {row.identifier_type: row for row in source.requirements}
    return [
        (
            value,
            key,
            "COMPANY"
            if requirements[value.identifier_type].namespace_rule == "COMPANY"
            else str(source.item_id),
        )
        for value, key in validate_identifier_inputs(source.requirements, values)
    ]
