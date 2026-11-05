"""India dealer licence-form matrix; H/H1 is a separate prescription axis."""

from typing import Literal

from billing_platform.errors import ConflictError

LicenceClass = Literal["OTHER_THAN_C_C1_X", "C_C1_EXCLUDING_X", "SCHEDULE_X"]
Operation = Literal["RETAIL", "WHOLESALE"]


def required_form(operation: Operation, licence_class: LicenceClass) -> str:
    if licence_class == "SCHEDULE_X":
        raise ConflictError("Schedule X dealer controls are not enabled")
    forms = {
        ("RETAIL", "OTHER_THAN_C_C1_X"): "20",
        ("RETAIL", "C_C1_EXCLUDING_X"): "21",
        ("WHOLESALE", "OTHER_THAN_C_C1_X"): "20B",
        ("WHOLESALE", "C_C1_EXCLUDING_X"): "21B",
    }
    try:
        return forms[(operation, licence_class)]
    except KeyError as exc:
        raise ConflictError("unsupported dealer licence operation or class") from exc
