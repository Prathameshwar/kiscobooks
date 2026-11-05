"""The department materialized-path rules, tested with no database (CLAUDE.md §7)."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.errors import ValidationFailedError

from identity.domain import department_tree as dt


def test_root_path_is_own_id() -> None:
    root = uuid.UUID(int=1)
    assert dt.child_path(None, root) == f"/{root.hex}/"
    assert dt.depth(dt.child_path(None, root)) == 1


def test_child_appends_to_parent() -> None:
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    root = dt.child_path(None, a)
    child = dt.child_path(root, b)
    assert child == f"/{a.hex}/{b.hex}/"
    assert dt.depth(child) == 2
    assert dt.is_ancestor_or_self(root, child)
    assert dt.is_ancestor_or_self(child, child)
    assert not dt.is_ancestor_or_self(child, root)


def test_depth_cap_is_enforced() -> None:
    path = "/" + "/".join(uuid.UUID(int=i).hex for i in range(dt.MAX_DEPTH)) + "/"
    dt.assert_within_depth(path)  # exactly MAX_DEPTH is allowed
    too_deep = "/" + "/".join(uuid.UUID(int=i).hex for i in range(dt.MAX_DEPTH + 1)) + "/"
    with pytest.raises(ValidationFailedError):
        dt.assert_within_depth(too_deep)


def test_reparent_under_own_descendant_is_a_cycle() -> None:
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    root = dt.child_path(None, a)
    child = dt.child_path(root, b)
    assert dt.would_create_cycle(moving_path=root, new_parent_path=child)
    assert not dt.would_create_cycle(moving_path=child, new_parent_path=root)


def test_rewritten_path_moves_only_the_prefix() -> None:
    a, b, c = (uuid.UUID(int=i) for i in (1, 2, 3))
    old_root = dt.child_path(None, a)  # /a/
    moving = dt.child_path(old_root, b)  # /a/b/
    grandchild = dt.child_path(moving, c)  # /a/b/c/
    new_parent = dt.child_path(None, uuid.UUID(int=9))  # /9/
    new_moving = dt.child_path(new_parent, b)  # /9/b/

    rewritten = dt.rewritten_path(old_prefix=moving, new_prefix=new_moving, path=grandchild)
    assert rewritten == f"{new_moving}{c.hex}/"
    assert dt.is_ancestor_or_self(new_parent, rewritten)
