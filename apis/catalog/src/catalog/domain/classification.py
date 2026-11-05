"""Dated operational groups and independent merchandising category cardinality."""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from billing_platform.errors import ValidationFailedError
from billing_platform.statutory import assert_window_ordered

MAX_DEPTH = 8
MAX_GRAPH_ROWS = 10000
MAX_PATH_CHECKS = 100000
KINDS = {
    "GOODS": frozenset({"GOODS"}),
    "SERVICE": frozenset({"SERVICE"}),
    "BOTH": frozenset({"GOODS", "SERVICE"}),
}


@dataclass(frozen=True, slots=True)
class GroupNode:
    id: uuid.UUID
    company_id: uuid.UUID
    allowed_kind: Literal["GOODS", "SERVICE", "BOTH"]

    def __post_init__(self) -> None:
        if self.id.int == 0 or self.company_id.int == 0 or self.allowed_kind not in KINDS:
            raise ValidationFailedError("invalid group identity or allowed product kind")


@dataclass(frozen=True, slots=True)
class ParentInterval:
    group_id: uuid.UUID
    parent_group_id: uuid.UUID | None
    valid_from: dt.date
    valid_to: dt.date | None = None

    def __post_init__(self) -> None:
        if self.group_id.int == 0 or (self.parent_group_id and self.parent_group_id.int == 0):
            raise ValidationFailedError("group hierarchy requires real identities")
        if type(self.valid_from) is not dt.date or (
            self.valid_to is not None and type(self.valid_to) is not dt.date
        ):
            raise ValidationFailedError("group hierarchy uses business dates")
        assert_window_ordered(self.valid_from, self.valid_to, what="group parent interval")


def validate_group_history(
    nodes: tuple[GroupNode, ...],
    edges: tuple[ParentInterval, ...],
    *,
    company_id: uuid.UUID,
) -> None:
    """Sweep each changed date, checking only affected descendants and ancestor paths.

    An explicit root interval terminates ancestry; an absent interval never silently
    becomes a root. Removals precede all additions at a boundary, so adjacent dated
    reparentings are validated together. Work is bounded for the synchronous path.
    """
    if len(nodes) > MAX_GRAPH_ROWS or len(edges) > MAX_GRAPH_ROWS:
        raise ValidationFailedError("hierarchy requires the larger reviewed job workflow")
    by_id = {node.id: node for node in nodes}
    if (
        company_id.int == 0
        or len(by_id) != len(nodes)
        or any(node.company_id != company_id for node in nodes)
    ):
        raise ValidationFailedError("group hierarchy crosses or duplicates its company scope")
    by_group: dict[uuid.UUID, list[ParentInterval]] = defaultdict(list)
    additions: dict[dt.date, list[ParentInterval]] = defaultdict(list)
    removals: dict[dt.date, list[uuid.UUID]] = defaultdict(list)
    for edge in edges:
        if edge.group_id not in by_id or (
            edge.parent_group_id is not None and edge.parent_group_id not in by_id
        ):
            raise ValidationFailedError("unknown group in hierarchy")
        if (
            edge.parent_group_id is not None
            and not KINDS[by_id[edge.group_id].allowed_kind]
            <= KINDS[by_id[edge.parent_group_id].allowed_kind]
        ):
            raise ValidationFailedError("child group kind exceeds its parent's allowed kinds")
        by_group[edge.group_id].append(edge)
        additions[edge.valid_from].append(edge)
        if edge.valid_to is not None and edge.valid_to < dt.date.max:
            removals[edge.valid_to + dt.timedelta(days=1)].append(edge.group_id)
    for intervals in by_group.values():
        ordered = sorted(intervals, key=lambda edge: edge.valid_from)
        for previous, current in pairwise(ordered):
            if previous.valid_to is None or current.valid_from <= previous.valid_to:
                raise ValidationFailedError("group has overlapping parent intervals")
    parents: dict[uuid.UUID, uuid.UUID | None] = {}
    children: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    checks = 0
    for day in sorted(set(additions) | set(removals)):
        changed = set(removals[day]) | {edge.group_id for edge in additions[day]}
        for group in removals[day]:
            old = parents.pop(group)
            if old is not None:
                children[old].remove(group)
        for edge in additions[day]:
            parents[edge.group_id] = edge.parent_group_id
            if edge.parent_group_id is not None:
                children[edge.parent_group_id].add(edge.group_id)
        affected = set(changed)
        frontier = list(changed)
        while frontier:
            for child in children[frontier.pop()]:
                if child not in affected:
                    affected.add(child)
                    frontier.append(child)
        for group in affected:
            if group not in parents:
                continue  # expired node; its remaining descendants are checked separately
            checks += 1
            if checks > MAX_PATH_CHECKS:
                raise ValidationFailedError("hierarchy requires the larger reviewed job workflow")
            ancestors: set[uuid.UUID] = set()
            current_group: uuid.UUID | None = group
            while current_group is not None:
                if current_group in ancestors:
                    raise ValidationFailedError("group hierarchy contains a dated cycle")
                ancestors.add(current_group)
                if len(ancestors) > MAX_DEPTH:
                    raise ValidationFailedError("group hierarchy exceeds maximum depth 8")
                if current_group not in parents:
                    raise ValidationFailedError(
                        "parent hierarchy is unavailable on an effective date"
                    )
                current_group = parents[current_group]


@dataclass(frozen=True, slots=True)
class CategorySelection:
    category_id: uuid.UUID
    scheme_id: uuid.UUID
    is_primary: bool = False


def validate_category_selection(
    selections: tuple[CategorySelection, ...],
    *,
    schemes: dict[uuid.UUID, Literal["SINGLE", "MULTIPLE"]],
    categories: dict[uuid.UUID, uuid.UUID],
) -> None:
    """Inputs are already company-scoped authoritative master identities."""
    if len(selections) > 256 or len({row.category_id for row in selections}) != len(selections):
        raise ValidationFailedError("duplicate or excessive category selections")
    grouped: dict[uuid.UUID, list[CategorySelection]] = defaultdict(list)
    for row in selections:
        if row.scheme_id not in schemes or categories.get(row.category_id) != row.scheme_id:
            raise ValidationFailedError("category does not belong to the selected scheme")
        if row.category_id.int == 0 or row.scheme_id.int == 0 or type(row.is_primary) is not bool:
            raise ValidationFailedError("invalid category selection")
        grouped[row.scheme_id].append(row)
    for scheme, rows in grouped.items():
        if schemes[scheme] not in {"SINGLE", "MULTIPLE"}:
            raise ValidationFailedError("unsupported category scheme cardinality")
        if schemes[scheme] == "SINGLE" and len(rows) > 1:
            raise ValidationFailedError("single-membership scheme accepts one category")
        if sum(row.is_primary for row in rows) > 1:
            raise ValidationFailedError("scheme has more than one primary category")
