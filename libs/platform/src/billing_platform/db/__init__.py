"""Database mechanism: base, types, mixins, session, tenant filter."""

from billing_platform.db.base import MARIADB_TABLE_ARGS, NAMING_CONVENTION, Base, metadata_obj
from billing_platform.db.mixins import (
    AuditMixin,
    DeactivableMixin,
    EffectiveMixin,
    IdMixin,
    StatusMixin,
    TenantMixin,
)
from billing_platform.db.platform_models import (
    TENANT_FILTER_EXEMPT,
    IdempotencyKey,
    Outbox,
    ProcessedMessage,
)
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.db.session import (
    SKIP_TENANT_FILTER,
    create_engine,
    create_session_factory,
    session_scope,
)
from billing_platform.db.tenant_context import (
    TenantContextError,
    get_current_tenant,
    require_current_tenant,
    tenant_scope,
    unfiltered,
)
from billing_platform.db.types import Money, Quantity, UtcDateTime, Uuid7, utcnow

__all__ = [
    "MARIADB_TABLE_ARGS",
    "NAMING_CONVENTION",
    "SKIP_TENANT_FILTER",
    "TENANT_FILTER_EXEMPT",
    "AuditMixin",
    "Base",
    "Country",
    "Currency",
    "DeactivableMixin",
    "EffectiveMixin",
    "IdMixin",
    "IdempotencyKey",
    "Money",
    "Outbox",
    "ProcessedMessage",
    "Quantity",
    "State",
    "StatusMixin",
    "TenantContextError",
    "TenantMixin",
    "UtcDateTime",
    "Uuid7",
    "create_engine",
    "create_session_factory",
    "get_current_tenant",
    "metadata_obj",
    "require_current_tenant",
    "session_scope",
    "tenant_scope",
    "unfiltered",
    "utcnow",
]
