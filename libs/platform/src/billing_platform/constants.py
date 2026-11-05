"""Platform-wide sentinel values and fixed scales."""

from __future__ import annotations

import uuid
from decimal import Decimal

#: Sentinel meaning "applies to every row at this scope", stored instead of NULL.
#:
#: MariaDB treats NULL values as *distinct* inside a UNIQUE index, so two rows
#: with NULL in the same nullable column of a unique key both insert. Five tables
#: rely on a unique key containing a nullable scope column to mean "all"
#: (``role.tenant_id``, ``role_assignment.scope_id``, ``field_policy.scope_id``,
#: ``field_config.company_id``, ``custom_field_definition.company_id``), so those
#: columns are NOT NULL and carry this sentinel instead.
#:
#: Never exposed by an API: the boundary translates it to/from ``None``.
#: See docs/identity-db-plan.md §2.
SCOPE_ALL: uuid.UUID = uuid.UUID(int=0)

#: Fixed *storage* scale for every amount and quantity column, in every service
#: and every replica. Not a per-column choice: MariaDB rounds to a narrower
#: target scale on insert without raising, so one DECIMAL(19,2) column downstream
#: loses data silently. Display scale is separate (``company.amount_precision``).
MONEY_SCALE: int = 4
MONEY_PRECISION: int = 19

#: Largest value a DECIMAL(19,4) column can hold.
MONEY_MAX: Decimal = Decimal("999999999999999.9999")
MONEY_MIN: Decimal = -MONEY_MAX

from typing import Literal

#: Inventory negative stock policies for company, template, and item levels.
#: BLOCK: Reject any voucher/stock transaction that causes stock balance < 0.
#: WARN: Permit negative stock but emit warning diagnostics in voucher response.
#: ALLOW: Permit negative stock silently.
NegativeStockPolicy = Literal["BLOCK", "WARN", "ALLOW"]
NEGATIVE_STOCK_POLICIES: tuple[str, ...] = ("BLOCK", "WARN", "ALLOW")
DEFAULT_NEGATIVE_STOCK_POLICY: str = "BLOCK"
