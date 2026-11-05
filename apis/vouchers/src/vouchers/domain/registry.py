"""Code-defined capabilities. Runtime configuration can only narrow this catalogue."""

from dataclasses import dataclass

from billing_platform.errors import ValidationFailedError


@dataclass(frozen=True, slots=True)
class Kind:
    code: str
    family: str
    sections: frozenset[str]
    effect_batch: str
    profiles: tuple[str, ...] = ("STANDARD",)


COMMON = frozenset({"PARTIES", "REFERENCES", "ATTACHMENTS"})
KINDS = tuple(
    (
        Kind(code, family, COMMON | frozenset(sections), batch, profiles)
        for code, family, sections, batch, profiles in (
            ("CONTRA", "ACCOUNTING", ("ACCOUNTS", "TENDERS"), "B10", ("STANDARD",)),
            (
                "PAYMENT",
                "ACCOUNTING",
                ("ACCOUNTS", "TENDERS", "BILL_ALLOCATIONS"),
                "B13",
                ("STANDARD", "ADVANCE"),
            ),
            (
                "RECEIPT",
                "ACCOUNTING",
                ("ACCOUNTS", "TENDERS", "BILL_ALLOCATIONS"),
                "B13",
                ("STANDARD", "ADVANCE"),
            ),
            (
                "JOURNAL",
                "ACCOUNTING",
                ("ACCOUNTS", "TENDERS", "BILL_ALLOCATIONS"),
                "B10",
                ("STANDARD",),
            ),
            (
                "SALES",
                "ACCOUNTING",
                ("ACCOUNTS", "ITEMS", "INVENTORY", "CHARGES", "TAX", "TENDERS", "BILL_ALLOCATIONS"),
                "B17/B24",
                ("STANDARD", "PRO_FORMA"),
            ),
            (
                "PURCHASE",
                "ACCOUNTING",
                ("ACCOUNTS", "ITEMS", "INVENTORY", "CHARGES", "TAX", "TENDERS", "BILL_ALLOCATIONS"),
                "B17/B24",
                ("STANDARD",),
            ),
            (
                "CREDIT_NOTE",
                "ACCOUNTING",
                ("ACCOUNTS", "ITEMS", "INVENTORY", "CHARGES", "TAX", "BILL_ALLOCATIONS"),
                "B17/B25",
                ("STANDARD",),
            ),
            (
                "DEBIT_NOTE",
                "ACCOUNTING",
                ("ACCOUNTS", "ITEMS", "INVENTORY", "CHARGES", "TAX", "BILL_ALLOCATIONS"),
                "B17/B25",
                ("STANDARD",),
            ),
            ("RECEIPT_NOTE", "INVENTORY", ("ITEMS", "INVENTORY"), "B23", ("STANDARD",)),
            (
                "DELIVERY_NOTE",
                "INVENTORY",
                ("ITEMS", "INVENTORY"),
                "B23",
                ("STANDARD", "DELIVERY_CHALLAN"),
            ),
            ("REJECTIONS_IN", "INVENTORY", ("ITEMS", "INVENTORY"), "B25", ("STANDARD",)),
            ("REJECTIONS_OUT", "INVENTORY", ("ITEMS", "INVENTORY"), "B25", ("STANDARD",)),
            (
                "STOCK_JOURNAL",
                "INVENTORY",
                ("ITEMS", "INVENTORY", "JOB_PROCESS"),
                "B23/B39",
                (
                    "STANDARD",
                    "OPENING",
                    "TRANSFER",
                    "TRANSFER_DISPATCH",
                    "TRANSFER_RECEIPT",
                    "MANUFACTURING",
                    "REQUISITION",
                ),
            ),
            ("PHYSICAL_STOCK", "INVENTORY", ("ITEMS", "INVENTORY"), "B25", ("STANDARD",)),
            (
                "MATERIAL_IN",
                "JOB_WORK",
                ("ITEMS", "INVENTORY", "JOB_PROCESS"),
                "B38",
                ("STANDARD",),
            ),
            (
                "MATERIAL_OUT",
                "JOB_WORK",
                ("ITEMS", "INVENTORY", "JOB_PROCESS"),
                "B38",
                ("STANDARD",),
            ),
            (
                "PURCHASE_ORDER",
                "ORDER",
                ("ITEMS", "CHARGES", "TAX", "FULFILLMENT"),
                "B28",
                ("STANDARD",),
            ),
            (
                "SALES_ORDER",
                "ORDER",
                ("ITEMS", "CHARGES", "TAX", "FULFILLMENT"),
                "B28",
                ("STANDARD", "QUOTATION"),
            ),
            (
                "JOB_WORK_IN_ORDER",
                "JOB_WORK",
                ("ITEMS", "FULFILLMENT", "JOB_PROCESS"),
                "B38",
                ("STANDARD",),
            ),
            (
                "JOB_WORK_OUT_ORDER",
                "JOB_WORK",
                ("ITEMS", "FULFILLMENT", "JOB_PROCESS"),
                "B38",
                ("STANDARD",),
            ),
            ("MEMORANDUM", "GENERAL", ("ACCOUNTS", "ITEMS"), "B33", ("STANDARD",)),
            ("REVERSING_JOURNAL", "GENERAL", ("ACCOUNTS",), "B34", ("STANDARD",)),
        )
    )
)
BY_KIND = {kind.code: kind for kind in KINDS}
FOUNDATION_SECTIONS = COMMON | {"ITEMS"}
REGISTRY_VERSION = 1


def resolve_kind(code: str, profile: str) -> Kind:
    kind = BY_KIND.get(code)
    if kind is None or profile not in kind.profiles:
        raise ValidationFailedError("unsupported voucher kind/profile")
    return kind


def executable(code: str, profile: str) -> bool:
    resolve_kind(code, profile)
    return False
