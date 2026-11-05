"""Chart v5: opening offset and clearing defaults, preserving existing account identities."""

VERSION = "5"
# code, label, head, parent
GROUPS = (
    ("BRANCH_DIVISIONS", "Branch / Divisions", "LIABILITY", None),
    ("SUSPENSE", "Suspense Account", "LIABILITY", None),
    ("MISC_EXPENSES", "Miscellaneous Expenses", "ASSET", None),
    ("CURRENT_ASSETS", "Current Assets", "ASSET", None),
    ("FIXED_ASSETS", "Fixed Assets", "ASSET", None),
    ("INVESTMENTS", "Investments", "ASSET", None),
    ("CURRENT_LIABILITIES", "Current Liabilities", "LIABILITY", None),
    ("LOANS", "Loans", "LIABILITY", None),
    ("CAPITAL", "Capital Account", "EQUITY", None),
    ("RESERVES", "Reserves and Surplus", "EQUITY", "CAPITAL"),
    ("SALES", "Sales Accounts", "INCOME", None),
    ("DIRECT_INCOME", "Direct Income", "INCOME", None),
    ("INDIRECT_INCOME", "Indirect Income", "INCOME", None),
    ("PURCHASES", "Purchase Accounts", "EXPENSE", None),
    ("DIRECT_EXPENSES", "Direct Expenses", "EXPENSE", None),
    ("INDIRECT_EXPENSES", "Indirect Expenses", "EXPENSE", None),
    ("CASH", "Cash-in-hand", "ASSET", "CURRENT_ASSETS"),
    ("BANKS", "Bank Accounts", "ASSET", "CURRENT_ASSETS"),
    ("DEBTORS", "Sundry Debtors", "ASSET", "CURRENT_ASSETS"),
    ("STOCK", "Stock-in-hand", "ASSET", "CURRENT_ASSETS"),
    ("DEPOSITS", "Deposits", "ASSET", "CURRENT_ASSETS"),
    ("ADVANCES", "Loans and Advances", "ASSET", "CURRENT_ASSETS"),
    ("CREDITORS", "Sundry Creditors", "LIABILITY", "CURRENT_LIABILITIES"),
    ("TAX_PAYABLE", "Duties and Taxes", "LIABILITY", "CURRENT_LIABILITIES"),
    ("PROVISIONS", "Provisions", "LIABILITY", "CURRENT_LIABILITIES"),
    ("SECURED_LOANS", "Secured Loans", "LIABILITY", "LOANS"),
    ("UNSECURED_LOANS", "Unsecured Loans", "LIABILITY", "LOANS"),
    ("BANK_OD", "Bank Overdraft", "LIABILITY", "LOANS"),
)
CORE = (
    ("CASH_MAIN", "Cash", "CASH", "CASH"),
    ("RETAINED_EARNINGS", "Accumulated Profit/Loss", "RESERVES", "GENERAL"),
)
BUSINESS: tuple[tuple[str, str, str, str], ...] = (
    ("SALES_REVENUE", "Sales Revenue", "SALES", "GENERAL"),
    ("SERVICE_REVENUE", "Service Revenue", "DIRECT_INCOME", "GENERAL"),
    ("SALES_RETURNS", "Sales Returns", "SALES", "GENERAL"),
    ("NONSTOCK_PURCHASES", "Non-stock Purchases Expense", "PURCHASES", "GENERAL"),
    ("RENT", "Office Rent", "INDIRECT_EXPENSES", "GENERAL"),
    ("UTILITIES", "Utilities Expense", "INDIRECT_EXPENSES", "GENERAL"),
    ("SALARIES", "Salaries Expense", "INDIRECT_EXPENSES", "GENERAL"),
    ("BANK_CHARGES", "Bank Charges", "INDIRECT_EXPENSES", "GENERAL"),
    ("ROUNDING_GAIN", "Round-off Gain", "INDIRECT_INCOME", "GENERAL"),
    ("ROUNDING_LOSS", "Round-off Loss", "INDIRECT_EXPENSES", "GENERAL"),
)
HIGH_PRIORITY = (
    ("DISCOUNT_ALLOWED", "Discount Allowed", "INDIRECT_EXPENSES", "GENERAL"),
    ("DISCOUNT_RECEIVED", "Discount Received", "INDIRECT_INCOME", "GENERAL"),
    ("PURCHASE_RETURNS", "Purchase Returns", "PURCHASES", "GENERAL"),
    ("FREIGHT_INWARD", "Freight Inward", "DIRECT_EXPENSES", "GENERAL"),
    ("FREIGHT_OUTWARD", "Freight Outward", "INDIRECT_EXPENSES", "GENERAL"),
    ("GATEWAY_CLEARING", "Payment Gateway Clearing", "CURRENT_ASSETS", "GENERAL"),
    ("POS_CLEARING", "POS Clearing", "CURRENT_ASSETS", "GENERAL"),
    ("MERCHANT_FEES", "Merchant Fees", "INDIRECT_EXPENSES", "GENERAL"),
    ("OPENING_BALANCE_OFFSET", "Opening Balance Offset", "CAPITAL", "GENERAL"),
    ("MIGRATION_CLEARING", "Migration Clearing", "CURRENT_ASSETS", "GENERAL"),
)
BUSINESS += HIGH_PRIORITY
# The standard stock accounts a company with inventory starts with (2026-11-03), in the
# order of the stock account policy's inventory, receipt, dispatch, opening and variance.
STOCK = (
    ("STOCK_IN_HAND", "Stock-in-hand", "STOCK", "GENERAL"),
    ("GOODS_RECEIVED_NOT_BILLED", "Goods Received, Not Billed", "CURRENT_LIABILITIES", "GENERAL"),
    ("GOODS_DISPATCHED_NOT_BILLED", "Goods Dispatched, Not Billed", "CURRENT_ASSETS", "GENERAL"),
    ("OPENING_STOCK_OFFSET", "Opening Stock Offset", "CAPITAL", "GENERAL"),
    ("STOCK_VARIANCE", "Stock Variance", "DIRECT_EXPENSES", "GENERAL"),
)
