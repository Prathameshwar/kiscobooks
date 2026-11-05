"""Fixed internal account packs selected from signed company facts, never user payloads."""

from __future__ import annotations

import base64
import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from billing_platform.errors import ValidationFailedError

from accounting.domain.rules import regime_permits
from accounting.domain.voucher_tax import bare_state
from accounting.seeds.templates import GROUPS

type Group = tuple[str, str, str, str | None]
type Account = tuple[str, str, str, str]


@dataclass
class DefaultAccounts:
    key: str
    accounts: list[Account]
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    # account code -> existing posting-purpose vocabulary
    mappings: dict[str, str] = field(default_factory=dict)
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    def groups(self) -> list[Group]:
        catalogue = [*GROUPS, ("TAX_RECOVERABLE", "Tax Recoverables", "ASSET", "CURRENT_ASSETS")]
        parents = {code: parent for code, _, _, parent in catalogue}
        required = {account[2] for account in self.accounts}
        for code in tuple(required):
            while (parent := parents[code]) is not None:
                required.add(parent)
                code = parent
        return [group for group in catalogue if group[0] in required]


def applicable_accounts(
    registrations: tuple[dict[str, Any], ...],
    features: frozenset[str],
    books_begin: dt.date,
    today: dt.date,
    utgst_states: frozenset[str],
) -> list[DefaultAccounts]:
    packs = []
    if "inventory" in features:
        packs.append(
            DefaultAccounts(
                "defaults.inventory",
                [("COST_OF_GOODS", "Cost of Goods Sold", "DIRECT_EXPENSES", "GENERAL")],
                mappings={"COST_OF_GOODS": "COST_OF_GOODS"},
                valid_from=books_begin,
            )
        )
    for duty in ("TDS", "TCS"):
        if duty.lower() not in features:
            continue
        pack = DefaultAccounts("defaults." + duty.lower(), [], valid_from=books_begin)
        for suffix, purpose, group in (
            ("PAYABLE", "OUTPUT_PAYABLE", "TAX_PAYABLE"),
            ("RECEIVABLE", "INPUT_RECOVERABLE", "TAX_RECOVERABLE"),
        ):
            code = duty + "_" + suffix
            pack.accounts.append((code, duty + " " + suffix.title(), group, "TAX"))
            pack.profiles[code] = {
                "scheme": "OTHER",
                "duty_type": duty,
                "component": "OTHER",
                "purpose": purpose,
                "company_registration_id": None,
            }
            pack.mappings[code] = code
        packs.append(pack)
    for registration in registrations:
        system, regime = registration.get("tax_system"), registration.get("regime")
        if system not in {"gst_in", "vat_gb", "vat_eu", "vat_ae", "vat_sa"}:
            continue
        try:
            identifier = uuid.UUID(registration["id"])
            start = dt.date.fromisoformat(registration["valid_from"])
            end = (
                dt.date.fromisoformat(registration["valid_to"])
                if registration.get("valid_to")
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationFailedError("company registration validity is unavailable") from exc
        if end is not None and end < max(today, books_begin, start):
            continue
        suffix = base64.b32encode(identifier.bytes).decode().rstrip("=")
        gst = system == "gst_in"
        if gst:
            if regime not in {
                "regular",
                "composition",
                "sez_unit",
                "sez_developer",
                "casual_taxable_person",
            }:
                continue
            state = bare_state(registration.get("jurisdiction_code"))
            if state is None:
                raise ValidationFailedError("GST registration jurisdiction is unavailable")
            local = "UTGST" if state in utgst_states else "SGST"
            components: tuple[str, ...] = ("CGST", local, "IGST", "CESS")
            directions = []
            if regime_permits("RECOVER", "gst_in", str(regime)):
                directions.extend(["INPUT", "PENDING"])
            if regime_permits("CHARGE", "gst_in", str(regime)):
                directions.append("OUTPUT")
            if "reverse_charge" in features:
                directions.append("RCM")
        else:
            if regime not in {
                "standard",
                "cash_accounting",
                "annual_accounting",
                "flat_rate",
                "margin_scheme",
            }:
                continue
            components = ("VAT",)
            directions = ["OUTPUT"]
            if regime in {"standard", "cash_accounting", "annual_accounting"}:
                directions.append("INPUT")
        if not directions:
            continue
        pack = DefaultAccounts(
            # Keep all UUID bits while fitting the 60-character installation key.
            "defaults.tax." + suffix + "." + "".join(d[0] for d in directions),
            [],
            valid_from=max(books_begin, start),
            valid_to=end,
        )
        for direction in directions:
            purpose = {
                "INPUT": "INPUT_RECOVERABLE",
                "OUTPUT": "OUTPUT_PAYABLE",
                "PENDING": "INPUT_PENDING",
                "RCM": "RCM_PAYABLE",
            }[direction]
            group = "TAX_RECOVERABLE" if direction in {"INPUT", "PENDING"} else "TAX_PAYABLE"
            for component in components:
                code = f"{direction}_{component}_{suffix}"
                pack.accounts.append((code, f"{direction.title()} {component}", group, "TAX"))
                pack.profiles[code] = {
                    "company_registration_id": identifier,
                    "scheme": "GST_IN" if gst else "VAT",
                    "duty_type": "GST" if gst else "VAT",
                    "component": component,
                    "purpose": purpose,
                }
                if gst:
                    pack.mappings[code] = f"{direction}_{component}"
        # A clearing ledger is not a fabricated bank or tax-rate configuration.
        control = "GST" if gst else "VAT"
        pack.accounts.append(
            (f"{control}_PAYMENT_{suffix}", f"{control} Payment Control", "TAX_PAYABLE", "GENERAL")
        )
        packs.append(pack)
    return packs
