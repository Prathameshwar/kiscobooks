"""Pure regulated-goods decisions; reviewed source is never user input."""

import datetime as dt
import uuid
from dataclasses import dataclass

from billing_platform.errors import ConflictError


@dataclass(frozen=True)
class RegulatorySelection:
    classification_id: uuid.UUID
    source_version: int
    item_id: uuid.UUID
    valid_from: dt.date
    valid_to: dt.date | None
    product_kind: str
    licence_class: str | None
    prescription_schedule: str | None
    source_sha256: str
    food_category_code: str | None = None


@dataclass(frozen=True)
class DealerLicenceSelection:
    licence_id: uuid.UUID
    source_version: int
    party_id: uuid.UUID
    address_id: uuid.UUID
    licence_form: str
    licence_number: str
    valid_from: dt.date
    valid_to: dt.date | None
    source_sha256: str


def required_dealer_form(operation: str, licence_class: str) -> str:
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


def require_dealer_licence(
    selected: DealerLicenceSelection | None,
    *,
    party_id: uuid.UUID,
    address_id: uuid.UUID,
    operation: str,
    licence_class: str,
    supply_date: dt.date,
) -> DealerLicenceSelection:
    required = required_dealer_form(operation, licence_class)
    if (
        selected is None
        or selected.party_id != party_id
        or selected.address_id != address_id
        or selected.licence_form != required
        or selected.valid_from > supply_date
        or (selected.valid_to is not None and selected.valid_to < supply_date)
    ):
        raise ConflictError("reviewed counterparty dealer licence is unavailable")
    return selected


def require_supported_medicine(
    selected: RegulatorySelection | None, *, item_id: uuid.UUID, supply_date: dt.date
) -> RegulatorySelection:
    if selected is None or selected.item_id != item_id:
        raise ConflictError("reviewed medicine classification is unavailable")
    if selected.valid_from > supply_date or (
        selected.valid_to is not None and selected.valid_to < supply_date
    ):
        raise ConflictError("reviewed medicine classification does not cover supply date")
    if selected.product_kind != "MEDICINE":
        raise ConflictError("item is not classified as medicine")
    if selected.licence_class is None or selected.prescription_schedule is None:
        raise ConflictError("medicine classification is incomplete")
    if selected.licence_class == "SCHEDULE_X" or selected.prescription_schedule == "X":
        raise ConflictError("Schedule X is unavailable until its separate controls are enabled")
    return selected
