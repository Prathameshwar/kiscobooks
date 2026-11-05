"""Durable review decisions, bounded synchronization, and verified provider reconciliation."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace

from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, IdempotencyConflictError, NotFoundError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.domain.account_review import Applicant, fingerprint, transition
from identity.models import AccountReview, AccountReviewCommand, PlatformInstallation, User
from identity.schemas.account_review import (
    AccountCommand,
    AccountDecision,
    AccountHandoff,
    AccountReconciliation,
    AccountReviewDetail,
)
from identity.services.account_provider import AccountProviderUnavailableError
from identity.services.audit import record
from identity.services.identity_provider import AccountDirectory
from identity.services.tenant_provisioning import create_tenant


async def detail(
    db: AsyncSession, account_id: uuid.UUID, settings: Settings | None = None
) -> AccountReviewDetail:
    row = await db.get(AccountReview, account_id)
    if row is None:
        raise NotFoundError("Account registration not found.")
    history = list(
        await db.scalars(
            select(AccountReviewCommand)
            .where(AccountReviewCommand.account_id == row.id)
            .order_by(AccountReviewCommand.created_at.desc(), AccountReviewCommand.id.desc())
            .limit(50)
        )
    )
    handoff = None
    if settings and row.status == "approved" and row.provider_active and row.provider_verified:
        from identity.services.onboarding_handoff import (
            invitation_link,
            notification_queued,
            sign_in_url,
        )

        link = sign_in_url(settings)
        if link:
            handoff = AccountHandoff(
                username=row.username,
                sign_in_url=link,
                invitation_url=await invitation_link(db, settings, row.email)
                if row.workspace_name == ""
                else None,
                notification_status="queued"
                if await notification_queued(db, settings, row.id)
                else "manual",
            )
    return AccountReviewDetail(
        **{
            key: getattr(row, key)
            for key in AccountReviewDetail.model_fields
            if key not in {"history", "handoff"}
        },
        history=[AccountCommand.model_validate(command) for command in history],
        handoff=handoff,
    )


async def import_page(db: AsyncSession, current: Actor, rows: list[Applicant]) -> int:
    for observed in rows:
        row = await db.scalar(
            select(AccountReview)
            .where(AccountReview.provider_uuid == observed.provider_uuid)
            .with_for_update()
        )
        token = fingerprint(observed)
        if row is None:
            # Pre-existing activated users must never enter the pending approval queue.
            if observed.is_active or observed.verified:
                continue
            row = AccountReview(
                tenant_id=current.tenant_id,
                provider_uuid=observed.provider_uuid,
                provider_id=observed.provider_id,
                name=observed.name,
                username=observed.username,
                email=observed.email,
                country_code=observed.country_code,
                state_code=observed.state_code,
                workspace_name=observed.workspace_name,
                provider_active=observed.is_active,
                provider_verified=observed.verified,
                fingerprint=token,
            )
            db.add(row)
            await db.flush()
            record(
                db,
                current,
                action="platform.account_imported",
                entity="account_review",
                entity_id=row.id,
                category="admin",
                changes={"status": row.status},
            )
        elif row.fingerprint != token:
            row.name, row.username, row.email = observed.name, observed.username, observed.email
            row.country_code, row.state_code = observed.country_code, observed.state_code
            row.workspace_name = observed.workspace_name
            row.provider_active, row.provider_verified = observed.is_active, observed.verified
            row.fingerprint = token
            row.version += 1
            # Any profile change invalidates previous evidence, including an email-only change.
            row.needs_attention = True
            record(
                db,
                current,
                action="platform.account_drift_detected",
                entity="account_review",
                entity_id=row.id,
                changes={
                    "version": row.version,
                    "needs_attention": True,
                    "provider_active": row.provider_active,
                    "provider_verified": row.provider_verified,
                },
            )
    await db.flush()
    return len(rows)


async def pending_email(
    db: AsyncSession, current: Actor, provider: AccountDirectory | None, email: str
) -> list[AccountReview]:
    if provider is not None:
        await import_page(db, current, await provider.pending_email(email))
    return list(
        await db.scalars(
            select(AccountReview)
            .where(
                AccountReview.email == email.casefold(),
                AccountReview.status == "pending",
                AccountReview.provider_active.is_(False),
                AccountReview.provider_verified.is_(False),
            )
            .limit(2)
        )
    )


async def acknowledge_drift(
    db: AsyncSession,
    current: Actor,
    provider: AccountDirectory,
    account_id: uuid.UUID,
    body: AccountReconciliation,
) -> AccountReviewDetail:
    """Acknowledge a fresh inactive snapshot; provider state and old evidence stay unchanged."""
    row = await db.scalar(
        select(AccountReview).where(AccountReview.id == account_id).with_for_update()
    )
    if row is None:
        raise NotFoundError("Account registration not found.")
    if row.version != body.version or not row.needs_attention or row.status == "approved":
        raise ConflictError("Refresh this registration before reconciling its details.")
    if await db.scalar(
        select(AccountReviewCommand.id)
        .where(AccountReviewCommand.account_id == row.id, AccountReviewCommand.status == "queued")
        .limit(1)
    ):
        raise ConflictError("The saved decision must finish reconciliation before a new review.")
    observed, _ = await provider.read(row.provider_id)
    if observed.provider_uuid != row.provider_uuid or observed.is_active or observed.verified:
        raise ConflictError(
            "Restore this registration to inactive and unverified in Authentik before reconciling."
        )
    row.name, row.username, row.email = observed.name, observed.username, observed.email
    row.country_code, row.state_code = observed.country_code, observed.state_code
    row.workspace_name = observed.workspace_name
    row.provider_active = row.provider_verified = row.needs_attention = False
    row.fingerprint = fingerprint(observed)
    row.version += 1
    record(
        db,
        current,
        action="platform.account_reconciled",
        entity="account_review",
        entity_id=row.id,
        reason=body.reason,
        changes={"version": row.version},
    )
    await db.flush()
    return await detail(db, account_id)


async def decide(
    db: AsyncSession, current: Actor, account_id: uuid.UUID, body: AccountDecision, key: str
) -> AccountReviewCommand:
    digest = hashlib.sha256(
        json.dumps(
            {"account_id": str(account_id), **body.model_dump(exclude_none=True)}, sort_keys=True
        ).encode()
    ).hexdigest()
    previous = await db.scalar(
        select(AccountReviewCommand).where(
            AccountReviewCommand.actor_id == current.user_id,
            AccountReviewCommand.request_key == key,
        )
    )
    if previous is not None:
        if previous.request_hash != digest:
            raise IdempotencyConflictError("Use a new request key for a different decision.")
        return previous
    row = await db.scalar(
        select(AccountReview).where(AccountReview.id == account_id).with_for_update()
    )
    if row is None:
        raise NotFoundError("Account registration not found.")
    if row.version != body.version or row.needs_attention:
        raise ConflictError("The registration changed. Refresh and review its current details.")
    if await db.scalar(
        select(AccountReviewCommand.id)
        .where(AccountReviewCommand.account_id == row.id, AccountReviewCommand.status == "queued")
        .limit(1)
    ):
        raise ConflictError("A saved decision is still being processed. Refresh its status.")
    try:
        transition(row.status, body.action)
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc
    if body.action == "approve":
        if row.workspace_name == "" and body.workspace_name is not None:
            raise ConflictError(
                "This registration joins an existing invitation; it cannot create a workspace."
            )
        if row.workspace_name and body.workspace_name not in (None, row.workspace_name):
            raise ConflictError("The requested workspace name changed. Refresh the registration.")
        if row.workspace_name is None and body.workspace_name is None:
            raise ConflictError("Enter a workspace name for this earlier registration.")
    elif body.workspace_name is not None:
        raise ConflictError("A workspace name is only allowed when approving an account.")
    command = AccountReviewCommand(
        tenant_id=current.tenant_id,
        account_id=row.id,
        actor_id=current.user_id,
        request_key=key,
        request_hash=digest,
        action=body.action,
        reason=body.reason,
        attested=body.attested,
        workspace_name=(
            row.workspace_name if row.workspace_name is not None else body.workspace_name
        ),
        expected_fingerprint=row.fingerprint,
        created_by=current.user_id,
    )
    db.add(command)
    await db.flush()
    row.version += 1
    record(
        db,
        current,
        action="platform.account_decision_requested",
        entity="account_review",
        entity_id=row.id,
        reason=body.reason,
        changes={"action": body.action, "command_id": str(command.id), "attested": body.attested},
    )
    return command


async def reconcile(
    db: AsyncSession,
    current: Actor,
    provider: AccountDirectory,
    command: AccountReviewCommand,
    settings: Settings,
) -> None:
    row = await db.scalar(
        select(AccountReview).where(AccountReview.id == command.account_id).with_for_update()
    )
    if row is None or command.status != "queued":
        return
    # Share the bootstrap mutex with /onboarding/tenant. Provider activation can
    # precede the local commit, so the self-service endpoint must see queued intent.
    await db.scalar(
        select(PlatformInstallation).where(PlatformInstallation.key == "platform").with_for_update()
    )
    command.attempts += 1
    try:
        observed, raw = await provider.read(row.provider_id)
        if observed.provider_uuid != row.provider_uuid:
            raise AccountProviderUnavailableError("Registration identity changed.")
        approved_subject = (
            provider.subject(raw)
            if command.action == "approve" and command.workspace_name
            else None
        )
        active = verified = command.action == "approve"
        tagged = raw.get("attributes", {}).get("billing_account_review_command") == str(command.id)
        prior_profile = replace(observed, is_active=False, verified=False)
        if (
            tagged
            and observed.is_active == active
            and observed.verified == verified
            and fingerprint(prior_profile) == command.expected_fingerprint
        ):
            pass  # A lost response after the native write is reconciled without repeating it.
        elif fingerprint(observed) != command.expected_fingerprint:
            command.status, command.error_code = "blocked", "applicant_changed"
            row.needs_attention = True
            row.version += 1
            record(
                db,
                current,
                action="platform.account_decision_blocked",
                entity="account_review",
                entity_id=row.id,
                changes={"command_id": str(command.id), "error_code": command.error_code},
            )
            return
        else:
            await provider.apply(
                row.provider_id, raw, active=active, verified=verified, command_id=command.id
            )
            observed, raw = await provider.read(row.provider_id)
            if (
                observed.provider_uuid != row.provider_uuid
                or fingerprint(replace(observed, is_active=False, verified=False))
                != command.expected_fingerprint
                or observed.is_active != active
                or observed.verified != verified
                or (approved_subject is not None and provider.subject(raw) != approved_subject)
                or raw.get("attributes", {}).get("billing_account_review_command")
                != str(command.id)
            ):
                raise AccountProviderUnavailableError("Provider result could not be confirmed.")
        target_tenant_id = None
        if command.action == "approve" and command.workspace_name:
            subject = approved_subject
            if subject is None:
                raise AccountProviderUnavailableError(
                    "Registration subject could not be confirmed."
                )
            with unfiltered():
                linked = await db.scalar(select(User.id).where(User.authentik_sub == subject))
            if linked is not None:
                raise ConflictError("This identity already belongs to a workspace.")
            from identity.api.platform import TenantProvision

            provision = TenantProvision(
                name=command.workspace_name,
                administrator_name=observed.name,
                administrator_email=observed.email,
                country_code=observed.country_code,
                state_code=observed.state_code or None,
            )
            target_tenant_id = uuid7()
            await create_tenant(
                db,
                provision,
                settings,
                tenant_id=target_tenant_id,
                user_id=uuid7(),
                actor_id=current.user_id,
                subject=subject,
            )
        if command.action == "approve":
            from identity.services.onboarding_handoff import invitation_link, queue_ready

            access_url = (
                await invitation_link(db, settings, observed.email)
                if not command.workspace_name
                else None
            )
            await queue_ready(
                db,
                settings,
                reference=row.id,
                target_tenant_id=target_tenant_id,
                email=observed.email,
                username=observed.username,
                access_url=access_url,
            )
        row.status = transition(row.status, command.action)
        row.provider_active, row.provider_verified = observed.is_active, observed.verified
        row.fingerprint = fingerprint(observed)
        row.needs_attention = False
        row.version += 1
        command.status, command.error_code, command.completed_at = "completed", None, utcnow()
        record(
            db,
            current,
            action="platform.account_decision_completed",
            entity="account_review",
            entity_id=row.id,
            changes={
                "status": row.status,
                "command_id": str(command.id),
                "attested": command.attested,
            },
        )
    except AccountProviderUnavailableError as exc:
        import logging

        from billing_platform.audit_context import correlation
        from billing_platform.diagnostics import log_failure

        log_failure(
            logging.getLogger(__name__),
            service="identity",
            event="platform.account_provider_unavailable",
            error=exc,
            trace_id=correlation()[0],
        )
        command.error_code = "provider_unavailable"
        # Keep intent queued, with a safe diagnostic. The worker retries after a bounded delay.
