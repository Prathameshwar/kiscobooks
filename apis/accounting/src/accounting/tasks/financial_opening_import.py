"""Durable import review produces declarations/drafts only, never posting approvals."""

import hashlib
import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import CommandResult, canonical_json
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.domain.financial_opening import declaration_hash
from accounting.domain.financial_opening_import import decode
from accounting.models.financial_opening import FinancialOpeningImport
from accounting.models.fiscal import FinancialSetup, FiscalPeriod
from accounting.models.masters import Account, AccountGroup, AccountHead, Record
from accounting.models.subledger import OpeningBatch
from accounting.schemas.financial_opening import OpeningDeclaration
from accounting.schemas.financial_opening_import import (
    FinancialOpeningImportCommit,
    FinancialOpeningImportDetail,
    FinancialOpeningImportStage,
)
from accounting.schemas.masters import ExpectedVersion
from accounting.tasks.access import authority_fingerprint
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.financial_opening import (
    audit,
    audit_values,
    command,
    create_in_workspace,
    prepare_in_transaction,
    record,
    require_read,
    revision,
    validate,
)
from accounting.tasks.financial_opening import detail as workspace_detail
from accounting.tasks.openings import require_available, require_opening_revision_window


async def detail(
    db: AsyncSession, current: Any, identity: uuid.UUID
) -> FinancialOpeningImportDetail:
    require_read(current)
    row = await company_object(
        db, FinancialOpeningImport, identity, company_id=current.context.company_id
    )
    workspace = await workspace_detail(db, current, row.batch_id) if row.batch_id else None
    complete = bool(workspace and "OPENING_DRAFTS_NOT_PREPARED" not in workspace.blockers)
    return FinancialOpeningImportDetail(
        id=row.id,
        company_id=row.company_id,
        row_version=row.row_version,
        source_key=row.source_key,
        state=row.state,
        input_hash=row.input_hash,
        review_hash=row.review_hash,
        batch_id=row.batch_id,
        issues=row.issues,
        journal_ids=workspace.journal_ids if workspace else [],
        drafts_complete=complete,
        effect_kind="DECLARATION_AND_DRAFTS_ONLY",
        posting_required=workspace is None or workspace.status != "FINALIZED",
        opening_status=workspace.status if workspace else None,
    )


async def stage(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    body: FinancialOpeningImportStage,
    key: str,
) -> CommandResult[BaseModel]:
    require_read(current)
    current.actor.require_scope(
        "accounting.finance.manage", target=ScopePath(company_id=current.context.company_id)
    )
    document = decode(body)
    digest = declaration_hash(document)

    async def mutate(db: AsyncSession) -> Record:
        from accounting.tasks.financial_opening import require_capture_write

        await require_capture_write(db, current, document)
        existing = await db.scalar(
            select(FinancialOpeningImport).where(
                FinancialOpeningImport.company_id == current.context.company_id,
                FinancialOpeningImport.source_key == body.source_key,
            )
        )
        if existing:
            if existing.input_hash != digest:
                raise ConflictError(
                    "import source key has different content; use a new reviewed reference"
                )
            return existing
        duplicate = await db.scalar(
            select(FinancialOpeningImport)
            .where(
                FinancialOpeningImport.company_id == current.context.company_id,
                FinancialOpeningImport.input_hash == digest,
                FinancialOpeningImport.state != "CANCELLED",
            )
            .order_by(FinancialOpeningImport.id)
            .limit(1)
        )
        if duplicate:
            return duplicate
        row = record(
            current,
            FinancialOpeningImport,
            source_key=body.source_key,
            input_hash=digest,
            state="STAGED",
            batch_id=None,
            review_hash=None,
            document=document.model_dump(mode="json"),
            issues=[],
        )
        db.add(row)
        await db.flush()
        audit(db, current, row, "create")
        return row

    return await command(
        factory,
        current,
        "import_stage",
        body,
        key,
        mutate,
        scope_model=FinancialOpeningImport,
        renderer=detail,
    )


async def review_hash(db: AsyncSession, current: Any, body: OpeningDeclaration) -> str:
    await require_available(db, current, body.replacement_of_id)
    await require_opening_revision_window(db, current, body.posting_date)
    await validate(db, current, body)
    accounts = list(
        await db.execute(
            select(
                Account.id,
                Account.row_version,
                AccountGroup.id.label("group_id"),
                AccountGroup.row_version.label("group_version"),
                AccountHead.id.label("head_id"),
                AccountHead.row_version.label("head_version"),
            )
            .join(AccountGroup, AccountGroup.id == Account.group_id)
            .join(AccountHead, AccountHead.id == AccountGroup.head_id)
            .where(
                Account.company_id == current.context.company_id,
                Account.id.in_(
                    {entry.account_id for entry in body.entries}
                    | ({body.clearing_account_id} if body.clearing_account_id else set())
                ),
            )
            .order_by(Account.id)
        )
    )
    periods = list(
        await db.execute(
            select(FiscalPeriod.id, FiscalPeriod.row_version)
            .where(
                FiscalPeriod.company_id == current.context.company_id,
                FiscalPeriod.end_date >= body.posting_date,
                FiscalPeriod.start_date <= body.posting_date,
            )
            .order_by(FiscalPeriod.id)
            .limit(2)
        )
    )
    setup_version = await db.scalar(
        select(FinancialSetup.row_version).where(
            FinancialSetup.company_id == current.context.company_id
        )
    )
    return hashlib.sha256(
        canonical_json(
            {
                "input": declaration_hash(body),
                "accounts": [
                    [
                        str(row.id),
                        row.row_version,
                        str(row.group_id),
                        row.group_version,
                        str(row.head_id),
                        row.head_version,
                    ]
                    for row in accounts
                ],
                "periods": [[str(row.id), row.row_version] for row in periods],
                "financial_setup_version": setup_version,
                "configuration": financial_context(current).configuration_hash,
                "authority": authority_fingerprint(current),
            }
        )
    ).hexdigest()


async def action(
    factory: async_sessionmaker[AsyncSession],
    current: Any,
    identity: uuid.UUID,
    body: ExpectedVersion,
    key: str,
    operation: str,
) -> CommandResult[BaseModel]:
    async def mutate(db: AsyncSession) -> Record:
        row = await company_object(
            db, FinancialOpeningImport, identity, company_id=current.context.company_id
        )
        if row.row_version != body.expected_version:
            raise ConflictError("opening import changed; reload and review its current version")
        before = audit_values(row)
        document = OpeningDeclaration.model_validate(row.document)
        if operation == "validate":
            if row.state not in {"STAGED", "BLOCKED", "READY"}:
                raise ConflictError("this import cannot be revalidated")
            try:
                row.review_hash = await review_hash(db, current, document)
                row.state = "READY"
                row.issues = []
            except (ConflictError, ValidationFailedError) as problem:
                row.state = "BLOCKED"
                row.review_hash = None
                row.issues = [{"code": problem.code, "message": problem.message, **problem.extra}]
        elif operation == "commit":
            if (
                not isinstance(body, FinancialOpeningImportCommit)
                or row.state != "READY"
                or body.review_hash != row.review_hash
            ):
                raise ConflictError("a current reviewed opening import is required")
            if await review_hash(db, current, document) != row.review_hash:
                raise ConflictError("opening facts or authority changed; validate and review again")
            batch = await create_in_workspace(db, current, document)
            await prepare_in_transaction(db, current, batch)
            row.batch_id = batch.id
            row.state = "COMMITTED"
        elif operation == "prepare-drafts":
            if row.state != "COMMITTED" or not row.batch_id:
                raise ConflictError("commit this import before preparing remaining drafts")
            batch = await company_object(db, OpeningBatch, row.batch_id, company_id=row.company_id)
            current_revision = await revision(db, current, batch)
            if (
                current_revision.manifest_hash != row.input_hash
                or batch.status != "DRAFT"
                or batch.payload.get("opening_correction")
            ):
                raise ConflictError(
                    "the declaration changed or closed; continue through its native workspace"
                )
            await prepare_in_transaction(db, current, batch)
        elif operation == "cancel":
            # A prepared/posted declaration is an independent financial owner. Cancellation
            # only stops this job and retains every existing draft and receipt.
            if row.state == "CANCELLED":
                return row
            row.state = "CANCELLED"
        else:
            raise ValidationFailedError("unsupported financial opening import action")
        row.row_version += 1
        row.updated_by = current.actor.user_id
        await db.flush()
        audit(db, current, row, "update", before=before)
        return row

    return await command(
        factory,
        current,
        "import_" + operation,
        body,
        key,
        mutate,
        identity,
        scope_model=FinancialOpeningImport,
        renderer=detail,
    )
