"""India's GST state identifiers come from the committed statutory seed mapping."""

from collections.abc import Mapping
from functools import cache
from types import MappingProxyType

from billing_platform.reference import load


@cache
def gst_state_codes() -> Mapping[str, str]:
    return MappingProxyType(
        {
            row["code"]: row["tax_jurisdiction_code"]
            for row in load("state")
            if row["country_code"] == "IN"
        }
    )
