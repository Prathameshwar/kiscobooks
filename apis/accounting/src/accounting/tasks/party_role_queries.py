"""One field-protected active-role predicate for party lists and reference choices."""

from typing import Any

from billing_platform.errors import PermissionDeniedError
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from accounting.api.auth import Access
from accounting.resources import BY_NAME
from accounting.tasks.access import authorize, readable


def active_party_role(current: Access, party_id: Any, role: str) -> ColumnElement[bool]:
    spec = BY_NAME["party_role"]
    authorize(current, spec, "read")
    if not {"party_id", "role", "status"} <= readable(current, spec):
        raise PermissionDeniedError("party roles are not readable")
    model: Any = spec.model
    return (
        select(model.id)
        .where(
            model.company_id == current.context.company_id,
            model.party_id == party_id,
            model.role == role,
            model.status == "ACTIVE",
        )
        .exists()
    )
