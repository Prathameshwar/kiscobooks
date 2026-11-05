"""Exact full-result summaries for the native Books workspaces."""

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.reconcile import fixed, money

BOOK_CODES = frozenset(
    {
        "DAY_BOOK",
        "CASH_BOOK",
        "BANK_BOOK",
        "SALES_REGISTER",
        "PURCHASE_REGISTER",
        "PAYMENT_REGISTER",
        "RECEIPT_REGISTER",
        "ACCOUNT_LEDGER",
        "PARTY_LEDGER",
        "ITEM_LEDGER",
    }
)
LEDGER_CODES = frozenset({"CASH_BOOK", "BANK_BOOK", "ACCOUNT_LEDGER", "PARTY_LEDGER"})
INVOICE_CODES = frozenset({"SALES_REGISTER", "PURCHASE_REGISTER"})
TENDER_CODES = frozenset({"PAYMENT_REGISTER", "RECEIPT_REGISTER"})


class BookSummary:
    """Incremental exact arithmetic; comparative rows never contaminate current cards."""

    def __init__(self, code: str):
        if code not in BOOK_CODES:
            raise ValueError("book summary is unavailable")
        self.code = code
        self.records = 0
        self.entries = 0
        self.reductions = 0
        self.instruments = 0
        self.vouchers: set[str] = set()
        self.amounts: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        self.closing: dict[tuple[str, str], Decimal] = {}
        self.quantities: dict[str, Decimal] = defaultdict(Decimal)
        self.quantity_closing: dict[str, Decimal] = {}
        self.units: set[str] = set()

    def add(self, row: dict[str, Any]) -> None:
        self.records += 1
        if row.get("period", "CURRENT") != "CURRENT":
            return
        currency = str(row.get("currency") or "")
        if self.code == "DAY_BOOK":
            self.entries += 1
            self.amounts[currency]["debit"] += money(row.get("debit", "0.0000"))
            self.amounts[currency]["credit"] += money(row.get("credit", "0.0000"))
        elif self.code in LEDGER_CODES:
            account = str(row["account_id"])
            self.closing[(currency, account)] = money(row.get("balance", "0.0000"))
            if row.get("row_kind") != "OPENING":
                self.entries += 1
                self.amounts[currency]["debit"] += money(row.get("debit", "0.0000"))
                self.amounts[currency]["credit"] += money(row.get("credit", "0.0000"))
        elif self.code in INVOICE_CODES:
            if row.get("row_kind") != "INVOICE":
                return
            self.entries += 1
            if row.get("direction") == "REDUCTION":
                self.reductions += 1
                sign = Decimal(-1)
            else:
                sign = Decimal(1)
            for key in ("commercial_total", "tax_total", "payable"):
                self.amounts[currency][key] += sign * money(row.get(key, "0.0000"))
        elif self.code in TENDER_CODES:
            self.entries += 1
            self.vouchers.add(str(row.get("journal_id") or row.get("number") or self.records))
            if row.get("instrument_id"):
                self.instruments += 1
            # Tender amounts are magnitudes; the journal sign also carries reversals.
            signed = money(row["signed_amount"])
            self.amounts[currency]["amount"] += (
                -signed if self.code == "PAYMENT_REGISTER" else signed
            )
        else:
            position = str(row["position_id"])
            unit = row.get("unit")
            if unit:
                self.units.add(str(unit))
            self.quantity_closing[position] = money(row.get("balance", "0.0000"))
            if row.get("row_kind") != "OPENING":
                self.entries += 1
                self.quantities["inward"] += money(row.get("inward", "0.0000"))
                self.quantities["outward"] += money(row.get("outward", "0.0000"))

    def finish(self) -> dict[str, Any]:
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            decimal_amounts = {currency: dict(values) for currency, values in self.amounts.items()}
            if self.code in LEDGER_CODES:
                for (currency, _account), value in self.closing.items():
                    currency_amounts = decimal_amounts.setdefault(currency, {})
                    currency_amounts["closing"] = (
                        currency_amounts.get("closing", Decimal(0)) + value
                    )
            amounts = {
                currency: {key: fixed(value) for key, value in sorted(values.items())}
                for currency, values in sorted(decimal_amounts.items())
            }
            result: dict[str, Any] = {
                "code": self.code,
                "record_count": self.records,
                "entry_count": self.entries,
                "amounts": amounts,
            }
            if self.code in INVOICE_CODES:
                result["reduction_count"] = self.reductions
            elif self.code in TENDER_CODES:
                result |= {
                    "voucher_count": len(self.vouchers),
                    "instrument_count": self.instruments,
                }
            elif self.code == "ITEM_LEDGER":
                result |= {
                    "quantities": {
                        "inward": fixed(self.quantities["inward"]),
                        "outward": fixed(self.quantities["outward"]),
                        "closing": fixed(sum(self.quantity_closing.values(), Decimal(0))),
                    },
                    "unit": next(iter(self.units)) if len(self.units) == 1 else None,
                }
            return result


def summarize(code: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if code not in BOOK_CODES:
        return None
    summary = BookSummary(code)
    for row in rows:
        summary.add(row)
    return summary.finish()
