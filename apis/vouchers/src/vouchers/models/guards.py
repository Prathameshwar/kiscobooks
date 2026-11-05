"""Fail closed on accidental in-place history edits, including internal ORM callers."""

from billing_platform.errors import ConflictError
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from vouchers.models import core as m
from vouchers.models import imports as imp
from vouchers.models import invoice as i
from vouchers.models import stock as stock
from vouchers.models.supporting_files import PurchaseSupportingFile

IMMUTABLE = (
    PurchaseSupportingFile,
    stock.VoucherStockContext,
    stock.VoucherStockDetail,
    stock.VoucherStockUnit,
    i.VoucherInvoiceDetail,
    i.VoucherSupplyDetail,
    i.VoucherSupplyQuantity,
    i.VoucherSupplyTaxContext,
    i.VoucherChargeDetail,
    i.VoucherChargeTarget,
    i.VoucherChargeDependency,
    m.VoucherTypeRevision,
    m.VoucherTypeOrigin,
    m.VoucherClass,
    m.VoucherRevision,
    m.VoucherLine,
    m.VoucherItemDetail,
    m.VoucherFulfillmentTerms,
    m.VoucherFinancialDetail,
    m.VoucherAccountDetail,
    m.VoucherTender,
    m.VoucherBillInstruction,
    m.VoucherParty,
    m.VoucherReference,
    m.VoucherAttachment,
    m.VoucherLink,
    m.VoucherApproval,
    m.VoucherNumberAssignment,
    m.VoucherTemplateRevision,
    m.VoucherPostingReference,
    m.VoucherTransition,
    imp.VoucherImportEffect,
)

_NEW_REVISIONS = "voucher_revisions_created_in_transaction"


@event.listens_for(Session, "before_flush")
def preserve_history(session: Session, flush_context: object, instances: object) -> None:
    revisions = session.info.get(_NEW_REVISIONS, set()) | {
        (row.tenant_id, row.company_id, row.id)
        for row in session.new
        if isinstance(row, m.VoucherRevision)
    }
    if any(
        (row.tenant_id, row.company_id, row.revision_id) not in revisions
        for row in session.new
        if isinstance(
            row,
            m.VoucherFulfillmentTerms
            | stock.VoucherStockContext
            | stock.VoucherStockDetail
            | stock.VoucherStockUnit,
        )
    ):
        raise ConflictError("native document details require a new voucher revision")
    for row in session.dirty:
        if isinstance(
            row, imp.VoucherImportRevision | imp.VoucherImportResult | imp.ImportTemplateSnapshot
        ):
            if session.is_modified(row) and not session.info.get("import_cleanup"):
                raise ConflictError("import input and completed result evidence are immutable")
        if isinstance(row, imp.VoucherImportAttempt):
            attempt_state = inspect(row)
            assert attempt_state is not None
            history = attempt_state.attrs.finished_at.history
            previous = (
                history.deleted[0]
                if history.deleted
                else (None if history.added else row.finished_at)
            )
            if previous is not None and session.is_modified(row):
                raise ConflictError("completed import attempts are immutable")
        if not isinstance(row, m.Record):
            continue
        state = inspect(row)
        assert state is not None
        changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
        if not changed:
            continue
        if isinstance(row, IMMUTABLE):
            raise ConflictError("voucher content and evidence revisions are immutable")
        if changed & {"id", "tenant_id", "company_id", "created_at", "created_by"}:
            raise ConflictError("voucher ownership is immutable")
        if isinstance(row, m.VoucherType) and changed & {"kind", "profile", "code"}:
            raise ConflictError("voucher type identity is immutable")
        if isinstance(row, m.VoucherConfigurationRevision) and changed - {
            "status",
            "row_version",
            "updated_at",
            "updated_by",
        }:
            raise ConflictError("configuration revision content is immutable")
        if isinstance(row, m.VoucherOperation) and changed & {
            "voucher_id",
            "revision_id",
            "execution_id",
            "purpose",
            "content_hash",
            "configuration_hash",
            "request_hash",
            "command",
        }:
            raise ConflictError("execution identity is immutable")
        if isinstance(row, m.VoucherOperation):
            history = state.attrs.status.history
            old = history.deleted[0] if history.deleted else row.status
            if old in {"COMMITTED", "REJECTED", "CANCELLED"} and changed - {
                "updated_at",
                "updated_by",
            }:
                raise ConflictError("terminal operation evidence is immutable")
        if isinstance(row, m.VoucherArtifact):
            history = state.attrs.status.history
            old = history.deleted[0] if history.deleted else row.status
            if old == "READY":
                raise ConflictError("completed artifacts are immutable")
        row.updated_by = session.info.get("voucher_actor")
    for row in session.deleted:
        if isinstance(
            row,
            imp.VoucherImportRevision
            | imp.VoucherImportAttempt
            | imp.VoucherImportResult
            | imp.ImportTemplateSnapshot,
        ) and not session.info.get("import_cleanup"):
            raise ConflictError("import history requires the retention maintenance path")
        if isinstance(row, IMMUTABLE) or isinstance(
            row, m.Voucher | m.VoucherType | m.VoucherConfigurationProfile | m.VoucherNumberSeries
        ):
            raise ConflictError("voucher history must be retired or corrected, never deleted")


@event.listens_for(Session, "after_flush")
def remember_new_voucher_revisions(session: Session, context: object) -> None:
    new = {
        (row.tenant_id, row.company_id, row.id)
        for row in session.new
        if isinstance(row, m.VoucherRevision)
    }
    if new:
        session.info.setdefault(_NEW_REVISIONS, set()).update(new)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def forget_new_voucher_revisions(session: Session) -> None:
    session.info.pop(_NEW_REVISIONS, None)
