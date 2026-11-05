"""Suite wiring.

The fixtures themselves live in ``billing_platform.testing`` so seven service
suites share one definition of how a session is built.
"""

from __future__ import annotations

# Importing the fixture models registers them on Base.metadata before create_all.
from billing_platform.testing import (  # noqa: F401
    engine,
    factory,
    session,
    tenant_a,
    tenant_b,
)
from tests.models import (  # noqa: F401
    ExemptThing,
    PlaceLike,
    RootLike,
    SharedThing,
    TenantThing,
)
