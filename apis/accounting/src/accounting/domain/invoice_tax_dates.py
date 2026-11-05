"""Version-two India service tax dates; legacy posting-date resolution is unchanged.

Ordinary section 13(2), supplier-invoiced RCM under section 13(3), and section 14
operate on a single consideration slice. Partial payments need separate source slices.
Special service deadlines and recipient self-invoices require their own legal profiles.
"""

import datetime as dt
from dataclasses import dataclass, replace

from billing_platform.errors import ValidationFailedError

GST_START = dt.date(2017, 7, 1)


@dataclass(frozen=True)
class TaxPoint:
    date_contract_version: int
    tax_point_date: dt.date
    legal_basis: str
    invoice_date: dt.date
    supply_date: dt.date
    payment_date: dt.date | None
    rate_change_date: dt.date | None


def payment_date(
    book: dt.date | None, bank: dt.date | None, *, change: dt.date | None = None
) -> dt.date | None:
    known = [value for value in (book, bank) if value is not None]
    if not known:
        return None
    # Section 14's special bank-credit rule overrides the normal earlier-of dates.
    if change is not None and bank is not None and (bank - change).days > 4:
        return bank
    return min(known)


def service_tax_point(
    *,
    invoice: dt.date,
    supplied: dt.date,
    payment_book: dt.date | None = None,
    payment_bank: dt.date | None = None,
    reverse_charge: bool = False,
    supplier_issued: bool = True,
    rate_change: dt.date | None = None,
) -> TaxPoint:
    dates = [
        value
        for value in (invoice, supplied, payment_book, payment_bank, rate_change)
        if value is not None
    ]
    if any(value < GST_START for value in dates):
        raise ValidationFailedError("GST service dates precede this legal profile")
    source_dates = [
        value for value in (invoice, supplied, payment_book, payment_bank) if value is not None
    ]
    if rate_change is not None and (
        rate_change <= min(source_dates) or rate_change > max(source_dates)
    ):
        ordinary = service_tax_point(
            invoice=invoice,
            supplied=supplied,
            payment_book=payment_book,
            payment_bank=payment_bank,
            reverse_charge=reverse_charge,
            supplier_issued=supplier_issued,
        )
        return replace(ordinary, rate_change_date=rate_change)
    paid = payment_date(payment_book, payment_bank, change=rate_change)
    if rate_change is not None:
        if reverse_charge:
            raise ValidationFailedError(
                "RCM with a rate transition requires a dedicated legal profile"
            )
        if paid is None:
            raise ValidationFailedError("rate transition requires payment evidence for this slice")
        supply_before, invoice_before, payment_before = (
            supplied < rate_change,
            invoice < rate_change,
            paid < rate_change,
        )
        if supply_before:
            if invoice_before == payment_before:
                point = min(invoice, paid)
                basis = "CGST_14_A_I" if not invoice_before else "CGST_13_2"
            elif invoice_before:
                point, basis = invoice, "CGST_14_A_II"
            else:
                point, basis = paid, "CGST_14_A_III"
        elif invoice_before and not payment_before:
            point, basis = paid, "CGST_14_B_I"
        elif not invoice_before and payment_before:
            point, basis = invoice, "CGST_14_B_III"
        else:
            point, basis = min(invoice, paid), "CGST_14_B_II" if invoice_before else "CGST_13_2"
    elif reverse_charge:
        if not supplier_issued:
            raise ValidationFailedError("recipient self-invoices require their dated legal profile")
        try:
            deadline = invoice + dt.timedelta(days=61)
        except OverflowError as error:
            raise ValidationFailedError("RCM tax-point date exceeds the supported range") from error
        point = min(deadline, paid) if paid else deadline
        basis = (
            "CGST_13_3_PAYMENT"
            if paid is not None and paid <= deadline
            else "CGST_13_3_SUPPLIER_60_DAYS"
        )
    else:
        # Ordinary services only. Banking/insurance, continuous supply and other
        # exceptions must never inherit this thirty-day deadline implicitly.
        timely = (invoice - supplied).days <= 30
        origin = invoice if timely else supplied
        point = min(origin, paid) if paid else origin
        basis = (
            "CGST_13_2_PAYMENT"
            if paid is not None and paid <= origin
            else "CGST_13_2_A"
            if timely
            else "CGST_13_2_B"
        )
    return TaxPoint(2, point, basis, invoice, supplied, paid, rate_change)
