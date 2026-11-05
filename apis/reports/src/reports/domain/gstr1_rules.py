"""Dated GSTR-1 field/table rules verified against the GST Portal guide."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from reports.domain.gstr3b import ELIGIBLE_REGIMES, period_bounds

RULE_VERSION = "GSTR1_2025_10"
FIRST_PERIOD = dt.date(2025, 10, 1)
STATES = frozenset(
    {
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "23",
        "24",
        "26",
        "27",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "97",
    }
)
UQC = frozenset(
    {
        "BAG",
        "BAL",
        "BDL",
        "BKL",
        "BOU",
        "BOX",
        "BTL",
        "BUN",
        "CAN",
        "CBM",
        "CCM",
        "CMS",
        "CTN",
        "DOZ",
        "DRM",
        "GGK",
        "GMS",
        "GRS",
        "GYD",
        "KGS",
        "KLR",
        "KME",
        "LTR",
        "MTR",
        "MTS",
        "NOS",
        "PAC",
        "PCS",
        "PRS",
        "QTL",
        "ROL",
        "SET",
        "SQF",
        "SQM",
        "SQY",
        "TBS",
        "TGM",
        "THD",
        "TON",
        "TUB",
        "UGS",
        "UNT",
        "YDS",
        "OTH",
        "NA",
        "N.A.",
    }
)
DOCUMENT_CATEGORIES = (
    "OUTWARD_INVOICE",
    "INWARD_UNREGISTERED_INVOICE",
    "REVISED_INVOICE",
    "DEBIT_NOTE",
    "CREDIT_NOTE",
    "RECEIPT_VOUCHER",
    "PAYMENT_VOUCHER",
    "REFUND_VOUCHER",
    "CHALLAN_JOB_WORK",
    "CHALLAN_LIQUID_GAS",
    "CHALLAN_APPROVAL",
    "CHALLAN_OTHER",
)
TABLES = {
    "4A": "Registered invoices",
    "4B": "Outward reverse-charge invoices",
    "6B": "SEZ supplies",
    "6C": "Deemed exports",
    "5": "Interstate B2C large invoices",
    "6A": "Export invoices",
    "7": "B2C others",
    "8": "Nil-rated, exempt and non-GST supplies",
    "9B_REG": "Registered credit/debit notes",
    "9B_UNREG": "Unregistered/export credit/debit notes",
    "9A_B2B": "Amended registered invoices",
    "9A_B2CL": "Amended B2C large invoices",
    "9A_EXP": "Amended export invoices",
    "9C_REG": "Amended registered notes",
    "9C_UNREG": "Amended unregistered/export notes",
    "10": "Amended B2C others",
    "11A": "Taxable advances received",
    "11B": "Advances adjusted",
    "11A_AMEND": "Amended advances received",
    "11B_AMEND": "Amended advance adjustments",
    "12_B2B": "HSN summary — B2B",
    "12_B2C": "HSN summary — B2C",
    "13": "Documents issued",
    "14_TCS": "Supplier ECO supplies — section 52",
    "14_9_5": "Supplier ECO supplies — section 9(5)",
    "14A_TCS": "Amended supplier ECO supplies — section 52",
    "14A_9_5": "Amended supplier ECO supplies — section 9(5)",
    **{
        f"{prefix}_{role}": f"{'Amended ' if prefix == '15A' else ''}ECO section 9(5) — {role}"
        for prefix in ("15", "15A")
        for role in ("B2B", "B2C", "URP2B", "URP2C")
    },
}


def applicable(registration: dict[str, Any]) -> bool:
    return (
        registration.get("country_code") == "IN"
        and registration.get("tax_system") == "gst_in"
        and registration.get("regime") in ELIGIBLE_REGIMES
        and registration.get("registration_class")
        not in {"isd", "tds", "tcs", "non_resident", "oidar"}
    )


def threshold(document_date: dt.date) -> Decimal:
    return Decimal("100000") if document_date >= dt.date(2024, 8, 1) else Decimal("250000")


def hsn_digits(turnover: Decimal) -> int:
    return 6 if turnover > Decimal("50000000") else 4


def money(value: Decimal) -> str:
    result = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(abs(result) if result == 0 else result, ".2f")


def bounds(period: str, frequency: str) -> tuple[dt.date, dt.date]:
    start, end = period_bounds(period, frequency)
    if start < FIRST_PERIOD:
        raise ValueError(
            "GSTR-1 currently supports October 2025 onward; earlier form rules are not activated"
        )
    return start, end


def correction_cutoff(original_date: dt.date, annual_filed_date: dt.date | None) -> dt.date:
    year = original_date.year if original_date.month >= 4 else original_date.year - 1
    deadline = dt.date(year + 1, 11, 30)
    return min(deadline, annual_filed_date) if annual_filed_date else deadline
