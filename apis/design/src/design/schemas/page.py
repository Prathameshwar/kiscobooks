"""The list envelope every growing collection returns (docs/api-conventions.md).

Lists are keyset-paginated and return a lean item schema — never the detail model, and
never an unused JSON column. A ``layout_definition`` or a ``content_definition`` is a
detail read: shipping it in a list page is how a cheap index turns into a slow one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None = None
    has_more: bool = False


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    page: PageMeta
