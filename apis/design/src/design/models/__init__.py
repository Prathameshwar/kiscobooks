"""Design models package.

``Outbox`` is imported so the shared table registers on ``Base.metadata`` for this
service too: audit events are staged on the same session as the row they describe
(CLAUDE.md §6.8), and a publisher drains them (``tasks/audit_publisher.py``).
"""

from billing_platform.db.platform_models import Outbox

from design.models.template import (
    InvoiceRenderSnapshot,
    InvoiceTemplate,
    InvoiceTemplateAsset,
    InvoiceTemplateAssignment,
    InvoiceTemplateComponent,
    InvoiceTemplateVersion,
)

__all__ = [
    "InvoiceRenderSnapshot",
    "InvoiceTemplate",
    "InvoiceTemplateAsset",
    "InvoiceTemplateAssignment",
    "InvoiceTemplateComponent",
    "InvoiceTemplateVersion",
    "Outbox",
]
