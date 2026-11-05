"""Explicit factories for automatic report readiness evidence."""

import uuid

from billing_platform.db.types import utcnow

from reports.models.readiness import ReportReadiness


def build_readiness(tenant: uuid.UUID, company: uuid.UUID) -> ReportReadiness:
    return ReportReadiness(tenant_id=tenant, company_id=company, next_attempt_at=utcnow())
