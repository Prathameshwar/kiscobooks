"""Test factories for `identity` models.

Kept alongside the models they build (CLAUDE.md §2: a model change is not done
until its factory is updated), and deliberately **not** generic. Each one takes
the fields a test would plausibly vary and supplies a valid value for the rest,
so a test states only what it is about.

Reference rows are inserted here rather than by running the full
``seed_reference``: the SQLite fixture enforces foreign keys, so a `tenant` needs
a `country` and a `currency` to exist, but a test about tenant isolation has no
business waiting on five thousand ISO subdivisions.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.db.tenant_context import unfiltered
from billing_platform.ids import uuid7
from billing_platform.tax import registration_class
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    AccountReview,
    AccountReviewCommand,
    CatalogSourceEnrollment,
    Company,
    CompanyAddress,
    CompanyBankAccount,
    CompanyContact,
    CompanyDocument,
    CompanyFeature,
    CompanyLicence,
    CompanySetupRun,
    CompanySetupStep,
    CompanyStatutoryId,
    CompanyTaxRegistration,
    CustomFieldDefinition,
    CustomFieldSequence,
    CustomFieldValueIndex,
    Department,
    FieldConfig,
    FieldPolicy,
    ImpersonationSession,
    Membership,
    PlatformInstallation,
    PostingReservation,
    ReportSourceEnrollment,
    Role,
    RoleAssignment,
    RolePermission,
    Tenant,
    User,
    UserApiToken,
    UserGroup,
    UserGroupMember,
    UserIdentity,
    UserInvitation,
    UserNotificationPreference,
)
from identity.models.reference_cache import ReferenceCacheGeneration
from identity.models.reference_change import ReferenceChange


def build_company_setup_run(
    tenant_id: uuid.UUID, company_id: uuid.UUID, **overrides: Any
) -> CompanySetupRun:
    from billing_platform.db.types import utcnow

    return CompanySetupRun(
        **(
            {
                "id": uuid7(),
                "tenant_id": tenant_id,
                "company_id": company_id,
                "command_key": uuid7().hex,
                "request_hash": "0" * 64,
                "configuration": {},
                "available_at": utcnow(),
                "requested_features": [],
            }
            | overrides
        )
    )


def build_company_setup_step(
    tenant_id: uuid.UUID, company_id: uuid.UUID, **overrides: Any
) -> CompanySetupStep:
    return CompanySetupStep(
        **(
            {
                "id": uuid7(),
                "tenant_id": tenant_id,
                "company_id": company_id,
                "key": "features",
                "evidence": {},
            }
            | overrides
        )
    )


def build_report_enrollment(
    tenant_id: uuid.UUID, company_id: uuid.UUID, **overrides: Any
) -> ReportSourceEnrollment:
    return ReportSourceEnrollment(
        **(
            {
                "id": uuid7(),
                "tenant_id": tenant_id,
                "company_id": company_id,
                "status": "ACTIVE",
                "revision": 1,
            }
            | overrides
        )
    )


def build_platform_installation(**overrides: Any) -> PlatformInstallation:
    """An unclaimed installation control row, intentionally outside tenant scoping."""
    return PlatformInstallation(**({"id": uuid7(), "key": "platform"} | overrides))


def build_reference_revision(**overrides: Any) -> ReferenceRevision:
    """Global reference management provenance; no tenant-owned data."""
    return ReferenceRevision(
        **(
            {
                "id": uuid7(),
                "kind": "language",
                "code": "en",
                "name": "English",
                "parent_code": None,
                "is_active": True,
                "source": "seed",
                "version": 0,
                "is_custom": False,
                "payload": {
                    "code": "en",
                    "iso3": "eng",
                    "name": "English",
                    "native_name": None,
                    "is_active": True,
                },
            }
            | overrides
        )
    )


def build_reference_sync_state(**overrides: Any) -> ReferenceSyncState:
    return ReferenceSyncState(**({"id": uuid7(), "service": "catalog", "cursor": None} | overrides))


def build_reference_change(**overrides: Any) -> ReferenceChange:
    return ReferenceChange(
        **(
            {
                "id": uuid7(),
                "kind": "language",
                "code": "en",
                "version": 1,
                "payload": build_reference_revision().payload,
            }
            | overrides
        )
    )


def build_currency(code: str = "INR", **overrides: Any) -> Currency:
    values: dict[str, Any] = {
        "code": code,
        "numeric_code": "356",
        "name": "Indian Rupee",
        "symbol": "₹",
        "minor_unit": 2,
        "major_unit_name": "Rupees",
        "minor_unit_name": "Paisa",
        "minor_unit_name_plural": "Paise",
        "is_active": True,
    }
    return Currency(**(values | overrides))


def build_country(code: str = "IN", currency_code: str = "INR", **overrides: Any) -> Country:
    values: dict[str, Any] = {
        "code": code,
        "iso3": "IND",
        "numeric_code": "356",
        "name": "India",
        "official_name": "Republic of India",
        "default_currency_code": currency_code,
        "phone_prefix": "+91",
        "subdivision_label": "State",
        "is_active": True,
    }
    return Country(**(values | overrides))


def build_tenant(
    *, tenant_id: uuid.UUID | None = None, slug: str = "acme", **overrides: Any
) -> Tenant:
    """A valid ``active`` tenant. ``tenant_id`` becomes its ``id`` — the two are the
    same value, which is the whole point of this table."""
    values: dict[str, Any] = {
        "id": tenant_id or uuid7(),
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "status": "active",
        "plan_id": None,
        "primary_contact_email": f"billing@{slug}.example",
        "default_country_code": "IN",
        "default_state_code": None,
        "default_currency_code": "INR",
        "default_locale": "en-IN",
        "default_timezone": "Asia/Kolkata",
        "trial_ends_on": None,
        "suspended_at": None,
        "suspended_reason": None,
    }
    return Tenant(**(values | overrides))


def build_state(code: str = "MH", country_code: str = "IN", **overrides: Any) -> State:
    """A subdivision. The ``(country_code, code)`` pair is the composite FK target
    that makes an impossible jurisdiction unrepresentable on `company`."""
    values: dict[str, Any] = {
        "code": code,
        "country_code": country_code,
        "name": "Maharashtra",
        "subdivision_type": "State",
        "tax_jurisdiction_code": "27",
        "is_active": True,
    }
    return State(**(values | overrides))


def build_company(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None = None,
    code: str = "MAIN",
    **overrides: Any,
) -> Company:
    """A valid Indian company, pre-first-posting.

    ``first_posted_at`` is None so the immutability tests can set it deliberately —
    a factory that defaulted it would make the freeze invisible in every other test.
    """
    values: dict[str, Any] = {
        "id": company_id or uuid7(),
        "tenant_id": tenant_id,
        "parent_company_id": None,
        "code": code,
        "legal_name": "Acme Traders Private Limited",
        "trade_name": "Acme",
        "display_name": "Acme Traders",
        "entity_type": "pvt_ltd",
        "incorporation_date": dt.date(2019, 4, 1),
        "country_code": "IN",
        "state_code": "MH",
        "status": "active",
        "first_posted_at": None,
        "base_currency": "INR",
        "reporting_currency": None,
        "fiscal_year_start_month": 4,
        "fiscal_year_start_day": 1,
        "books_begin_date": dt.date(2026, 4, 1),
        "amount_precision": 2,
        "quantity_precision": 3,
        "rounding_mode": "half_up",
        "default_tax_system": "gst_in",
        "tax_treatment_default": "exclusive",
        "default_payment_terms_days": 30,
        "credit_limit_default": None,
        "cash_receipt_limit": Decimal("200000.0000"),
        "backdated_posting_limit_days": 30,
        "industry_code": None,
        "business_nature": "trading",
        "business_category_code": None,
        "business_roles": [],
        "store_format_code": None,
        "timezone": "Asia/Kolkata",
        "locale": "en-IN",
        "date_format": "dd-MM-yyyy",
        "datetime_format": "dd-MM-yyyy HH:mm",
        "digit_grouping": "indian",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "negative_format": "minus",
        "show_amount_in_words": True,
        "currency_symbol_position": "prefix",
        "currency_symbol_override": None,
        "logo_url": None,
        "signature_url": None,
        "brand_color": None,
        "print_template_id": None,
        "terms_and_conditions": None,
        "declaration_text": None,
        "jurisdiction_text": None,
        "signatory_name": None,
        "signatory_designation": None,
        "dsc_thumbprint": None,
        "visibility": "listed",
        "requires_step_up": False,
        "visibility_changed_at": None,
        "visibility_changed_by": None,
        "custom_fields": None,
    }
    return Company(**(values | overrides))


def build_company_address(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    address_type: str = "registered",
    **overrides: Any,
) -> CompanyAddress:
    """A registered office in Maharashtra.

    The keyword is ``address_type`` rather than ``type``: the column is ``type``, but
    a parameter of that name shadows the builtin inside the factory.
    """
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "type": address_type,
        "label": None,
        "line1": "12 Marine Drive",
        "line2": None,
        "city": "Mumbai",
        "state_code": "MH",
        "postal_code": "400020",
        "country_code": "IN",
        "is_primary": True,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CompanyAddress(**(values | overrides))


def build_company_feature(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    feature_key: str = "inventory",
    is_enabled: bool = True,
    **overrides: Any,
) -> CompanyFeature:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "feature_key": feature_key,
        "is_enabled": is_enabled,
        "enabled_at": dt.datetime(2026, 4, 1, tzinfo=dt.UTC) if is_enabled else None,
        "enabled_by": None,
        "disabled_at": None,
        "disabled_by": None,
        "locked_at": None,
        "lock_reason": None,
    }
    return CompanyFeature(**(values | overrides))


def build_company_tax_registration(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    tax_system: str = "gst_in",
    jurisdiction_code: str = "MH",
    valid_from: dt.date = dt.date(2026, 4, 1),
    **overrides: Any,
) -> CompanyTaxRegistration:
    """A regular Maharashtra GST registration, open-ended.

    The GSTIN is a format-valid fake: ``27`` is Maharashtra's state code and the
    middle ten characters are a syntactically valid PAN. It is not a real
    registration and no secret (CLAUDE.md §5.9) — the format matters because the
    profile pattern checks it.
    """
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "tax_system": tax_system,
        "regime": "regular",
        "registration_class": "supplier",
        "number": "27AAAPA1234A1ZT",
        "jurisdiction_code": jurisdiction_code,
        "legal_name_on_registration": None,
        "registered_address_id": None,
        "is_primary": True,
        "verified_at": None,
        "verified_by": None,
        "verification_reference": None,
        "valid_from": valid_from,
        "valid_to": None,
    }
    values |= overrides
    if "regime" in overrides and "registration_class" not in overrides:
        values["registration_class"] = registration_class(values["tax_system"], values["regime"])
    return CompanyTaxRegistration(**values)


def build_company_statutory_id(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    kind: str = "pan",
    value: str | None = "AAAPA1234A",
    **overrides: Any,
) -> CompanyStatutoryId:
    """A PAN — a *business* identifier, so stored in full.

    ``value_last4`` is derived from ``value`` rather than defaulted, because a
    factory that let the two disagree would make
    ``assert_statutory_row_storable``'s consistency check untestable. Restricted
    kinds pass ``value=None`` and their own ``value_last4``.
    """
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "kind": kind,
        "value": value,
        "value_last4": value[-4:] if value else "0000",
        "holder_name": None,
        "issued_on": None,
        "valid_to": None,
        "verified_at": None,
        "verified_by": None,
        "verification_reference": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CompanyStatutoryId(**(values | overrides))


def build_company_licence(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    kind: str = "drug_licence_20b",
    number: str = "MH-MUM-20B-4471",
    valid_from: dt.date = dt.date(2026, 4, 1),
    **overrides: Any,
) -> CompanyLicence:
    """A retail drug licence, expiring — the kind that gates a posting."""
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "kind": kind,
        "number": number,
        "issuing_authority": "Maharashtra FDA",
        "premises_address_id": None,
        "issued_on": dt.date(2026, 3, 20),
        "renewal_reminder_days": 60,
        "document_url": None,
        "is_primary": True,
        "valid_from": valid_from,
        "valid_to": dt.date(2031, 3, 31),
    }
    return CompanyLicence(**(values | overrides))


def build_user(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    email: str = "asha@alpha.example",
    **overrides: Any,
) -> User:
    """An ``active`` tenant user.

    ``authentik_sub`` is None by default — the ``invited`` state is the more common
    one and a default subject would make every test look like an accepted invitation.
    Tests about login pass one explicitly.
    """
    values: dict[str, Any] = {
        "id": user_id or uuid7(),
        "tenant_id": tenant_id,
        "authentik_sub": None,
        "tokens_valid_after_at": None,
        "user_type": "tenant_user",
        "salutation": None,
        "first_name": "Asha",
        "middle_name": None,
        "last_name": "Rao",
        "display_name": "Asha Rao",
        "email": email,
        "email_verified_at": None,
        "phone_country_code": None,
        "phone": None,
        "phone_verified_at": None,
        "employee_code": None,
        "job_title": None,
        "reporting_manager_id": None,
        "default_company_id": None,
        "default_department_id": None,
        "date_of_joining": None,
        "date_of_exit": None,
        "locale": None,
        "timezone": None,
        "date_format": None,
        "datetime_format": None,
        "digit_grouping": None,
        "currency_display": None,
        "theme": None,
        "landing_page": None,
        "status": "active",
        "invited_by": None,
        "invited_at": None,
        "activated_at": None,
        "last_active_at": None,
        "deactivated_at": None,
        "deactivated_by": None,
        "deactivation_reason": None,
        "anonymized_at": None,
        "terms_accepted_at": None,
        "terms_version": None,
        "privacy_accepted_at": None,
        "custom_fields": None,
    }
    return User(**(values | overrides))


def build_user_identity(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    provider: str = "google",
    provider_sub: str = "google-oauth2|100000000000000000001",
    **overrides: Any,
) -> UserIdentity:
    """A second IdP link. The subject is a public identifier, not a credential."""
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "provider": provider,
        "provider_sub": provider_sub,
        "linked_at": dt.datetime(2026, 4, 1, tzinfo=dt.UTC),
        "last_login_at": None,
    }
    return UserIdentity(**(values | overrides))


def build_role(
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID | None = None,
    key: str = "billing_clerk",
    **overrides: Any,
) -> Role:
    """A role. Pass ``tenant_id=SCOPE_ALL`` for a system role — there is no
    ``is_system`` argument, because ``is_system`` is derived from ``tenant_id`` and a
    factory that took both could build the row the model makes unrepresentable."""
    values: dict[str, Any] = {
        "id": role_id or uuid7(),
        "tenant_id": tenant_id,
        "key": key,
        "name": key.replace("_", " ").title(),
        "description": None,
        "cloned_from_role_id": None,
        "scope_hint": "company",
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return Role(**(values | overrides))


def build_role_permission(
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    permission_key: str = "invoice.create",
    **overrides: Any,
) -> RolePermission:
    """One granted key.

    ``tenant_id`` must match the role's — the composite foreign key enforces it, and
    a test that gets it wrong is testing that constraint whether it meant to or not.
    """
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "role_id": role_id,
        "permission_key": permission_key,
    }
    return RolePermission(**(values | overrides))


def build_role_assignment(
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    subject_id: uuid.UUID,
    subject_type: str = "user",
    scope_type: str = "tenant",
    scope_id: uuid.UUID = SCOPE_ALL,
    valid_from: dt.date = dt.date(2026, 4, 1),
    **overrides: Any,
) -> RoleAssignment:
    """The ``(subject, role, scope)`` triple, tenant-scoped and open-ended.

    ``scope_id`` defaults to ``SCOPE_ALL`` to match ``scope_type="tenant"``. A test
    narrowing the scope passes both, which is the pairing the API validates.
    """
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "role_id": role_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "granted_by": None,
        "grant_reason": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
        "valid_from": valid_from,
        "valid_to": None,
    }
    return RoleAssignment(**(values | overrides))


def build_department(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    department_id: uuid.UUID | None = None,
    code: str = "SALES",
    parent_id: uuid.UUID | None = None,
    path: str | None = None,
    **overrides: Any,
) -> Department:
    """A top-level department. ``path`` defaults to a single-segment materialized path
    of its own id — what ``domain/department_tree`` writes for a root."""
    dept_id = department_id or uuid7()
    values: dict[str, Any] = {
        "id": dept_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "parent_id": parent_id,
        "code": code,
        "name": code.replace("_", " ").title(),
        "cost_centre_code": None,
        "head_user_id": None,
        "path": path if path is not None else f"/{dept_id.hex}/",
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return Department(**(values | overrides))


def build_user_group(
    *,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID | None = None,
    code: str = "finance",
    **overrides: Any,
) -> UserGroup:
    values: dict[str, Any] = {
        "id": group_id or uuid7(),
        "tenant_id": tenant_id,
        "code": code,
        "name": code.replace("_", " ").title(),
        "description": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return UserGroup(**(values | overrides))


def build_user_group_member(
    *, tenant_id: uuid.UUID, user_group_id: uuid.UUID, user_id: uuid.UUID, **overrides: Any
) -> UserGroupMember:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_group_id": user_group_id,
        "user_id": user_id,
        "added_by": None,
    }
    return UserGroupMember(**(values | overrides))


def build_membership(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    department_id: uuid.UUID | None = None,
    is_primary: bool = True,
    **overrides: Any,
) -> Membership:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "company_id": company_id,
        "department_id": department_id,
        "is_primary": is_primary,
        "started_on": dt.date(2026, 4, 1),
        "ended_on": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return Membership(**(values | overrides))


def build_company_contact(
    *, tenant_id: uuid.UUID, company_id: uuid.UUID, contact_type: str = "finance", **overrides: Any
) -> CompanyContact:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "type": contact_type,
        "name": "Priya Menon",
        "designation": "Finance Head",
        "email": "finance@acme.example",
        "phone_country_code": "+91",
        "phone": "9820098200",
        "is_primary": True,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CompanyContact(**(values | overrides))


def build_company_bank_account(
    *, tenant_id: uuid.UUID, company_id: uuid.UUID, currency_code: str = "INR", **overrides: Any
) -> CompanyBankAccount:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "label": "Operating",
        "account_name": "Acme Traders Private Limited",
        "details_ciphertext": None,
        "encryption_key_id": None,
        "account_last4": None,
        "iban_last4": None,
        "account_number": "000123456789",
        "iban": None,
        "swift": "HDFCINBB",
        "ifsc": "HDFC0000001",
        "bank_name": "HDFC Bank",
        "branch": "Marine Drive",
        "currency_code": currency_code,
        "is_primary": True,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CompanyBankAccount(**(values | overrides))


def build_company_document(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    doc_type: str = "incorporation",
    **overrides: Any,
) -> CompanyDocument:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "type": doc_type,
        "title": "Certificate of Incorporation",
        "number": None,
        "file_url": f"identity/{tenant_id}/{company_id}/legacy-incorporation",
        "storage_state": "legacy",
        "content_sha256": None,
        "blob_snapshot": None,
        "upload_expires_at": None,
        "finalized_at": None,
        "file_size_bytes": 20480,
        "content_type": "application/pdf",
        "issued_on": dt.date(2019, 4, 1),
        "expires_on": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CompanyDocument(**(values | overrides))


def build_user_notification_preference(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    channel: str = "email",
    event_key: str = "invoice.posted",
    **overrides: Any,
) -> UserNotificationPreference:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "channel": channel,
        "event_key": event_key,
        "is_enabled": True,
        "source_version": 1,
    }
    return UserNotificationPreference(**(values | overrides))


def build_user_api_token(
    *, tenant_id: uuid.UUID, user_id: uuid.UUID, token_hash: str | None = None, **overrides: Any
) -> UserApiToken:
    """A token row. ``token_hash`` is a fake 64-char hex — never a real token, which is
    shown once and never stored (CLAUDE.md §5.9)."""
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "name": "CI deploy token",
        "token_prefix": "idt_ab12",
        "token_hash": token_hash or ("a" * 64),
        "scopes": None,
        "last_used_at": None,
        "last_used_ip": None,
        "expires_at": None,
        "revoked_at": None,
        "revoked_by": None,
    }
    return UserApiToken(**(values | overrides))


def build_impersonation_session(
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    started_at: dt.datetime = dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
    expires_at: dt.datetime = dt.datetime(2026, 5, 1, 1, tzinfo=dt.UTC),
    **overrides: Any,
) -> ImpersonationSession:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "actor_user_id": actor_user_id,
        "target_user_id": target_user_id,
        "reason": "support ticket",
        "ticket_reference": "SUP-1001",
        "started_at": started_at,
        "expires_at": expires_at,
        "ended_at": None,
        "ended_reason": None,
        "actor_ip": "203.0.113.7",
    }
    return ImpersonationSession(**(values | overrides))


def build_field_policy(
    *,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID,
    subject_type: str = "role",
    entity_type: str = "billing.invoice",
    field_key: str = "unit_price",
    access: str = "write",
    effect: str = "deny",
    scope_type: str = "tenant",
    scope_id: uuid.UUID = SCOPE_ALL,
    **overrides: Any,
) -> FieldPolicy:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "entity_type": entity_type,
        "field_key": field_key,
        "access": access,
        "effect": effect,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "condition": None,
        "reason": "clerks may not change price",
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return FieldPolicy(**(values | overrides))


def build_custom_field_definition(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = SCOPE_ALL,
    def_id: uuid.UUID | None = None,
    entity_type: str = "catalog.item",
    key: str = "warranty_months",
    data_type: str = "integer",
    **overrides: Any,
) -> CustomFieldDefinition:
    values: dict[str, Any] = {
        "id": def_id or uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "entity_type": entity_type,
        "key": key,
        "label": key.replace("_", " ").title(),
        "help_text": None,
        "placeholder": None,
        "data_type": data_type,
        "display_order": 10,
        "display_group": None,
        "is_searchable": False,
        "is_immutable_after_create": False,
        "requires_feature": None,
        "validation": None,
        "options": None,
        "option_source_key": None,
        "depends_on_key": None,
        "visibility": None,
        "sequence_config": None,
        "default_value": None,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    }
    return CustomFieldDefinition(**(values | overrides))


def build_field_config(
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = SCOPE_ALL,
    entity_type: str = "identity.company",
    field_key: str = "brand_color",
    field_source: str = "native",
    **overrides: Any,
) -> FieldConfig:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "entity_type": entity_type,
        "field_source": field_source,
        "field_key": field_key,
        "definition_id": None,
        "is_visible": True,
        "is_required": None,
        "display_order": 5,
        "display_group": None,
        "label_override": None,
        "help_text_override": None,
        "default_value": None,
    }
    return FieldConfig(**(values | overrides))


def build_custom_field_value_index(
    *,
    tenant_id: uuid.UUID,
    definition_id: uuid.UUID,
    company_id: uuid.UUID,
    entity_type: str = "catalog.item",
    entity_id: uuid.UUID | None = None,
    value_text: str | None = "GOLD",
    **overrides: Any,
) -> CustomFieldValueIndex:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "entity_type": entity_type,
        "entity_id": entity_id or uuid7(),
        "definition_id": definition_id,
        "company_id": company_id,
        "value_text": value_text,
        "value_number": None,
        "value_date": None,
        "value_bool": None,
    }
    return CustomFieldValueIndex(**(values | overrides))


def build_custom_field_sequence(
    *,
    tenant_id: uuid.UUID,
    definition_id: uuid.UUID,
    company_id: uuid.UUID,
    cycle_key: str = "",
    **overrides: Any,
) -> CustomFieldSequence:
    values: dict[str, Any] = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "definition_id": definition_id,
        "company_id": company_id,
        "cycle_key": cycle_key,
        "next_value": 1,
    }
    return CustomFieldSequence(**(values | overrides))


async def seed_jurisdiction(session: AsyncSession) -> None:
    """The one currency, country and state every row here points at.

    A `state` row is part of the minimum now: `company` and `company_address` both
    carry the composite `(country_code, state_code)` foreign key, and the SQLite
    fixture enforces it.
    """
    session.add(build_currency())
    await session.flush()
    session.add(build_country())
    await session.flush()
    session.add(build_state())
    await session.flush()


async def seed_two_tenants(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> None:
    """The two-tenant fixture the isolation pattern reuses for every later table.

    Written under ``unfiltered()`` because `tenant` is self-filtered: inserting a
    row for tenant B while scoped to tenant A is exactly the cross-tenant write the
    filter exists to make deliberate.
    """
    with unfiltered():
        await seed_jurisdiction(session)
        from identity.seeds.business_classifications import seed_business_classifications

        await seed_business_classifications(session)
        session.add_all(
            [
                build_tenant(tenant_id=tenant_a, slug="alpha"),
                build_tenant(tenant_id=tenant_b, slug="beta"),
            ]
        )
        await session.commit()


async def seed_two_companies(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """One company per tenant, both using the same ``code``, and their ids.

    The same ``code`` on purpose: ``uq_company_tenant_id_code`` is scoped to the
    tenant, so two tenants both calling their company ``MAIN`` must both succeed.
    A fixture that avoided the collision would never prove that.
    """
    company_a, company_b = uuid7(), uuid7()
    await seed_two_tenants(session, tenant_a, tenant_b)
    with unfiltered():
        session.add_all(
            [
                build_company(tenant_id=tenant_a, company_id=company_a, display_name="Alpha Ltd"),
                build_company(tenant_id=tenant_b, company_id=company_b, display_name="Beta Ltd"),
            ]
        )
        await session.commit()
    return company_a, company_b


async def seed_system_role(
    session: AsyncSession, key: str = "billing_clerk", *, permission_key: str = "invoice.create"
) -> uuid.UUID:
    """One shipped role at ``SCOPE_ALL``, with one permission, and its id.

    Written under ``unfiltered()``: a system role belongs to no tenant, so inserting
    it while scoped to one is the deliberate cross-tenant write the escape hatch is
    for — the same path the real seed takes.
    """
    role_id = uuid7()
    with unfiltered():
        session.add(build_role(tenant_id=SCOPE_ALL, role_id=role_id, key=key))
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=SCOPE_ALL, role_id=role_id, permission_key=permission_key
            )
        )
        await session.commit()
    return role_id


def build_user_invitation(
    *, tenant_id: uuid.UUID, user_id: uuid.UUID, **overrides: Any
) -> UserInvitation:
    values = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "status": "pending",
        "expires_at": dt.datetime(2030, 1, 1, tzinfo=dt.UTC),
        "accepted_at": None,
        "cancelled_at": None,
    }
    return UserInvitation(**(values | overrides))


def build_posting_reservation(
    *, tenant_id: uuid.UUID, company_id: uuid.UUID, actor_user_id: uuid.UUID, **overrides: Any
) -> PostingReservation:
    values = {
        "id": uuid7(),
        "tenant_id": tenant_id,
        "company_id": company_id,
        "operation_id": uuid7(),
        "actor_user_id": actor_user_id,
        "request_hash": "a" * 64,
        "configuration_hash": "b" * 64,
        "features": [],
        "status": "pending",
        "confirmed_at": None,
        "aborted_at": None,
        "terminal_reference": None,
    }
    return PostingReservation(**(values | overrides))


def build_reference_cache_generation() -> ReferenceCacheGeneration:
    return ReferenceCacheGeneration(key="global", token=uuid7())


def build_account_review(*, tenant_id: uuid.UUID, **overrides: Any) -> AccountReview:
    from identity.domain.account_review import Applicant, fingerprint

    profile = Applicant(
        provider_id=42,
        provider_uuid=uuid.uuid4(),
        name="Applicant",
        username="applicant",
        email="applicant@example.invalid",
        path="bill/pending-registration",
        user_type="external",
        is_active=False,
        verified=False,
        groups=(),
        roles=(),
        country_code="IN",
        state_code="IN-MH",
    )
    return AccountReview(
        **(
            {
                "tenant_id": tenant_id,
                "provider_id": profile.provider_id,
                "provider_uuid": profile.provider_uuid,
                "name": profile.name,
                "username": profile.username,
                "email": profile.email,
                "country_code": profile.country_code,
                "state_code": profile.state_code,
                "provider_active": False,
                "provider_verified": False,
                "fingerprint": fingerprint(profile),
            }
            | overrides
        )
    )


def build_account_review_command(
    *, tenant_id: uuid.UUID, account_id: uuid.UUID, actor_id: uuid.UUID, **overrides: Any
) -> AccountReviewCommand:
    return AccountReviewCommand(
        **(
            {
                "tenant_id": tenant_id,
                "account_id": account_id,
                "actor_id": actor_id,
                "request_key": uuid.uuid4().hex,
                "request_hash": "a" * 64,
                "action": "reject",
                "reason": "Independent review",
                "attested": False,
                "expected_fingerprint": "b" * 64,
            }
            | overrides
        )
    )


def build_catalog_source_enrollment(
    *, tenant_id: uuid.UUID, company_id: uuid.UUID, **overrides: Any
) -> CatalogSourceEnrollment:
    """An explicit active enrollment; disabled rows remain deliberate tombstones."""
    return CatalogSourceEnrollment(
        **(
            {"id": uuid7(), "tenant_id": tenant_id, "company_id": company_id, "is_active": True}
            | overrides
        )
    )
