import datetime as dt
from typing import Any, cast

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.domain import classification
from catalog.domain.classification import (
    CategorySelection,
    GroupNode,
    ParentInterval,
    validate_category_selection,
    validate_group_history,
)

START = dt.date(2025, 1, 1)
END = dt.date(2025, 1, 31)
NEXT = dt.date(2025, 2, 1)


def test_dated_parent_changes_preserve_history_and_allow_atomic_boundary_moves() -> None:
    company, a, b, c = uuid7(), uuid7(), uuid7(), uuid7()
    nodes = tuple(GroupNode(node, company, "BOTH") for node in (a, b, c))
    # Reverse the first two nodes' relationship on an adjacent day, atomically.
    edges = (
        ParentInterval(a, None, START, END),
        ParentInterval(b, a, START, END),
        ParentInterval(a, b, NEXT),
        ParentInterval(b, None, NEXT),
        ParentInterval(c, b, START),
    )
    validate_group_history(nodes, edges, company_id=company)
    validate_group_history(nodes, (), company_id=company)
    validate_group_history(
        nodes, (ParentInterval(a, None, START, dt.date.max),), company_id=company
    )


def test_future_cycle_and_ancestry_gap_reject_even_when_today_is_valid() -> None:
    company, a, b, c = uuid7(), uuid7(), uuid7(), uuid7()
    nodes = tuple(GroupNode(node, company, "BOTH") for node in (a, b, c))
    with pytest.raises(ValidationFailedError, match="cycle"):
        validate_group_history(
            nodes,
            (
                ParentInterval(a, None, START, END),
                ParentInterval(a, c, NEXT),
                ParentInterval(b, a, START),
                ParentInterval(c, b, START),
            ),
            company_id=company,
        )
    with pytest.raises(ValidationFailedError, match="unavailable"):
        validate_group_history(
            nodes,
            (ParentInterval(a, None, START, END), ParentInterval(b, a, START)),
            company_id=company,
        )
    with pytest.raises(ValidationFailedError, match="unavailable"):
        validate_group_history(
            nodes, (ParentInterval(a, None, NEXT), ParentInterval(b, a, START)), company_id=company
        )
    validate_group_history(
        nodes,
        (ParentInterval(a, None, START, END), ParentInterval(b, a, START, END)),
        company_id=company,
    )


def test_depth_limit_checks_descendants_after_parent_move() -> None:
    company = uuid7()
    nodes = tuple(GroupNode(uuid7(), company, "BOTH") for _ in range(9))
    edges = tuple(
        ParentInterval(node.id, nodes[index - 1].id if index else None, START)
        for index, node in enumerate(nodes)
    )
    validate_group_history(nodes[:8], edges[:8], company_id=company)
    with pytest.raises(ValidationFailedError, match="depth 8"):
        validate_group_history(nodes, edges, company_id=company)


def test_group_scope_kinds_overlap_and_unknown_nodes() -> None:
    company, other, a, b = uuid7(), uuid7(), uuid7(), uuid7()
    nodes = (GroupNode(a, company, "GOODS"), GroupNode(b, company, "SERVICE"))
    with pytest.raises(ValidationFailedError, match="kind"):
        validate_group_history(nodes, (ParentInterval(a, b, START),), company_id=company)
    same = (nodes[0], GroupNode(b, company, "GOODS"))
    for edges in [
        (ParentInterval(a, None, START), ParentInterval(a, None, NEXT)),
        (ParentInterval(a, None, START, END), ParentInterval(a, None, END)),
    ]:
        with pytest.raises(ValidationFailedError, match="overlapping"):
            validate_group_history(same, edges, company_id=company)
    with pytest.raises(ValidationFailedError, match="scope"):
        validate_group_history(nodes, (), company_id=other)
    with pytest.raises(ValidationFailedError, match="scope"):
        validate_group_history((nodes[0], nodes[0]), (), company_id=company)
    for edge in (ParentInterval(uuid7(), None, START), ParentInterval(a, uuid7(), START)):
        with pytest.raises(ValidationFailedError, match="unknown"):
            validate_group_history(same, (edge,), company_id=company)
    with pytest.raises(ValidationFailedError, match="cycle"):
        validate_group_history(same, (ParentInterval(a, a, START),), company_id=company)


def test_group_input_and_work_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    company, group = uuid7(), uuid7()
    nil = uuid.UUID(int=0)
    for arguments in [(nil, company, "BOTH"), (group, nil, "BOTH"), (group, company, "UNKNOWN")]:
        with pytest.raises(ValidationFailedError):
            GroupNode(*cast(Any, arguments))
    for edge_arguments in [
        (nil, None, START, None),
        (group, nil, START, None),
        (group, None, dt.datetime.now(dt.UTC), None),
        (group, None, START, dt.datetime.now(dt.UTC)),
        (group, None, NEXT, END),
    ]:
        with pytest.raises(ValidationFailedError):
            ParentInterval(*cast(Any, edge_arguments))
    node = GroupNode(group, company, "BOTH")
    with pytest.raises(ValidationFailedError, match="job"):
        validate_group_history((node,) * 10001, (), company_id=company)
    with pytest.raises(ValidationFailedError, match="job"):
        validate_group_history(
            (node,), (ParentInterval(group, None, START),) * 10001, company_id=company
        )
    with pytest.raises(ValidationFailedError, match="scope"):
        validate_group_history((), (), company_id=nil)
    monkeypatch.setattr(classification, "MAX_PATH_CHECKS", 1)
    with pytest.raises(ValidationFailedError, match="job"):
        validate_group_history(
            (node,),
            (ParentInterval(group, None, START, END), ParentInterval(group, None, NEXT)),
            company_id=company,
        )


def test_independent_category_schemes_cardinality_and_primary() -> None:
    first, second, a, b, c = (uuid7() for _ in range(5))
    schemes = {first: cast(Any, "MULTIPLE"), second: cast(Any, "SINGLE")}
    categories = {a: first, b: first, c: second}
    selections = (
        CategorySelection(a, first, True),
        CategorySelection(b, first),
        CategorySelection(c, second, True),
    )
    validate_category_selection(selections, schemes=schemes, categories=categories)
    validate_category_selection((), schemes=schemes, categories=categories)
    invalid = [
        (selections[0], selections[0]),
        (CategorySelection(a, first, True), CategorySelection(b, first, True)),
        (CategorySelection(a, second),),
        (CategorySelection(a, uuid7()),),
    ]
    for selected in invalid:
        with pytest.raises(ValidationFailedError):
            validate_category_selection(selected, schemes=schemes, categories=categories)
    with pytest.raises(ValidationFailedError, match="single-membership"):
        validate_category_selection(
            selections[:2], schemes={first: "SINGLE"}, categories=categories
        )
    with pytest.raises(ValidationFailedError, match="unsupported"):
        validate_category_selection(
            selections[:1], schemes={first: cast(Any, "UNKNOWN")}, categories=categories
        )
    with pytest.raises(ValidationFailedError, match="excessive"):
        validate_category_selection((selections[0],) * 257, schemes=schemes, categories=categories)
    with pytest.raises(ValidationFailedError, match="invalid category"):
        validate_category_selection(
            (CategorySelection(a, first, cast(Any, 1)),), schemes=schemes, categories=categories
        )
