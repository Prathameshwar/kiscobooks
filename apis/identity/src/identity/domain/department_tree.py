"""The department materialized-path rules.

docs/org-model.md §2.4, docs/identity-db-plan.md §8 (resolved: cap 6). A department's
``path`` is ``/<ancestor-id-hex>/…/<own-id-hex>/`` — a string that makes ancestor-or-self
resolution an indexed prefix test instead of a recursive CTE on every permission check.

The rules here are framework- and ORM-free (CLAUDE.md §4): the caller passes the parent's
path and the child's id and gets back the string to store, and passes two paths to ask
whether one contains the other. Path maintenance across a reparent — rewriting the moved
subtree's prefixes — is likewise a pure string transform the route applies to the rows it
has loaded.
"""

from __future__ import annotations

import uuid

from billing_platform.errors import ValidationFailedError

#: The deepest a department may nest (identity-db-plan §8, resolved). A cost-centre tree
#: past this is already beyond what the structure models, and an unbounded path is an
#: unbounded ``VARCHAR`` key and an unbounded reparent rewrite.
MAX_DEPTH = 6

_SEP = "/"


def child_path(parent_path: str | None, child_id: uuid.UUID) -> str:
    """The path for a department under ``parent_path`` (``None`` for a root).

    A root is ``/<id>/``; a child appends its own id to the parent's path. Both ends
    carry a slash so ``LIKE '/a/b/%'`` matches descendants and a prefix test matches
    ancestors without a segment-boundary ambiguity.
    """
    prefix = parent_path if parent_path is not None else _SEP
    if not prefix.startswith(_SEP) or not prefix.endswith(_SEP):
        raise ValidationFailedError("a department path is slash-delimited at both ends")
    return f"{prefix}{child_id.hex}{_SEP}"


def depth(path: str) -> int:
    """The number of segments in a path — the nesting level."""
    return len([segment for segment in path.split(_SEP) if segment])


def assert_within_depth(path: str) -> None:
    if depth(path) > MAX_DEPTH:
        raise ValidationFailedError(
            f"a department may nest at most {MAX_DEPTH} levels deep",
            fields={"parent_id": f"nesting would exceed {MAX_DEPTH} levels"},
        )


def is_ancestor_or_self(ancestor_path: str, descendant_path: str) -> bool:
    """Whether ``ancestor_path`` is an ancestor of ``descendant_path`` or the same node."""
    return descendant_path.startswith(ancestor_path)


def would_create_cycle(*, moving_path: str, new_parent_path: str) -> bool:
    """A reparent under one's own descendant is a cycle — refuse it.

    Moving A under B is a cycle exactly when B is A-or-below, i.e. B's path starts with
    A's. Checked before any rewrite, because the rewrite itself would corrupt the tree.
    """
    return is_ancestor_or_self(moving_path, new_parent_path)


def rewritten_path(*, old_prefix: str, new_prefix: str, path: str) -> str:
    """A descendant's path after its subtree root moves from ``old_prefix`` to
    ``new_prefix``. Only the leading prefix changes; the subtree's shape is preserved."""
    if not path.startswith(old_prefix):
        raise ValidationFailedError("path is not within the subtree being moved")
    return new_prefix + path[len(old_prefix) :]
