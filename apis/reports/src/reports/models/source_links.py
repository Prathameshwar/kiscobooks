"""Immutable derived execution-to-journal links, retained with their source version."""

import uuid

from billing_platform.db.base import Base
from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import Index, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from reports.models.core import Record, scope
from reports.models.source_versions import ReportFactVersion


class ReportJournalLink(Record, Base):
    __tablename__ = "report_journal_link"
    __table_args__ = scope(
        "report_journal_link",
        {"version_id": "report_fact_version", "epoch_id": "report_source_epoch"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "version_id",
            "journal_id",
            name="uq_report_journal_link_effect",
        ),
        Index(
            "ix_report_journal_link_lookup",
            "tenant_id",
            "company_id",
            "epoch_id",
            "journal_id",
            "version_id",
        ),
    )
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    epoch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    source_version: Mapped[ReportFactVersion] = relationship()


@event.listens_for(Session, "before_flush")
def derive_links(db: Session, context: object, instances: object) -> None:
    # Clients cannot insert links or append missing links to an already published version.
    if any(isinstance(row, ReportJournalLink) for row in db.new):
        raise ConflictError("journal links are derived from new source versions only")
    for row in db.dirty | db.deleted:
        if isinstance(row, ReportJournalLink) and (row in db.deleted or db.is_modified(row)):
            raise ConflictError("retained journal lineage is immutable")
    for row in tuple(db.new):
        if (
            not isinstance(row, ReportFactVersion)
            or row.entity != "voucher_execution"
            or not row.data
        ):
            continue
        journals = {
            uuid.UUID(effect["effect_id"])
            for effect in row.data["result"].get("effects", [])
            if effect["effect_kind"] == "JOURNAL"
        }
        if len(journals) > 1000:
            raise ConflictError("execution lineage exceeds its supported component bound")
        row.id = row.id or uuid7()
        for journal in sorted(journals):
            db.add(
                ReportJournalLink(
                    id=uuid7(),
                    tenant_id=row.tenant_id,
                    company_id=row.company_id,
                    version_id=row.id,
                    source_version=row,
                    epoch_id=row.epoch_id,
                    journal_id=journal,
                )
            )
