"""Register only Accounting and shared mechanism models."""

from billing_platform.db.language import Language
from billing_platform.db.platform_models import IdempotencyKey, Outbox, ProcessedMessage
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.import_models import IMPORT_MODELS

from accounting.models.bank_reconciliation import BANK_RECONCILIATION_MODELS
from accounting.models.charges import CHARGE_MODELS
from accounting.models.credit import CREDIT_MODELS
from accounting.models.exchange_rates import ExchangeRateQuote, ExchangeRateUsage
from accounting.models.financial_opening import FINANCIAL_OPENING_MODELS
from accounting.models.fiscal import FISCAL_MODELS
from accounting.models.gst_outward import GstOutwardRecord
from accounting.models.gst_return import GstReturnRecord
from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.models.invoice import INVOICE_MODELS
from accounting.models.invoice_credit import INVOICE_CREDIT_MODELS
from accounting.models.ledger import LEDGER_MODELS
from accounting.models.master_opening import MasterOpeningBalance
from accounting.models.masters import BUSINESS_MODELS
from accounting.models.party_opening import PARTY_OPENING_MODELS
from accounting.models.reporting import REPORT_MODELS
from accounting.models.reporting_snapshot import SNAPSHOT_MODELS
from accounting.models.stock import MODELS as STOCK_MODELS
from accounting.models.stock_count import StockCountApplication, StockCountObservation
from accounting.models.stock_opening import (
    StockOpeningClaim,
    StockOpeningControl,
    StockOpeningRevision,
)
from accounting.models.stock_tracking import MODELS as STOCK_TRACKING_MODELS
from accounting.models.subledger import SUBLEDGER_MODELS
from accounting.models.tax_replica import TAX_REPLICA_MODELS
from accounting.models.voucher_execution import VoucherExecution, VoucherSourceGuard
from accounting.models.voucher_money import VOUCHER_MONEY_MODELS
from accounting.models.voucher_tax import VOUCHER_TAX_MODELS
from accounting.models.workflows import MappingDraft, MasterRevision

MODELS = (
    MasterOpeningBalance,
    StockCountApplication,
    StockCountObservation,
    *FINANCIAL_OPENING_MODELS,
    *PARTY_OPENING_MODELS,
    *STOCK_MODELS,
    StockOpeningControl,
    StockOpeningClaim,
    StockOpeningRevision,
    *STOCK_TRACKING_MODELS,
    *IMPORT_MODELS,
    InventoryReportRecord,
    GstReturnRecord,
    GstOutwardRecord,
    ReferenceRevision,
    ReferenceSyncState,
    *BANK_RECONCILIATION_MODELS,
    ExchangeRateQuote,
    ExchangeRateUsage,
    *INVOICE_MODELS,
    *INVOICE_CREDIT_MODELS,
    *VOUCHER_MONEY_MODELS,
    *REPORT_MODELS,
    *SNAPSHOT_MODELS,
    VoucherSourceGuard,
    VoucherExecution,
    *TAX_REPLICA_MODELS,
    *BUSINESS_MODELS,
    *FISCAL_MODELS,
    *LEDGER_MODELS,
    *SUBLEDGER_MODELS,
    *CREDIT_MODELS,
    *CHARGE_MODELS,
    *VOUCHER_TAX_MODELS,
    MappingDraft,
    MasterRevision,
    IdempotencyKey,
    Outbox,
    ProcessedMessage,
    Currency,
    Country,
    State,
    Language,
)
