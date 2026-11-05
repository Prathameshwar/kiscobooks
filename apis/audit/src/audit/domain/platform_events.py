"""Exact administrative event/entity families; never infer authority from a prefix."""

EVENTS = {
    "platform.tenant_access.read": {
        "tenant": frozenset(
            {
                "platform.tenant_administrators_read",
                "platform.tenant_administrator_read",
                "platform.tenant_administrator_invited",
                "platform.tenant_administrator_edit",
                "platform.tenant_administrator_suspend",
                "platform.tenant_administrator_restore",
                "platform.tenant_administrator_revoke",
                "platform.tenant_administrator_resend_invitation",
                "platform.tenant_administrator_password_recovery_requested",
            }
        ),
    },
    "platform.account.read": {
        "account_review": frozenset(
            {
                "platform.accounts_read",
                "platform.account_imported",
                "platform.account_drift_detected",
                "platform.account_reconciled",
                "platform.account_decision_requested",
                "platform.account_decision_completed",
                "platform.account_decision_blocked",
            }
        ),
    },
    "platform.tenant.read": {
        "tenant": frozenset(
            {
                "platform.tenants_read",
                "platform.tenant_provisioned",
                "platform.tenant_updated",
                "platform.tenant_lifecycle_changed",
                "platform.administrator_invitation_read",
            }
        ),
    },
    "platform.config.manage": {
        "platform_price": frozenset(
            {
                "platform.price_created",
                "platform.price_updated",
                "platform.price_deleted",
                "platform.price_restored",
            }
        ),
        "platform_installation": frozenset(
            {"platform.setup_completed", "platform.details_updated"}
        ),
        "reference_revision": frozenset(
            {
                "platform.reference_created",
                "platform.reference_updated",
                "platform.reference_archived",
                "platform.reference_restored",
            }
        ),
    },
}

NOTIFICATION_TABLES = {
    "provider": (
        "provider_account",
        "sender_identity",
        "channel_setting",
        "notification_space",
        "notification_job",
    ),
    "template": (
        "notification_template",
        "template_variant",
        "template_version",
        "template_activation",
        "provider_template_binding",
        "notification_use_case_binding",
    ),
    "route": ("routing_rule",),
    "recipient": ("recipient_endpoint", "party_endpoint_checkpoint"),
    "request": ("notification_request", "notification_planning_outcome", "voucher_send_state"),
    "delivery": (
        "notification_delivery",
        "notification_content",
        "delivery_attempt",
        "delivery_event",
        "provider_event",
        "attachment",
        "delivery_attachment",
    ),
}
for family, tables in NOTIFICATION_TABLES.items():
    EVENTS[f"platform.notification_{family}.read"] = {
        f"notification.{table}": frozenset(
            f"notification.{table}.{operation}" for operation in ("created", "updated", "deleted")
        )
        for table in tables
    }
for family, tables in {
    "consent": ("consent_event", "consent_state"),
    "suppression": ("suppression",),
}.items():
    EVENTS[f"platform.notification_{family}.manage"] = {
        f"notification.{table}": frozenset(
            f"notification.{table}.{operation}" for operation in ("created", "updated", "deleted")
        )
        for table in tables
    }

ENTITIES = frozenset(entity for group in EVENTS.values() for entity in group)
