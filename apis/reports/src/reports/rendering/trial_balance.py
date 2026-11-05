"""Streaming presentation over preorder frozen rows, with full leaf-side totals."""

from typing import Any

from reports.domain.reporting.contracts import Column
from reports.schemas.trial_balance_options import TrialPresentation


def columns(selected: tuple[Column, ...], format_name: str) -> tuple[Column, ...]:
    if format_name not in {"CSV", "XLSX"}:
        return selected
    return (
        Column("row_kind", "Row type", "TEXT", nullable=False),
        Column("depth", "Hierarchy level", "INTEGER", nullable=False),
        Column("code", "Account / group code", "TEXT", nullable=False),
        Column("parent_key", "Parent reference", "IDENTIFIER", nullable=False),
        *selected,
    )


class Selection:
    """A depth stack bounds memory by ancestry, never by all accounts or UI pages."""

    def __init__(self, options: TrialPresentation):
        self.options = options
        self.expanded = set(options.expanded)
        self.collapsed = set(options.collapsed)
        self.parents: list[bool] = []

    def rows(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for raw in values:
            if raw["period"] != self.options.period:
                continue
            if raw["row_kind"] == "TRIAL_BALANCE_CONTROL":
                result.append(
                    raw | {"name": "Grand total", "code": "TOTAL", "depth": 0, "parent_key": "root"}
                )
                continue
            depth = raw["depth"]
            self.parents = self.parents[:depth]
            visible = all(self.parents) and (self.options.show_zero or not raw["is_zero"])
            key = raw["node_key"]
            opened = key not in self.collapsed and (
                key in self.expanded
                or self.options.level == "LEDGERS"
                or (self.options.level == "GROUPS" and raw["row_kind"] == "HEAD")
                or (self.options.level == "ALL_GROUPS" and raw["group_child_count"] > 0)
            )
            self.parents.append(visible and opened)
            if self.options.hierarchy == "ALL":
                visible = self.options.show_zero or not raw["is_zero"]
            if visible:
                result.append(raw | {"name": "\u00a0" * (min(depth, 40) * 2) + raw["name"]})
        return result
