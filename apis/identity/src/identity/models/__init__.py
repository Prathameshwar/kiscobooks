"""``identity`` ORM models.

Importing this module registers every table on ``Base.metadata`` — which is what
``dbs/identity/env.py`` relies on for autogenerate and what the test fixtures rely
on for ``create_all``. A model that is not re-exported here is a table that exists
in one file and nowhere else.

The platform-mechanism and ISO reference tables are re-exported rather than
redefined: they live in ``libs/platform`` because every service database needs an
identical shape for them (CLAUDE.md §3).
"""

from billing_platform.db.language import Language
from billing_platform.db.platform_models import IdempotencyKey, Outbox, ProcessedMessage
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.reference_models import Country, Currency, State

# Register the reference writer policy using direct model-module imports. Seeds and
# API writers share the same transactional source-change invalidation.
from identity.events import reference_cache as _reference_cache_events  # noqa: F401
from identity.models.account_review import AccountReview, AccountReviewCommand
from identity.models.business_classification import (
    BusinessCategory,
    BusinessRole,
    CompanyBusinessRole,
    StoreFormat,
)
from identity.models.catalog_enrollment import CatalogSourceEnrollment
from identity.models.catalog_source import (
    CatalogSourceGeneration,
    CatalogSourcePage,
    CatalogSourceSnapshot,
)
from identity.models.commercial_salesperson import CommercialSalesperson
from identity.models.company import (
    BUSINESS_NATURES,
    COMPANY_STATUSES,
    CURRENCY_SYMBOL_POSITIONS,
    DIGIT_GROUPINGS,
    ENTITY_TYPES,
    NEGATIVE_FORMATS,
    PRECISION_MAX,
    PRECISION_MIN,
    ROUNDING_MODES,
    TAX_TREATMENTS,
    VISIBILITIES,
    Company,
)
from identity.models.company_address import ADDRESS_TYPES, CompanyAddress
from identity.models.company_bank_account import CompanyBankAccount
from identity.models.company_contact import CONTACT_TYPES, CompanyContact
from identity.models.company_currency import CompanyCurrencyAllowance
from identity.models.company_document import CompanyDocument
from identity.models.company_feature import CompanyFeature
from identity.models.company_gst_filing import CompanyGstFilingPreference
from identity.models.company_licence import CompanyLicence
from identity.models.company_setup import CompanySetupRun, CompanySetupStep, ReportSourceEnrollment
from identity.models.company_statutory_id import CompanyStatutoryId
from identity.models.company_tax_registration import CompanyTaxRegistration
from identity.models.custom_field_definition import (
    CUSTOM_FIELD_DATA_TYPES,
    CustomFieldDefinition,
)
from identity.models.custom_field_sequence import CustomFieldSequence
from identity.models.custom_field_value_index import CustomFieldValueIndex
from identity.models.department import Department
from identity.models.field_config import FieldConfig
from identity.models.field_policy import (
    FIELD_ACCESS,
    FIELD_EFFECTS,
    FIELD_POLICY_SUBJECT_TYPES,
    FieldPolicy,
)
from identity.models.impersonation_session import (
    IMPERSONATION_END_REASONS,
    ImpersonationSession,
)
from identity.models.local_auth import (
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
    LocalSigningKey,
)
from identity.models.membership import Membership
from identity.models.platform_installation import PlatformInstallation
from identity.models.platform_price import PlatformPrice, PlatformPriceRevision
from identity.models.posting_reservation import PostingReservation
from identity.models.reference_cache import ReferenceCacheGeneration as ReferenceCacheGeneration
from identity.models.reference_change import ReferenceChange as ReferenceChange
from identity.models.role import SCOPE_HINTS, Role
from identity.models.role_assignment import (
    ASSIGNMENT_SCOPE_TYPES,
    SUBJECT_TYPES,
    RoleAssignment,
)
from identity.models.role_permission import RolePermission
from identity.models.tenant import TENANT_STATUSES, Tenant
from identity.models.timezone import Timezone
from identity.models.user import USER_STATUSES, USER_TYPES, User
from identity.models.user_api_token import UserApiToken
from identity.models.user_group import UserGroup
from identity.models.user_group_member import UserGroupMember
from identity.models.user_identity import IDENTITY_PROVIDERS, UserIdentity
from identity.models.user_invitation import UserInvitation
from identity.models.user_notification_preference import (
    NOTIFICATION_CHANNELS,
    UserNotificationPreference,
)

__all__ = [
    "ADDRESS_TYPES",
    "ASSIGNMENT_SCOPE_TYPES",
    "BUSINESS_NATURES",
    "COMPANY_STATUSES",
    "CONTACT_TYPES",
    "CURRENCY_SYMBOL_POSITIONS",
    "CUSTOM_FIELD_DATA_TYPES",
    "DIGIT_GROUPINGS",
    "ENTITY_TYPES",
    "FIELD_ACCESS",
    "FIELD_EFFECTS",
    "FIELD_POLICY_SUBJECT_TYPES",
    "IDENTITY_PROVIDERS",
    "IMPERSONATION_END_REASONS",
    "NEGATIVE_FORMATS",
    "NOTIFICATION_CHANNELS",
    "PRECISION_MAX",
    "PRECISION_MIN",
    "ROUNDING_MODES",
    "SCOPE_HINTS",
    "SUBJECT_TYPES",
    "TAX_TREATMENTS",
    "TENANT_STATUSES",
    "USER_STATUSES",
    "USER_TYPES",
    "VISIBILITIES",
    "AccountReview",
    "AccountReviewCommand",
    "BusinessCategory",
    "BusinessRole",
    "CatalogSourceEnrollment",
    "CatalogSourceGeneration",
    "CatalogSourceGeneration",
    "CatalogSourcePage",
    "CatalogSourcePage",
    "CatalogSourceSnapshot",
    "CatalogSourceSnapshot",
    "CommercialSalesperson",
    "Company",
    "CompanyAddress",
    "CompanyBankAccount",
    "CompanyBusinessRole",
    "CompanyContact",
    "CompanyCurrencyAllowance",
    "CompanyDocument",
    "CompanyFeature",
    "CompanyGstFilingPreference",
    "CompanyLicence",
    "CompanySetupRun",
    "CompanySetupStep",
    "CompanyStatutoryId",
    "CompanyTaxRegistration",
    "Country",
    "Currency",
    "CustomFieldDefinition",
    "CustomFieldSequence",
    "CustomFieldValueIndex",
    "Department",
    "FieldConfig",
    "FieldPolicy",
    "IdempotencyKey",
    "ImpersonationSession",
    "Language",
    "LocalAuthorization",
    "LocalCredential",
    "LocalIdentity",
    "LocalRecoveryToken",
    "LocalRefreshToken",
    "LocalSigningKey",
    "Membership",
    "Outbox",
    "PlatformInstallation",
    "PlatformPrice",
    "PlatformPriceRevision",
    "PostingReservation",
    "ProcessedMessage",
    "ReferenceCacheGeneration",
    "ReferenceRevision",
    "ReferenceSyncState",
    "ReportSourceEnrollment",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "State",
    "StoreFormat",
    "Tenant",
    "Timezone",
    "User",
    "UserApiToken",
    "UserGroup",
    "UserGroupMember",
    "UserIdentity",
    "UserInvitation",
    "UserNotificationPreference",
]
from identity.models.company_gst_outward import CompanyGstOutwardProfile  # noqa: F401
