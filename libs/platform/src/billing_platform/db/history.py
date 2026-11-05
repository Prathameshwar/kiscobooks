"""Old scalar values for flush guards, including expired or deferred attributes."""

from typing import Any, cast

from sqlalchemy import inspect, select
from sqlalchemy.orm import InstanceState, Session

from billing_platform.db.tenant_context import TenantContextError, require_current_tenant


def previous_scalar(session: Session, row: Any, key: str) -> Any:
    """Return the value before this flush; a missing history entry is never a NULL.

    The caller owns its transition policy. This helper requires a persistent tenant-owned
    instance in this session and uses the guarded session for its locking fallback read.
    """
    state = cast(InstanceState[Any], inspect(row))
    if state.session is not session or not state.persistent or key not in state.mapper.column_attrs:
        raise ValueError("previous_scalar requires a persistent scalar in this session")
    if getattr(row, "tenant_id", None) != require_current_tenant():
        raise TenantContextError("stored value belongs to a different tenant")
    history = state.attrs[key].history
    if history.deleted:
        return history.deleted[0]
    if history.unchanged:
        return history.unchanged[0]
    assert state.identity is not None
    model = type(row)
    query = select(getattr(model, key)).where(
        *(
            column == value
            for column, value in zip(state.mapper.primary_key, state.identity, strict=True)
        )
    )
    if hasattr(model, "company_id"):
        query = query.where(model.company_id == row.company_id)
    with session.no_autoflush:
        return session.execute(query.with_for_update()).scalar_one()
