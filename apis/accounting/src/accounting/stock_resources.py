"""Tracking metadata policies; deliberately absent from generic master/import writers."""

from voucher_execution.stock import StockInput, StockLine

from accounting.models.stock import (
    StockAccountPolicy,
    StockCostPool,
    StockMovement,
    StockPosition,
    StockPosting,
)
from accounting.models.stock_tracking import StockLot, StockUnit
from accounting.resources import Resource
from accounting.schemas import stock as physical
from accounting.schemas import stock_tracking as s

BATCH = Resource(
    "stock_lot",
    "stock-batches",
    "tracking",
    StockLot,
    s.BatchPrepare,
    s.BatchCorrect,
    s.BatchDetail,
    {},
    frozenset({"item_id", "code", "source_party_id"}),
)
SERIAL = Resource(
    "stock_unit",
    "stock-serials",
    "tracking",
    StockUnit,
    s.SerialPrepare,
    s.ExpectedVersion,
    s.SerialDetail,
    {},
    frozenset({"item_id", "lot_id", "identifiers"}),
)
STOCK_POLICY = Resource(
    "stock_account_policy",
    "stock-account-policies",
    "command",
    StockAccountPolicy,
    physical.StockAccountPolicyCreate,
    s.ExpectedVersion,
    physical.StockAccountPolicyDetail,
    {},
    frozenset(),
)
# Command inputs contain typed capture fields as well as the mapped effect fields.
# These specs expose native field authority, never generic CRUD/import writers.
STOCK_POSTING = Resource(
    "stock_posting",
    "stock-postings",
    "command",
    StockPosting,
    StockInput,
    s.ExpectedVersion,
    physical.StockPostingDetail,
    {},
    frozenset(),
)
STOCK_MOVEMENT = Resource(
    "stock_movement",
    "stock-movements",
    "command",
    StockMovement,
    StockLine,
    s.ExpectedVersion,
    physical.StockMovementDetail,
    {},
    frozenset(),
)
STOCK_POSITION = Resource(
    "stock_position",
    "stock-positions",
    "command",
    StockPosition,
    StockLine,
    s.ExpectedVersion,
    physical.StockPositionDetail,
    {},
    frozenset(),
)
STOCK_POOL = Resource(
    "stock_cost_pool",
    "stock-cost-pools",
    "command",
    StockCostPool,
    StockLine,
    s.ExpectedVersion,
    physical.StockCostPoolDetail,
    {},
    frozenset(),
)
STOCK_RESOURCES = (
    BATCH,
    SERIAL,
    STOCK_POLICY,
    STOCK_POSTING,
    STOCK_MOVEMENT,
    STOCK_POSITION,
    STOCK_POOL,
)
STOCK_SAFE_FIELDS = frozenset(
    {
        "id",
        "status",
        "is_held",
        "manufactured_on",
        "expires_on",
        "item_id",
        "lot_id",
        "source_party_id",
        "mrp_amount",
        "mrp_currency",
        "mrp_unit_id",
    }
)
