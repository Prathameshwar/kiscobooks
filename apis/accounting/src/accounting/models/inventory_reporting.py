"""Stock-owner reporting handoff, not an independently writable stock balance."""

from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.inventory import InventoryRecord
from sqlalchemy import JSON, event, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from accounting.models.masters import Record
from accounting.models.subledger import constraints


class InventoryReportRecord(Record):
    __tablename__ = "inventory_report_record"
    __table_args__ = constraints("inventory_report_record", {})
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


@event.listens_for(Session, "before_flush")
def validate_inventory_evidence(db: Session, context: object, instances: object) -> None:
    import uuid

    native_tables = {
        "stock_position",
        "stock_balance",
        "stock_cost_pool",
        "stock_posting",
        "stock_lot",
        "stock_unit",
        "stock_unit_identifier",
        "stock_unit_position",
        "stock_cost_layer",
    }
    companies = {
        row.company_id
        for row in db.new | db.dirty | db.deleted
        if getattr(row, "__tablename__", "") in native_tables
        and (row in db.new or row in db.deleted or db.is_modified(row))
    }
    for company in companies:
        identity = uuid.uuid5(company, "native-stock-summary:COVERAGE:complete")
        coverage = db.scalar(
            select(InventoryReportRecord).where(
                InventoryReportRecord.company_id == company, InventoryReportRecord.id == identity
            )
        )
        if coverage and coverage.payload.get("native_stock_current", True):
            coverage.payload = coverage.payload | {"native_stock_current": False}
            coverage.row_version += 1
    for row in db.new | db.dirty:
        if isinstance(row, InventoryReportRecord):
            InventoryRecord.model_validate({"payload": row.payload})
    for row in db.dirty | db.deleted:
        if not isinstance(row, InventoryReportRecord) or (
            not db.is_modified(row) and row not in db.deleted
        ):
            continue
        history = inspect(row).attrs.payload.history
        prior = (
            history.deleted[0]
            if history.deleted
            else db.scalar(
                select(
                    InventoryReportRecord.payload,
                ).where(
                    InventoryReportRecord.id == row.id,
                    InventoryReportRecord.company_id == row.company_id,
                )
            )
        )
        if prior and prior["kind"] == "MOVEMENT" and (row in db.deleted or prior != row.payload):
            raise ConflictError("committed inventory movement evidence is immutable")
