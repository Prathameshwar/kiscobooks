"""Additional owner partitions inside a tenant, with guarded identity-map access.

Services register a mixin and supply policy for resolving the active partition.
The mechanism never invents a tenant or decides who may select a partition.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from billing_platform.db.guarded import GuardedSession
from billing_platform.db.tenant_context import TenantContextError, is_filter_disabled

_POLICIES: list[tuple[type[Any], str, Callable[[], uuid.UUID | None]]] = []


def _pin(db: Session, mixin: type[Any], resolve: Callable[[], uuid.UUID | None]) -> uuid.UUID:
    value = resolve()
    if value is None:
        raise TenantContextError("partition context is required")
    if isinstance(db, PartitionedSession):
        key = f"partition:{mixin.__module__}.{mixin.__name__}"
        if db.info.setdefault(key, value) != value:
            raise TenantContextError("a scoped session cannot change partition")
    return value


class PartitionedSession(GuardedSession):
    preserve_pending_gets = True

    def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        policies = []
        if not is_filter_disabled():
            mapper = inspect(entity)
            policies = [
                (column, _pin(self, mixin, resolve))
                for mixin, column, resolve in _POLICIES
                if issubclass(mapper.class_, mixin)
            ]
        row = super().get(entity, ident, **kwargs)
        if row is not None and any(getattr(row, column) != value for column, value in policies):
            return None
        return row


def install_partition_guard(
    mixin: type[Any], *, column: str, resolve: Callable[[], uuid.UUID | None]
) -> None:
    """Install one service-owned partition policy on all ORM session paths."""

    _POLICIES.append((mixin, column, resolve))

    @event.listens_for(Session, "do_orm_execute")
    def read_guard(state: ORMExecuteState) -> None:
        if is_filter_disabled():
            return
        if not any(issubclass(mapper.class_, mixin) for mapper in state.all_mappers):
            return
        value = _pin(state.session, mixin, resolve)
        if not state.is_select:
            raise TenantContextError(
                "partitioned bulk writes require an explicit maintenance scope"
            )
        # The attribute name is fixed per registered policy. A closure over the
        # value keeps SQLAlchemy's statement cache parameterized across partitions.
        state.statement = state.statement.options(
            *(
                with_loader_criteria(
                    mapper.class_,
                    getattr(mapper.class_, column) == value,
                    include_aliases=True,
                )
                for mapper in state.all_mappers
                if issubclass(mapper.class_, mixin)
            )
        )

    @event.listens_for(Session, "before_flush")
    def write_guard(db: Session, context: Any, instances: Any) -> None:
        for row in list(db.new | db.dirty | db.deleted):
            if not isinstance(row, mixin):
                continue
            value = getattr(row, column, None)
            expected = resolve()
            if value is None and row in db.new:
                value = expected or getattr(row, "tenant_id", None)
                setattr(row, column, value)
            if value is None:
                raise TenantContextError("partition ownership is required")
            if is_filter_disabled():
                continue
            if value != _pin(db, mixin, resolve):
                raise TenantContextError("write target is outside the active partition")
            state = inspect(row)
            if state.persistent and state.attrs[column].history.has_changes():
                raise TenantContextError("partition ownership is immutable")
