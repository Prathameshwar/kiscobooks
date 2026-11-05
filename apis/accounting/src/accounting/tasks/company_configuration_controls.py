"""Company-aware editor hints; existing commands retain mutation authority."""

from accounting.api.auth import Access
from accounting.domain.withholding import FEATURES
from accounting.schemas.configuration import ConfigurationField
from accounting.tasks.validation import WITHHOLDING


def company_controls(
    current: Access, name: str, fields: list[ConfigurationField], *, authoring: bool = True
) -> tuple[str | None, list[str]]:
    context = current.context
    by_key = {field.key: field for field in fields}

    def dependency(key: str, controller: str, values: list[str], required: bool = False) -> None:
        field, parent = by_key.get(key), by_key.get(controller)
        if field is None or parent is None:
            return
        if not parent.readable or not parent.visible or parent.conditional_access:
            field.control.disabled_reason = (
                "The controlling field is protected. Ask an administrator."
            )
            return
        field.control.depends_on = {controller: values}
        field.control.required_when_active = required

    notices: list[str] = []
    if any(
        field.control.reference == "currencies"
        and field.readable
        and field.visible
        and not field.conditional_access
        for field in fields
    ):
        notices.append(
            "New currency defaults use the company base currency: " + context.base_currency + "."
        )
    for field in fields:
        if not field.readable or not field.visible or field.conditional_access:
            continue
        key, control = field.key, field.control
        if control.reference == "currencies":
            field.initial = context.base_currency
            if name not in WITHHOLDING:
                control.reference_filters = {"company_currency": "true"}
            elif name in WITHHOLDING:
                control.reference_filters = {"base_only": "true"}
        if name == "account" and key == "currency_mode":
            if authoring and "multi_currency" not in context.features:
                control.choices = [choice for choice in control.choices if choice != "MULTI"]
            if by_key.get("kind") and by_key["kind"].readable:
                control.choice_dependencies = {
                    "MULTI": {"kind": ["GENERAL", "PARTY", "INVENTORY_CONTROL", "ASSET_CONTROL"]}
                }
        if name in {"account_bank_profile", "account_tax_profile"} and key == "account_id":
            control.reference_filters = {
                "kind": "BANK" if name == "account_bank_profile" else "TAX"
            }
        if key == "company_bank_id":
            control.reference_values = sorted(str(value) for value in context.bank_ids)
        if key == "company_registration_id":
            control.reference_values = sorted(str(row["id"]) for row in context.registrations)
        if name in WITHHOLDING and key == "kind" and authoring:
            control.choices = [
                choice for choice in control.choices if FEATURES[choice] in context.features
            ]
            if control.choices:
                field.initial = control.choices[0]
            else:
                control.disabled_reason = (
                    "Enable TDS or TCS in Company Config before creating withholding masters."
                )
        if control.reference == "withholding-sections" and name in WITHHOLDING:
            # Native options also apply the company feature gate to new choices.
            if name == "party_withholding_profile":
                dependency(key, "kind", ["TDS", "TCS"])
        if name == "party_withholding_profile" and key == "pan_identifier_id":
            control.reference_filters = {"scheme": "PAN"}

    if name == "account":
        dependency("currency", "currency_mode", ["FIXED"], True)
        dependency("party_id", "kind", ["PARTY"], True)
        dependency("party_role", "kind", ["PARTY"], True)
        dependency("rounding_limit", "rounding_method", ["NORMAL", "UP", "DOWN"], True)
    if name == "account_tax_profile":
        # Native duty validation requires a registration for GST/VAT and matching components.
        dependency("company_registration_id", "scheme", ["GST_IN", "VAT"], True)
        components = by_key.get("component")
        if components and by_key["scheme"].readable:
            components.control.choice_dependencies = {
                choice: {
                    "scheme": [
                        "GST_IN" if choice in {"CGST", "SGST", "UTGST", "IGST", "CESS"} else choice
                    ]
                }
                for choice in components.control.choices
            }
        scheme = by_key.get("scheme")
        if scheme and authoring and scheme.readable and scheme.visible:
            supported = {"OTHER"} | {
                {"gst_in": "GST_IN", "vat": "VAT"}.get(str(row.get("tax_system")), "OTHER")
                for row in context.registrations
            }
            scheme.control.choices = [
                choice for choice in scheme.control.choices if choice in supported
            ]
        duty = by_key.get("duty_type")
        if duty and scheme and scheme.readable:
            duty.control.choice_dependencies = {
                "GST": {"scheme": ["GST_IN"]},
                "VAT": {"scheme": ["VAT"]},
                "TDS": {"scheme": ["OTHER"]},
                "TCS": {"scheme": ["OTHER"]},
                "EXCISE": {"scheme": ["OTHER"]},
                "CESS": {"scheme": ["GST_IN", "OTHER"], "component": ["CESS", "OTHER"]},
            }
    if name == "party_credit_policy":
        dependency("limit_amount", "limit_mode", ["LIMITED"], True)
        if "credit_limits" not in context.features:
            notices.append(
                "Credit-limit enforcement is disabled. You can prepare policies; "
                "they take effect when credit limits are enabled in Company Config."
            )
    if name == "party_withholding_profile":
        dependency("pan_identifier_id", "pan_status", ["VERIFIED"], True)
    reason = None
    if name in WITHHOLDING and not any(
        feature in context.features for feature in FEATURES.values()
    ):
        reason = (
            "Enable TDS or TCS in Company Config before managing withholding masters. "
            "Historical records remain available."
        )
        for field in fields:
            field.editable = False
    return reason, notices
