"""Exact immutable daily deltas keep historical ledger balances independent of line count."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.base import Base
from billing_platform.db.types import Uuid7
from billing_platform.errors import ConflictError
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    cast,
    event,
    func,
    select,
    tuple_,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from reports.models.core import Record, ReportGeneration, scope
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportSourceCut

GRAIN = ("account_id", "posting_date", "currency", "base_currency", "side", "opening_effect")


class ReportDailyBalance(Record, Base):
    __tablename__ = "report_daily_balance"
    __table_args__ = scope(
        "report_daily_balance",
        {"cut_id": "report_source_cut", "epoch_id": "report_source_epoch"},
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "epoch_id",
            "valid_from_sequence",
            *GRAIN,
            name="uq_report_daily_balance_grain",
        ),
        CheckConstraint(
            "line_count > 0 AND amount >= 0 AND base_amount >= 0 AND valid_from_sequence >= 0",
            name="ck_report_daily_balance_values",
        ),
        CheckConstraint("side IN ('DEBIT', 'CREDIT')", name="ck_report_daily_balance_side"),
        Index(
            "ix_report_daily_balance_account",
            "tenant_id",
            "company_id",
            "epoch_id",
            "account_id",
            "posting_date",
            "valid_from_sequence",
        ),
        Index(
            "ix_report_daily_balance_cut",
            "tenant_id",
            "company_id",
            "epoch_id",
            "valid_from_sequence",
            "base_currency",
            "side",
        ),
    )
    cut_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    epoch_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    valid_from_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid7, nullable=False)
    posting_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    opening_effect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    line_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 4), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(38, 4), nullable=False)


def grouped(company: uuid.UUID, epoch: uuid.UUID, sequence: int) -> Any:
    p = ReportPostedLine
    keys = [getattr(p, key) for key in GRAIN]
    return (
        select(
            *keys,
            func.count(p.id).label("line_count"),
            cast(func.sum(p.amount), Numeric(38, 4)).label("amount"),
            cast(func.sum(p.base_amount), Numeric(38, 4)).label("base_amount"),
        )
        .where(p.company_id == company, p.epoch_id == epoch, p.valid_from_sequence == sequence)
        .group_by(*keys)
    )


@event.listens_for(Session, "before_flush")
def derive(db: Session, context: object, instances: object) -> None:
    for row in db.dirty | db.deleted:
        if isinstance(row, ReportDailyBalance) and (row in db.deleted or db.is_modified(row)):
            raise ConflictError("daily query projection is immutable")
    pending = [row for row in db.new if isinstance(row, ReportDailyBalance)]
    if not pending:
        return
    if len(pending) > 200 or len({(row.company_id, row.cut_id) for row in pending}) != 1:
        raise ConflictError("daily projection batch exceeds its scoped bound")
    first = pending[0]
    cut = db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == first.company_id,
            ReportSourceCut.id == first.cut_id,
        )
    )
    generation = (
        None
        if cut is None
        else db.scalar(
            select(ReportGeneration)
            .where(
                ReportGeneration.company_id == first.company_id,
                ReportGeneration.id == cut.generation_id,
            )
            .with_for_update()
        )
    )
    if (
        cut is None
        or cut.verification is None
        or generation is None
        or generation.status != "BUILDING"
    ):
        raise ConflictError("daily projection requires a verified building source generation")
    identities = [tuple(getattr(row, key) for key in GRAIN) for row in pending]
    p = ReportPostedLine
    source = grouped(first.company_id, cut.epoch_id, cut.sequence).where(
        tuple_(*(getattr(p, key) for key in GRAIN)).in_(identities)
    )
    expected = {tuple(row[key] for key in GRAIN): row for row in db.execute(source).mappings()}
    for row, identity in zip(pending, identities, strict=True):
        values = expected.get(identity)
        if values is None:
            raise ConflictError("daily projection has no posted source grain")
        for key, value in dict(
            values, epoch_id=cut.epoch_id, valid_from_sequence=cut.sequence
        ).items():
            supplied = getattr(row, key)
            if supplied is not None and supplied != value:
                raise ConflictError("daily projection differs from exact posted source totals")
            setattr(row, key, value)
