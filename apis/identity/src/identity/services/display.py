"""One owner resolution path for browser and frozen report presentation."""

from typing import Any

from identity.models import Company, User
from identity.schemas.company import DisplayConfig


def resolve_display(company: Company, user: User | None) -> dict[str, Any]:
    values = DisplayConfig.model_validate(company).model_dump()
    if user is not None:
        for key in (
            "locale",
            "timezone",
            "date_format",
            "datetime_format",
            "digit_grouping",
            "currency_display",
        ):
            value = getattr(user, key)
            if value is not None:
                values[key] = value
    return values
