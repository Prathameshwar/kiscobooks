"""Setup intent and creation receipt share Identity's creation transaction."""

import hashlib
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models.company import Company
from identity.models.company_setup import CompanySetupRun, CompanySetupStep, ReportSourceEnrollment
from identity.schemas.company import CompanyCreate
from identity.services.audit import record

STEPS = ("features", "catalog", "vouchers", "chart", "books", "calendar", "opening", "reports")


def command_key(current: Actor, key: str | None) -> str:
    if key is not None and (not 1 <= len(key) <= 200 or any(not 33 <= ord(c) <= 126 for c in key)):
        raise ValidationFailedError("invalid company creation key")
    return hashlib.sha256(f"{current.user_id}:{key or uuid7()}".encode()).hexdigest()


def identity(current: Actor, body: CompanyCreate, key: str | None) -> tuple[str, str]:
    command = command_key(current, key)
    # Preserve receipts created before the optional registration field was added.
    values = body.model_dump(mode="json")
    if body.initial_tax_registration is None:
        values.pop("initial_tax_registration")
    digest = hashlib.sha256(canonical_json(values)).hexdigest()
    return command, digest


async def replay(db: AsyncSession, current: Actor, command: str, digest: str) -> Company | None:
    # The request dependency already locks this tenant before mutation.
    run = await db.scalar(select(CompanySetupRun).where(CompanySetupRun.command_key == command))
    if run is None:
        return None
    if run.request_hash != digest:
        raise ConflictError("company creation key belongs to different details")
    current.require_scope("company.read", target=ScopePath(company_id=run.company_id))
    return await db.get(Company, run.company_id)


async def refresh_accounting_defaults(
    db: AsyncSession,
    current: Actor,
    company_id: uuid.UUID,
) -> None:
    """A registration added after creation must reach the already-enrolled books step.

    The statutory caller holds the tenant/company mutation locks. Invalidate any
    in-flight lease so its stale completion cannot hide the new registration.
    The original setup actor is retained and its live authority is rechecked.
    """
    run = await db.scalar(
        select(CompanySetupRun)
        .where(
            CompanySetupRun.company_id == company_id,
        )
        .with_for_update()
    )
    if run is None:
        return
    step = await db.scalar(
        select(CompanySetupStep).where(
            CompanySetupStep.company_id == company_id,
            CompanySetupStep.key == "books",
        )
    )
    if step is None:
        raise ConflictError("company setup bookkeeping step is unavailable")
    step.status, step.failure_code = "PENDING", None
    run.status, run.failure_code, run.available_at = "PENDING", None, utcnow()
    run.lease_token = run.lease_expires_at = None
    run.attempt = 0
    run.updated_by = step.updated_by = current.user_id
    record(
        db,
        current,
        action="company.setup_retried",
        entity="company_setup_run",
        entity_id=run.id,
        company_id=company_id,
        changes={"step": {"to": "books"}, "status": {"to": "PENDING"}},
        reason="Tax registration changed; refresh accounting defaults",
    )


async def enroll(
    db: AsyncSession,
    current: Actor,
    company: Company,
    body: CompanyCreate,
    command: str,
    digest: str,
) -> CompanySetupRun:
    if current.impersonation_id:
        # A background plan must not outlive a bounded support session by
        # resolving the impersonated user's unrestricted native grants.
        raise ConflictError("support sessions cannot start automatic company setup")
    options = body.setup
    from identity.domain.company_features import plan_enable

    for feature in options.features:
        plan_enable(feature, rows={}, tax_system=company.default_tax_system)
    if options.features:
        # Publish the company and its selected capabilities atomically. Catalog's
        # enrollment worker may run immediately after commit; it must not freeze
        # starter masters from an intermediate company without these features.
        # Reuse the native command with the creator's actual newly granted role.
        from identity.api.companies import enable_feature
        from identity.services.login import live_grants

        grants, groups = await live_grants(db, current.user_id)
        setup_actor = Actor(current.tenant_id, current.user_id, grants, group_ids=groups)
        for feature in options.features:
            await enable_feature(company.id, feature, current=setup_actor, db=db)
    run = CompanySetupRun(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company.id,
        command_key=command,
        request_hash=digest,
        status="PENDING",
        opening_choice=options.opening_choice,
        opening_reason=options.opening_reason,
        requested_features=options.features,
        configuration={
            k: body.model_dump(mode="json")[k]
            for k in (
                "books_begin_date",
                "fiscal_year_start_month",
                "fiscal_year_start_day",
                "base_currency",
                "country_code",
                "state_code",
                "default_tax_system",
                "amount_precision",
                "quantity_precision",
                "rounding_mode",
                "timezone",
                "default_payment_terms_days",
            )
        },
        available_at=utcnow(),
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    db.add(run)
    for key in STEPS:
        db.add(
            CompanySetupStep(
                id=uuid7(),
                tenant_id=current.tenant_id,
                company_id=company.id,
                key=key,
                status="PENDING",
                evidence={},
                created_by=current.user_id,
                updated_by=current.user_id,
            )
        )
    db.add(
        ReportSourceEnrollment(
            id=uuid7(),
            tenant_id=current.tenant_id,
            company_id=company.id,
            status="ACTIVE",
            revision=1,
            created_by=current.user_id,
            updated_by=current.user_id,
        )
    )
    record(
        db,
        current,
        action="company.setup_requested",
        entity="company_setup_run",
        entity_id=run.id,
        company_id=company.id,
        changes={"status": {"from": None, "to": "PENDING"}},
    )
    return run
