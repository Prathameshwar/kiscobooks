"""Protected, reviewed bank statement and reconciliation routes."""

import uuid
from typing import Annotated, cast

from billing_platform.db.access import company_object
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access, access
from accounting.api.common import ERROR_RESPONSES, session
from accounting.domain.statement_matching import MatchPreview
from accounting.models.bank_reconciliation import (
    BankAdjustmentProposal,
    BankMatchEvent,
    BankOpeningItem,
    BankReconciliationPolicy,
    BankReconciliationSession,
    BankStatementEntry,
    BankStatementImport,
    BankStatementMapping,
)
from accounting.schemas.bank_reconciliation import (
    CandidateView,
    DuplicateDecision,
    EntryView,
    ImportDecision,
    ImportView,
    MappingCreate,
    MappingView,
    MatchAssessment,
    MatchCommand,
    MatchView,
    OpeningCreate,
    OpeningView,
    PolicyCreate,
    PolicyView,
    ProposalCreate,
    ProposalDecision,
    ProposalView,
    SessionCreate,
    SessionView,
    StatementUpload,
    UnmatchCommand,
)
from accounting.tasks import bank_reconciliation as service

router = APIRouter(
    prefix="/v1/companies/{company_id}/bank-reconciliation", responses=ERROR_RESPONSES
)


@router.post(
    "/proposals", response_model=ProposalView, response_model_exclude_none=True, status_code=201
)
async def proposal_create(
    company_id: uuid.UUID,
    body: ProposalCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ProposalView:
    return ProposalView.model_validate(
        service.public(await service.prepare_proposal(db, current, body), current)
    )


@router.get("/proposals", response_model=list[ProposalView], response_model_exclude_none=True)
async def proposal_list(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[ProposalView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankAdjustmentProposal).where(
        BankAdjustmentProposal.company_id == company_id,
        BankAdjustmentProposal.account_id == account_id,
    )
    if after:
        query = query.where(BankAdjustmentProposal.id > after)
    rows = await db.scalars(query.order_by(BankAdjustmentProposal.id).limit(limit))
    return [ProposalView.model_validate(service.public(row, current)) for row in rows]


@router.post(
    "/proposals/{proposal_id}/reject", response_model=ProposalView, response_model_exclude_none=True
)
async def proposal_reject(
    company_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: ProposalDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ProposalView:
    return ProposalView.model_validate(
        service.public(
            await service.decide_proposal(db, current, proposal_id, "REJECTED", body), current
        )
    )


@router.post(
    "/proposals/{proposal_id}/resolve",
    response_model=ProposalView,
    response_model_exclude_none=True,
)
async def proposal_resolve(
    company_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: ProposalDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ProposalView:
    return ProposalView.model_validate(
        service.public(
            await service.decide_proposal(db, current, proposal_id, "RESOLVED", body), current
        )
    )


@router.post(
    "/policies", response_model=PolicyView, response_model_exclude_none=True, status_code=201
)
async def policy_create(
    company_id: uuid.UUID,
    body: PolicyCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> PolicyView:
    return PolicyView.model_validate(
        service.public(await service.create_policy(db, current, body), current)
    )


@router.get("/policies", response_model=list[PolicyView], response_model_exclude_none=True)
async def policy_list(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[PolicyView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankReconciliationPolicy).where(
        BankReconciliationPolicy.company_id == company_id,
        BankReconciliationPolicy.account_id == account_id,
    )
    if after:
        query = query.where(BankReconciliationPolicy.id > after)
    rows = await db.scalars(query.order_by(BankReconciliationPolicy.id).limit(limit))
    return [PolicyView.model_validate(service.public(row, current)) for row in rows]


@router.get("/rows/{row_id}/candidates", response_model=list[CandidateView])
async def row_candidates(
    company_id: uuid.UUID,
    row_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[CandidateView]:
    return await service.candidates(db, current, row_id)


@router.post(
    "/opening-items", response_model=OpeningView, response_model_exclude_none=True, status_code=201
)
async def opening_create(
    company_id: uuid.UUID,
    body: OpeningCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> OpeningView:
    return OpeningView.model_validate(
        service.public(await service.opening_item(db, current, body), current)
    )


@router.get("/opening-items", response_model=list[OpeningView], response_model_exclude_none=True)
async def opening_list(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[OpeningView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankOpeningItem).where(
        BankOpeningItem.company_id == company_id, BankOpeningItem.account_id == account_id
    )
    if after:
        query = query.where(BankOpeningItem.id > after)
    rows = await db.scalars(query.order_by(BankOpeningItem.id).limit(limit))
    return [OpeningView.model_validate(service.public(row, current)) for row in rows]


@router.post(
    "/mappings", response_model=MappingView, response_model_exclude_none=True, status_code=201
)
async def mapping_create(
    company_id: uuid.UUID,
    body: MappingCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MappingView:
    return MappingView.model_validate(
        service.public(await service.create_mapping(db, current, body), current)
    )


@router.get("/mappings", response_model=list[MappingView], response_model_exclude_none=True)
async def mappings(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[MappingView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankStatementMapping).where(
        BankStatementMapping.company_id == company_id, BankStatementMapping.account_id == account_id
    )
    if after:
        query = query.where(BankStatementMapping.id > after)
    rows = await db.scalars(query.order_by(BankStatementMapping.id).limit(limit))
    return [MappingView.model_validate(service.public(row, current)) for row in rows]


@router.get("/mappings/{mapping_id}", response_model=MappingView, response_model_exclude_none=True)
async def mapping_detail(
    company_id: uuid.UUID,
    mapping_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MappingView:
    service.authorize(current)
    row = await company_object(db, BankStatementMapping, mapping_id, company_id=company_id)
    return MappingView.model_validate(service.public(row, current))


@router.get("/imports", response_model=list[ImportView], response_model_exclude_none=True)
async def import_list(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[ImportView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankStatementImport).where(
        BankStatementImport.company_id == company_id,
        BankStatementImport.account_id == account_id,
    )
    if after:
        query = query.where(BankStatementImport.id > after)
    rows = await db.scalars(query.order_by(BankStatementImport.id).limit(limit))
    return [ImportView.model_validate(service.public(row, current)) for row in rows]


@router.get("/matches", response_model=list[MatchView], response_model_exclude_none=True)
async def match_history(
    company_id: uuid.UUID,
    statement_entry_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[MatchView]:
    service.authorize(current)
    await company_object(db, BankStatementEntry, statement_entry_id, company_id=company_id)
    query = select(BankMatchEvent).where(
        BankMatchEvent.company_id == company_id,
        BankMatchEvent.statement_entry_id == statement_entry_id,
    )
    if after:
        query = query.where(BankMatchEvent.id > after)
    rows = await db.scalars(query.order_by(BankMatchEvent.id).limit(limit))
    return [MatchView.model_validate(service.public(row, current)) for row in rows]


@router.post(
    "/imports", response_model=ImportView, response_model_exclude_none=True, status_code=201
)
async def import_preview(
    company_id: uuid.UUID,
    body: StatementUpload,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ImportView:
    return ImportView.model_validate(
        service.public(await service.upload(db, current, body), current)
    )


@router.get("/imports/{import_id}", response_model=ImportView, response_model_exclude_none=True)
async def import_detail(
    company_id: uuid.UUID,
    import_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ImportView:
    service.authorize(current)
    row = await company_object(db, BankStatementImport, import_id, company_id=company_id)
    return ImportView.model_validate(service.public(row, current))


@router.get(
    "/imports/{import_id}/rows", response_model=list[EntryView], response_model_exclude_none=True
)
async def import_rows(
    company_id: uuid.UUID,
    import_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[EntryView]:
    service.authorize(current)
    await company_object(db, BankStatementImport, import_id, company_id=company_id)
    query = select(BankStatementEntry).where(
        BankStatementEntry.company_id == company_id, BankStatementEntry.import_id == import_id
    )
    if after:
        query = query.where(BankStatementEntry.id > after)
    rows = await db.scalars(query.order_by(BankStatementEntry.id).limit(limit))
    return [EntryView.model_validate(service.public(row, current)) for row in rows]


@router.post(
    "/rows/{row_id}/duplicate-decision", response_model=EntryView, response_model_exclude_none=True
)
async def duplicate_decision(
    company_id: uuid.UUID,
    row_id: uuid.UUID,
    body: DuplicateDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> EntryView:
    return EntryView.model_validate(
        service.public(await service.decide_duplicate(db, current, row_id, body), current)
    )


@router.post(
    "/imports/{import_id}/commit", response_model=ImportView, response_model_exclude_none=True
)
async def import_commit(
    company_id: uuid.UUID,
    import_id: uuid.UUID,
    body: ImportDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ImportView:
    return ImportView.model_validate(
        service.public(await service.commit_import(db, current, import_id, body.reason), current)
    )


@router.post(
    "/imports/{import_id}/reject", response_model=ImportView, response_model_exclude_none=True
)
async def import_reject(
    company_id: uuid.UUID,
    import_id: uuid.UUID,
    body: ImportDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> ImportView:
    return ImportView.model_validate(
        service.public(await service.reject_import(db, current, import_id, body.reason), current)
    )


@router.post(
    "/matches", response_model=list[MatchView], response_model_exclude_none=True, status_code=201
)
async def match_create(
    company_id: uuid.UUID,
    body: MatchCommand,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[MatchView]:
    rows = cast(list[BankMatchEvent], await service.match(db, current, body))
    return [MatchView.model_validate(service.public(row, current)) for row in rows]


@router.post("/matches/preview", response_model=MatchAssessment)
async def match_preview(
    company_id: uuid.UUID,
    body: MatchCommand,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MatchAssessment:
    assessment = cast(MatchPreview, await service.match(db, current, body, dry_run=True))
    return MatchAssessment(
        statement_residuals=assessment.statement_residuals,
        instrument_residuals=assessment.instrument_residuals,
    )


@router.post(
    "/matches/{match_id}/unmatch", response_model=MatchView, response_model_exclude_none=True
)
async def match_unmatch(
    company_id: uuid.UUID,
    match_id: uuid.UUID,
    body: UnmatchCommand,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> MatchView:
    return MatchView.model_validate(
        service.public(await service.unmatch(db, current, match_id, body.reason), current)
    )


@router.post(
    "/sessions", response_model=SessionView, response_model_exclude_none=True, status_code=201
)
async def session_create(
    company_id: uuid.UUID,
    body: SessionCreate,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> SessionView:
    return SessionView.model_validate(
        service.public(await service.create_session(db, current, body), current)
    )


@router.get("/sessions", response_model=list[SessionView], response_model_exclude_none=True)
async def sessions(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: uuid.UUID | None = None,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> list[SessionView]:
    service.authorize(current)
    await service.bank_account(db, current, account_id)
    query = select(BankReconciliationSession).where(
        BankReconciliationSession.company_id == company_id,
        BankReconciliationSession.account_id == account_id,
    )
    if after:
        query = query.where(BankReconciliationSession.id > after)
    rows = await db.scalars(query.order_by(BankReconciliationSession.id).limit(limit))
    return [SessionView.model_validate(service.public(row, current)) for row in rows]


@router.get("/sessions/{session_id}", response_model=SessionView, response_model_exclude_none=True)
async def session_detail(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> SessionView:
    service.authorize(current)
    row = await company_object(db, BankReconciliationSession, session_id, company_id=company_id)
    return SessionView.model_validate(service.public(row, current))


@router.post(
    "/sessions/{session_id}/finalize", response_model=SessionView, response_model_exclude_none=True
)
async def session_finalize(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    body: ImportDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> SessionView:
    return SessionView.model_validate(
        service.public(
            await service.finalize_session(db, current, session_id, body.reason), current
        )
    )


@router.post(
    "/sessions/{session_id}/amend", response_model=SessionView, response_model_exclude_none=True
)
async def session_amend(
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    body: ImportDecision,
    current: Access = Depends(access),
    db: AsyncSession = Depends(session),
) -> SessionView:
    return SessionView.model_validate(
        service.public(await service.amend_session(db, current, session_id, body.reason), current)
    )
