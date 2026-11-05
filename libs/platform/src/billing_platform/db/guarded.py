"""Strict tenant sessions for request/worker units of work.

A session cannot change tenant after touching scoped data: ORM identity maps do
not run query filters on cache hits. Bulk DML bypasses ORM flush guards, so scoped
bulk statements require an explicit, reviewed unfiltered block. Ordinary commands
load bounded rows and flush under their original tenant.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from sqlalchemy import Select, event, inspect
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause, TextClause
from sqlalchemy.sql.selectable import Join, Subquery
from sqlalchemy.sql.util import find_tables

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.mixins import SelfTenantMixin, TenantMixin
from billing_platform.db.tenant_context import (
    TenantContextError,
    is_filter_disabled,
    require_current_tenant,
)


class GuardedSession(Session):
    preserve_pending_gets: ClassVar[bool] = False

    def tenant(self) -> uuid.UUID:
        tenant = require_current_tenant()
        if tenant == SCOPE_ALL:
            raise TenantContextError("a request tenant must be a real tenant")
        previous = self.info.setdefault("guarded_tenant", tenant)
        if previous != tenant:
            raise TenantContextError("a scoped session cannot change tenant; open a new session")
        return tenant

    def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        tenant = None
        key = None
        if not is_filter_disabled():
            mapper = inspect(entity)
            if issubclass(mapper.class_, TenantMixin | SelfTenantMixin):
                tenant = self.tenant()
                key = "tenant_id" if issubclass(mapper.class_, TenantMixin) else "id"
                if self.preserve_pending_gets:
                    if isinstance(ident, dict):
                        primary = tuple(
                            ident.get(mapper.get_property_by_column(c).key)
                            for c in mapper.primary_key
                        )
                    else:
                        primary = tuple(ident) if isinstance(ident, tuple | list) else (ident,)
                    cached = self.identity_map.get(
                        mapper.identity_key_from_primary_key(
                            primary, identity_token=kwargs.get("identity_token")
                        )
                    )
                    pending = cached is not None and self.is_modified(
                        cached, include_collections=False
                    )
                    kwargs["populate_existing"] = (
                        kwargs.get("populate_existing", False) or not pending
                    )
                else:
                    # Preserve existing guarded-session refresh semantics for services
                    # that have not opted into pending-change preservation.
                    kwargs["populate_existing"] = True
        row = super().get(entity, ident, **kwargs)
        # Validate cache hits too, preserving unflushed local changes. A forced
        # refresh here would silently discard pending state in autoflush=False units.
        if row is not None and key is not None and getattr(row, key) != tenant:
            return None
        return row


@event.listens_for(GuardedSession, "do_orm_execute")
def guard_statement(state: ORMExecuteState) -> None:
    if is_filter_disabled():
        return
    # Runtime import avoids a session-factory import cycle.
    from billing_platform.db.session import _touches_a_tenant_table

    if isinstance(state.statement, TextClause):
        raise TenantContextError("raw session SQL requires an explicit unfiltered operation")
    if not _touches_a_tenant_table(state):
        return
    session = state.session
    assert isinstance(session, GuardedSession)
    session.tenant()
    if state.execution_options.get("skip_tenant_filter"):
        raise TenantContextError("statement filter bypass requires an unfiltered operation")
    if not state.is_select:
        raise TenantContextError("scoped bulk writes require a reviewed unfiltered operation")
    _require_filterable_froms(state.statement)


def _require_filterable_froms(statement: Any) -> None:
    """Check every SELECT separately: one ORM column cannot bless a raw alias.

    SQLAlchemy only adds loader criteria to ORM-aware occurrences. Compare exact
    FROM identities (never merely their base table) so an unrelated Core alias or
    nested SELECT cannot borrow another occurrence's tenant predicate.
    """
    from billing_platform.db.session import _tenant_scoped_tables

    scoped = _tenant_scoped_tables()
    for node in visitors.iterate(statement):
        if isinstance(node, TextClause) or (isinstance(node, ColumnClause) and node.is_literal):
            raise TenantContextError("embedded SQL requires an explicit unfiltered operation")
        if not isinstance(node, Select):
            continue
        known: set[int] = set()
        pending = list(node.get_children())
        while pending:
            child = pending.pop()
            if isinstance(child, Select):
                continue
            if child._annotations.get("parentmapper") is not None:
                table = getattr(child, "table", None)
                known.add(id((table if table is not None else child)._deannotate()))
            pending.extend(child.get_children())
        sources = list(node.get_final_froms())
        while sources:
            source = sources.pop()
            if isinstance(source, Join):
                sources.extend((source.left, source.right))
            elif isinstance(source, Subquery):
                # Its SELECT receives its own independent check above.
                continue
            elif any(table.name in scoped for table in find_tables(source)):
                if id(source._deannotate()) not in known:
                    raise TenantContextError("scoped Core FROM has no reachable ORM tenant filter")


@event.listens_for(GuardedSession, "before_flush")
def guard_flush(session: GuardedSession, context: Any, instances: Any) -> None:
    if is_filter_disabled():
        return
    for row in session.new | session.dirty | session.deleted:
        if not isinstance(row, TenantMixin | SelfTenantMixin):
            continue
        tenant = session.tenant()
        key = "tenant_id" if isinstance(row, TenantMixin) else "id"
        owner = getattr(row, key)
        if owner != tenant:
            raise TenantContextError("write target does not belong to the current tenant")
        state = inspect(row)
        assert state is not None
        if state.persistent:
            for name in (key, "company_id"):
                if name in state.attrs and state.attrs[name].history.has_changes():
                    raise TenantContextError("persisted ownership cannot be changed")
