"""The native-field catalogue for `identity`'s entities.

docs/identity-schema.md §6.2 and docs/custom-fields.md: *fields are data, but the set
of fields a form is built from is code.* Clients render forms from the ``field-set``
endpoint and never hardcode a field list (CLAUDE.md invariant 15), so the shape of
that endpoint has to come from somewhere authoritative — this module.

Each entry is a real column on the model. ``registry.validate_against_models`` runs at
boot (``main.create_app``) and turns a drifted entry — a field renamed on the model
but not here — into a boot failure rather than a form that silently omits it.

What this is **not**: authorization. A field being present, required or hideable here
is layout only. Whether an actor may read or write it is ``field_policy``'s job
(docs/field-permissions.md §6); a hidden field is still accepted by the API and still
present in exports.
"""

from __future__ import annotations

from billing_platform.fields import EntityFields, NativeField, registry

#: The entity type as it appears in the ``field-set`` URL and in custom-field
#: definitions: ``<service>.<entity>``.
COMPANY_ENTITY_TYPE = "identity.company"

#: Reason strings for non-hideable fields (``NativeField`` requires one, so the
#: rejection of a hide attempt can explain itself).
_MANDATORY = "required to identify the company on every document"
_RATCHET = "immutable after first posting; changing it would reinterpret filed figures"
_RENDERING = "required for consistent money and date rendering across web, mobile and PDF"


def _fixed(group: str, order: int, *, reason: str, renameable: bool = True) -> NativeField:
    """A required, non-hideable field."""
    return NativeField(
        required=True,
        hideable=False,
        renameable=renameable,
        group=group,
        order=order,
        reason=reason,
    )


def _optional(group: str, order: int) -> NativeField:
    """An optional, hideable field."""
    return NativeField(required=False, hideable=True, group=group, order=order)


def _company_fields() -> dict[str, NativeField]:
    """Company's form fields, grouped as the create/edit form lays them out.

    The ten immutability-ratchet columns (docs/company.md §5.2) are required and
    non-hideable — they are the company's identity, not decoration — and their
    post-posting freeze is enforced in ``company_immutability``, not here.
    """
    return {
        # identity
        "legal_name": _fixed("identity", 10, reason=_MANDATORY),
        "trade_name": _optional("identity", 20),
        "display_name": _fixed("identity", 30, reason=_MANDATORY),
        "entity_type": _fixed("identity", 40, reason=_MANDATORY),
        "incorporation_date": _optional("identity", 50),
        "code": _fixed("identity", 60, reason=_RATCHET, renameable=False),
        "country_code": _fixed("identity", 70, reason=_RATCHET, renameable=False),
        "state_code": _fixed("identity", 80, reason=_RATCHET, renameable=False),
        # financial (every one immutable after first posting)
        "base_currency": _fixed("financial", 100, reason=_RATCHET),
        "reporting_currency": _optional("financial", 110),
        "fiscal_year_start_month": _fixed("financial", 120, reason=_RATCHET),
        "fiscal_year_start_day": _fixed("financial", 130, reason=_RATCHET),
        "books_begin_date": _fixed("financial", 140, reason=_RATCHET),
        "amount_precision": _fixed("financial", 150, reason=_RATCHET),
        "quantity_precision": _fixed("financial", 160, reason=_RATCHET),
        "rounding_mode": _fixed("financial", 170, reason=_RATCHET),
        # tax posture (defaults only; never read by a posting path)
        "default_tax_system": _fixed("tax", 200, reason=_MANDATORY),
        "tax_treatment_default": _fixed("tax", 210, reason=_MANDATORY),
        # commercial defaults
        "default_payment_terms_days": _fixed("commercial", 300, reason=_MANDATORY),
        "credit_limit_default": _optional("commercial", 310),
        "cash_receipt_limit": _optional("commercial", 320),
        "backdated_posting_limit_days": _optional("commercial", 330),
        "industry_code": _optional("commercial", 340),
        "business_nature": _optional("commercial", 350),
        "business_category_code": _optional("commercial", 360),
        "store_format_code": _optional("commercial", 370),
        # locale and presentation
        "timezone": _fixed("locale", 400, reason=_RENDERING),
        "locale": _fixed("locale", 410, reason=_RENDERING),
        "date_format": _fixed("locale", 420, reason=_RENDERING),
        "datetime_format": _fixed("locale", 430, reason=_RENDERING),
        "digit_grouping": _fixed("locale", 440, reason=_RENDERING),
        "decimal_separator": _fixed("locale", 450, reason=_RENDERING),
        "thousands_separator": _fixed("locale", 460, reason=_RENDERING),
        "negative_format": _fixed("locale", 470, reason=_RENDERING),
        "show_amount_in_words": _optional("locale", 480),
        "currency_symbol_position": _fixed("locale", 490, reason=_RENDERING),
        "currency_symbol_override": _optional("locale", 500),
        # branding and print
        "logo_url": _optional("branding", 600),
        "signature_url": _optional("branding", 610),
        "brand_color": _optional("branding", 620),
        "terms_and_conditions": _optional("branding", 630),
        "declaration_text": _optional("branding", 640),
        "jurisdiction_text": _optional("branding", 650),
        "signatory_name": _optional("branding", 660),
        "signatory_designation": _optional("branding", 670),
        # visibility (a display preference, not access control)
        "visibility": _optional("visibility", 700),
        "requires_step_up": _optional("visibility", 710),
    }


def register_native_fields() -> None:
    """Idempotent registration, called at import so the registry is populated before
    the first ``field-set`` request and before the boot-time validation runs."""
    if COMPANY_ENTITY_TYPE in registry.entity_types():
        return
    registry.register(
        EntityFields(
            entity_type=COMPANY_ENTITY_TYPE, model_name="Company", fields=_company_fields()
        )
    )


register_native_fields()


# Relationship selections are form fields but not scalar model columns.
COMPANY_RELATIONSHIP_FIELDS = {"business_roles": _optional("commercial", 365)}
