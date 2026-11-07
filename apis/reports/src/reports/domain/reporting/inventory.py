"""Exact stock reports over one complete, frozen owner inventory evidence set."""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from typing import Any

from reporting_contract.inventory import (
    Coverage,
    GLControl,
    Group,
    InventoryRecord,
    Item,
    Location,
    Movement,
    Position,
)

from reports.domain.reporting.contracts import fingerprint

CODES = (
    "STOCK_SUMMARY",
    "ITEM_LEDGER",
    "LOCATION_STOCK",
    "STOCK_VALUATION",
    "BATCH_SUMMARY",
    "STOCK_EXPIRY",
    "STOCK_REORDER",
    "STOCK_AGEING",
    "STOCK_MOVEMENT",
    "STOCK_GROUP_SUMMARY",
)
ZERO = Decimal(0)
FOUR = Decimal("0.0001")


def number(value: str | None) -> Decimal:
    if value is None:
        raise ValueError("required inventory amount is unavailable")
    return Decimal(value)


def fixed(value: Decimal) -> str:
    return format(value, ".4f")


def ancestors(rows: dict[str, Group] | dict[str, Location], key: str) -> set[str]:
    result: set[str] = set()
    while key:
        if len(result) >= 64:
            raise ValueError("inventory hierarchy exceeds the supported depth")
        if key in result or key not in rows:
            raise ValueError("inventory hierarchy is cyclic or incomplete")
        result.add(key)
        parent = rows[key].parent_id
        key = str(parent) if parent else ""
    return result


class Inventory:
    def __init__(self, records: list[dict[str, Any]], *, movements_loaded: bool = True) -> None:
        parsed = [InventoryRecord.model_validate(row).payload for row in records]
        coverage = [row for row in parsed if isinstance(row, Coverage)]
        if len(coverage) != 1:
            raise ValueError("complete inventory source coverage is unavailable")
        self.coverage = coverage[0]
        self.movements_loaded = movements_loaded
        self.items = {str(row.item_id): row for row in parsed if isinstance(row, Item)}
        self.locations = {str(row.location_id): row for row in parsed if isinstance(row, Location)}
        self.groups = {str(row.group_id): row for row in parsed if isinstance(row, Group)}
        self.positions = {str(row.position_id): row for row in parsed if isinstance(row, Position)}
        self.movements = [row for row in parsed if isinstance(row, Movement)]
        self.gl = {str(row.account_id): row for row in parsed if isinstance(row, GLControl)}
        expected = self.coverage
        if not expected.native_stock_current:
            raise ValueError(
                "native stock changed after inventory publication; a fresh source is required"
            )
        counts: Counter[str] = Counter(row.kind for row in parsed)
        for kind, actual, required in (
            ("ITEM", len(self.items), expected.item_count),
            ("LOCATION", len(self.locations), expected.location_count),
            ("GROUP", len(self.groups), expected.group_count),
            ("POSITION", len(self.positions), expected.position_count),
            ("GL_CONTROL", len(self.gl), counts["GL_CONTROL"]),
        ):
            if counts[kind] != actual or actual != required:
                raise ValueError("inventory source identities or coverage counts differ")
        if movements_loaded and (
            counts["MOVEMENT"] != expected.movement_count
            or len({row.movement_id for row in self.movements}) != len(self.movements)
        ):
            raise ValueError("inventory movement coverage differs")
        self.memberships = {
            key: set().union(*(ancestors(self.groups, str(g)) for g in row.group_ids))
            for key, row in self.items.items()
        }
        for group_key in self.groups:
            ancestors(self.groups, group_key)
        self.location_tree = {key: ancestors(self.locations, key) for key in self.locations}
        serials: set[tuple[str, str]] = set()
        grains: set[tuple[str, ...]] = set()
        for position in self.positions.values():
            grain = tuple(
                str(value)
                for value in (
                    position.item_id,
                    position.location_id,
                    position.bin_id,
                    position.lot_id,
                    position.owner,
                    position.owner_party_id,
                    position.custody,
                    position.custodian_id,
                    position.disposition,
                )
            )
            if grain in grains:
                raise ValueError("duplicate stock position grain")
            grains.add(grain)
            item = self.items.get(str(position.item_id))
            if item is None or str(position.location_id) not in self.locations:
                raise ValueError("stock position has an unknown item or location")
            if item.lot_tracked and position.lot_id is None:
                raise ValueError("tracked stock position has no lot identity")
            if expected.reservations_complete and position.reserved is None:
                raise ValueError("complete reservations require every position balance")
            if (
                expected.valuation_complete
                and position.owner == "OWN"
                and (position.carrying_value is None or position.costing_method is None)
            ):
                raise ValueError("complete valuation requires every owned position value")
            if expected.origins_complete:
                if sum((number(o.quantity) for o in position.origins), ZERO) != number(
                    position.quantity
                ):
                    raise ValueError("remaining receipt origins do not reconcile to position")
            if len({origin.origin_id for origin in position.origins}) != len(position.origins):
                raise ValueError("duplicate receipt origin in stock position")
            for origin in position.origins:
                if (origin.provenance == "KNOWN" and origin.receipt_date is None) or any(
                    day and day > expected.as_of
                    for day in (
                        origin.receipt_date,
                        origin.manufacture_date,
                    )
                ):
                    raise ValueError("receipt origin date or provenance is invalid")
            if position.valuation_detail and any(
                layer.receipt_date > expected.as_of for layer in position.valuation_detail.layers
            ):
                raise ValueError("valuation cost layer date follows snapshot")
            if item.serial_tracked:
                if Decimal(len(position.serials)) != number(position.quantity):
                    raise ValueError("serial identities do not reconcile to whole-unit quantity")
                for serial in position.serials:
                    serial_key = (str(item.item_id), serial.casefold())
                    if serial_key in serials:
                        raise ValueError("serial identity occurs in multiple positions")
                    serials.add(serial_key)
        if movements_loaded and expected.movements_complete:
            balances: dict[str, Decimal] = defaultdict(Decimal)
            values: dict[str, Decimal] = defaultdict(Decimal)
            missing_values: set[str] = set()
            order: set[tuple[dt.date, int]] = set()
            for movement in sorted(
                self.movements, key=lambda r: (r.effective_date, r.sequence, str(r.movement_id))
            ):
                movement_position = self.positions.get(str(movement.position_id))
                if movement_position is None or (
                    movement.item_id,
                    movement.location_id,
                    movement.lot_id,
                ) != (
                    movement_position.item_id,
                    movement_position.location_id,
                    movement_position.lot_id,
                ):
                    raise ValueError("movement position dimensions differ")
                if not expected.history_start <= movement.effective_date <= expected.as_of:
                    raise ValueError("movement falls outside declared history")
                movement_key = (
                    movement.effective_date,
                    movement.sequence,
                )
                if movement_key in order:
                    raise ValueError("movement sequence is ambiguous")
                order.add(movement_key)
                balances[str(movement.position_id)] += number(movement.quantity_delta)
                if balances[str(movement.position_id)] < 0:
                    raise ValueError("unsupported negative stock history")
                if movement.value_delta is not None:
                    values[str(movement.position_id)] += number(movement.value_delta)
                else:
                    missing_values.add(str(movement.position_id))
            for key, position in self.positions.items():
                if balances[key] != number(position.quantity):
                    raise ValueError("movement closing quantity does not reconcile")
                if (
                    expected.valuation_complete
                    and position.owner == "OWN"
                    and (key in missing_values or values[key] != number(position.carrying_value))
                ):
                    raise ValueError("movement closing value does not reconcile")

    def selected(self, p: dict[str, Any]) -> list[Position]:
        if p["as_of"] != self.coverage.as_of.isoformat():
            raise ValueError("as_of requires a matching frozen inventory snapshot")
        for key, rows in (
            ("item_id", self.items),
            ("location_id", self.locations),
            ("group_id", self.groups),
        ):
            if p.get(key) and p[key] not in rows:
                raise ValueError("inventory filter is outside the frozen source scope")
        return [
            row
            for row in self.positions.values()
            if (
                (not p.get("item_id") or str(row.item_id) == p["item_id"])
                and (
                    not p.get("location_id")
                    or p["location_id"] in self.location_tree[str(row.location_id)]
                )
                and (not p.get("group_id") or p["group_id"] in self.memberships[str(row.item_id)])
                and (not p.get("owner") or row.owner == p["owner"])
                and (not p.get("custody") or row.custody == p["custody"])
                and (p.get("include_inactive", True) or self.items[str(row.item_id)].active)
                and (not p.get("lot_id") or str(row.lot_id) == p["lot_id"])
            )
        ]

    def label(self, position: Position) -> dict[str, Any]:
        item = self.items[str(position.item_id)]
        location = self.locations[str(position.location_id)]
        return {
            "item_id": str(item.item_id),
            "item_code": item.code,
            "item_name": item.name,
            "unit": item.unit,
            "location_id": str(location.location_id),
            "location_code": location.code,
            "location_name": location.name,
            "lot_id": str(position.lot_id) if position.lot_id else None,
            "lot_code": position.lot_code,
            "owner": position.owner,
            "custody": position.custody,
            "position_id": str(position.position_id),
            "currency": self.coverage.currency,
            "as_of": self.coverage.as_of.isoformat(),
        }

    def eligibility(self, position: Position) -> tuple[Decimal, list[str]]:
        reasons: list[str] = []
        location = self.locations[str(position.location_id)]
        item = self.items[str(position.item_id)]
        if location.sale_eligible is False or location.is_group:
            reasons.append("WAREHOUSE_POLICY")
        if not item.active or not item.sale_location_permissions.get(
            position.location_id, item.sale_location_mode != "ALLOW_LIST"
        ):
            reasons.append("PRODUCT_POLICY")
        as_of = self.coverage.as_of
        if position.disposition != "GOOD":
            reasons.append(position.disposition)
        if position.owner != "OWN":
            reasons.append("THIRD_PARTY")
        if position.custody != "LOCAL":
            reasons.append(position.custody)
        if position.expiry_date:
            days = (position.expiry_date - as_of).days
            if days < 0 or (days == 0 and not position.expiry_day_usable):
                reasons.append("EXPIRED")
            elif days < position.minimum_remaining_days:
                reasons.append("MINIMUM_LIFE")
        elif position.minimum_remaining_days:
            reasons.append("UNKNOWN_EXPIRY")
        return (
            ZERO
            if reasons
            else number(
                position.eligible_quantity
                if position.eligible_quantity is not None
                else position.quantity
            )
        ), reasons

    def summary(self, selected: list[Position], dimension: str) -> list[dict[str, Any]]:
        values: dict[tuple[str, ...], dict[str, Any]] = {}
        keys: list[tuple[str, ...]]
        for position in sorted(selected, key=lambda r: str(r.position_id)):
            label = self.label(position)
            if dimension == "group_id":
                keys = [
                    (g, label["unit"], position.owner, position.custody)
                    for g in sorted(self.memberships[str(position.item_id)]) or ["UNGROUPED"]
                ]
            elif dimension == "location_id":
                keys = [
                    (
                        str(position.location_id),
                        str(position.item_id),
                        position.owner,
                        position.custody,
                    )
                ]
            elif dimension == "lot_id":
                keys = [
                    (
                        str(position.item_id),
                        str(position.location_id),
                        str(position.lot_id),
                        position.owner,
                        position.custody,
                    )
                ]
            else:
                keys = [(str(position.item_id), position.owner, position.custody)]
            for key in keys:
                if key not in values:
                    row = label.copy()
                    if dimension in {"item_id", "group_id"}:
                        for name in (
                            "location_id",
                            "location_code",
                            "location_name",
                            "lot_id",
                            "lot_code",
                            "position_id",
                        ):
                            row.pop(name, None)
                    elif dimension == "location_id":
                        for name in ("lot_id", "lot_code", "position_id"):
                            row.pop(name, None)
                    if dimension == "group_id":
                        for name in ("item_id", "item_code", "item_name"):
                            row.pop(name, None)
                        group = self.groups.get(key[0])
                        row.update(
                            group_id=key[0] if group else None,
                            group_code=group.code if group else "UNGROUPED",
                            group_name=group.name if group else "Ungrouped",
                        )
                    row.update(
                        {
                            name: ZERO
                            for name in (
                                "opening",
                                "inward",
                                "outward",
                                "quantity",
                                "eligible",
                                "reserved",
                                "available",
                                "carrying_value",
                            )
                        }
                    )
                    row["reservation_status"] = (
                        "COMPLETE" if self.coverage.reservations_complete else "UNAVAILABLE"
                    )
                    row["valuation_status"] = (
                        "COMPLETE" if self.coverage.valuation_complete else "UNAVAILABLE"
                    )
                    values[key] = row
                row = values[key]
                row["opening"] += number(position.opening_quantity)
                row["inward"] += number(position.inward_quantity)
                row["outward"] += number(position.outward_quantity)
                row["quantity"] += number(position.quantity)
                eligible, _ = self.eligibility(position)
                row["eligible"] += eligible
                if self.coverage.reservations_complete:
                    reserved = number(position.reserved)
                    if reserved > eligible:
                        # Invalidated/held reservations remain visible but not available.
                        row["available"] += ZERO
                    else:
                        row["available"] += eligible - reserved
                    row["reserved"] += reserved
                if self.coverage.valuation_complete and position.owner == "OWN":
                    row["carrying_value"] += number(position.carrying_value)
        result = []
        for _, row in sorted(values.items()):
            for name in (
                "opening",
                "inward",
                "outward",
                "quantity",
                "eligible",
                "reserved",
                "available",
                "carrying_value",
            ):
                row[name] = fixed(row[name])
            if not self.coverage.reservations_complete:
                row["reserved"] = row["available"] = None
            if not self.coverage.valuation_complete or row["owner"] != "OWN":
                row["carrying_value"] = None
            result.append(row)
        return result

    def zero_items(self, rows: list[dict[str, Any]], p: dict[str, Any]) -> list[dict[str, Any]]:
        """Complete company coverage proves zero; an absent feed never calls this method."""
        present = {
            row["item_id"] for row in rows if row["owner"] == "OWN" and row["custody"] == "LOCAL"
        }
        if p.get("owner") == "THIRD_PARTY" or p.get("custody") not in {None, "LOCAL"}:
            return rows
        for key, item in sorted(self.items.items()):
            if (
                key in present
                or (p.get("item_id") and key != p["item_id"])
                or (p.get("group_id") and p["group_id"] not in self.memberships[key])
                or (not p.get("include_inactive", True) and not item.active)
            ):
                continue
            rows.append(
                {
                    "item_id": key,
                    "item_code": item.code,
                    "item_name": item.name,
                    "unit": item.unit,
                    "owner": "OWN",
                    "custody": "LOCAL",
                    "currency": self.coverage.currency,
                    "as_of": self.coverage.as_of.isoformat(),
                    **{
                        name: "0.0000"
                        for name in ("opening", "inward", "outward", "quantity", "eligible")
                    },
                    "reserved": "0.0000" if self.coverage.reservations_complete else None,
                    "available": "0.0000" if self.coverage.reservations_complete else None,
                    "carrying_value": "0.0000" if self.coverage.valuation_complete else None,
                    "reservation_status": "COMPLETE"
                    if self.coverage.reservations_complete
                    else "UNAVAILABLE",
                    "valuation_status": "COMPLETE"
                    if self.coverage.valuation_complete
                    else "UNAVAILABLE",
                }
            )
        return sorted(rows, key=lambda r: (r["item_id"], r["owner"], r["custody"]))


def calculate(
    code: str,
    records: list[dict[str, Any]],
    p: dict[str, Any],
    *,
    movements_loaded: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        return _calculate(code, Inventory(records, movements_loaded=movements_loaded), p)


def _calculate(
    code: str,
    stock: Inventory,
    p: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = stock.selected(p)
    coverage = stock.coverage
    summary = stock.zero_items(stock.summary(selected, "item_id"), p)
    rows: list[dict[str, Any]]
    if code == "STOCK_SUMMARY":
        rows = summary
    elif code == "LOCATION_STOCK":
        rows = stock.summary(selected, "location_id")
        search = p.get("search", "").strip().casefold()
        if search:
            rows = [
                row
                for row in rows
                if any(
                    search in str(row.get(key, "")).casefold()
                    for key in ("item_code", "item_name", "location_code", "location_name")
                )
            ]
    elif code == "STOCK_GROUP_SUMMARY":
        rows = stock.summary(selected, "group_id")
        search = p.get("search", "").strip().casefold()
        if search:
            rows = [
                row
                for row in rows
                if search in row["group_code"].casefold() or search in row["group_name"].casefold()
            ]
    elif code == "BATCH_SUMMARY":
        rows = []
        search = p.get("search", "").strip().casefold()
        if search:
            selected = [
                position
                for position in selected
                if any(
                    search in str(stock.label(position).get(key, "")).casefold()
                    for key in (
                        "item_code",
                        "item_name",
                        "lot_code",
                        "location_code",
                        "location_name",
                    )
                )
            ]
        for position in sorted(selected, key=lambda r: str(r.position_id)):
            item = stock.items[str(position.item_id)]
            if item.lot_tracked or item.serial_tracked:
                if p.get("serial") and p["serial"].casefold() not in {
                    serial.casefold() for serial in position.serials
                }:
                    continue
                row = stock.label(position) | {
                    "row_kind": "BATCH_POSITION",
                    "quantity": "1.0000" if p.get("serial") else position.quantity,
                    "source_position_quantity": position.quantity,
                    "serial": next(
                        (
                            serial
                            for serial in position.serials
                            if p.get("serial") and serial.casefold() == p["serial"].casefold()
                        ),
                        None,
                    ),
                    "manufacture_date": position.manufacture_date,
                    "expiry_date": position.expiry_date,
                    "serial_count": 1 if p.get("serial") else len(position.serials),
                    "serials": ", ".join(
                        serial
                        for serial in position.serials
                        if not p.get("serial") or serial.casefold() == p["serial"].casefold()
                    ),
                    "origins": ", ".join(str(o.origin_id) for o in position.origins),
                }
                rows.append(row)
        if p.get("include_history"):
            from reports.domain.reporting.inventory_trace import history

            rows.extend(history(stock, selected, p))
    elif code == "STOCK_EXPIRY":
        rows = []
        search = p.get("search", "").strip().casefold()
        if search:
            selected = [
                position
                for position in selected
                if any(
                    search in str(stock.label(position).get(key, "")).casefold()
                    for key in (
                        "item_code",
                        "item_name",
                        "lot_code",
                        "location_code",
                        "location_name",
                    )
                )
            ]
        for position in sorted(selected, key=lambda r: str(r.position_id)):
            if not number(position.quantity):
                continue
            exposure = {
                "carrying_value": fixed(number(position.carrying_value))
                if coverage.valuation_complete and position.owner == "OWN"
                else None,
                "reserved": fixed(number(position.reserved))
                if coverage.reservations_complete
                else None,
                "valuation_status": "COMPLETE"
                if coverage.valuation_complete and position.owner == "OWN"
                else "UNAVAILABLE",
                "reservation_status": "COMPLETE"
                if coverage.reservations_complete
                else "UNAVAILABLE",
            }
            if position.expiry_date is None:
                if (
                    stock.items[str(position.item_id)].lot_tracked
                    or position.minimum_remaining_days
                ):
                    rows.append(
                        stock.label(position)
                        | exposure
                        | {
                            "quantity": position.quantity,
                            "expiry_date": None,
                            "days_to_expiry": None,
                            "status": "UNKNOWN_EXPIRY",
                            "eligibility_reasons": ", ".join(stock.eligibility(position)[1]),
                        }
                    )
                continue
            days = (position.expiry_date - coverage.as_of).days
            _, reasons = stock.eligibility(position)
            expired = "EXPIRED" in reasons
            if days > p["days_ahead"] or (expired and not p["include_expired"]):
                continue
            rows.append(
                stock.label(position)
                | exposure
                | {
                    "quantity": position.quantity,
                    "expiry_date": position.expiry_date.isoformat(),
                    "days_to_expiry": days,
                    "status": "EXPIRED" if expired else "NEAR_EXPIRY",
                    "eligibility_reasons": ", ".join(reasons),
                }
            )
    elif code == "STOCK_VALUATION":
        if not coverage.valuation_complete:
            raise ValueError("complete owner valuation evidence is unavailable")
        rows = []
        controls: dict[str, Decimal] = defaultdict(Decimal)
        search = p.get("search", "").strip().casefold()
        if search:
            selected = [
                position
                for position in selected
                if any(
                    search in str(stock.label(position).get(key, "")).casefold()
                    for key in (
                        "item_code",
                        "item_name",
                        "location_code",
                        "location_name",
                        "lot_code",
                    )
                )
            ]
        for position in sorted(selected, key=lambda r: str(r.position_id)):
            if position.owner != "OWN":
                continue
            quantity, value = number(position.quantity), number(position.carrying_value)
            rows.append(
                stock.label(position)
                | {
                    "quantity": fixed(quantity),
                    "carrying_value": fixed(value),
                    "unit_cost": fixed(value / quantity) if quantity else None,
                    "costing_method": position.costing_method,
                    "account_id": str(position.control_account_id)
                    if position.control_account_id
                    else None,
                    "row_kind": "POSITION",
                    "valuation_detail_status": "COMPLETE"
                    if position.valuation_detail is not None
                    else "UNAVAILABLE",
                }
            )
            if position.control_account_id:
                controls[str(position.control_account_id)] += value
            elif coverage.gl_complete:
                raise ValueError("owned stock has no inventory control mapping")
        # A filtered inventory subset cannot be reconciled against a whole-account GL balance.
        unfiltered = not any(
            p.get(k) for k in ("item_id", "location_id", "group_id", "owner", "search")
        )
        if coverage.gl_complete and unfiltered and p.get("include_inactive", True):
            for account in sorted(controls.keys() | stock.gl.keys()):
                gl = stock.gl.get(account)
                if gl is None or gl.currency != coverage.currency:
                    raise ValueError("mapped stock-to-GL evidence is incomplete")
                value = controls[account]
                rows.append(
                    {
                        "row_kind": "GL_CONTROL",
                        "account_id": account,
                        "currency": coverage.currency,
                        "carrying_value": fixed(value),
                        "gl_balance": gl.balance,
                        "difference": fixed(value - number(gl.balance)),
                    }
                )
        if p.get("include_cost_details"):
            from reports.domain.reporting.inventory_valuation import detail_rows

            rows.extend(detail_rows(stock, selected))
    elif code == "STOCK_REORDER":
        from reports.domain.reporting.inventory_reorder import calculate as reorder

        rows, configured = reorder(stock, p)
    elif code == "STOCK_AGEING":
        if not coverage.origins_complete:
            raise ValueError("complete residual receipt-origin evidence is unavailable")
        rows = []
        search = p.get("search", "").strip().casefold()
        if search:
            selected = [
                position
                for position in selected
                if any(
                    search in str(stock.label(position).get(key, "")).casefold()
                    for key in (
                        "item_code",
                        "item_name",
                        "lot_code",
                        "location_code",
                        "location_name",
                    )
                )
            ]
        for position in sorted(selected, key=lambda r: str(r.position_id)):
            for origin in sorted(position.origins, key=lambda r: str(r.origin_id)):
                day = (
                    origin.receipt_date if p["age_basis"] == "RECEIPT" else origin.manufacture_date
                )
                age = (coverage.as_of - day).days if day else None
                lower = 0
                bucket = "UNKNOWN"
                if age is not None:
                    for upper in p["buckets"]:
                        if age < upper:
                            bucket = f"{lower}-{upper - 1}"
                            break
                        lower = upper
                    else:
                        bucket = f"{lower}+"
                rows.append(
                    stock.label(position)
                    | {
                        "origin_id": str(origin.origin_id),
                        "quantity": origin.quantity,
                        "origin_date": day.isoformat() if day else None,
                        "age_days": age,
                        "age_bucket": bucket,
                        "age_basis": p["age_basis"],
                        "provenance": origin.provenance,
                    }
                )
    elif code in {"ITEM_LEDGER", "STOCK_MOVEMENT"}:
        if code == "STOCK_MOVEMENT" and p.get("search", "").strip():
            search = p["search"].strip().casefold()
            summary = [
                row
                for row in summary
                if any(
                    search in str(row.get(key, "")).casefold() for key in ("item_code", "item_name")
                )
            ]
        if not coverage.movements_complete:
            raise ValueError("complete retained stock movement history is unavailable")
        start = dt.date.fromisoformat(p["date_from"])
        if start < coverage.history_start:
            raise ValueError("movement period predates retained stock history")
        keys = {str(position.position_id) for position in selected}
        movements = sorted(
            (m for m in stock.movements if str(m.position_id) in keys),
            key=lambda m: (m.effective_date, m.sequence, str(m.movement_id)),
        )
        rows = []
        if code == "ITEM_LEDGER":
            # Keep distinct physical dimensions; running totals never mix owners/units/locations.
            running: dict[str, Decimal] = defaultdict(Decimal)
            running_value: dict[str, Decimal] = defaultdict(Decimal)
            for m in movements:
                if m.effective_date < start:
                    running[str(m.position_id)] += number(m.quantity_delta)
                    if (
                        coverage.valuation_complete
                        and stock.positions[str(m.position_id)].owner == "OWN"
                    ):
                        running_value[str(m.position_id)] += number(m.value_delta)
            for key in sorted(keys):
                rows.append(
                    stock.label(stock.positions[key])
                    | {
                        "row_kind": "OPENING",
                        "date": start.isoformat(),
                        "inward": "0.0000",
                        "outward": "0.0000",
                        "balance": fixed(running[key]),
                        "value_delta": "0.0000"
                        if coverage.valuation_complete and stock.positions[key].owner == "OWN"
                        else None,
                        "value_balance": fixed(running_value[key])
                        if coverage.valuation_complete and stock.positions[key].owner == "OWN"
                        else None,
                    }
                )
            for m in movements:
                if m.effective_date < start:
                    continue
                quantity = number(m.quantity_delta)
                running[str(m.position_id)] += quantity
                valued = (
                    coverage.valuation_complete
                    and stock.positions[str(m.position_id)].owner == "OWN"
                )
                if valued:
                    running_value[str(m.position_id)] += number(m.value_delta)
                rows.append(
                    stock.label(stock.positions[str(m.position_id)])
                    | {
                        "row_kind": "MOVEMENT",
                        "date": m.effective_date.isoformat(),
                        "movement_id": str(m.movement_id),
                        "voucher_id": str(m.voucher_id),
                        "voucher_number": m.voucher_number,
                        "action": m.action,
                        "inward": fixed(max(ZERO, quantity)),
                        "outward": fixed(max(ZERO, -quantity)),
                        "balance": fixed(running[str(m.position_id)]),
                        "value_delta": fixed(number(m.value_delta)) if valued else None,
                        "value_balance": fixed(running_value[str(m.position_id)])
                        if valued
                        else None,
                    }
                )
        else:
            by_item: dict[str, list[Movement]] = defaultdict(list)
            for m in movements:
                by_item[str(m.item_id)].append(m)
            for row in summary:
                matching = [
                    m
                    for m in by_item[row["item_id"]]
                    if stock.positions[str(m.position_id)].owner == row["owner"]
                    and stock.positions[str(m.position_id)].custody == row["custody"]
                ]
                genuine = [
                    m.effective_date for m in matching if m.action in {"SALE", "CONSUMPTION"}
                ]
                last = max(genuine) if genuine else None
                # No historical consumption is not evidence of age since purchase.
                days_without = (coverage.as_of - last).days if last else None
                boundary = coverage.as_of - dt.timedelta(days=p["nonmoving_days"])
                history_known = last is not None or coverage.history_start <= boundary
                nonmoving = (
                    (days_without is None or days_without >= p["nonmoving_days"])
                    if history_known
                    else None
                )
                if p["only_nonmoving"] and nonmoving is not True:
                    continue
                window = [m for m in matching if m.effective_date >= start]
                action_totals: dict[str, Decimal] = defaultdict(Decimal)
                for m in window:
                    action_totals[m.action] += abs(number(m.quantity_delta))
                valued = coverage.valuation_complete and row["owner"] == "OWN"
                rows.append(
                    row
                    | {
                        "opening_value": fixed(
                            sum(
                                (
                                    number(m.value_delta)
                                    for m in matching
                                    if m.effective_date < start
                                ),
                                ZERO,
                            )
                        )
                        if valued
                        else None,
                        "inward_value": fixed(
                            sum((max(ZERO, number(m.value_delta)) for m in window), ZERO)
                        )
                        if valued
                        else None,
                        "outward_value": fixed(
                            sum((max(ZERO, -number(m.value_delta)) for m in window), ZERO)
                        )
                        if valued
                        else None,
                        "closing_value": row["carrying_value"] if valued else None,
                        "opening": fixed(
                            sum(
                                (
                                    number(m.quantity_delta)
                                    for m in matching
                                    if m.effective_date < start
                                ),
                                ZERO,
                            )
                        ),
                        "inward": fixed(
                            sum((max(ZERO, number(m.quantity_delta)) for m in window), ZERO)
                        ),
                        "outward": fixed(
                            sum((max(ZERO, -number(m.quantity_delta)) for m in window), ZERO)
                        ),
                        "receipts": fixed(action_totals["RECEIPT"]),
                        "sales": fixed(action_totals["SALE"]),
                        "consumption": fixed(action_totals["CONSUMPTION"]),
                        "customer_returns": fixed(action_totals["CUSTOMER_RETURN"]),
                        "supplier_returns": fixed(action_totals["SUPPLIER_RETURN"]),
                        "transfer_in": fixed(action_totals["TRANSFER_IN"]),
                        "transfer_out": fixed(action_totals["TRANSFER_OUT"]),
                        "last_consumption_date": last.isoformat() if last else None,
                        "days_without_consumption": days_without,
                        "nonmoving": nonmoving,
                        "history_status": "COMPLETE" if history_known else "INSUFFICIENT_HISTORY",
                    }
                )
    else:
        raise ValueError("unknown inventory report")
    for row in rows:
        row.setdefault("row_kind", code)
        row.setdefault("period", "CURRENT")
        # Typed dates in source-only views must cross the result boundary as JSON strings.
        for key, value in row.items():
            if isinstance(value, dt.date):
                row[key] = value.isoformat()
    evidence = {
        "inventory_coverage": coverage.model_dump(mode="json"),
        "row_count": len(rows),
        "source_identity": fingerprint(coverage.model_dump(mode="json")),
        "classification_semantics": "PINNED_SNAPSHOT",
        "scope": "FILTERED"
        if any(
            p.get(k)
            for k in (
                "item_id",
                "location_id",
                "group_id",
                "owner",
                "lot_id",
                "serial",
                "search",
                "custody",
            )
        )
        else ("COMPLETE_COMPANY" if p.get("include_inactive", True) else "FILTERED"),
        "quantity_totals": "PER_UNIT_OWNER_CUSTODY",
        "group_totals": "OVERLAPPING_GROUP_ROWS_MUST_NOT_BE_SUMMED",
    }
    if code == "STOCK_SUMMARY":
        if not p.get("include_zero", True):
            evidence["scope"] = "FILTERED"
        search = p.get("search", "").strip().casefold()
        rows = [
            r
            for r in rows
            if (
                not search
                or search in r["item_code"].casefold()
                or search in r["item_name"].casefold()
            )
            and (p.get("include_zero", True) or number(r["quantity"]) != ZERO)
        ]
        column = {
            "ITEM_CODE": "item_code",
            "ITEM_NAME": "item_name",
            "QUANTITY": "quantity",
            "VALUE": "carrying_value",
        }.get(p.get("sort", "ITEM_CODE"), "item_code")
        rows.sort(key=lambda r: (r["item_id"], r["owner"], r["custody"]))
        known = [r for r in rows if r[column] is not None]
        unknown = [r for r in rows if r[column] is None]
        known.sort(
            key=lambda r: number(r[column])
            if column in {"quantity", "carrying_value"}
            else r[column].casefold(),
            reverse=p.get("descending", False),
        )
        rows = known + unknown
        quantities: dict[tuple[str, str, str], dict[str, Any]] = {}
        owned_value: Decimal | None = ZERO
        for row in rows:
            unit_scope = (row["unit"], row["owner"], row["custody"])
            metric_totals = quantities.setdefault(
                unit_scope,
                {
                    "unit": unit_scope[0],
                    "owner": unit_scope[1],
                    "custody": unit_scope[2],
                    **{
                        k: ZERO
                        for k in (
                            "opening",
                            "inward",
                            "outward",
                            "quantity",
                            "eligible",
                            "reserved",
                            "available",
                        )
                    },
                },
            )
            for metric in (
                "opening",
                "inward",
                "outward",
                "quantity",
                "eligible",
                "reserved",
                "available",
            ):
                metric_totals[metric] = (
                    None
                    if metric_totals[metric] is None or row[metric] is None
                    else metric_totals[metric] + number(row[metric])
                )
            if row["owner"] == "OWN":
                owned_value = (
                    None
                    if owned_value is None or row["carrying_value"] is None
                    else owned_value + number(row["carrying_value"])
                )
        evidence["row_count"] = len(rows)
        evidence["stock_summary"] = {
            "item_count": len({r["item_id"] for r in rows}),
            "row_count": len(rows),
            "owned_value": fixed(owned_value) if owned_value is not None else None,
            "currency": coverage.currency,
            "quantities": [
                {k: fixed(v) if isinstance(v, Decimal) else v for k, v in unit_totals.items()}
                for _, unit_totals in sorted(quantities.items())
            ],
            "unavailable_value_rows": sum(
                r["owner"] == "OWN" and r["carrying_value"] is None for r in rows
            ),
            "unavailable_availability_rows": sum(r["available"] is None for r in rows),
            "filters": {
                **({"Item": stock.items[p["item_id"]].name} if p.get("item_id") else {}),
                **(
                    {"Warehouse": stock.locations[p["location_id"]].name}
                    if p.get("location_id")
                    else {}
                ),
                **({"Item group": stock.groups[p["group_id"]].name} if p.get("group_id") else {}),
                **({"Search": search} if search else {}),
                "Include zero stock": "Yes" if p.get("include_zero", True) else "No",
                "Include inactive items": "Yes" if p.get("include_inactive", True) else "No",
            },
        }
    if code == "ITEM_LEDGER":
        from reports.domain.reporting.inventory_metrics import ledger

        evidence["inventory_metrics"] = ledger(rows, coverage.currency)
    elif code == "LOCATION_STOCK":
        from reports.domain.reporting.inventory_metrics import balances

        evidence["inventory_metrics"] = balances(code, rows, coverage.currency)
    elif code == "STOCK_MOVEMENT":
        from reports.domain.reporting.inventory_metrics import balances

        inventory_stats = balances(code, rows, coverage.currency)
        inventory_stats.update(
            nonmoving_count=sum(row["nonmoving"] is True for row in rows),
            unknown_count=sum(row["nonmoving"] is None for row in rows),
        )
        inventory_stats["quantities"] = [
            {
                key: value
                for key, value in row.items()
                if key not in {"eligible", "reserved", "available"}
            }
            for row in inventory_stats["quantities"]
        ]
        evidence["inventory_metrics"] = inventory_stats
    elif code == "STOCK_GROUP_SUMMARY":
        from reports.domain.reporting.inventory_metrics import balances

        groups = {row["group_id"] for row in rows}
        positions = [
            position
            for position in selected
            if stock.memberships[str(position.item_id)] & groups
            or (not stock.memberships[str(position.item_id)] and None in groups)
        ]
        inventory_stats = balances(code, stock.summary(positions, "item_id"), coverage.currency)
        inventory_stats.update(
            group_count=len(groups), row_count=len(rows), aggregation="DISTINCT_POSITIONS"
        )
        evidence["inventory_metrics"] = inventory_stats
    elif code == "STOCK_VALUATION":
        from reports.domain.reporting.inventory_metrics import balances

        inventory_stats = balances(
            code, [row for row in rows if row["row_kind"] == "POSITION"], coverage.currency
        )
        inventory_stats.update(
            balance_count=inventory_stats["row_count"],
            row_count=len(rows),
            control_count=sum(row["row_kind"] == "GL_CONTROL" for row in rows),
            detail_count=sum(row["row_kind"] in {"COST_LAYER", "COST_POOL"} for row in rows),
        )
        evidence["inventory_metrics"] = inventory_stats
    elif code == "STOCK_AGEING":
        from reports.domain.reporting.inventory_metrics import balances

        inventory_stats = balances(code, rows, coverage.currency)
        bands: dict[tuple[str, str, str, str], Decimal] = defaultdict(Decimal)
        for row in rows:
            bands[(row["unit"], row["owner"], row["custody"], row["age_bucket"])] += number(
                row["quantity"]
            )
        inventory_stats.update(
            cohort_count=len(rows),
            unknown_count=sum(row["age_days"] is None for row in rows),
            assumed_count=sum(row["provenance"] == "ASSUMED" for row in rows),
            age_basis=p["age_basis"],
            age_buckets=[
                {
                    "unit": key[0],
                    "owner": key[1],
                    "custody": key[2],
                    "band": key[3],
                    "quantity": fixed(value),
                }
                for key, value in sorted(bands.items())
            ],
        )
        evidence["inventory_metrics"] = inventory_stats
    elif code == "STOCK_EXPIRY":
        from reports.domain.reporting.inventory_metrics import balances

        rows.sort(
            key=lambda row: (
                row["expiry_date"] is None,
                row["expiry_date"] or "",
                row["item_code"],
                row.get("lot_code") or "",
                row["location_id"],
                row["position_id"],
            )
        )
        inventory_stats = balances(code, rows, coverage.currency)
        inventory_stats.update(
            expired_count=sum(row["status"] == "EXPIRED" for row in rows),
            near_expiry_count=sum(row["status"] == "NEAR_EXPIRY" for row in rows),
            unknown_expiry_count=sum(row["status"] == "UNKNOWN_EXPIRY" for row in rows),
        )
        evidence["inventory_metrics"] = inventory_stats
    elif code == "BATCH_SUMMARY":
        from reports.domain.reporting.inventory_metrics import balances

        physical = [row for row in rows if row["row_kind"] == "BATCH_POSITION"]
        inventory_stats = balances(code, physical, coverage.currency)
        inventory_stats.update(
            balance_count=len(physical),
            row_count=len(rows),
            batch_count=len({row["lot_id"] for row in physical if row.get("lot_id")}),
            serial_count=sum(row["serial_count"] for row in physical),
            history_count=len(rows) - len(physical),
        )
        evidence["inventory_metrics"] = inventory_stats
    if code == "STOCK_REORDER":
        from reports.domain.reporting.inventory_metrics import balances

        inventory_stats = balances(code, rows, coverage.currency)
        inventory_stats.update(
            configured_count=configured,
            shortage_count=sum(number(row["shortage"]) > ZERO for row in rows),
            limited_count=sum(number(row["shortfall_after_order"]) > ZERO for row in rows),
            quantity_basis=p.get("quantity_basis", "AVAILABLE"),
        )
        # Company and warehouse bands can overlap; their stock quantities are not additive.
        inventory_stats["quantities"] = []
        inventory_stats["owned_value"] = None
        evidence["inventory_metrics"] = inventory_stats
    return rows, evidence
