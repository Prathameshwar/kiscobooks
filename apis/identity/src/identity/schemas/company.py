"""Request and response schemas for the company resource.

Distinct create / update / list-item / detail shapes (api-conventions §CRUD): the
create body forbids unknown fields so no request value is ever mass-assigned onto the
ORM row (CLAUDE.md §5.6), the list item is a lean projection, and the detail carries
the full readable row. Enum-like columns are validated here against the model's own
frozensets rather than a MySQL ``ENUM`` (CLAUDE.md §4).

Server-managed columns — ``id``, ``tenant_id``, ``first_posted_at``, the audit stamps,
``visibility_changed_*`` — are never accepted from the client; they are set by the
route or the immutability/visibility paths.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from billing_platform.custom_fields import CustomDefinition
from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from identity.domain.business_classification import normalize_business_roles
from identity.domain.company_calendar import validate_fiscal_anchor
from identity.models import (
    BUSINESS_NATURES,
    CURRENCY_SYMBOL_POSITIONS,
    DIGIT_GROUPINGS,
    ENTITY_TYPES,
    NEGATIVE_FORMATS,
    PRECISION_MAX,
    PRECISION_MIN,
    ROUNDING_MODES,
    TAX_TREATMENTS,
    VISIBILITIES,
)
from identity.schemas.base import PageMeta, StrictModel
from identity.schemas.company_setup import CompanySetupOptions
from identity.schemas.company_statutory import InitialTaxRegistration

_Precision = Annotated[int, Field(ge=PRECISION_MIN, le=PRECISION_MAX)]
_Month = Annotated[int, Field(ge=1, le=12)]
_Day = Annotated[int, Field(ge=1, le=31)]
_ClassificationCode = Annotated[
    str, StringConstraints(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
]
_BusinessRoles = Annotated[
    list[_ClassificationCode], Field(max_length=32), AfterValidator(normalize_business_roles)
]


def _one_of(value: str, allowed: frozenset[str], field_name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {', '.join(sorted(allowed))}")
    return value


def _identity_text(value: Any) -> Any:
    if isinstance(value, str):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("company names and codes cannot contain control characters")
        return value.strip()
    return value


class CompanyCreate(StrictModel):
    setup: CompanySetupOptions = Field(default_factory=CompanySetupOptions)
    initial_tax_registration: InitialTaxRegistration | None = None

    @model_validator(mode="after")
    def _calendar(self) -> CompanyCreate:
        validate_fiscal_anchor(self.fiscal_year_start_month, self.fiscal_year_start_day)
        return self

    _clean_identity = field_validator(
        "code", "legal_name", "display_name", "trade_name", mode="before"
    )(_identity_text)
    custom_fields: dict[str, Any] = Field(default_factory=dict, max_length=128)
    code: str = Field(min_length=1, max_length=20)
    legal_name: str = Field(min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    entity_type: str
    incorporation_date: dt.date | None = None
    parent_company_id: uuid.UUID | None = None

    country_code: str = Field(min_length=2, max_length=2)
    state_code: str = Field(min_length=1, max_length=6)

    base_currency: str = Field(min_length=3, max_length=3)
    reporting_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Reporting currency; null uses base currency. Does not enable FX billing.",
    )
    fiscal_year_start_month: _Month
    fiscal_year_start_day: _Day
    books_begin_date: dt.date
    amount_precision: _Precision
    quantity_precision: _Precision
    rounding_mode: str

    default_tax_system: str = Field(min_length=1, max_length=20)
    tax_treatment_default: str

    default_payment_terms_days: int = Field(ge=0, le=3650)
    credit_limit_default: Decimal | None = None
    cash_receipt_limit: Decimal | None = None
    backdated_posting_limit_days: int | None = Field(default=None, ge=0, le=3650)

    industry_code: str | None = Field(default=None, max_length=20)
    business_nature: str | None = None
    business_category_code: _ClassificationCode | None = None
    business_roles: _BusinessRoles = Field(default_factory=list)
    store_format_code: _ClassificationCode | None = None

    timezone: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=8)
    date_format: str = Field(min_length=1, max_length=20)
    datetime_format: str = Field(min_length=1, max_length=30)
    digit_grouping: str
    decimal_separator: str = Field(min_length=1, max_length=2)
    thousands_separator: str = Field(default="", max_length=2)
    negative_format: str
    show_amount_in_words: bool = False
    currency_symbol_position: str
    currency_symbol_override: str | None = Field(default=None, max_length=8)

    logo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    brand_color: str | None = Field(default=None, min_length=7, max_length=7)
    terms_and_conditions: str | None = None
    declaration_text: str | None = None
    jurisdiction_text: str | None = Field(default=None, max_length=200)
    signatory_name: str | None = Field(default=None, max_length=150)
    signatory_designation: str | None = Field(default=None, max_length=100)

    visibility: str = "listed"
    requires_step_up: bool = False

    @field_validator("entity_type")
    @classmethod
    def _entity_type(cls, v: str) -> str:
        return _one_of(v, ENTITY_TYPES, "entity_type")

    @field_validator("rounding_mode")
    @classmethod
    def _rounding_mode(cls, v: str) -> str:
        return _one_of(v, ROUNDING_MODES, "rounding_mode")

    @field_validator("tax_treatment_default")
    @classmethod
    def _tax_treatment(cls, v: str) -> str:
        return _one_of(v, TAX_TREATMENTS, "tax_treatment_default")

    @field_validator("business_nature")
    @classmethod
    def _business_nature(cls, v: str | None) -> str | None:
        return None if v is None else _one_of(v, BUSINESS_NATURES, "business_nature")

    @field_validator("digit_grouping")
    @classmethod
    def _digit_grouping(cls, v: str) -> str:
        return _one_of(v, DIGIT_GROUPINGS, "digit_grouping")

    @field_validator("negative_format")
    @classmethod
    def _negative_format(cls, v: str) -> str:
        return _one_of(v, NEGATIVE_FORMATS, "negative_format")

    @field_validator("currency_symbol_position")
    @classmethod
    def _symbol_position(cls, v: str) -> str:
        return _one_of(v, CURRENCY_SYMBOL_POSITIONS, "currency_symbol_position")

    @field_validator("visibility")
    @classmethod
    def _visibility(cls, v: str) -> str:
        return _one_of(v, VISIBILITIES, "visibility")


class CompanyUpdate(StrictModel):
    _clean_identity = field_validator(
        "code", "legal_name", "display_name", "trade_name", mode="before"
    )(_identity_text)
    expected_updated_at: AwareDatetime | None = Field(
        default=None, description="Optional optimistic concurrency precondition; never stored."
    )
    custom_fields: dict[str, Any] | None = Field(default=None, max_length=128)
    nonnullable = frozenset(
        [
            "amount_precision",
            "base_currency",
            "books_begin_date",
            "business_roles",
            "code",
            "country_code",
            "currency_symbol_position",
            "date_format",
            "datetime_format",
            "decimal_separator",
            "default_payment_terms_days",
            "default_tax_system",
            "digit_grouping",
            "display_name",
            "entity_type",
            "fiscal_year_start_day",
            "fiscal_year_start_month",
            "legal_name",
            "locale",
            "negative_format",
            "quantity_precision",
            "rounding_mode",
            "show_amount_in_words",
            "state_code",
            "tax_treatment_default",
            "thousands_separator",
            "timezone",
        ]
    )

    """Partial update. Every field optional; the route diffs against the persisted row
    and rejects a change to an immutability-ratchet column once anything has posted."""

    legal_name: str | None = Field(default=None, min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    entity_type: str | None = None
    incorporation_date: dt.date | None = None

    # ratchet columns — accepted so an unchanged full PUT is not rejected, but a real
    # change is refused post-posting by ``company_immutability`` in the route.
    code: str | None = Field(default=None, min_length=1, max_length=20)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    state_code: str | None = Field(default=None, min_length=1, max_length=6)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)
    reporting_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Reporting currency; null uses base currency. Does not enable FX billing.",
    )
    fiscal_year_start_month: _Month | None = None
    fiscal_year_start_day: _Day | None = None
    books_begin_date: dt.date | None = None
    amount_precision: _Precision | None = None
    quantity_precision: _Precision | None = None
    rounding_mode: str | None = None

    default_tax_system: str | None = Field(default=None, min_length=1, max_length=20)
    tax_treatment_default: str | None = None
    default_payment_terms_days: int | None = Field(default=None, ge=0, le=3650)
    credit_limit_default: Decimal | None = None
    cash_receipt_limit: Decimal | None = None
    backdated_posting_limit_days: int | None = Field(default=None, ge=0, le=3650)
    industry_code: str | None = Field(default=None, max_length=20)
    business_nature: str | None = None
    business_category_code: _ClassificationCode | None = None
    business_roles: _BusinessRoles = Field(default_factory=list)
    store_format_code: _ClassificationCode | None = None

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    locale: str | None = Field(default=None, min_length=2, max_length=8)
    date_format: str | None = Field(default=None, min_length=1, max_length=20)
    datetime_format: str | None = Field(default=None, min_length=1, max_length=30)
    digit_grouping: str | None = None
    decimal_separator: str | None = Field(default=None, min_length=1, max_length=2)
    thousands_separator: str | None = Field(default=None, max_length=2)
    negative_format: str | None = None
    show_amount_in_words: bool | None = None
    currency_symbol_position: str | None = None
    currency_symbol_override: str | None = Field(default=None, max_length=8)

    logo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    brand_color: str | None = Field(default=None, min_length=7, max_length=7)
    terms_and_conditions: str | None = None
    declaration_text: str | None = None
    jurisdiction_text: str | None = Field(default=None, max_length=200)
    signatory_name: str | None = Field(default=None, max_length=150)
    signatory_designation: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _validate_enums(self) -> CompanyUpdate:
        for name in ("country_code", "state_code", "base_currency", "default_tax_system"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        checks = (
            ("entity_type", self.entity_type, ENTITY_TYPES),
            ("rounding_mode", self.rounding_mode, ROUNDING_MODES),
            ("tax_treatment_default", self.tax_treatment_default, TAX_TREATMENTS),
            ("business_nature", self.business_nature, BUSINESS_NATURES),
            ("digit_grouping", self.digit_grouping, DIGIT_GROUPINGS),
            ("negative_format", self.negative_format, NEGATIVE_FORMATS),
            ("currency_symbol_position", self.currency_symbol_position, CURRENCY_SYMBOL_POSITIONS),
        )
        for name, value, allowed in checks:
            if value is not None:
                _one_of(value, allowed, name)
        return self


def sparse_company_schema(schema: dict[str, Any]) -> None:
    """OpenAPI marks fields that policies may omit as optional, never fabricated nulls."""
    from billing_platform.fields import registry

    from identity.domain.field_registry import COMPANY_ENTITY_TYPE, COMPANY_RELATIONSHIP_FIELDS

    deniable = set(registry.get(COMPANY_ENTITY_TYPE).fields) | set(COMPANY_RELATIONSHIP_FIELDS)
    schema["required"] = [name for name in schema.get("required", []) if name not in deniable]


class CompanyListItem(StrictModel):
    model_config = ConfigDict(json_schema_extra=sparse_company_schema)

    id: uuid.UUID
    code: str
    display_name: str
    legal_name: str
    country_code: str
    state_code: str
    base_currency: str
    status: str
    visibility: str
    #: So a switcher can mark a company that will ask for a proof *before* it is chosen.
    #: Not a secret: it is a property of the login the company demands, and a caller who
    #: can list the company learns it on the first attempt to open it anyway.
    requires_step_up: bool
    updated_at: dt.datetime


class CompanyDetail(StrictModel):
    custom_fields: dict[str, Any] | None = None
    model_config = ConfigDict(json_schema_extra=sparse_company_schema)

    id: uuid.UUID
    parent_company_id: uuid.UUID | None
    code: str
    legal_name: str
    trade_name: str | None
    display_name: str
    entity_type: str
    incorporation_date: dt.date | None
    country_code: str
    state_code: str
    status: str
    first_posted_at: dt.datetime | None

    base_currency: str
    reporting_currency: str | None
    fiscal_year_start_month: int
    fiscal_year_start_day: int
    books_begin_date: dt.date
    amount_precision: int
    quantity_precision: int
    rounding_mode: str

    default_tax_system: str
    tax_treatment_default: str
    default_payment_terms_days: int
    credit_limit_default: Decimal | None
    cash_receipt_limit: Decimal | None
    backdated_posting_limit_days: int | None
    industry_code: str | None
    business_nature: str | None
    business_category_code: str | None
    business_roles: list[str]
    store_format_code: str | None

    timezone: str
    locale: str
    date_format: str
    datetime_format: str
    digit_grouping: str
    decimal_separator: str
    thousands_separator: str
    negative_format: str
    show_amount_in_words: bool
    currency_symbol_position: str
    currency_symbol_override: str | None

    logo_url: str | None
    signature_url: str | None
    brand_color: str | None
    terms_and_conditions: str | None
    declaration_text: str | None
    jurisdiction_text: str | None
    signatory_name: str | None
    signatory_designation: str | None
    dsc_thumbprint: str | None

    visibility: str
    requires_step_up: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class FeatureCatalogueItem(StrictModel):
    """One capability a company may be given, as a setup form needs it.

    The graph is ``billing_platform.features`` and the wording
    ``identity.domain.company_features``; this is the two of them joined for a client, so
    no client has to keep its own list of what the platform can do.
    """

    key: str
    label: str
    description: str
    #: Features that must be on for this one, as stated — not the transitive closure.
    #: The server closes it upward on enable either way (``plan_enable``).
    requires: list[str]
    #: Tax systems this is offerable under. Empty means every system; a GST e-way bill
    #: on a UK VAT company is meaningless and must not be selectable.
    tax_systems: list[str]
    #: Permanently enabled once it has shaped posted data (docs/company-features.md §4),
    #: so a form can warn before the choice stops being reversible.
    locks: bool


class FeatureCatalogue(StrictModel):
    items: list[FeatureCatalogueItem]


class ClassificationChoice(StrictModel):
    code: str
    label: str
    sort_order: int


class CompanyClassifications(StrictModel):
    business_categories: list[ClassificationChoice]
    business_roles: list[ClassificationChoice]
    store_formats: list[ClassificationChoice]


class CompanyPage(StrictModel):
    items: list[CompanyListItem]
    page: PageMeta


class DisplayConfig(StrictModel):
    model_config = ConfigDict(json_schema_extra=sparse_company_schema)

    """The resolved money/date presentation for a company (docs/company.md §4.5).

    Storage scale is always ``DECIMAL(19,4)``; these are display and rounding scales
    only. Both clients and the PDF worker render from this one payload so a company's
    invoices never differ by which surface drew them.
    """

    timezone: str
    currency_display: str = "symbol"
    base_currency: str
    amount_precision: int
    quantity_precision: int
    rounding_mode: str
    locale: str
    date_format: str
    datetime_format: str
    digit_grouping: str
    decimal_separator: str
    thousands_separator: str
    negative_format: str
    currency_symbol_position: str
    currency_symbol_override: str | None
    show_amount_in_words: bool


class FieldDescriptor(StrictModel):
    custom: CustomDefinition | None = None
    source: str = "native"
    help_text: str | None = None
    placeholder: str | None = None
    default_value: Any = None
    label: str | None = None
    is_visible: bool = True
    writable: bool = True
    data_type: str | None = None
    validation: dict[str, Any] | None = None
    choices: list[dict[str, Any]] | None = None

    key: str
    required: bool
    hideable: bool
    renameable: bool
    requires_feature: str | None
    group: str
    order: int


class FieldSet(StrictModel):
    """Merged native/custom field set for an entity (docs/identity-schema.md §6.2).

    Includes layout and effective policy/permission/lifecycle write hints. The API
    independently enforces every mutation; presentation visibility is not authorization.
    """

    entity_type: str
    model_name: str
    fields: list[FieldDescriptor]


class FeatureView(StrictModel):
    feature_key: str
    is_enabled: bool
    locked: bool
    locked_at: dt.datetime | None


class FeatureList(StrictModel):
    enabled: list[str]
    features: list[FeatureView]


class SetupFeature(StrictModel):
    feature_key: str
    state: Literal["ENABLED", "DISABLED", "INCONSISTENT"]
    required_features: list[str]
    missing_prerequisites: list[str]
    tax_system_supported: bool
    locked_at: dt.datetime | None
    lock_reason: str | None
    source_updated_at: dt.datetime | None


class CompanySetupReadiness(StrictModel):
    company_id: uuid.UUID
    company_status: str
    company_updated_at: dt.datetime
    first_posted_at: dt.datetime | None
    frozen_company_fields: list[str]
    features: list[SetupFeature]
    scope: Literal["IDENTITY_ONLY"] = "IDENTITY_ONLY"


class FeatureActionRequest(StrictModel):
    """Optional reason recorded on the audit event; an empty body is allowed."""

    reason: str | None = Field(default=None, max_length=200)
    expected_updated_at: AwareDatetime | None = None

    @field_validator("reason")
    @classmethod
    def _printable_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("reason must contain printable characters")
        return value.strip() or None
