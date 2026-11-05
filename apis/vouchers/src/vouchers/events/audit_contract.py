"""Exact voucher audit routing allowlist; no wildcard producer authority."""

AUDIT_EVENTS = frozenset(
    f"vouchers.{entity}.{action}"
    for entity, actions in {
        "voucher": (
            "create",
            "update",
            "submit",
            "approve",
            "reject",
            "issue",
            "cancel",
            "share",
            "notification_skipped",
        ),
        "type": ("create", "revise", "class_create", "retire"),
        "configuration": ("create", "revise", "publish", "bind", "binding_close", "retire"),
        "series": ("create", "retire"),
        "template": ("create", "retire"),
        "definition": ("adopt",),
        "artifact": ("create", "rendered"),
        "print_job": ("create", "started", "failed", "ready", "download"),
        "supporting_file": ("upload", "download"),
        "source": ("applied",),
        "stock_retirement_fence": ("acquire", "release"),
        "operation": ("create", "result", "recover"),
        "counter_outlet": ("create", "status"),
        "checkout_counter": ("create", "status"),
        "counter_operator": ("assign", "status"),
        "counter_session": ("open", "close"),
        "counter_cash_event": ("create",),
        "import_job": (
            "stage",
            "validate",
            "validated",
            "commit",
            "complete",
            "cancel",
            "report_access",
            "cleanup",
            "revise",
            "template",
        ),
    }.items()
    for action in actions
)

AUDIT_EVENTS = AUDIT_EVENTS | {"vouchers.operation.cancel_request"}
AUDIT_EVENTS = AUDIT_EVENTS | {
    "vouchers.stock_opening_import." + action
    for action in ("stage", "validate", "commit", "cancel", "report_access")
}
