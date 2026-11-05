"""A stock source lease must still cover the final root transaction commit."""

import datetime as dt

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

SOURCE_DEADLINE = "accounting_stock_source_expires_at"


@event.listens_for(Session, "before_commit")
def require_current_source(db: Session) -> None:
    if db.in_nested_transaction() or SOURCE_DEADLINE not in db.info:
        return
    deadline = db.info[SOURCE_DEADLINE]
    if (
        not isinstance(deadline, dt.datetime)
        or deadline.tzinfo is None
        or deadline <= utcnow() + dt.timedelta(seconds=5)
    ):
        raise ConflictError("stock definition lease must remain current through commit")


@event.listens_for(Session, "after_transaction_end")
def clear_source(db: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        db.info.pop(SOURCE_DEADLINE, None)
