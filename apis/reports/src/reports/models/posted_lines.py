"""Immutable posted-line projection: indexed dates and balances over retained source cuts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import Base
from billing_platform.db.types import Money, Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from reports.domain.reporting.opening import opening_effect
from reports.models.core import Record, ReportGeneration, scope
from reports.models.source_versions import ReportFactVersion, ReportSourceCut


class ReportPostedLine(Record, Base):
    __tablename__ = "report_posted_line"
    __table_args__ = scope(
        "report_posted_line",
        {
            "cut_id": "report_source_cut",
            "epoch_id": "report_source_epoch",
            "line_version_id": "report_fact_version",
            "journal_version_id": "report_fact_version",
        },
        UniqueConstraint(
            "tenant_id", "company_id", "epoch_id", "line_id", name="uq_report_posted_line_identity"
        ),
        Index(
            "ix_report_posted_line_date",
            "tenant_id",
            "company_id",
            "epoch_id",
            "posting_date",
            "journal_id",
            "line_sequence",
            "line_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_posted_line_journal",
            "tenant_id",
            "company_id",
            "epoch_id",
            "journal_id",
            "posting_date",
            "line_sequence",
            "line_id",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_posted_line_balance",
            "tenant_id",
            "company_id",
            "epoch_id",
            "account_id",
            "posting_date",
            "journal_id",
            "line_sequence",
            "line_id",
            "valid_from_sequence",
            "side",
            "currency",
            "amount",
            "base_amount",
        ),
        Index(
            "ix_report_posted_line_control",
            "tenant_id",
            "company_id",
            "epoch_id",
            "valid_from_sequence",
            "base_currency",
            "side",
            "base_amount",
        ),
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    epoch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_version_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_version_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    journal_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    line_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opening_effect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


@event.listens_for(Session, "before_flush")
def projection_evidence(db: Session, context: object, instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, ReportPostedLine) and (row in db.deleted or db.is_modified(row)):
            raise ConflictError("posted query projection is immutable")
    pending = [row for row in db.new if isinstance(row, ReportPostedLine)]
    if not pending:
        return
    if len(pending) > 200:
        raise ConflictError("posted query projection batch exceeds its bound")
    companies = {row.company_id for row in pending}
    if len(companies) != 1 or len({row.cut_id for row in pending}) != 1:
        raise ConflictError("posted query projection batch must belong to one company")
    company = pending[0].company_id
    cuts = {
        cut.id: cut
        for cut in db.scalars(
            select(ReportSourceCut).where(
                ReportSourceCut.company_id == company,
                ReportSourceCut.id.in_({row.cut_id for row in pending}),
            )
        )
    }
    generations = {
        row.id: row
        for row in db.scalars(
            select(ReportGeneration)
            .where(
                ReportGeneration.company_id == company,
                ReportGeneration.id.in_({cut.generation_id for cut in cuts.values()}),
            )
            .with_for_update()
        )
    }
    versions = {
        row.id: row
        for row in db.execute(
            select(
                ReportFactVersion.id,
                ReportFactVersion.epoch_id,
                ReportFactVersion.entity,
                ReportFactVersion.source_id,
                ReportFactVersion.relation_id,
                ReportFactVersion.account_id,
                ReportFactVersion.valid_from_sequence,
                ReportFactVersion.valid_to_sequence,
                ReportFactVersion.source_status,
                ReportFactVersion.posting_date,
                ReportFactVersion.line_sequence,
                ReportFactVersion.wire_bytes,
                ReportFactVersion.side,
                ReportFactVersion.currency,
                ReportFactVersion.base_currency,
                ReportFactVersion.amount,
                ReportFactVersion.base_amount,
                ReportFactVersion.data["kind"].as_string().label("source_kind"),
                ReportFactVersion.data["reversal_of_id"].as_string().label("reversal_of"),
            ).where(
                ReportFactVersion.company_id == company,
                ReportFactVersion.id.in_(
                    {
                        key
                        for row in pending
                        for key in (row.line_version_id, row.journal_version_id)
                    }
                ),
            )
        )
    }
    original_ids = {
        uuid.UUID(row.reversal_of)
        for row in versions.values()
        if row.entity == "journal" and row.source_kind == "REVERSAL" and row.reversal_of
    }
    selected_cut = next(iter(cuts.values()), None)
    originals = (
        list(
            db.execute(
                select(
                    ReportFactVersion.source_id,
                    ReportFactVersion.epoch_id,
                    ReportFactVersion.valid_from_sequence,
                    ReportFactVersion.valid_to_sequence,
                    ReportFactVersion.data["kind"].as_string().label("source_kind"),
                )
                .where(
                    ReportFactVersion.company_id == company,
                    ReportFactVersion.entity == "journal",
                    ReportFactVersion.source_id.in_(original_ids),
                    ReportFactVersion.epoch_id == selected_cut.epoch_id,
                    ReportFactVersion.valid_from_sequence <= selected_cut.sequence,
                    or_(
                        ReportFactVersion.valid_to_sequence.is_(None),
                        ReportFactVersion.valid_to_sequence > selected_cut.sequence,
                    ),
                )
                .limit(201)
            )
        )
        if original_ids and selected_cut is not None
        else []
    )
    if len(originals) > 200:
        raise ConflictError("original journal component exceeds its bound")
    for row in pending:
        cut = cuts.get(row.cut_id)
        line, journal = versions.get(row.line_version_id), versions.get(row.journal_version_id)
        if (
            cut is None
            or cut.verification is None
            or cut.epoch_id != row.epoch_id
            or generations[cut.generation_id].status != "BUILDING"
            or line is None
            or journal is None
            or line.entity != "journal_line"
            or journal.entity != "journal"
            or journal.source_status != "POSTED"
            or line.relation_id != journal.source_id
        ):
            raise ConflictError("posted query projection requires verified building source")
        for source in (line, journal):
            if (
                source.epoch_id != cut.epoch_id
                or source.valid_from_sequence > cut.sequence
                or (
                    source.valid_to_sequence is not None
                    and source.valid_to_sequence <= cut.sequence
                )
            ):
                raise ConflictError("posted query projection source is outside its cut")
        original = next(
            (
                value.source_kind
                for value in originals
                if str(value.source_id) == journal.reversal_of
                and value.epoch_id == cut.epoch_id
                and value.valid_from_sequence <= cut.sequence
                and (value.valid_to_sequence is None or value.valid_to_sequence > cut.sequence)
            ),
            None,
        )
        try:
            initial = opening_effect(journal.source_kind, journal.reversal_of is not None, original)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        values: dict[str, Any] = {
            "opening_effect": initial,
            "line_id": line.source_id,
            "journal_id": journal.source_id,
            "account_id": line.account_id,
            "valid_from_sequence": cut.sequence,
            "posting_date": journal.posting_date,
            "line_sequence": line.line_sequence,
            "source_bytes": line.wire_bytes + journal.wire_bytes,
            **{
                key: getattr(line, key)
                for key in ("side", "currency", "base_currency", "amount", "base_amount")
            },
        }
        for key, value in values.items():
            if value is None or getattr(row, key) not in (None, value):
                raise ConflictError("posted query projection differs from source evidence")
            setattr(row, key, value)
