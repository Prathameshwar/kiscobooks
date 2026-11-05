"""Company-authorized shared master imports."""

import uuid

from billing_platform.import_routes import router_for
from fastapi import Request

from accounting.api.auth import Access, access
from accounting.tasks.master_imports import AccountingImportAdapter


def build(request: Request, current: Access, company: uuid.UUID) -> AccountingImportAdapter:
    current.context.assert_current(current.actor, company)
    return AccountingImportAdapter(current, request.app.state.settings)


router = router_for("accounting", access, build)
