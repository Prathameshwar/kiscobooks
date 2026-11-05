"""Deterministic route resolution."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import NotFoundError, ValidationFailedError


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    id: uuid.UUID
    company_id: uuid.UUID
    event_key: str
    category: str
    priority: int
    weight: int
    is_active: bool = True
    conditions: dict[str, Any] | None = None


def _specificity(
    route: RouteCandidate, company_id: uuid.UUID, event_key: str, category: str
) -> int | None:
    company = route.company_id == company_id
    tenant = route.company_id == SCOPE_ALL
    category_ok = route.category in {"*", category}
    event = route.event_key == event_key and category_ok
    category_match = route.category == category and route.event_key == "*"
    if company and event:
        return 0
    if company and category_match:
        return 1
    if tenant and event:
        return 2
    if tenant and category_match:
        return 3
    return None


def select_route(
    candidates: list[RouteCandidate],
    *,
    company_id: uuid.UUID,
    event_key: str,
    category: str,
    stable_key: uuid.UUID,
) -> RouteCandidate:
    eligible = [
        (rank, route)
        for route in candidates
        if route.is_active
        and not route.conditions
        and (rank := _specificity(route, company_id, event_key, category)) is not None
    ]
    if not eligible:
        raise NotFoundError("no active notification route")
    best_rank = min(rank for rank, _ in eligible)
    ranked = [route for rank, route in eligible if rank == best_rank]
    best_priority = min(route.priority for route in ranked)
    pool = sorted(
        (route for route in ranked if route.priority == best_priority), key=lambda r: r.id.bytes
    )
    total = sum(route.weight for route in pool)
    if total <= 0:
        raise ValidationFailedError("route weights must be positive")
    point = int.from_bytes(hashlib.sha256(stable_key.bytes).digest()[:8], "big") % total
    for route in pool:
        point -= route.weight
        if point < 0:
            return route
    raise AssertionError("weighted route selection exhausted")
