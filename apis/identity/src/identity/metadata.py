"""Identity-owned migrated schema and readiness contract."""

from billing_platform.db.base import NAMING_CONVENTION, Base
from sqlalchemy import MetaData

from identity import models  # noqa: F401 register owned tables

MIGRATION_HEAD = "0100"
TABLES = frozenset(
    {
        "account_review",
        "account_review_command",
        "business_category",
        "business_role",
        "catalog_source_enrollment",
        "catalog_source_generation",
        "catalog_source_page",
        "catalog_source_snapshot",
        "commercial_salesperson",
        "company",
        "company_address",
        "company_bank_account",
        "company_business_role",
        "company_contact",
        "company_currency_allowance",
        "company_document",
        "company_feature",
        "company_licence",
        "company_statutory_id",
        "company_setup_run",
        "company_setup_step",
        "company_tax_registration",
        "company_gst_filing_preference",
        "company_gst_outward_profile",
        "country",
        "currency",
        "custom_field_definition",
        "custom_field_sequence",
        "custom_field_value_index",
        "department",
        "field_config",
        "field_policy",
        "idempotency_key",
        "impersonation_session",
        "language",
        "local_authorization",
        "local_credential",
        "local_identity",
        "local_recovery_token",
        "local_refresh_token",
        "local_signing_key",
        "membership",
        "outbox",
        "platform_installation",
        "platform_price",
        "platform_price_revision",
        "posting_reservation",
        "processed_message",
        "reference_cache_generation",
        "reference_change",
        "reference_revision",
        "reference_sync_state",
        "report_source_enrollment",
        "role",
        "role_assignment",
        "role_permission",
        "state",
        "store_format",
        "tenant",
        "timezone",
        "user",
        "user_api_token",
        "user_group",
        "user_group_member",
        "user_identity",
        "user_invitation",
        "user_notification_preference",
    }
)


def service_metadata() -> MetaData:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    for name in sorted(TABLES):
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata
