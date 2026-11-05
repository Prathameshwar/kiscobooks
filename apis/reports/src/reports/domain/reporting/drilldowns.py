"""Reviewed account-to-ledger mapping; callers cannot choose target filters."""

import calendar
import datetime as dt
import uuid
from typing import Any


def account_entries(parameters: dict[str, Any], row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("account_id"):
        return None
    account = str(uuid.UUID(str(row["account_id"])))
    comparative = row.get("period") == "COMPARATIVE"
    start = parameters.get("comparative_from" if comparative else "date_from")
    end = parameters.get("comparative_to" if comparative else "date_to")
    if not start or not end:
        return None
    begin, finish = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if row.get("grain") in {"DAY", "MONTH"} and row.get("date"):
        begin = max(begin, dt.date.fromisoformat(row["date"]))
        last = (
            begin
            if row["grain"] == "DAY"
            else begin.replace(day=calendar.monthrange(begin.year, begin.month)[1])
        )
        finish = min(finish, last)
    if begin > finish:
        return None
    return {
        "date_from": begin.isoformat(),
        "date_to": finish.isoformat(),
        "account_id": account,
        **{
            key: value
            for key, value in parameters.items()
            if key in {"basis", "currency", "party_id", "role"}
        },
    }


def parameters_for(
    key: str,
    parameters: dict[str, Any],
    row: dict[str, Any],
    coverage: str | None,
    *,
    retained_only: bool = False,
) -> dict[str, Any] | None:
    if retained_only and key != "row_detail":
        # Imported YTD is an aggregate, not reconstructed invoice or ledger history.
        end = parameters.get("comparative_to" if row.get("period") == "COMPARATIVE" else "date_to")
        if not coverage or not end or end < coverage:
            return None
        parameters = parameters | {
            field: max(parameters[field], coverage)
            for field in ("date_from", "comparative_from")
            if parameters.get(field)
        }
    if key in {"balance_account_entries", "balance_comparison_entries"}:
        end = parameters.get("comparative_to" if key == "balance_comparison_entries" else "date_to")
        if not coverage or not end or coverage > end:
            return None
        return account_entries({"date_from": coverage, "date_to": end}, row)
    if key == "row_detail":
        return {}
    if key == "profit_group_products":
        group = row.get("group_id")
        if not group or parameters.get("group_id") not in {None, group}:
            # Ancestor rows may contain only the parent's filtered subset.
            return None
        comparative = row.get("period") == "COMPARATIVE"
        return {
            **{name: parameters[name] for name in ("party_id", "item_id") if parameters.get(name)},
            "date_from": parameters.get("comparative_from" if comparative else "date_from"),
            "date_to": parameters.get("comparative_to" if comparative else "date_to"),
            "currency": row["currency"],
            "group_id": str(uuid.UUID(group)),
        }
    if key in {"analytics_sales", "analytics_purchases"}:
        party = row.get("party_id")
        invoice = None
        if key == "analytics_sales" and row.get("row_kind") in {"BUYER_PROFIT", "INVOICE_PROFIT"}:
            invoice = row.get("invoice_id") or row.get("_sales_invoice_id")
            if not invoice and parameters.get("search") and not row.get("_sales_complete_buyer"):
                # The sales register cannot express a multi-invoice reference search.
                # Do not replace the selected subset with the entire buyer's activity.
                return None
        if not party and not invoice:
            return None
        comparative = row.get("period") == "COMPARATIVE"
        begin = parameters.get("comparative_from" if comparative else "date_from")
        end = parameters.get("comparative_to" if comparative else "date_to")
        return (
            {
                "date_from": begin,
                "date_to": end,
                **({"party_id": str(uuid.UUID(party))} if party else {}),
                **({"invoice_id": str(uuid.UUID(invoice))} if invoice else {}),
                **(
                    {"currency": row.get("document_currency") or row["currency"]}
                    if row.get("currency")
                    else {}
                ),
            }
            if begin and end
            else None
        )
    if (
        row.get("period") == "COMPARATIVE"
        and parameters.get("comparative_from")
        and parameters.get("comparative_to")
    ):
        parameters = parameters | {
            "date_from": parameters["comparative_from"],
            "date_to": parameters["comparative_to"],
        }
    if key in {"stock_item_entries", "stock_group_items", "stock_item_locations"}:
        identity = row.get("group_id" if key == "stock_group_items" else "item_id")
        if not identity or not parameters.get("as_of"):
            return None
        if (
            key == "stock_group_items"
            and parameters.get("group_id")
            and parameters["group_id"] != identity
        ):
            # Ancestor and overlapping rollups can include only the parent's selected
            # items. A single group filter cannot safely express that intersection.
            return None
        result: dict[str, Any] = {
            **{
                field: parameters[field]
                for field in ("item_id", "location_id", "group_id", "owner", "include_inactive")
                if field in parameters
            },
            "as_of": parameters["as_of"],
            "group_id" if key == "stock_group_items" else "item_id": str(uuid.UUID(identity)),
        }
        if key == "stock_item_entries":
            if not coverage:
                return None
            result["date_from"] = parameters.get("date_from") or coverage
            if row.get("lot_id") or parameters.get("lot_id"):
                result["lot_id"] = row.get("lot_id") or parameters["lot_id"]
        if row.get("location_id"):
            result["location_id"] = row["location_id"]
        if row.get("owner"):
            result["owner"] = row["owner"]
        if key in {"stock_item_entries", "stock_item_locations"} and row.get("custody"):
            result["custody"] = row["custody"]
        return result
    if key == "account_entries":
        if row.get("row_kind") in {"ACCOUNT_CONTINUITY", "BILL_CONTINUITY", "ADVANCE_CONTINUITY"}:
            return account_entries(parameters | {"date_from": coverage}, row) if coverage else None
        return account_entries(
            parameters | {"date_from": parameters.get("date_from") or coverage}, row
        )
    if key == "comparison_account_entries":
        if not parameters.get("comparative_from") or not parameters.get("comparative_to"):
            return None
        return account_entries(parameters, row | {"period": "COMPARATIVE"})
    if key == "group_entries":
        selected = account_entries(parameters, row | {"account_id": row.get("group_id")})
        if selected is not None:
            selected["group_id"] = selected.pop("account_id")
        return selected
    comparative = row.get("period") == "COMPARATIVE"
    begin = parameters.get("comparative_from" if comparative else "date_from") or coverage
    end = parameters.get("comparative_to" if comparative else "date_to")
    if not begin or not end:
        return None
    if key == "journal_entries":
        if not row.get("journal_id"):
            return None
        posting = (
            row.get("journal_posting_date")
            or row.get("posting_date")
            or row.get("date")
            or row.get("booking_date")
        )
        if posting:
            begin = end = posting
        return {
            "date_from": begin,
            "date_to": end,
            "journal_id": str(uuid.UUID(str(row["journal_id"]))),
            **{name: value for name, value in parameters.items() if name in {"basis", "currency"}},
        }
    if key == "party_bills":
        if row.get("row_kind") == "OPENING":
            return None
        account = row.get("account_id") or row.get("party_account_id")
        if not account:
            return None
        if (
            row.get("row_kind") == "ACCOUNT_CONTINUITY"
            or row.get("row_kind") == "EARNINGS_CONTINUITY"
        ):
            return None
        if row.get("row_kind") in {"BILL_CONTINUITY", "ADVANCE_CONTINUITY"}:
            end = (
                dt.date.fromisoformat(parameters["date_from"]) - dt.timedelta(days=1)
            ).isoformat()
        return {
            "date_to": end,
            "account_id": str(uuid.UUID(str(account))),
            **{
                name: value
                for name, value in parameters.items()
                if name in {"basis", "currency", "party_id", "role"}
            },
        }
    if key.startswith("invoice_"):
        if not row.get("invoice_id"):
            return None
        # The target register's date semantics are posting dates, not document/tax dates.
        # Cover retained posting history through the selected end instead of silently
        # transferring a document-date boundary to a different calculation grain.
        posting = row.get("posting_date")
        end = max(end, posting) if posting else end
        return {
            "date_from": coverage or begin,
            "date_to": end,
            "invoice_id": str(uuid.UUID(str(row["invoice_id"]))),
            **{name: value for name, value in parameters.items() if name in {"currency"}},
        }
    return None
