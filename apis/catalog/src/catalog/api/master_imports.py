"""Shared import routes with current Catalog authority."""

import re
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.import_engine import scoped_job
from billing_platform.import_models import ImportTemplateSnapshot
from billing_platform.import_routes import router_for
from fastapi import Request

from catalog.api.auth import actor
from catalog.api.simple_product_creation import context, owners
from catalog.tasks.simple_import_adapter import SimpleCatalogImportAdapter
from catalog.tasks.simple_import_definition import DEFINITION


async def build(request: Request, current: Actor, company: uuid.UUID) -> SimpleCatalogImportAdapter:
    adapter = SimpleCatalogImportAdapter(
        current,
        company,
        request.app.state.session_factory,
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
        context(request, company, current) if request.headers.get("x-company-context") else None,
        owners(request),
    )
    path = request.url.path
    selected: str | None = None
    kind: str | None = None
    values = (
        await request.json()
        if request.method == "POST" and path.endswith(("/import-templates", "/import-jobs"))
        else {}
    )
    template_id = values.get("template_id")
    template_match = re.search(r"/import-templates/([0-9a-f-]{36})(?:/|$)", path)
    job_match = re.search(r"/(?:import-jobs|simple-product-imports)/([0-9a-f-]{36})(?:/|$)", path)
    if path.endswith("/import-templates") and request.method == "POST":
        selected, kind = values.get("definition"), values.get("parameters", {}).get("kind")
    elif template_id or template_match or job_match:
        with tenant_scope(current.tenant_id):
            async with adapter.factory() as db:
                if job_match:
                    job = await scoped_job(db, adapter, uuid.UUID(job_match.group(1)))
                    selected, template_id = job.definition, str(job.template_id)
                else:
                    await adapter.authorize(db, write=False)
                if not template_id:
                    assert template_match is not None
                    template_id = template_match.group(1)
                identifier = uuid.UUID(template_id)
                template = await company_object(
                    db, ImportTemplateSnapshot, identifier, company_id=company
                )
                if template.actor_user_id != current.user_id:
                    raise PermissionDeniedError("Template belongs to another user")
                selected = selected or template.definition
                kind = (template.snapshot or {}).get("parameters", {}).get("kind")
    if selected == DEFINITION:
        adapter.command_group_limit = 1
        facts = adapter.context
        if facts is None:
            raise AuthenticationRequiredError(
                "Fresh company context is required for Simple imports"
            )
        facts.assert_current(current, company)
        adapter.kind = kind
        if (
            kind != "SERVICE"
            and "inventory" in facts.features
            and current.allows_scope("accounting.stock.read", target=ScopePath(company_id=company))
        ):
            metadata = await adapter.owners.call(
                "accounting", "GET", f"/v1/companies/{company}/stock/openings/capture-fields"
            )
            adapter.opening_fields = metadata["fields"]
    return adapter


router = router_for("catalog", actor, build)
