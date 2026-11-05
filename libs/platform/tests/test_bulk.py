from typing import Any

import pytest
from pydantic import ValidationError

from billing_platform.bulk import (
    BulkBatch,
    BulkRecord,
    BulkTarget,
    ordered_records,
    references,
    resolve_references,
    selection_digest,
)


def record(key: str, **values: Any) -> BulkRecord:
    return BulkRecord(key=key, change_set=key, resource="unit", **values)


def test_exact_envelope_and_dependency_order() -> None:
    child = record("child", data={"id": {"$ref": "parent", "field": "family.id"}})
    parent = record("parent")
    batch = BulkBatch(records=[child, parent])
    assert [row.key for row in ordered_records(batch.records)] == ["parent", "child"]
    assert references([None, 2, {"a": [{"$ref": "parent", "field": "id"}]}]) == {"parent"}
    assert resolve_references(child.data, {"parent": {"family": {"id": "known"}}}) == {
        "id": "known"
    }
    assert resolve_references([False, {"x": 1}], {}) == [False, {"x": 1}]
    assert selection_digest({"a": 1, "b": "1.0000"}) == selection_digest({"b": "1.0000", "a": 1})
    assert BulkTarget(external_system="owner", external_key="00012").external_key == "00012"


@pytest.mark.parametrize(
    "value",
    [
        {"$ref": "a"},
        {"$ref": "a", "field": "id", "extra": 1},
        {"$ref": 1, "field": "id"},
        {"$ref": "!", "field": "id"},
        {"$ref": "a", "field": 1},
        {"$ref": "a", "field": "../secret"},
    ],
)
def test_reference_shape_is_closed(value: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="staged reference"):
        references(value)


@pytest.mark.parametrize("value", [None, [], {}, 1.5])
def test_reference_cannot_select_objects_or_inexact_values(value: Any) -> None:
    with pytest.raises(ValueError, match="scalar"):
        resolve_references({"$ref": "a", "field": "id"}, {"a": {"id": value}})


def test_duplicate_unknown_and_cyclic_dependencies_are_rejected() -> None:
    for rows in (
        [record("a"), record("a")],
        [record("a", depends_on=["missing"])],
        [record("a", depends_on=["b"]), record("b", depends_on=["a"])],
        [record("a", depends_on=["a"])],
    ):
        with pytest.raises(ValueError):
            ordered_records(rows)
    a = record("a")
    b = record("b", depends_on=["a"])
    c = record("c", depends_on=["b"])
    c.change_set = "a"
    with pytest.raises(ValueError, match="change sets are cyclic"):
        ordered_records([a, b, c])
    rows = [record(str(i), depends_on=[str(i - 1)] if i else []) for i in range(33)]
    with pytest.raises(ValueError, match="depth"):
        ordered_records(rows)


def test_input_native_shapes_and_atomic_bounds() -> None:
    for fields in (
        {"depends_on": ["a", "a"]},
        {"depends_on": ["bad key"]},
        {"clear_fields": ["name", "name"]},
        {"clear_fields": ["../name"]},
        {"clear_fields": ["name"], "data": {"name": "both"}},
        {"data": {"amount": 1.5}},
    ):
        with pytest.raises(ValueError):
            record("a", **fields)
    for target_fields in ({"id": "00000000-0000-0000-0000-000000000000"}, {"external_key": "x"}):
        with pytest.raises(ValueError):
            BulkTarget.model_validate(target_fields)
    with pytest.raises(ValidationError):
        BulkBatch(records=[])
    with pytest.raises(ValueError, match="100 aggregates"):
        BulkBatch(records=[record(str(i)) for i in range(101)], atomicity="ATOMIC")
    rows = [record(str(i)) for i in range(101)]
    for row in rows:
        row.change_set = "same"
    with pytest.raises(ValueError, match="100 commands"):
        BulkBatch(records=rows)
